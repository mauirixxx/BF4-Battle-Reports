# BF4BR website

These files are the version-controlled source for the BF4 Battle Reports website.

Production deployment path on the `reports` host: `/var/www/html/`.

The PHP pages use the local PostgreSQL peer-authenticated `www-data` account and require the `pgsql` PHP extension. The discovery control page also invokes the separately installed `/opt/bf4reports/web-discovery-launch.sh` helper, subject to host sudoers policy.

Deployment is **not automatic** from this directory. Review and copy only the intended files to the production document root, then validate with `php -l` and HTTP checks. Keep secrets, host-specific configuration, and backup copies out of Git.
