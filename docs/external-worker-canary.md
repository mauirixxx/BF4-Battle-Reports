# External worker — first one-shot canary

The standalone worker is `bf4br/external_worker.py` and is **not** enabled as a service.
It uses the existing `bf4br.detail_fetch.fetch_detail` endpoint implementation.

## Prerequisites on an external host

- Python 3.10+ and the `curl` executable.
- A checkout of this repository; no PostgreSQL credentials or connectivity required.
- The per-worker API key at `/root/bf4br-external-worker.key`, mode 0600.
- HTTPS access to `https://reports.bf4playerstats.com/api/v1/health`.
- The worker host's public IPv4/IPv6 addresses allowed through tcou Apache.

## Run exactly one batch

```bash
cd /opt/BF4-Battle-Reports
python3 -m bf4br.external_worker --once --concurrency 4 \
  --key-file /root/bf4br-external-worker.key
```

The worker claims one random persona and up to 40 newest eligible reports, fetches only that
persona's detail per report, renews each lease, submits validated responses through the API,
releases failures and never-dispatched work, completes the batch, and exits.

**Do not start a continuous worker service before the one-shot canary is accepted.**
The API enforces a 61-second cooldown after batch completion; HTTP 429 currently has a
separate 180-second minimum. A failed process can leave leases until expiry, so inspect
the server-side batch ledger before repeating a failed canary.

## Future service

A separate systemd unit for `do-mailbox` can run this module without `--once`
once error recovery, persistent cooldown, restart behavior, and 429 policy have been
tested. Do not install or enable it as part of the first canary.
