<?php
function bf4br_can_discover(): bool {
    $ip = $_SERVER['REMOTE_ADDR'] ?? '';
    return $ip === '192.168.10.13'
        || (filter_var($ip, FILTER_VALIDATE_IP, FILTER_FLAG_IPV4) !== false
            && str_starts_with($ip, '192.168.200.')
            && (int)substr($ip, strlen('192.168.200.')) <= 255);
}
function bf4br_header(string $active): void {
    $links = ['archive'=>['battle-reports.php','Archive'],'shared'=>['shared-reports.php','Shared-player search'],'discovery'=>['discovery-control.php','Player discovery'],'live'=>['battle-reports-live.php','Live collection']];
    if (!bf4br_can_discover()) unset($links['discovery']);
    echo '<div class="bf4br-shell"><header class="bf4br-header"><div class="bf4br-brand"><a href="battle-reports.php">BF4 <span>BATTLE REPORTS</span></a><div class="bf4br-subtitle">Independent archived match explorer</div></div><nav class="bf4br-nav" aria-label="Main navigation">';
    foreach ($links as $key => [$href,$label]) {
        echo '<a href="'.$href.'"'.($key===$active?' aria-current="page"':'').'>'.$label.'</a>';
    }
    echo '</nav></header><main class="bf4br-content">';
}
function bf4br_footer(): void {
    echo '</main><footer class="bf4br-footer"><span>BF4 Battle Reports · Independent archived match explorer</span><span><a href="battle-reports.php">Archive</a> · <a href="shared-reports.php">Shared-player search</a>';
    if (bf4br_can_discover()) echo ' · <a href="discovery-control.php">Player discovery</a>';
    echo ' · <a href="battle-reports-live.php">Live collection</a></span></footer></div>';
}
