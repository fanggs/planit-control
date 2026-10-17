-- Private model-evidence extension. Existing contract columns remain intact.
CREATE TABLE public.model_input_snapshots (
    snapshot_id TEXT PRIMARY KEY CHECK (snapshot_id ~ '^[0-9a-f]{64}$'),
    site_id BIGINT NOT NULL REFERENCES public.sites(site_id),
    cutoff_at TIMESTAMPTZ NOT NULL,
    captured_at TIMESTAMPTZ NOT NULL,
    schema_version TEXT NOT NULL,
    features JSONB NOT NULL CHECK (jsonb_typeof(features) = 'object'),
    evidence JSONB NOT NULL CHECK (jsonb_typeof(evidence) = 'object'),
    CHECK (captured_at <= cutoff_at)
);
CREATE INDEX model_inputs_site_cutoff ON public.model_input_snapshots (site_id, cutoff_at DESC);
CREATE TABLE public.screening_models (
    artifact_sha256 TEXT PRIMARY KEY CHECK (artifact_sha256 ~ '^[0-9a-f]{64}$'),
    artifact JSONB NOT NULL,
    validation JSONB NOT NULL,
    registered_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE public.screening_predictions (
    site_id BIGINT NOT NULL REFERENCES public.sites(site_id),
    scored_at TIMESTAMPTZ NOT NULL,
    snapshot_id TEXT NOT NULL REFERENCES public.model_input_snapshots(snapshot_id),
    artifact_sha256 TEXT NOT NULL REFERENCES public.screening_models(artifact_sha256),
    score DOUBLE PRECISION NOT NULL CHECK (score BETWEEN 0 AND 10 AND score < 'Infinity'::float8),
    baseline DOUBLE PRECISION NOT NULL,
    factors JSONB NOT NULL CHECK (jsonb_typeof(factors) = 'array'),
    status TEXT NOT NULL CHECK (status IN ('research', 'validated_prototype')),
    target TEXT NOT NULL,
    PRIMARY KEY (site_id, scored_at)
);
COMMENT ON TABLE public.screening_predictions IS 'Warning-exposure research index. Not the shared 8/2 API score; never used to clear safety alerts.';
CREATE TABLE public.weather_source_payloads (
    sha256 TEXT NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),
    site_id BIGINT NOT NULL REFERENCES public.sites(site_id),
    source_kind TEXT NOT NULL CHECK (source_kind IN ('latest','forecast')),
    source_name TEXT NOT NULL,
    source_url TEXT NOT NULL,
    retrieved_at TIMESTAMPTZ NOT NULL,
    payload JSONB NOT NULL CHECK (jsonb_typeof(payload) = 'object'),
    PRIMARY KEY (sha256, site_id, source_kind)
);
COMMENT ON TABLE public.weather_source_payloads IS 'Verified original hourly weather arrays, including humidity and gusts, with provider units and source hash.';
