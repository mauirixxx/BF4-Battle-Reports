-- BF4CR native-import cursor, independent of collector/enrichment completion.
CREATE TABLE IF NOT EXISTS public.bf4cr_import_checkpoint (
 source_name text PRIMARY KEY,
 last_report_id text NOT NULL DEFAULT '0',
 rows_imported bigint NOT NULL DEFAULT 0,
 batches_imported bigint NOT NULL DEFAULT 0,
 updated_at timestamptz NOT NULL DEFAULT now(),
 CONSTRAINT bf4cr_checkpoint_cursor_numeric CHECK (last_report_id ~ '^[0-9]{1,19}$')
);
CREATE TABLE IF NOT EXISTS public.bf4cr_import_rejected (
 source_name text NOT NULL,
 report_id text NOT NULL,
 persona_id text NOT NULL,
 error text NOT NULL,
 payload jsonb NOT NULL,
 rejected_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY(source_name,report_id,persona_id)
);
