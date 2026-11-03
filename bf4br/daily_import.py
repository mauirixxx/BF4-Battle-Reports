"""Bounded, idempotent BF4SW session import; no network calls at import time.

Run with separate BF4SW_READ_DSN (SELECT-only) and BF4BR_DSN credentials.
Never modifies historical persona jobs.
"""
import argparse
import os
from datetime import date, datetime, time, timedelta, timezone

import psycopg
from bf4br.daily_window import platform_code, previous_utc_day


def import_day(source, target, day: date, *, batch_size=500):
    if type(day) is not date or not 1 <= batch_size <= 1000:
        raise ValueError('invalid day or batch size')
    start=datetime.combine(day,time.min,tzinfo=timezone.utc)
    end=start+timedelta(days=1)
    # Keyset pagination avoids OFFSET scans and bounds memory usage.
    last_id=0
    total=0
    missing=0
    unknown=0
    while True:
        with source.cursor() as cur:
            cur.execute('''SELECT id,platform,persona_id FROM bf4_player_sessions
                WHERE id>%s AND time_joined<%s
                  AND COALESCE(time_left,last_seen)>=%s
                ORDER BY id LIMIT %s''',(last_id,end,start,batch_size))
            rows=cur.fetchall()
        if not rows: break
        last_id=rows[-1][0]
        personas=set()
        batch_missing=0
        batch_unknown=0
        for _,label,persona in rows:
            platform=platform_code(label)
            if platform is None:
                batch_unknown+=1
            elif persona is None or int(persona)<=0:
                batch_missing+=1
            else:
                personas.add((platform,int(persona)))
        missing+=batch_missing
        unknown+=batch_unknown
        with target.transaction():
            with target.cursor() as cur:
                cur.execute('''INSERT INTO bf4br_daily_windows(day_utc)
                    VALUES (%s) ON CONFLICT DO NOTHING''',(day,))
                for platform,persona in personas:
                    cur.execute('''INSERT INTO bf4br_daily_persona_jobs
                        (day_utc,platform,persona_id) VALUES (%s,%s,%s)
                        ON CONFLICT DO NOTHING''',(day,platform,persona))
                    total+=cur.rowcount
                cur.execute('UPDATE bf4br_daily_windows SET last_import_at=now() WHERE day_utc=%s',(day,))
    # Replace, do not increment, counters on repeated imports.
    with target.transaction():
        with target.cursor() as cur:
            cur.execute("""UPDATE bf4br_daily_windows SET
                missing_persona_sessions=%s,
                unsupported_platform_sessions=%s,
                imported_personas=(SELECT count(*) FROM bf4br_daily_persona_jobs WHERE day_utc=%s),
                last_import_at=now() WHERE day_utc=%s""",(missing,unknown,day,day))
    return {'new_personas':total,'missing_persona_sessions':missing,
            'unsupported_platform_sessions':unknown}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--day',help='UTC day YYYY-MM-DD (default: yesterday)')
    args=parser.parse_args()
    day=date.fromisoformat(args.day) if args.day else previous_utc_day(datetime.now(timezone.utc))[0].date()
    with psycopg.connect(os.environ['BF4SW_READ_DSN'],autocommit=True) as source:
        with psycopg.connect(os.environ['BF4BR_DSN'],autocommit=True) as target:
            print(import_day(source,target,day))

if __name__=='__main__': main()
