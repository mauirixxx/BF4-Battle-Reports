-- Additive external-worker liveness/version telemetry. No secret material.
BEGIN;
SET LOCAL lock_timeout = '5s';
ALTER TABLE public.bf4br_external_workers
  ADD COLUMN IF NOT EXISTS last_heartbeat_at timestamptz,
  ADD COLUMN IF NOT EXISTS worker_version text;
COMMIT;
