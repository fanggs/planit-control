-- Convert populated tables without replacing their rows, keys or foreign keys.
-- The migration runner supplies the transaction and migration checksum tracking.
SET LOCAL lock_timeout = '15s';
SET LOCAL statement_timeout = '5min';

DO $preflight$
DECLARE installed TEXT;
BEGIN
    SELECT extversion INTO installed FROM pg_extension WHERE extname = 'timescaledb';
    IF installed IS NULL THEN
        RAISE EXCEPTION 'TimescaleDB must already be installed' USING ERRCODE = '55000';
    END IF;
    IF (split_part(installed, '.', 1)::INTEGER, split_part(installed, '.', 2)::INTEGER) < (2, 13) THEN
        RAISE EXCEPTION 'TimescaleDB 2.13 or newer is required' USING ERRCODE = '0A000';
    END IF;
END;
$preflight$;

-- Referenced table first, as recommended for migrate_data with foreign keys.
LOCK TABLE public.sites IN SHARE ROW EXCLUSIVE MODE;
LOCK TABLE public.hazard_scores, public.lightning_strikes,
           public.weather_forecasts, public.weather_readings IN ACCESS EXCLUSIVE MODE;

SELECT create_hypertable('public.weather_readings', by_range('observed_at', INTERVAL '7 days'),
                         migrate_data => TRUE, if_not_exists => TRUE);
SELECT create_hypertable('public.weather_forecasts', by_range('valid_at', INTERVAL '7 days'),
                         migrate_data => TRUE, if_not_exists => TRUE);
SELECT create_hypertable('public.lightning_strikes', by_range('struck_at', INTERVAL '7 days'),
                         migrate_data => TRUE, if_not_exists => TRUE);
SELECT create_hypertable('public.hazard_scores', by_range('scored_at', INTERVAL '7 days'),
                         migrate_data => TRUE, if_not_exists => TRUE);

DO $verify$
DECLARE matched INTEGER;
BEGIN
    SELECT count(*) INTO matched
    FROM timescaledb_information.dimensions d
    JOIN (VALUES ('weather_readings','observed_at'), ('weather_forecasts','valid_at'),
                 ('lightning_strikes','struck_at'), ('hazard_scores','scored_at')) expected(tab, col)
      ON d.hypertable_name = expected.tab AND d.column_name = expected.col
    WHERE d.hypertable_schema = 'public' AND d.dimension_type = 'Time';
    IF matched <> 4 THEN
        RAISE EXCEPTION 'Expected four correctly time-partitioned hypertables' USING ERRCODE = '55000';
    END IF;
END;
$verify$;
