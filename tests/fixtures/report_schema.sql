CREATE TABLE battle_report_raw (
 platform smallint NOT NULL,battlelog_report_id bigint NOT NULL,
 raw_response jsonb NOT NULL,fetched_at timestamptz DEFAULT now(),
 imported_at timestamptz,PRIMARY KEY(platform,battlelog_report_id));
CREATE TABLE battle_report_details (
 platform smallint NOT NULL,battlelog_report_id bigint NOT NULL,
 report_json jsonb NOT NULL,extracted_at timestamptz DEFAULT now(),
 PRIMARY KEY(platform,battlelog_report_id));

[executed on device: reports (d4380674-2627-4f06-a351-173869e82fbe)]