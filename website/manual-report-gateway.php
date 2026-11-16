<?php
declare(strict_types=1);
header('Content-Type: application/json; charset=utf-8');
header('Cache-Control: no-store');
header('X-Content-Type-Options: nosniff');
function respond(int $status,array $data):never {http_response_code($status);echo json_encode($data);exit;}
$host=strtolower($_SERVER['HTTP_HOST']??'');
if($host!=='reports.bf4playerstats.com')respond(403,['error'=>'host']);
if(empty($_SERVER['HTTPS'])||$_SERVER['HTTPS']==='off')respond(403,['error'=>'https_required']);
session_name('BF4BR_MANUAL');
session_set_cookie_params(['lifetime'=>0,'path'=>'/','secure'=>true,'httponly'=>true,'samesite'=>'Strict']);
session_start();
if(($_SERVER['REQUEST_METHOD']??'')==='GET'){
 if(empty($_SESSION['csrf']))$_SESSION['csrf']=bin2hex(random_bytes(32));
 respond(200,['csrf'=>$_SESSION['csrf']]);
}
if(($_SERVER['REQUEST_METHOD']??'')!=='POST')respond(405,['error'=>'method']);
if(($_SERVER['HTTP_ORIGIN']??'')!=='https://reports.bf4playerstats.com')respond(403,['error'=>'origin']);
if(!in_array($_SERVER['HTTP_SEC_FETCH_SITE']??'same-origin',['same-origin','none'],true))respond(403,['error'=>'fetch_site']);
if(empty($_SESSION['csrf'])||!hash_equals($_SESSION['csrf'],$_SERVER['HTTP_X_BF4BR_CSRF']??''))respond(403,['error'=>'csrf']);
if(strtolower(trim(explode(';',$_SERVER['CONTENT_TYPE']??'')[0]))!=='application/json')respond(415,['error'=>'content_type']);
if((int)($_SERVER['CONTENT_LENGTH']??0)>1024)respond(413,['error'=>'too_large']);
$data=json_decode(file_get_contents('php://input',false,null,0,1025),true);
if(!is_array($data)||array_keys($data)!==['url']||!is_string($data['url'])||strlen($data['url'])>300)respond(400,['error'=>'invalid_request']);
$url=parse_url($data['url']);
if(!is_array($url)||($url['scheme']??'')!=='https'||($url['host']??'')!=='battlelog.battlefield.com'||isset($url['port'])||isset($url['user'])||isset($url['pass'])||isset($url['query'])||isset($url['fragment'])||!preg_match('~^/bf4/battlereport/show/(1|32|64)/([1-9][0-9]{0,18})/([1-9][0-9]{0,18})/?$~',$url['path']??''))respond(400,['error'=>'invalid_url']);
$ip=$_SERVER['REMOTE_ADDR']??'';
if(!filter_var($ip,FILTER_VALIDATE_IP))respond(403,['error'=>'client_ip']);
$dir='/var/lib/bf4br-manual/limits';
if(!is_dir($dir)||!is_writable($dir))respond(503,['error'=>'limiter_unavailable']);
$fp=fopen($dir.'/'.hash('sha256',$ip).'.json','c+');
if(!$fp||!flock($fp,LOCK_EX))respond(503,['error'=>'limiter_unavailable']);
$times=json_decode(stream_get_contents($fp),true);
if(!is_array($times))$times=[];
$now=time();$times=array_values(array_filter($times,fn($t)=>is_int($t)&&$t>$now-3600));
if(count($times)>=10){flock($fp,LOCK_UN);fclose($fp);header('Retry-After: 3600');respond(429,['error'=>'rate_limited']);}
$times[]=$now;ftruncate($fp,0);rewind($fp);fwrite($fp,json_encode($times));fflush($fp);flock($fp,LOCK_UN);fclose($fp);
session_write_close();
// Private backend must run on loopback and validate the URL again.
$ch=curl_init('http://127.0.0.1:8794/manual-report');
curl_setopt_array($ch,[CURLOPT_POST=>true,CURLOPT_POSTFIELDS=>json_encode($data),CURLOPT_HTTPHEADER=>['Content-Type: application/json'],CURLOPT_RETURNTRANSFER=>true,CURLOPT_TIMEOUT=>12,CURLOPT_CONNECTTIMEOUT=>2]);
$result=curl_exec($ch);$status=(int)curl_getinfo($ch,CURLINFO_HTTP_CODE);curl_close($ch);
if(!is_string($result)||$status<100||$status>599)respond(503,['error'=>'backend_unavailable']);
http_response_code($status);echo $result;
