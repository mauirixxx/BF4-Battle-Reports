<?php
declare(strict_types=1);
session_start();
header('X-Content-Type-Options: nosniff');
require_once __DIR__ . '/bf4br-layout.php';
if (!bf4br_can_discover()) { http_response_code(403); exit('Access denied'); }
function esc($s):string{return htmlspecialchars((string)$s,ENT_QUOTES|ENT_SUBSTITUTE,'UTF-8');}
if(empty($_SESSION['discovery_token']))$_SESSION['discovery_token']=bin2hex(random_bytes(24));
$notice='';
if($_SERVER['REQUEST_METHOD']==='POST'){
 if(!hash_equals($_SESSION['discovery_token'],(string)($_POST['token']??''))){http_response_code(403);exit('Invalid token');}
 $pid=(string)($_POST['persona']??'');$platform=(string)($_POST['platform']??'1');
 if(!preg_match('/^[1-9][0-9]{0,18}$/',$pid)||!in_array($platform,['1','32','64'],true)){$notice='Invalid Persona ID or platform.';}
 else{
  $lock='/run/lock/bf4reports-web-discovery.lock';
  $check=exec('/usr/bin/flock -n '.escapeshellarg($lock).' /bin/true 2>/dev/null; echo $?');
  if(trim((string)$check)!=='0')$notice='Discovery already running. Wait for it to finish.';
  else{
   $cmd='/usr/bin/sudo -n /opt/bf4reports/web-discovery-launch.sh '.escapeshellarg($pid).' '.escapeshellarg($platform);
   exec('/usr/bin/nohup /bin/sh -c '.escapeshellarg($cmd.' >> /var/log/bf4reports-web/discovery.log 2>&1').' </dev/null >/dev/null 2>&1 &');
   $notice='Discovery requested for Persona '.$pid.' (platform '.$platform.').';
  }
 }
}
$log='/var/log/bf4reports-web/discovery.log';
$lines=is_readable($log)?array_slice(file($log,FILE_IGNORE_NEW_LINES)?:[],-80):[];
?><!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="refresh" content="15"><title>BF4 Player Discovery</title><style>body{font:15px/1.5 system-ui;background:#0c121b;color:#e6edf7;margin:0}.bf4br-content>h1,.bf4br-content>p,.bf4br-content>.panel{max-width:1100px;margin-left:auto;margin-right:auto}a{color:#88caff}.panel{background:#152232;border:1px solid #2b4056;border-radius:12px;padding:20px;margin:18px 0}input,select,button{font:inherit;padding:10px;background:#1c2b3b;color:#fff;border:1px solid #415a72;border-radius:7px}button{background:#f4a24c;color:#101923;font-weight:bold;cursor:pointer}pre{overflow:auto;white-space:pre-wrap;overflow-wrap:anywhere;background:#0b1520;padding:15px;border-radius:8px;max-height:560px}label{margin-right:12px}</style><link rel="stylesheet" href="bf4br-layout.css?v=1"></head><body><?php require_once __DIR__ . "/bf4br-layout.php"; bf4br_header("discovery"); ?><h1>Player Discovery</h1><p>Starts the existing discovery script in the background. Refreshes every 15 seconds. Closing this page does not stop collection.</p><div class="panel"><form method="post"><input type="hidden" name="token" value="<?=esc($_SESSION['discovery_token'])?>"><label>Persona ID <input name="persona" inputmode="numeric" required pattern="[1-9][0-9]*" value="<?=esc($_GET['persona']??'')?>"></label><label>Platform <select name="platform"><option value="1">PC</option><option value="32">PlayStation</option><option value="64">Xbox</option></select></label><button type="submit">Start discovery</button></form><?php if($notice):?><p><?=esc($notice)?></p><?php endif;?></div><div class="panel"><h2>Recent discovery output</h2><pre><?=esc(implode("\n",$lines))?></pre></div><?php bf4br_footer(); ?></body></html>
