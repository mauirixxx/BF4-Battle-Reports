\set ON_ERROR_STOP on
BEGIN;
SET LOCAL lock_timeout = '3s';
SET LOCAL statement_timeout = '120s';
WITH eligible AS (
 SELECT d.platform,d.battlelog_report_id, count(*) AS required
 FROM bf4br_detail_reports d
 JOIN battle_reports r ON r.platform=d.platform AND r.battlelog_report_id=d.battlelog_report_id
 JOIN report_players rp ON rp.report_id=r.id
 JOIN players p ON p.id=rp.player_id AND p.platform=r.platform
 WHERE d.state='pending'
 GROUP BY d.platform,d.battlelog_report_id
 HAVING count(*)>0 AND count(*)=count(*) FILTER (WHERE EXISTS (
  SELECT 1 FROM bf4br_detail_players dp
  JOIN bf4br_player_report_raw raw USING(platform,battlelog_report_id,persona_id)
  WHERE dp.platform=d.platform AND dp.battlelog_report_id=d.battlelog_report_id
    AND dp.persona_id=p.persona_id AND dp.state='done'
 ))
), candidates AS (
 SELECT d.platform,d.battlelog_report_id,e.required
 FROM eligible e JOIN bf4br_detail_reports d USING(platform,battlelog_report_id)
 WHERE d.state='pending' AND NOT EXISTS (
  SELECT 1 FROM bf4br_detail_players dp
  WHERE dp.platform=d.platform AND dp.battlelog_report_id=d.battlelog_report_id AND dp.state<>'done'
 )
 FOR UPDATE OF d SKIP LOCKED
), updated AS (
 UPDATE bf4br_detail_reports d
 SET state='complete',expected_players=c.required,completed_at=now(),updated_at=now(),last_error=NULL
 FROM candidates c WHERE d.platform=c.platform AND d.battlelog_report_id=c.battlelog_report_id AND d.state='pending'
 RETURNING d.platform,d.battlelog_report_id
)
SELECT count(*) AS reconciled FROM updated;
COMMIT;