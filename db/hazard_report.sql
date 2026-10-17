
BEGIN;

CREATE TABLE public.hazard_reports (
    id UUID PRIMARY KEY,
    site_id BIGINT NOT NULL REFERENCES public.sites(site_id),
    -- Verified Auth0 access-token subject, never supplied by report JSON.
    reporter_id VARCHAR(255) NOT NULL
        CHECK (char_length(reporter_id) > 0 AND reporter_id !~ '[[:space:][:cntrl:]]'),
    hazard_type VARCHAR(32) NOT NULL
        CHECK (hazard_type IN (
            'heat', 'lightning', 'flooding', 'wildfire',
            'soil_saturation', 'wildlife', 'other'
        )),
    severity VARCHAR(6) NOT NULL CHECK (severity IN ('low', 'medium', 'high')),
    description TEXT NOT NULL
        CHECK (char_length(description) BETWEEN 1 AND 2000
               AND description ~ '[^[:space:]]'),
    latitude DOUBLE PRECISION CHECK (latitude BETWEEN -90 AND 90),
    longitude DOUBLE PRECISION CHECK (longitude BETWEEN -180 AND 180),
    -- Opaque reference from POST /photos; the image bytes stay private on the server.
    photo_key VARCHAR(1024)
        CHECK (photo_key IS NULL OR (
            char_length(photo_key) BETWEEN 1 AND 1024
            AND photo_key !~ '^[[:space:]]|[[:space:]]$|[[:cntrl:]]'
            AND photo_key !~ '^[A-Za-z][A-Za-z0-9+.-]*:'
            AND left(photo_key, 2) <> '//'
        )),
    status VARCHAR(8) NOT NULL DEFAULT 'open'
        CHECK (status IN ('open', 'resolved')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    resolved_at TIMESTAMPTZ,
    resolved_by VARCHAR(255)
        CHECK (resolved_by IS NULL OR (
            char_length(resolved_by) > 0
            AND resolved_by !~ '[[:space:][:cntrl:]]'
        )),
    CONSTRAINT hazard_reports_coordinate_pair
        CHECK ((latitude IS NULL) = (longitude IS NULL)),
    CONSTRAINT hazard_reports_resolution_state
        CHECK (
            (status = 'open' AND resolved_at IS NULL AND resolved_by IS NULL)
            OR
            (status = 'resolved' AND resolved_at IS NOT NULL AND resolved_by IS NOT NULL)
        )
);

-- Supports GET /reports?site_id=... ordered from newest to oldest.
CREATE INDEX hazard_reports_site_created_id_idx
    ON public.hazard_reports (site_id, created_at DESC, id DESC);

-- High-severity warnings are rows in the shared alerts table. The report
-- service's warning adapter writes and clears those rows in this same DB
-- transaction; Alan publishes their ID-only events after commit.
-- Sid's Gemini /ask database user must stay read-only. Expose an approved
-- report view if /ask needs report facts; avoid granting private photo keys
-- and reporter IDs to a model-generated SQL query.

COMMIT;
