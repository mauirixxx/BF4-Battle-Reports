"""Validated manual report requests. Caller supplies a trusted PostgreSQL connection.

Never fetch the submitted URL: workers construct their own Battlelog request
from validated platform/report identifiers. The trailing persona is only a hint.
"""
import re
from urllib.parse import urlsplit

PATH = re.compile(r'^/bf4/battlereport/show/(1|32|64)/([1-9][0-9]{0,18})/([1-9][0-9]{0,18})/?$')
MAX_BIGINT = 9223372036854775807


def parse_report_url(value):
    if not isinstance(value, str) or len(value) > 300:
        raise ValueError('Invalid Battlelog report URL')
    parsed = urlsplit(value)
    if (parsed.scheme != 'https' or parsed.netloc != 'battlelog.battlefield.com'
            or parsed.query or parsed.fragment or parsed.username or parsed.password):
        raise ValueError('Use a direct HTTPS Battlelog report URL')
    match = PATH.fullmatch(parsed.path)
    if not match:
        raise ValueError('Unsupported Battlelog report URL')
    platform, report, persona = map(int, match.groups())
    if report > MAX_BIGINT or persona > MAX_BIGINT:
        raise ValueError('Report or persona ID out of range')
    return platform, report, persona


def submit(conn, url):
    """Queue a missing generic report, or prioritize existing incomplete enrichment.

    Caller must independently enforce public per-IP limits and transaction bounds.
    """
    platform, report, persona = parse_report_url(url)
    with conn.transaction():
        with conn.cursor() as cur:
            cur.execute('''SELECT 1 FROM battle_reports WHERE platform=%s AND battlelog_report_id=%s''', (platform, report))
            archived = cur.fetchone() is not None
            cur.execute('''SELECT state FROM bf4br_detail_reports WHERE platform=%s AND battlelog_report_id=%s''', (platform, report))
            detail = cur.fetchone()
            if archived and detail and detail[0] == 'complete':
                return 'already_complete'
            cur.execute('''INSERT INTO bf4br_manual_report_requests(platform,battlelog_report_id,requested_persona_id)
                VALUES (%s,%s,%s) ON CONFLICT(platform,battlelog_report_id)
                DO UPDATE SET last_requested_at=now(),request_count=bf4br_manual_report_requests.request_count+1''', (platform, report, persona))
            if archived:
                cur.execute('''INSERT INTO bf4br_detail_reports(platform,battlelog_report_id,report_timestamp,manual_priority)
                    SELECT platform,battlelog_report_id,report_timestamp,true FROM battle_reports
                    WHERE platform=%s AND battlelog_report_id=%s
                    ON CONFLICT(platform,battlelog_report_id) DO UPDATE SET manual_priority=true,updated_at=now()
                    WHERE bf4br_detail_reports.state <> 'complete' ''', (platform, report))
                return 'enrichment_prioritized'
            cur.execute('''INSERT INTO bf4br_report_jobs(platform,battlelog_report_id,manual_priority)
                VALUES (%s,%s,true) ON CONFLICT(platform,battlelog_report_id)
                DO UPDATE SET manual_priority=true,
                    state=CASE WHEN bf4br_report_jobs.state='done' THEN 'ready' ELSE bf4br_report_jobs.state END,
                    next_attempt_at=CASE WHEN bf4br_report_jobs.state='done' THEN now() ELSE bf4br_report_jobs.next_attempt_at END,
                    updated_at=now() ''', (platform, report))
            return 'generic_prioritized'
