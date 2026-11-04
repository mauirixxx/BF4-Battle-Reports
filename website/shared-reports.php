<?php
declare(strict_types=1);
header('X-Content-Type-Options: nosniff');
function h($s): string { return htmlspecialchars((string)$s, ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8'); }
$platforms = ['pc'=>1,'ps4'=>32,'xboxone'=>64];
$platform = (string)($_GET['platform'] ?? 'pc');
$input = trim((string)($_GET['ids'] ?? ''));
$error = '';
$rows = [];
$ids = preg_split('/[\\s,;]+/', $input, -1, PREG_SPLIT_NO_EMPTY);
$ids = array_values(array_unique($ids));
if ($input !== '') {
 if (!isset($platforms[$platform]) || count($ids)<2 || count($ids)>20 || array_filter($ids, fn($v)=>!ctype_digit($v) || (float)$v<=0 || strlen($v)>19)) {
  $error = 'Choose a platform and enter 2–20 distinct positive persona IDs.';
 } else {
  $db = pg_connect('dbname=bf4_battle_reports user=www-data');
  if (!$db) { $error='Database connection unavailable.'; }
  else {
   $params = array_merge([$platforms[$platform]], $ids, [count($ids)]);
   $placeholders = implode(',', array_map(fn($i)=>'$'.($i+2), range(0,count($ids)-1)));
   $countParam = '$'.(count($ids)+2);
   $query = "SELECT r.battlelog_report_id, to_char(r.report_timestamp AT TIME ZONE 'UTC','YYYY-MM-DD HH24:MI:SS') AS created_utc, s.current_name AS server_name, string_agg(DISTINCT rp.player_name_observed || ' (' || p.persona_id || ')', ', ') AS matched FROM battle_reports r JOIN servers s ON s.id=r.server_id JOIN report_players rp ON rp.report_id=r.id JOIN players p ON p.id=rp.player_id WHERE r.platform=$1 AND p.platform=$1 AND p.persona_id IN ($placeholders) GROUP BY r.id,r.battlelog_report_id,r.report_timestamp,s.current_name HAVING count(DISTINCT p.persona_id)=$countParam ORDER BY r.report_timestamp DESC,r.battlelog_report_id DESC LIMIT 200";
   $result = pg_query_params($db,$query,$params);
   if (!$result) $error='Search failed.';
   else $rows=pg_fetch_all($result) ?: [];
  }
 }
}
?><!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>BF4 Shared Battle Reports</title><style>
body{font:16px system-ui,sans-serif;background:#0c121b;color:#e6edf4;margin:0}main{max-width:1100px;margin:auto}h1{font-size:1.9rem}p{color:#b9c8d7}form{display:flex;flex-wrap:wrap;gap:12px;align-items:end;margin:24px 0}label{display:flex;flex-direction:column;gap:6px}input,select,button{font:inherit;padding:11px;border-radius:7px;border:1px solid #51647a}input{min-width:300px;flex:1}button{background:#f39b3d;color:#151515;font-weight:700;cursor:pointer}table{border-collapse:collapse;width:100%}th,td{text-align:left;border-bottom:1px solid #34485a;padding:12px;vertical-align:top}th{color:#aabed1}a{color:#89c8ff}section{overflow-x:auto}.error{color:#ff9a9a}small{color:#aebdcc}
</style><link rel="stylesheet" href="bf4br-layout.css?v=1"></head><body><?php require_once __DIR__ . "/bf4br-layout.php"; bf4br_header("shared"); ?><main><h1>BF4 Shared Battle Reports</h1><p>Find imported rounds where <strong>all</strong> specified persona IDs played together.</p>
<form method="get"><label>Platform<select name="platform"><?php foreach ($platforms as $key=>$num): ?><option value="<?=h($key)?>" <?=$platform===$key?'selected':''?>><?=h(['pc'=>'PC','ps4'=>'PlayStation','xboxone'=>'Xbox'][$key])?></option><?php endforeach; ?></select></label><label>Persona IDs (comma or space separated)<input name="ids" value="<?=h($input)?>" placeholder="236753552, 1007512245583" required></label><button type="submit">Find shared rounds</button></form>
<?php if ($error): ?><p class="error"><?=h($error)?></p><?php elseif ($input!==''): ?><p><?=count($rows)?> shared imported reports found<?=count($rows)===200?' (first 200)':''?>.</p>
<section><table><thead><tr><th>Battle report</th><th>Battlelog report created (UTC)</th><th>Server name</th><th>Matched players</th></tr></thead><tbody>
<?php foreach($rows as $row): $url='https://battlelog.battlefield.com/bf4/battlereport/show/1/'.rawurlencode($row['battlelog_report_id']).'/'.$platform.'/'; ?>
<tr><td><a href="<?=h($url)?>" target="_blank" rel="noopener noreferrer"><?=h($row['battlelog_report_id'])?></a></td><td><?=h($row['created_utc'])?></td><td><?=h($row['server_name'])?></td><td><?=h($row['matched'])?></td></tr>
<?php endforeach; ?></tbody></table></section><?php endif; ?>
<p><small>Searches imported reports only. Times are Battlelog report timestamps, not collection times. Server names reflect the currently stored server name.</small></p></main><?php bf4br_footer(); ?></body></html>
