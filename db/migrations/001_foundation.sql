-- PostgreSQL foundation. Time columns are included in every time-series key.
-- Deliberately no extension creation or automatic cloud privilege changes.
CREATE TABLE public.sites (
 site_id BIGINT PRIMARY KEY CHECK (site_id > 0), name TEXT NOT NULL CHECK (btrim(name) <> ''),
 utility TEXT, state TEXT NOT NULL CHECK (state ~ '^[A-Z]{2}$'), county TEXT,
 county_fips TEXT CHECK (county_fips ~ '^[0-9]{5}$'),
 latitude DOUBLE PRECISION NOT NULL CHECK (latitude BETWEEN -90 AND 90),
 longitude DOUBLE PRECISION NOT NULL CHECK (longitude BETWEEN -180 AND 180),
 timezone TEXT NOT NULL CHECK (btrim(timezone) <> ''), plant_type TEXT NOT NULL,
 hazard_region TEXT NOT NULL, operating_status TEXT NOT NULL,
 is_monitored BOOLEAN NOT NULL DEFAULT FALSE, source_vintage TEXT NOT NULL,
 source_name TEXT NOT NULL CHECK (btrim(source_name) <> ''), source_url TEXT NOT NULL CHECK (source_url ~ '^https?://[^/]+'), retrieved_at TIMESTAMPTZ NOT NULL
);
CREATE TABLE public.weather_readings (
 site_id BIGINT NOT NULL REFERENCES public.sites, observed_at TIMESTAMPTZ NOT NULL,
 provider TEXT NOT NULL CHECK (btrim(provider) <> ''), source_name TEXT NOT NULL CHECK (btrim(source_name) <> ''), source_url TEXT NOT NULL CHECK (source_url ~ '^https?://[^/]+'), retrieved_at TIMESTAMPTZ NOT NULL,
 PRIMARY KEY (site_id, observed_at, provider), temperature_f DOUBLE PRECISION, heat_index_f DOUBLE PRECISION, wind_mph DOUBLE PRECISION CHECK (wind_mph >= 0 AND wind_mph < 'Infinity'::float8), precip_1h_in DOUBLE PRECISION CHECK (precip_1h_in >= 0 AND precip_1h_in < 'Infinity'::float8), precip_24h_in DOUBLE PRECISION CHECK (precip_24h_in >= 0 AND precip_24h_in < 'Infinity'::float8), soil_moisture DOUBLE PRECISION CHECK (soil_moisture BETWEEN 0 AND 1), CHECK (temperature_f > '-Infinity'::float8 AND temperature_f < 'Infinity'::float8), CHECK (heat_index_f > '-Infinity'::float8 AND heat_index_f < 'Infinity'::float8)
);
CREATE TABLE public.weather_forecasts (
 site_id BIGINT NOT NULL REFERENCES public.sites, issued_at TIMESTAMPTZ NOT NULL,
 valid_at TIMESTAMPTZ NOT NULL, provider TEXT NOT NULL CHECK (btrim(provider) <> ''),
 source_name TEXT NOT NULL CHECK (btrim(source_name) <> ''), source_url TEXT NOT NULL CHECK (source_url ~ '^https?://[^/]+'), retrieved_at TIMESTAMPTZ NOT NULL, PRIMARY KEY (site_id, valid_at, issued_at, provider), temperature_f DOUBLE PRECISION, heat_index_f DOUBLE PRECISION, wind_mph DOUBLE PRECISION CHECK (wind_mph >= 0 AND wind_mph < 'Infinity'::float8), precip_1h_in DOUBLE PRECISION CHECK (precip_1h_in >= 0 AND precip_1h_in < 'Infinity'::float8), precip_24h_in DOUBLE PRECISION CHECK (precip_24h_in >= 0 AND precip_24h_in < 'Infinity'::float8), soil_moisture DOUBLE PRECISION CHECK (soil_moisture BETWEEN 0 AND 1), CHECK (temperature_f > '-Infinity'::float8 AND temperature_f < 'Infinity'::float8), CHECK (heat_index_f > '-Infinity'::float8 AND heat_index_f < 'Infinity'::float8)
);
CREATE TABLE public.environmental_events (
 id TEXT NOT NULL, site_id BIGINT NOT NULL REFERENCES public.sites,
 hazard_type TEXT NOT NULL CHECK (hazard_type IN ('heat','lightning','flooding','wildfire','soil_saturation','wildlife','other')), event_kind TEXT NOT NULL, title TEXT NOT NULL,
 severity TEXT, starts_at TIMESTAMPTZ NOT NULL, ends_at TIMESTAMPTZ,
 source_name TEXT NOT NULL CHECK (btrim(source_name) <> ''), source_url TEXT NOT NULL CHECK (source_url ~ '^https?://[^/]+'), retrieved_at TIMESTAMPTZ NOT NULL, PRIMARY KEY (id, site_id), CHECK (ends_at IS NULL OR ends_at >= starts_at)
);
CREATE TABLE public.wildlife_observations (
 occurrence_id BIGINT PRIMARY KEY, species TEXT NOT NULL, observed_at TIMESTAMPTZ NOT NULL,
 latitude DOUBLE PRECISION NOT NULL CHECK (latitude BETWEEN -90 AND 90),
 longitude DOUBLE PRECISION NOT NULL CHECK (longitude BETWEEN -180 AND 180), source_name TEXT NOT NULL CHECK (btrim(source_name) <> ''), source_url TEXT NOT NULL CHECK (source_url ~ '^https?://[^/]+'), retrieved_at TIMESTAMPTZ NOT NULL
);
CREATE TABLE public.lightning_strikes (
 strike_id TEXT NOT NULL, struck_at TIMESTAMPTZ NOT NULL,
 latitude DOUBLE PRECISION NOT NULL CHECK (latitude BETWEEN -90 AND 90),
 longitude DOUBLE PRECISION NOT NULL CHECK (longitude BETWEEN -180 AND 180),
 is_replay BOOLEAN NOT NULL, source_name TEXT NOT NULL CHECK (btrim(source_name) <> ''), source_url TEXT NOT NULL CHECK (source_url ~ '^https?://[^/]+'), retrieved_at TIMESTAMPTZ NOT NULL, PRIMARY KEY (strike_id, struck_at)
);
CREATE TABLE public.hazard_scores (
 site_id BIGINT NOT NULL REFERENCES public.sites, scored_at TIMESTAMPTZ NOT NULL,
 horizon_hours INTEGER NOT NULL CHECK (horizon_hours = 24),
 score DOUBLE PRECISION NOT NULL CHECK (score BETWEEN 0 AND 10),
 baseline DOUBLE PRECISION NOT NULL CHECK (baseline > '-Infinity'::float8 AND baseline < 'Infinity'::float8),
 factors JSONB NOT NULL CHECK (jsonb_typeof(factors) = 'array' AND jsonb_array_length(factors) > 0),
 model_version TEXT NOT NULL CHECK (btrim(model_version) <> ''), inputs_observed_at TIMESTAMPTZ NOT NULL,
 PRIMARY KEY (site_id, scored_at)
);
CREATE TABLE public.alerts (
 id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
 site_id BIGINT NOT NULL REFERENCES public.sites, hazard_type TEXT NOT NULL CHECK (hazard_type IN ('heat','lightning','flooding','wildfire','soil_saturation','wildlife','other')),
 level TEXT NOT NULL CHECK (level IN ('warning','stop_work')), message TEXT NOT NULL,
 started_at TIMESTAMPTZ NOT NULL, last_trigger_at TIMESTAMPTZ NOT NULL,
 clear_at TIMESTAMPTZ, ended_at TIMESTAMPTZ, trigger JSONB NOT NULL,
 CHECK (last_trigger_at >= started_at), CHECK (clear_at IS NULL OR clear_at >= started_at),
 CHECK (ended_at IS NULL OR ended_at >= started_at)
);
CREATE TABLE public.briefings (
 id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
 site_id BIGINT NOT NULL REFERENCES public.sites, for_date DATE NOT NULL,
 generated_at TIMESTAMPTZ NOT NULL, text TEXT NOT NULL, model TEXT NOT NULL, inputs JSONB NOT NULL
);
CREATE INDEX weather_forecasts_site_issue_idx ON public.weather_forecasts (site_id, issued_at DESC, valid_at);
CREATE INDEX environmental_events_site_time_idx ON public.environmental_events (site_id, starts_at DESC);
CREATE INDEX lightning_strikes_time_idx ON public.lightning_strikes (struck_at DESC);
CREATE INDEX alerts_active_site_idx ON public.alerts (site_id) WHERE ended_at IS NULL;
CREATE INDEX briefings_site_date_idx ON public.briefings (site_id, for_date DESC, generated_at DESC);
