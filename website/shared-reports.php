<?php
declare(strict_types=1);
header('X-Content-Type-Options: nosniff');
function h($s): string { return htmlspecialchars((string)$s, ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8'); }
$mapNames=['MP_Abandoned'=>'Zavod 311','MP_Damage'=>'Lancang Dam','MP_Flooded'=>'Flood Zone','MP_Journey'=>'Golmud Railway','MP_Naval'=>'Paracel Storm','MP_Prison'=>'Operation Locker','MP_Resort'=>'Hainan Resort','MP_Siege'=>'Siege of Shanghai','MP_TheDish'=>'Rogue Transmission','MP_Tremors'=>'Dawnbreaker','XP1_001'=>'Silk Road','XP1_002'=>'Altai Range','XP1_003'=>'Guilin Peaks','XP1_004'=>'Dragon Pass','XP0_Caspian'=>'Caspian Border 2014','XP0_Firestorm'=>'Firestorm 2014','XP0_Metro'=>'Operation Metro 2014','XP0_Oman'=>'Gulf of Oman 2014','XP2_001'=>'Lost Islands','XP2_002'=>'Nansha Strike','XP2_003'=>'Wave Breaker','XP2_004'=>'Operation Mortar','XP3_MarketPl'=>'Pearl Market','XP3_Prpganda'=>'Propaganda','XP3_UrbanGdn'=>'Lumphini Garden','XP3_WtrFront'=>'Sunken Dragon','XP4_Arctic'=>'Operation Whiteout','XP4_SubBase'=>'Hammerhead','XP4_Titan'=>'Hangar 21','XP4_WlkrFtry'=>'Giants of Karelia','XP5_Night_01'=>'Zavod:Graveyard Shift','XP6_CMP'=>'Operation Outbreak','XP7_Valley'=>'Dragon Valley 2015'];
function sharedMapLabel($code): string { global $mapNames; return $mapNames[(string)$code] ?? (string)($code ?: 'Unknown'); }
$platforms = ['pc'=>1,'ps4'=>32,'xboxone'=>64];
$platform = (string)($_GET['platform'] ?? 'pc');
// Lightweight indexed name lookup for the shared-round player picker.
if (isset($_GET['lookup'])) {
 header('Content-Type: application/json; charset=utf-8');
 header('Cache-Control: no-store');
 $term = trim((string)($_GET['lookup'] ?? ''));
 $lookupPlatform = (string)($_GET['platform'] ?? '');
 if (!isset($platforms[$lookupPlatform]) || strlen($term)<3 || strlen($term)>80) {
  echo json_encode(['players'=>[]]); exit;
 }
 $dbLookup = pg_connect('dbname=bf4_battle_reports user=www-data');
 if (!$dbLookup) { http_response_code(503); echo json_encode(['error'=>'Search unavailable']); exit; }
 pg_query($dbLookup, "SET statement_timeout = '3000ms'");
 $escaped = str_replace(['!','%','_'],['!!','!%','!_'],$term);
 $resultLookup = pg_query_params($dbLookup, "SELECT persona_id,current_name FROM players WHERE platform=$1 AND lower(current_name) LIKE '%' || lower($2) || '%' ESCAPE '!' ORDER BY CASE WHEN lower(current_name)=lower($3) THEN 0 WHEN lower(current_name) LIKE lower($4) || '%' ESCAPE '!' THEN 1 ELSE 2 END, length(current_name), current_name LIMIT 15", [$platforms[$lookupPlatform],$escaped,$term,$escaped]);
 if (!$resultLookup) { http_response_code(503); echo json_encode(['error'=>'Search unavailable']); exit; }
 echo json_encode(['players'=>pg_fetch_all($resultLookup) ?: []], JSON_INVALID_UTF8_SUBSTITUTE);
 exit;
}
$input = trim((string)($_GET['ids'] ?? ''));
$error = '';
$rows = [];
$total = 0;
$page = max(1, min(1000000, (int)($_GET['page'] ?? 1)));
$perPage = 100;
$exportUnenriched = ($_GET['unenriched_export'] ?? '') === '1';
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
   $base = "FROM battle_reports r JOIN servers s ON s.id=r.server_id JOIN report_players rp ON rp.report_id=r.id JOIN players p ON p.id=rp.player_id WHERE r.platform=$1 AND p.platform=$1 AND p.persona_id IN ($placeholders) GROUP BY r.id,r.battlelog_report_id,r.report_timestamp,s.current_name HAVING count(DISTINCT p.persona_id)=$countParam";
   if ($exportUnenriched) {
    $exportSql = "SELECT matches.battlelog_report_id FROM (SELECT r.battlelog_report_id,r.platform,r.report_timestamp $base) matches LEFT JOIN bf4br_detail_reports ed ON ed.platform=matches.platform AND ed.battlelog_report_id=matches.battlelog_report_id WHERE ed.state IS DISTINCT FROM 'complete' ORDER BY matches.report_timestamp DESC,matches.battlelog_report_id DESC";
    $exportResult=pg_query_params($db,$exportSql,$params);
    if (!$exportResult) { http_response_code(503); exit('Unable to generate unenriched report list'); }
    header('Content-Type: text/plain; charset=UTF-8');
    header('Content-Disposition: attachment; filename="shared_unenriched_'.$platform.'_report_ids.txt"');
    header('Cache-Control: no-store, private');
    while ($exportRow=pg_fetch_row($exportResult)) echo $exportRow[0]."\n";
    exit;
   }
   $countResult = pg_query_params($db,"SELECT count(*) FROM (SELECT r.id $base) matches",$params);
   if (!$countResult) $error='Search failed.';
   else {
    $total = (int)pg_fetch_result($countResult,0,0);
    $pages = max(1,(int)ceil($total/$perPage));
    $page = min($page,$pages);
    $params[] = $perPage;
    $params[] = ($page-1)*$perPage;
    $limitParam = '$'.(count($params)-1);
    $offsetParam = '$'.count($params);
    $query = "SELECT r.battlelog_report_id, to_char(r.report_timestamp AT TIME ZONE 'UTC','YYYY-MM-DD HH24:MI:SS') AS created_utc, s.current_name AS server_name, (SELECT ed.state='complete' FROM bf4br_detail_reports ed WHERE ed.platform=r.platform AND ed.battlelog_report_id=r.battlelog_report_id) AS fully_enriched, (SELECT d.report_json->'gameServer'->>'map' FROM battle_report_details d WHERE d.platform=r.platform AND d.battlelog_report_id=r.battlelog_report_id) AS map_code, string_agg(DISTINCT rp.player_name_observed || ' (' || p.persona_id || ')', ', ') AS matched $base ORDER BY r.report_timestamp DESC,r.battlelog_report_id DESC LIMIT $limitParam OFFSET $offsetParam";
    $result = pg_query_params($db,$query,$params);
    if (!$result) $error='Search failed.';
    else $rows=pg_fetch_all($result) ?: [];
   }
  }
 }
}
?><!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>BF4 Shared Battle Reports</title><style>
body{font:16px system-ui,sans-serif;background:#0c121b;color:#e6edf4;margin:0}main{max-width:1450px;margin:auto}h1{font-size:1.9rem}p{color:#b9c8d7}form{display:flex;flex-wrap:wrap;gap:12px;align-items:end;margin:24px 0}label{display:flex;flex-direction:column;gap:6px}input,select,button{font:inherit;padding:11px;border-radius:7px;border:1px solid #51647a}input{min-width:300px;flex:1}button{background:#f39b3d;color:#151515;font-weight:700;cursor:pointer}table{border-collapse:collapse;width:100%}th,td{text-align:left;border-bottom:1px solid #34485a;padding:12px;vertical-align:top}th{color:#aabed1}a{color:#89c8ff}section{overflow-x:auto}.pagination{display:flex;flex-wrap:wrap;gap:12px;align-items:center;margin:18px 0}.pagination a{border:1px solid #51647a;border-radius:6px;padding:8px 12px;text-decoration:none}.pagination span{color:#b9c8d7}.error{color:#ff9a9a}small{color:#aebdcc}.picker{border:1px solid #34485a;background:#142233;border-radius:12px;padding:18px;margin:20px 0}.picker h2{margin:0 0 8px;font-size:1.2rem}.picker input{width:min(100%,460px);box-sizing:border-box}.picker-results{max-width:680px;margin-top:10px}.picker-result,.selected-player{display:flex;justify-content:space-between;align-items:center;gap:12px;padding:9px;border-bottom:1px solid #34485a}.picker-result button,.selected-player button{padding:6px 12px}.picker-result small,.selected-player small{display:block}.selected-list{margin-top:10px;max-width:680px}.picker-status{min-height:1.5em;margin:8px 0;color:#b9c8d7}.picker button:disabled{opacity:.5;cursor:default}.enrichment-icon{font-size:20px;font-weight:800}.enrichment-icon.yes{color:#75d58a}.enrichment-icon.no{color:#f16c76}.export-row{margin:0 0 18px}.export-row a{display:inline-block;padding:9px 13px;background:#294761;border:1px solid #537a9c;border-radius:7px;text-decoration:none;color:#e3f3ff}.export-row a:hover{background:#365c7a}@media(max-width:650px){.picker-result,.selected-player{flex-wrap:wrap}input{min-width:0}}
</style><link rel="stylesheet" href="bf4br-layout.css?v=1"></head><body><?php require_once __DIR__ . "/bf4br-layout.php"; bf4br_header("shared"); ?><main><h1>BF4 Shared Battle Reports</h1><p>Find imported rounds where <strong>all</strong> specified persona IDs played together.</p>
<div class="picker"><h2>Find players by name</h2><p>Search a name, add the correct Persona ID, then repeat. Up to 20 players on the same platform.</p><label for="player-lookup">Player name</label><input id="player-lookup" type="search" placeholder="Type at least 3 characters..." autocomplete="off" aria-describedby="lookup-status"><div id="lookup-status" class="picker-status" role="status" aria-live="polite"></div><div id="lookup-results" class="picker-results"></div><h2>Selected players <span id="selected-count">(0/20)</span></h2><div id="selected-list" class="selected-list"></div></div>
<form method="get" id="shared-form"><label>Platform<select name="platform" id="shared-platform"><?php foreach ($platforms as $key=>$num): ?><option value="<?=h($key)?>" <?=$platform===$key?'selected':''?>><?=h(['pc'=>'PC','ps4'=>'PlayStation','xboxone'=>'Xbox'][$key])?></option><?php endforeach; ?></select></label><label>Persona IDs (comma or space separated)<input name="ids" id="shared-ids" value="<?=h($input)?>" placeholder="236753552, 1007512245583" required></label><button type="submit">Find shared rounds</button></form>
<?php if ($input!=='' && !$error): ?><div class="export-row"><a href="<?=h('?'.http_build_query(['platform'=>$platform,'ids'=>$input,'unenriched_export'=>'1']))?>" title="Download all matching report IDs that are not fully enriched, across every page">↓ Download all unenriched report IDs</a></div><?php endif; ?>
<?php if ($error): ?><p class="error"><?=h($error)?></p><?php elseif ($input!==''): ?><p><?=number_format($total)?> shared imported reports found. Showing <?= $total ? number_format(($page-1)*$perPage+1) : 0 ?>–<?=number_format(($page-1)*$perPage+count($rows))?>.</p>
<?php $pages=max(1,(int)ceil($total/$perPage)); $pageUrl=fn(int $n)=>'?'.http_build_query(['platform'=>$platform,'ids'=>$input,'page'=>$n]); ?>
<?php if ($pages>1): ?><nav class="pagination" aria-label="Report pages"><?php if ($page>1): ?><a href="<?=h($pageUrl(1))?>">First</a><a href="<?=h($pageUrl($page-1))?>">Previous</a><?php endif; ?><span>Page <?=number_format($page)?> of <?=number_format($pages)?></span><?php if ($page<$pages): ?><a href="<?=h($pageUrl($page+1))?>">Next</a><a href="<?=h($pageUrl($pages))?>">Last</a><?php endif; ?></nav><?php endif; ?>
<section><table><thead><tr><th>Battle report</th><th aria-label="Enrichment status" title="Fully enriched status">✔ / ✘</th><th>Battlelog report created (UTC)</th><th>Server name</th><th>Map</th><th>Matched players</th></tr></thead><tbody>
<?php foreach($rows as $row): $url='battle-reports.php?'.http_build_query(['report'=>$row['battlelog_report_id'],'platform'=>$platforms[$platform],'highlight'=>implode(',',$ids)]); ?>
<tr><td><a href="<?=h($url)?>"><?=h($row['battlelog_report_id'])?></a></td><td><span class="enrichment-icon <?=($row['fully_enriched']==='t'?'yes':'no')?>" role="img" aria-label="<?=($row['fully_enriched']==='t'?'Fully enriched':'Not fully enriched')?>" title="<?=($row['fully_enriched']==='t'?'Fully enriched':'Not fully enriched')?>"><?=($row['fully_enriched']==='t'?'✔':'✘')?></span></td><td><?=h($row['created_utc'])?></td><td><?=h($row['server_name'])?></td><td><?=h(sharedMapLabel($row['map_code']??null))?></td><td><?=h($row['matched'])?></td></tr>
<?php endforeach; ?></tbody></table></section><?= $pages>1 ? '<nav class="pagination" aria-label="Report pages">' : '' ?><?php if ($pages>1): ?><?php if ($page>1): ?><a href="<?=h($pageUrl(1))?>">First</a><a href="<?=h($pageUrl($page-1))?>">Previous</a><?php endif; ?><span>Page <?=number_format($page)?> of <?=number_format($pages)?></span><?php if ($page<$pages): ?><a href="<?=h($pageUrl($page+1))?>">Next</a><a href="<?=h($pageUrl($pages))?>">Last</a><?php endif; ?></nav><?php endif; ?><?php endif; ?>
<p><small>Searches imported reports only. Times are Battlelog report timestamps, not collection times. Server names reflect the currently stored server name.</small></p></main><?php bf4br_footer(); ?><script>
(() => {
 const platform=document.getElementById('shared-platform'), ids=document.getElementById('shared-ids'), search=document.getElementById('player-lookup'), results=document.getElementById('lookup-results'), status=document.getElementById('lookup-status'), selectedList=document.getElementById('selected-list'), count=document.getElementById('selected-count');
 const selected=new Map(); let timer,controller,sequence=0;
 const validId=v=>/^\d{1,19}$/.test(v)&&!/^0+$/.test(v);
 const parsed=()=>[...new Set(ids.value.split(/[\s,;]+/).filter(validId))];
 function element(tag,text){const e=document.createElement(tag);if(text!==undefined)e.textContent=text;return e;}
 function renderSelected(){
  selectedList.replaceChildren();count.textContent='('+parsed().length+'/20)';
  for(const [id,name] of selected){
   if(!parsed().includes(id)){selected.delete(id);continue;}
   const row=element('div');row.className='selected-player';
   const label=element('span',name+' ');label.append(element('small','Persona '+id));
   const remove=element('button','Remove');remove.type='button';remove.addEventListener('click',()=>{selected.delete(id);ids.value=parsed().filter(v=>v!==id).join(', ');renderSelected();});
   row.append(label,remove);selectedList.append(row);
  }
 }
 ids.addEventListener('input',renderSelected);
 platform.addEventListener('change',()=>{selected.clear();ids.value='';search.value='';results.replaceChildren();status.textContent='Platform changed. Previous selection cleared.';renderSelected();});
 search.addEventListener('input',()=>{
  clearTimeout(timer);if(controller)controller.abort();const seq=++sequence;results.replaceChildren();
  const term=search.value.trim();
  if(term.length<3){status.textContent='Enter at least 3 characters.';return;}
  status.textContent='Searching...';
  timer=setTimeout(async()=>{
   controller=new AbortController();
   try{
    const url=new URL(window.location.href);url.search='';url.searchParams.set('lookup',term);url.searchParams.set('platform',platform.value);
    const response=await fetch(url,{signal:controller.signal,headers:{'Accept':'application/json'}});
    if(!response.ok)throw Error('Search unavailable');
    const data=await response.json();if(seq!==sequence)return;
    status.textContent=data.players.length?data.players.length+' matching players (maximum 15 shown).':'No matching players found.';
    for(const player of data.players){
     const id=String(player.persona_id);if(!validId(id))continue;
     const row=element('div');row.className='picker-result';
     const label=element('span',player.current_name);label.append(element('small','Persona '+id+' · '+platform.options[platform.selectedIndex].text));
     const add=element('button',selected.has(id)||parsed().includes(id)?'Added':'Add player');add.type='button';add.disabled=selected.has(id)||parsed().includes(id);
     add.addEventListener('click',()=>{
      const current=parsed();
      if(current.includes(id))return;
      if(current.length>=20){status.textContent='Maximum 20 players.';return;}
      selected.set(id,player.current_name);ids.value=[...current,id].join(', ');add.textContent='Added';add.disabled=true;renderSelected();
     });
     row.append(label,add);results.append(row);
    }
   }catch(err){if(err.name!=='AbortError'&&seq===sequence)status.textContent='Search temporarily unavailable.';}
  },250);
 });
 renderSelected();
})();
</script></body></html>