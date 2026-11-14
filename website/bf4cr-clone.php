<?php
declare(strict_types=1);
header('X-Content-Type-Options: nosniff');
function esc($v):string{return htmlspecialchars((string)$v,ENT_QUOTES|ENT_SUBSTITUTE,'UTF-8');}
$persona=(string)($_GET['persona']??$_GET['pid']??'');
if(!preg_match('/^[0-9]{1,19}$/',$persona)){http_response_code(400);exit('A numeric persona ID is required.');}
$platform=(string)($_GET['platform']??'1');if(!in_array($platform,['1','32','64'],true)){$platform='1';}
$cnt=max(1,min(200,(int)($_GET['cnt']??200)));
$modeFilter=(string)($_GET['mode']??'');if(!preg_match('/^[0-9]{0,20}$/',$modeFilter))$modeFilter='';
$mapFilter=(string)($_GET['map']??'');if(!preg_match('/^[A-Za-z0-9_]{0,64}$/',$mapFilter))$mapFilter='';
$db=pg_connect('dbname=bf4_battle_reports user=www-data');if(!$db){http_response_code(503);exit('Database unavailable');}
$sql=<<<'SQL'
SELECT r.battlelog_report_id,r.report_timestamp,r.platform,s.current_name AS server_name,
 d.report_json->>'duration' AS duration,d.report_json->>'gameMode' AS mode,
 d.report_json->'gameServer'->>'map' AS map,
 d.report_json->'gameServer'->>'guid' AS server_guid,
 d.report_json->'players'->$1 AS player_json,
 detail.raw_response->'playerReport' AS player_detail_json
FROM players p
JOIN report_players rp ON rp.player_id=p.id
JOIN battle_reports r ON r.id=rp.report_id
JOIN battle_report_details d ON d.platform=r.platform AND d.battlelog_report_id=r.battlelog_report_id
LEFT JOIN servers s ON s.id=r.server_id
LEFT JOIN bf4br_player_report_raw detail ON detail.platform=r.platform AND detail.battlelog_report_id=r.battlelog_report_id AND detail.persona_id=p.persona_id
WHERE p.persona_id=$1::bigint AND p.platform=$2::smallint
AND ($4::text='' OR d.report_json->>'gameMode'=$4::text)
AND ($5::text='' OR d.report_json->'gameServer'->>'map'=$5::text)
ORDER BY r.report_timestamp DESC,r.battlelog_report_id DESC
LIMIT $3::integer
SQL;
$res=pg_query_params($db,$sql,[$persona,$platform,$cnt,$modeFilter,$mapFilter]);
if(!$res){http_response_code(500);exit('Unable to load player history.');}
$rows=pg_fetch_all($res)?:[];
$mapNames=['MP_Abandoned'=>'Zavod 311','MP_Damage'=>'Lancang Dam','MP_Flooded'=>'Flood Zone','MP_Journey'=>'Golmud Railway','MP_Naval'=>'Paracel Storm','MP_Prison'=>'Operation Locker','MP_Resort'=>'Hainan Resort','MP_Siege'=>'Siege of Shanghai','MP_TheDish'=>'Rogue Transmission','MP_Tremors'=>'Dawnbreaker','XP1_001'=>'Silk Road','XP1_002'=>'Altai Range','XP1_003'=>'Guilin Peaks','XP1_004'=>'Dragon Pass','XP0_Caspian'=>'Caspian Border 2014','XP0_Firestorm'=>'Firestorm 2014','XP0_Metro'=>'Operation Metro 2014','XP0_Oman'=>'Gulf of Oman 2014','XP2_001'=>'Lost Islands','XP2_002'=>'Nansha Strike','XP2_003'=>'Wave Breaker','XP2_004'=>'Operation Mortar','XP3_MarketPl'=>'Pearl Market','XP3_Prpganda'=>'Propaganda','XP3_UrbanGdn'=>'Lumphini Garden','XP3_WtrFront'=>'Sunken Dragon','XP4_Arctic'=>'Operation Whiteout','XP4_SubBase'=>'Hammerhead','XP4_Titan'=>'Hangar 21','XP4_WlkrFtry'=>'Giants of Karelia','XP5_Night_01'=>'Zavod:Graveyard Shift','XP6_CMP'=>'Operation Outbreak','XP7_Valley'=>'Dragon Valley 2015'];
$modeNames=['1'=>'Conquest','2'=>'Rush','8'=>'Squad Deathmatch','32'=>'Team Deathmatch','64'=>'Conquest Large','512'=>'Gunmaster','1024'=>'Domination','524288'=>'Capture the Flag','2097152'=>'Obliteration','8388608'=>'Air Superiority','16777216'=>'Defuse','67108864'=>'Carrier Assault Large','134217728'=>'Carrier Assault','34359738368'=>'Chain Link','137438953472'=>'Squad Obliteration'];
// Enumerate modes from this player's full archive, not just the current 25–200 rows.
$modeSql=<<<'SQL'
SELECT DISTINCT d.report_json->>'gameMode' AS mode
FROM players p JOIN report_players rp ON rp.player_id=p.id
JOIN battle_reports r ON r.id=rp.report_id
JOIN battle_report_details d ON d.platform=r.platform AND d.battlelog_report_id=r.battlelog_report_id
WHERE p.persona_id=$1::bigint AND p.platform=$2::smallint
AND d.report_json->>'gameMode' ~ '^[0-9]+$'
SQL;
$modeRes=pg_query_params($db,$modeSql,[$persona,$platform]);
$availableModes=$modeRes?(pg_fetch_all_columns($modeRes,0)?:[]):[];
if($modeFilter!==''&&!in_array($modeFilter,$availableModes,true))$availableModes[]=$modeFilter;
$modeLabel=static function(string $id) use (&$modeNames):string{return $modeNames[$id]??('Mode '.$id);};
usort($availableModes,static function($a,$b) use ($modeLabel):int{
 if($a==='64')return -1;if($b==='64')return 1;
 if($a==='2')return -1;if($b==='2')return 1;
 return strcasecmp($modeLabel($a),$modeLabel($b))?:strcmp($a,$b);
});
// Enumerate maps for the selected mode across this player's entire archive.
$mapSql=<<<'SQL'
SELECT DISTINCT d.report_json->'gameServer'->>'map' AS map
FROM players p JOIN report_players rp ON rp.player_id=p.id
JOIN battle_reports r ON r.id=rp.report_id
JOIN battle_report_details d ON d.platform=r.platform AND d.battlelog_report_id=r.battlelog_report_id
WHERE p.persona_id=$1::bigint AND p.platform=$2::smallint
AND ($3::text='' OR d.report_json->>'gameMode'=$3::text)
AND d.report_json->'gameServer'->>'map' IS NOT NULL
SQL;
$mapRes=pg_query_params($db,$mapSql,[$persona,$platform,$modeFilter]);
$availableMaps=$mapRes?(pg_fetch_all_columns($mapRes,0)?:[]):[];
if($mapFilter!==''&&!in_array($mapFilter,$availableMaps,true))$availableMaps[]=$mapFilter;
$mapLabel=static function(string $id) use (&$mapNames):string{return $mapNames[$id]??$id;};
usort($availableMaps,static fn($a,$b)=>strcasecmp($mapLabel($a),$mapLabel($b))?:strcmp($a,$b));
$cols=['date'=>'Date (UTC)','duration'=>'Duration','report'=>'Report ID','name'=>'Player','rank'=>'Rank','kills'=>'Kills','deaths'=>'Deaths','kd'=>'K/D','accuracy'=>'Accuracy %','score'=>'Combat score','spm'=>'SPM','assists'=>'Assists','heals'=>'Heals','revives'=>'Revives','team'=>'Team','squad'=>'Squad','map'=>'Map','mode'=>'Mode','server'=>'Server','guid'=>'Server GUID','detail'=>'Detail','dscore'=>'Total score','dassists'=>'Detail assists','daccuracy'=>'Detail accuracy %','shots'=>'Shots hit / fired','bestclass'=>'Best class','bestweapon'=>'Best weapon','bestvehicle'=>'Best vehicle'];
$data=[];$playerName='Persona '.$persona;$enrichedCount=0;
foreach($rows as $r){$detail=json_decode($r['player_detail_json']??'',true);if(!is_array($detail))$detail=[];if($detail)$enrichedCount++;$ds=$detail['stats']??[];$sc=$detail['scores']??[];$best=$detail['best']??[];$pl=json_decode($r['player_json']??'',true);if(!is_array($pl))$pl=[];$playerName=(string)($pl['persona']['personaName']??$pl['user']['username']??$playerName);$kills=(int)($pl['kills']??0);$deaths=(int)($pl['deaths']??0);$score=(int)($pl['combatScore']??0);$seconds=(int)($r['duration']??0);$id=(string)$r['battlelog_report_id'];$map=(string)($r['map']??'');$mode=(string)($r['mode']??'');$data[]=['date'=>gmdate('Y-m-d H:i',strtotime($r['report_timestamp'])),'duration'=>$seconds>0?gmdate('H:i:s',$seconds):'—','report'=>$id,'name'=>$playerName,'rank'=>$pl['rank']??'—','kills'=>$kills,'deaths'=>$deaths,'kd'=>$deaths>0?round($kills/$deaths,2):($kills>0?'∞':'0'),'accuracy'=>isset($pl['accuracy'])?round((float)$pl['accuracy']*100,2):'—','score'=>$score,'spm'=>$seconds>0?round($score*60/$seconds):'—','assists'=>$pl['killAssists']??'—','heals'=>$pl['heals']??'—','revives'=>$pl['revives']??'—','team'=>$pl['team']??'—','squad'=>$pl['squadId']??'—','map'=>$mapNames[$map]??$map,'mode'=>$modeNames[$mode]??$mode,'server'=>$r['server_name']??'—','guid'=>$r['server_guid']??'—','detail'=>$detail?'✓ Collected':'—','dscore'=>$sc['total']??'—','dassists'=>$ds['assists']??'—','daccuracy'=>$ds['accuracy']??'—','shots'=>isset($ds['shots_hit'],$ds['shots_fired'])?$ds['shots_hit'].' / '.$ds['shots_fired']:'—','bestclass'=>$best['class']['slug']??'—','bestweapon'=>$best['weapon']['slug']??'—','bestvehicle'=>$best['vehicle']['slug']??'—'];}
?><!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>BF4CR Clone — <?=esc($playerName)?></title><style>
:root{color-scheme:dark}*{box-sizing:border-box}body{margin:0;background:#0c121b;color:#e6edf7;font:14px system-ui,Arial,sans-serif}.wrap{padding:22px;max-width:100%}h1{font-size:27px;margin:0 0 10px}a{color:#88caff;text-decoration:none}a:hover{text-decoration:underline}.muted{color:#9eb0c5}.toolbar{display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin:20px 0}.toolbar button,.toolbar select,.toolbar input{border:1px solid #415a72;background:#1c2b3b;color:#e6edf7;border-radius:7px;padding:8px 10px}.toolbar button{cursor:pointer}.panel{border:1px solid #2b4056;border-radius:12px;background:#152232;padding:14px}.scroll{overflow:auto;max-height:calc(100vh - 210px)}table{border-collapse:collapse;white-space:nowrap;font-variant-numeric:tabular-nums}th,td{padding:8px 10px;border-bottom:1px solid #2a3b4d;text-align:left}thead th{position:sticky;top:0;background:#22364b;color:#b6d2ea;z-index:1;cursor:pointer}tbody tr:nth-child(even){background:#1b2a3a}tbody tr:hover{background:#30445a}.hidden{display:none}.numeric{text-align:right}.pill{background:#273b51;border-radius:20px;padding:7px 12px}.column-controls{display:flex;gap:12px;flex-wrap:wrap;margin:10px 0}.column-controls label{white-space:nowrap;font-size:12px}.footer{color:#9eb0c5;margin:12px 0}
</style><link rel="stylesheet" href="/bf4cr-hover-chart.css?v=2"></head><body><main class="wrap"><h1>BF4CR Clone · <?=esc($playerName)?></h1><p class="muted">Persona <?=esc($persona)?> · <?=count($data)?> most recent <?=esc($modeFilter===''?'archived':$modeLabel($modeFilter))?> reports · <?=esc($enrichedCount)?> enriched (maximum 200) · <?=esc(['1'=>'PC','32'=>'PlayStation','64'=>'Xbox'][$platform])?></p><div class="toolbar"><a class="pill" href="battle-reports.php?persona=<?=urlencode($persona)?>&platform=<?=urlencode($platform)?>">← Original archive</a><form method="get"><input type="hidden" name="persona" value="<?=esc($persona)?>"><input type="hidden" name="platform" value="<?=esc($platform)?>"><input type="hidden" name="mode" value="<?=esc($modeFilter)?>"><input type="hidden" name="map" value="<?=esc($mapFilter)?>"><label>Reports <select name="cnt"><?php foreach([25,50,100,200] as $n):?><option value="<?=$n?>" <?=$cnt===$n?'selected':''?>><?=$n?></option><?php endforeach;?></select></label><button type="submit">Apply</button></form><button type="button" id="columns-toggle">Show/hide columns</button><button type="button" id="reset-columns">Reset columns</button><form method="get" id="mode-filter-form"><input type="hidden" name="persona" value="<?=esc($persona)?>"><input type="hidden" name="platform" value="<?=esc($platform)?>"><input type="hidden" name="cnt" value="<?=$cnt?>"><input type="hidden" name="map" value="<?=esc($mapFilter)?>"><label>Game mode <select name="mode" id="mode-filter"><option value="">All</option><?php foreach($availableModes as $m):?><option value="<?=esc($m)?>" <?=$modeFilter===$m?'selected':''?>><?=esc($modeLabel($m))?></option><?php endforeach;?></select></label></form><form method="get" id="map-filter-form"><input type="hidden" name="persona" value="<?=esc($persona)?>"><input type="hidden" name="platform" value="<?=esc($platform)?>"><input type="hidden" name="cnt" value="<?=$cnt?>"><input type="hidden" name="mode" value="<?=esc($modeFilter)?>"><label>Map <select name="map" id="map-filter"><option value="">All</option><?php foreach($availableMaps as $m):?><option value="<?=esc($m)?>" <?=$mapFilter===$m?'selected':''?>><?=esc($mapLabel($m))?></option><?php endforeach;?></select></label></form></div><div id="column-controls" class="column-controls hidden"></div><section class="panel"><div class="scroll"><table id="history"><thead><tr><?php foreach($cols as $key=>$label):?><th data-key="<?=esc($key)?>"><?=esc($label)?> ↕</th><?php endforeach;?></tr></thead><tbody><?php foreach($data as $r):?><tr><?php foreach($cols as $key=>$label):?><td data-key="<?=esc($key)?>" class="<?=in_array($key,['rank','kills','deaths','kd','accuracy','score','spm','assists','heals','revives'],true)?'numeric':''?>"><?php if($key==='report'):?><a href="battle-reports.php?report=<?=urlencode($r[$key])?>&platform=<?=urlencode($platform)?>"><?=esc($r[$key])?></a><?php else:?><?=esc($r[$key])?><?php endif;?></td><?php endforeach;?></tr><?php endforeach;?></tbody></table></div></section><p class="footer">Match statistics come from archived Battlelog reports. Detail columns appear only when a persona-specific report has been collected; missing details show —. Detail score and accuracy are separate Battlelog fields, not replacements for the generic match values. SPM uses combat score / match duration.</p></main><script>
document.getElementById('map-filter').addEventListener('change',()=>document.getElementById('map-filter-form').submit());document.getElementById('mode-filter').addEventListener('change',()=>document.getElementById('mode-filter-form').submit());const table=document.getElementById('history'),controls=document.getElementById('column-controls');const keys=[...table.tHead.rows[0].cells].map(x=>x.dataset.key);function toggleCol(k,visible){table.querySelectorAll('[data-key="'+k+'"]').forEach(x=>x.classList.toggle('hidden',!visible));}keys.forEach(k=>{const l=document.createElement('label'),c=document.createElement('input');c.type='checkbox';c.checked=true;c.addEventListener('change',()=>toggleCol(k,c.checked));l.append(c,document.createTextNode(' '+table.querySelector('th[data-key="'+k+'"]').textContent.replace(' ↕','')));controls.append(l)});document.getElementById('columns-toggle').onclick=()=>controls.classList.toggle('hidden');document.getElementById('reset-columns').onclick=()=>{controls.querySelectorAll('input').forEach(x=>{x.checked=true;toggleCol(keys[[...controls.querySelectorAll('input')].indexOf(x)],true)})};let sorted='',asc=false;table.querySelectorAll('thead th').forEach(th=>th.onclick=()=>{const k=th.dataset.key;asc=sorted===k?!asc:false;sorted=k;const index=keys.indexOf(k),body=table.tBodies[0];[...body.rows].sort((a,b)=>{const x=a.cells[index].textContent.trim(),y=b.cells[index].textContent.trim(),nx=Number(x.replace(/,/g,'')),ny=Number(y.replace(/,/g,''));const cmp=x!==''&&y!==''&&Number.isFinite(nx)&&Number.isFinite(ny)?nx-ny:x.localeCompare(y,undefined,{numeric:true});return asc?cmp:-cmp}).forEach(r=>body.append(r))});
</script><script defer src="/bf4cr-hover-chart.js?v=6"></script></body></html>