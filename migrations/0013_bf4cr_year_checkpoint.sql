-- Independent UTC calendar-year cursor; additive and resumable.
CREATE TABLE IF NOT EXISTS public.bf4cr_year_checkpoint (
 source_name text PRIMARY KEY,
 year integer NOT NULL CHECK (year BETWEEN 2013 AND 2030),
 last_ts text NOT NULL CHECK (last_ts ~ '^[0-9]{10}$'),
 last_report_id text NOT NULL CHECK (last_report_id ~ '^[0-9]{1,19}$'),
 rows_imported bigint NOT NULL DEFAULT 0,
 batches_imported bigint NOT NULL DEFAULT 0,
 updated_at timestamptz NOT NULL DEFAULT now()
);
