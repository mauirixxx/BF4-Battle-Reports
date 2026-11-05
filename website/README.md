# BF4BR website

These files are the version-controlled source for the BF4 Battle Reports website.

Production deployment path on the `reports` host: `/var/www/html/`.

The PHP pages use the local PostgreSQL peer-authenticated `www-data` account and require the `pgsql` PHP extension. The discovery control page also invokes the separately installed `/opt/bf4reports/web-discovery-launch.sh` helper, subject to host sudoers policy.

Deployment is **not automatic** from this directory. Review and copy only the intended files to the production document root, then validate with `php -l` and HTTP checks. Keep secrets, host-specific configuration, and backup copies out of Git.

### Cross-site soldier links

The archive's **BF4 Player Stats** link on each soldier's report uses `https://bf4playerstats.com/soldier.html?persona=<persona_id>&platform=<pc|ps4|xboxone>`, not a name search. The BF4PS dossier links back to `https://reports.bf4playerstats.com/battle-reports.php?persona=<persona_id>&platform=<code>` where codes are PC `1`, PlayStation `32`, Xbox `64`. These direct links preserve platform-specific identity without changing the BF4BR database schema.

Navigation behavior: the archive's **BF4 Player Stats** link opens in the same browser tab, while Battlelog and other third-party links retain their new-tab behavior. The BF4PS dossier's reciprocal **Battle Reports** link also stays in the current tab.
