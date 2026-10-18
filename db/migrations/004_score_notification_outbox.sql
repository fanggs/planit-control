CREATE TABLE public.score_notification_outbox (
    event_id TEXT PRIMARY KEY CHECK (event_id ~ '^[0-9a-f]{64}$'),
    event_type TEXT NOT NULL CHECK (event_type = 'scores.updated'),
    payload JSONB NOT NULL CHECK (jsonb_typeof(payload) = 'object' AND payload ? 'site_ids'
      AND jsonb_typeof(payload->'site_ids') = 'array' AND jsonb_array_length(payload->'site_ids') > 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    attempts INTEGER NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    delivered_at TIMESTAMPTZ,
    last_error_category TEXT
);
CREATE INDEX score_notifications_pending ON public.score_notification_outbox(next_attempt_at)
    WHERE delivered_at IS NULL;
COMMENT ON TABLE public.score_notification_outbox IS
    'Transactional score invalidation notices. At-least-once delivery; no private report data.';
