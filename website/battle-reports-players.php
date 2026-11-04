<?php
declare(strict_types=1);
function h($v):string{return htmlspecialchars((string)$v,ENT_QUOTES|ENT_SUBSTITUTE,'UTF-8');}
function n($v):string{return number_format((float)($v??0));}
$p=(string)($_POST['platform']??'');
$id=(string)($_POST['report']??'');
$action=(string)($_POST['action']??'');
$ids=array_values(array_unique(array_filter((array)($_POST['players']??[]),fn($v)=>is_string($v)&&preg_match('/^[0-9]{1,19}$/',$v))));
if(!in_array($p,['1','32','64'],true)||!preg_match('/^[0-9]{1,19}$/',$id)||count($ids)<2||count($ids)>80||!in_array($action,['compare','shared'],true)){http_response_code(400);exit('Invalid selection');}
$db=pg_connect('dbname=bf4_battle_reports user=www-data');
$r=pg_query_params($db,'SELECT report_json::text FROM battle_report_details WHERE platform=$1 AND battlelog_report_id=$2',[$p,$id]);
$payload=json_decode(pg_fetch_result($r,0,0)?:'{}',true);
$selected=[];
foreach(($payload['players']??[]) as $pl){$pid=(string)($pl['personaId']??'');if(in_array($pid,$ids,true))$selected[$pid]=$pl;}
$ids=array_values(array_filter($ids,fn($v)=>isset($selected[$v])));
if(count($ids)<2){http_response_code(400);exit('Players not found in this report');}
$names=array_map(fn($v)=>(string)($selected[$v]['persona']['personaName']??$selected[$v]['user']['username']??$v),$ids);
?>
<?php
$rows=[];
if($action==='shared'){
 $params=[$p];$slots=[];
 foreach($ids as $pid){$params[]=$pid;$slots[]='$'.count($params);}
 $params[]=count($ids);$required='$'.count($params);
 $sql="SELECT r.battlelog_report_id,r.report_timestamp,s.current_name FROM battle_reports r JOIN report_players rp ON rp.report_id=r.id JOIN players pl ON pl.id=rp.player_id JOIN servers s ON s.id=r.server_id WHERE r.platform=$1 AND pl.persona_id IN (".implode(',',$slots).") GROUP BY r.id,r.battlelog_report_id,r.report_timestamp,s.current_name HAVING COUNT(DISTINCT pl.persona_id)=$required ORDER BY r.report_timestamp DESC LIMIT 250";
 $result=pg_query_params($db,$sql,$params);
 $rows=$result?pg_fetch_all($result)?:[]:[];
}
?>
<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>BF4 Players</title><style>
body{background:#0c121b;color:#e8f1fa;font:15px/1.5 system-ui;margin:25px}h1{color:#ffb36b}.panel{background:#162536;border:1px solid #30455b;border-radius:12px;padding:18px;overflow:auto}table{border-collapse:collapse;width:100%}th,td{text-align:left;padding:11px;border-bottom:1px solid #30455b}th{color:#a8c9e9}a{color:#8ec8ff}.sub{color:#a4b9cc}button{background:#263f58;border:0;color:white;border-radius:6px;padding:8px 14px;cursor:pointer}
</style></head><body><h1><?=h($action==='compare'?'Round player comparison':'Shared battle reports')?></h1><p class="sub"><?=h(implode(' · ',$names))?> · <?=h(['1'=>'PC','32'=>'PlayStation','64'=>'Xbox'][$p])?></p>
<?php if($action==='compare'):?>
<div class="panel"><table><thead><tr><th>Round stat</th><?php foreach($names as $name):?><th><?=h($name)?></th><?php endforeach;?></tr></thead><tbody>
<?php foreach(['Score'=>'combatScore','Kills'=>'kills','Deaths'=>'deaths','Revives'=>'revives','Accuracy'=>'accuracy','Team'=>'team'] as $label=>$key):?>
<tr><th><?=h($label)?></th><?php foreach($ids as $pid):$v=$selected[$pid][$key]??null;?><td><?=h($v===null?'—':($key==='accuracy'?number_format((float)$v*100,1).'%':($key==='team'?$v:n($v))))?></td><?php endforeach;?></tr>
<?php endforeach;?>
<tr><th>K/D</th><?php foreach($ids as $pid):$pl=$selected[$pid];$k=(int)($pl['kills']??0);$d=(int)($pl['deaths']??0);?><td><?=h($d?number_format($k/$d,2):($k?'∞':'0.00'))?></td><?php endforeach;?></tr>
</tbody></table></div>
<?php else:?>
<div class="panel"><h2><?=count($rows)?> shared archived reports</h2><p class="sub">All selected players must appear together. Only locally archived reports are searched.</p><table><thead><tr><th>Date (UTC)</th><th>Server</th><th>Report</th></tr></thead><tbody><?php foreach($rows as $r):?><tr><td><?=h($r['report_timestamp'])?></td><td><?=h($r['current_name'])?></td><td><a target="_top" href="battle-reports.php?report=<?=h($r['battlelog_report_id'])?>&platform=<?=h($p)?>"><?=h($r['battlelog_report_id'])?></a></td></tr><?php endforeach;?></tbody></table></div>
<?php endif;?></body></html>
