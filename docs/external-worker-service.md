# External enrichment worker — single-droplet continuous canary

Status: opt-in service. First one-shot production batch successfully stored a
player-detail JSON. HTTP 200 / JSON null is retried after the normal delayed retry.

The external API persists a worker-local cooldown (61 seconds on completed batches;
currently 180 seconds minimum for HTTP 429). A restart while a batch is active
will be rejected with HTTP 409 until the outstanding 900-second leases expire.
After expiration, the API expires the old batch and enforces an additional
61-second cooldown before allowing another claim. Already stored player-detail
records are excluded from future claims. The client retries temporary transport
and API failures with bounded backoff. An API outage during a batch may still
strand work until lease expiry; it does not fabricate successful acknowledgements.

## Installation on do-mailbox

Only after checking that the prior one-shot batch is completed:

```bash
cd /opt/bf4br-external-worker
git pull --ff-only
install -m 0644 deploy/bf4br-external-worker.service /etc/systemd/system/
test -s /root/bf4br-external-worker.key
systemctl daemon-reload
systemctl enable --now bf4br-external-worker.service
systemctl status bf4br-external-worker.service --no-pager
journalctl -u bf4br-external-worker.service -f
```

The service runs as root because the existing API key is root-only. It uses
only HTTPS to the API and curl to Battlelog; it has no database credentials.
Do not copy the API key into systemd unit files or journal output.

## Stop and inspect

```bash
systemctl stop bf4br-external-worker.service
journalctl -u bf4br-external-worker.service --since '1 hour ago' --no-pager
```

Stop is not a batch drain. On SIGTERM during an active batch, outstanding
leases remain fenced until expiry. Do not manually reset or reuse those leases.
Watch multiple batches before scaling to other droplets. Each additional
droplet needs its own registered worker identity, bearer key and IP allowlist.

## Operational caveats

- A 429 response uses the server's current 180-second minimum; adjust this
  deliberately and test it before adopting a 61-second 429 policy.
- A successful HTTP 200 with JSON null is a failed item and gets delayed retry.
- If the API rejects credentials (401/403), the process exits and systemd
  records a failure; fix the credentials or allowlist rather than bypassing it.
- Batch completion cooldown begins at API acknowledgement, so the client also
  waits 61 seconds after each completed batch.
