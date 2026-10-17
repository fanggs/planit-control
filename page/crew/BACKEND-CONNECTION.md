# Connecting PlanIT Control's frontend

## Current repository report schema

At integration baseline `5502248`, `api/schemas/hazard_report.py` defines a strict **JSON** creation payload with numeric `site_id`, `hazard_type`, required `severity` (`low`, `medium`, `high`), `description`, optional paired UI coordinates, and `photo_key`. It forbids extra fields. It does not yet implement a photo-upload/report HTTP endpoint. The default multipart route below remains a proposed transport, not that finalized endpoint.

For the current schema, use `transport: 'custom'`: upload the File with the team's storage flow, then call `createHazardReportPayload(report, storedPhotoKey)` from `crew-report-mapping.js` before posting the JSON. That helper maps the UI category to `hazard_type` (Weather maps to `other`), converts safe numeric EIA IDs, validates severity, and excludes request ID, identity, timestamps and the raw File from JSON. Use a backend-agreed idempotency header for `report.request_id`. Do not put a `reporter_id` supplied by the browser into the body. Keep the actual schema owned by Aryan unchanged.

The worker's severity selection is included in the frontend report object. Agree the report response fields, upload endpoint, URL signing and idempotency header with Aryan before switching to live mode.

This is a proposed frontend interface for Alan/Aryan/Sid to map into their agreed API. It does not replace a shared team contract. **API** means the service the frontend requests data from; **adapter** means code translating its fields into this screen's shape. **SSE** (server-sent events) is an HTTP stream that delivers changes without reloading the page.

## 1. Public settings and Auth0

Edit `crew-config.js`:

```js
dataMode: 'live',
transport: 'http',
api: {
  baseURL: 'https://your-api.example',
  timeoutMs: 20000,
  heartbeatMs: 45000,
  routes: { /* retain or change the provided route mapping */ }
},
authRoleClaim: 'https://planit-control/roles',
auth: {
  domain: 'your-tenant.example.auth0.com',
  clientId: 'PUBLIC_SPA_CLIENT_ID',
  audience: 'YOUR_API_IDENTIFIER',
  redirectUri: /* retain the page-aware expression */
}
```

The Auth0 application must be a Single Page Application. Register both `crew.html` and `crew-supervisor.html` URLs as Allowed Callback URLs, register their origin as an Allowed Web Origin, and both return URLs as Allowed Logout URLs. Include local URLs for development and HTTPS production URLs when deployed. Set the configurable roles claim on the ID token for the supervisor screen. Tokens remain in SDK memory; bearer tokens are requested for API calls. Do not add a client secret, database URL, Gemini key or DeepSpace server key to frontend code.

The frontend's role display is not security. Aryan's API must validate issuer, audience, signature, expiry, roles and site access for every read/write/subscription. A user must not obtain another crew's data by changing a query parameter. The backend must allow the frontend's origin and needed CORS headers/methods, including `Authorization` and multipart requests. For SSE behind a proxy, disable response buffering and flush events promptly.

## 2. HTTP mapping

All requests carry `Authorization: Bearer <access token>`. Errors use non-2xx status codes. GET lists accept an array or `{items: [...], next_cursor: string|null}`; pagination uses `limit=1000` and `cursor`. List methods must include every authorized site/report, not just the first page.

| Config route | Method | Request / response |
|---|---|---|
| `sites` → `/sites` | GET | Available/assigned site summaries; supervisors get all authorized sites. |
| `site` → `/sites/{id}` | GET | Current site snapshot and active lightning/flood state. |
| `reports` → `/reports?site_id={id}` | GET | Stored reports including history. |
| `reports` → `/reports` | POST | Multipart upload; returns stored report receipt. |
| `briefings` → `/sites/{id}/briefings` | GET | Briefing history, newest first. |
| `briefing` → `/sites/{id}/briefings/{briefing_id}` | GET | Full briefing body, seven forecast factors and sources. |
| `preferences` → `/sites/{id}/briefing-preferences` | GET / PUT | Current user's daily delivery preferences and job/delivery status for that site. |
| `events` → `/events?site_id={id}` | GET stream | Crew's selected-site events. Without site_id: supervisor-authorized site events. |

These route paths are placeholders that you can change in config. If request/response shapes differ, use the custom adapter below. The HTTP adapter preserves an API path prefix in `baseURL`, such as `https://host.example/api`.

## 3. Site and model fields

See `crew-contract.d.ts` for field types. Example values below are illustrative, not measurements:

```json
{
  "id": "621", "name": "Turkey Point", "state": "Florida",
  "latitude": 25.4356, "longitude": -80.3308,
  "revision": 42, "server_time": "2026-10-17T12:00:00Z",
  "timezone": "America/New_York",
  "score": 8.2, "score_updated_at": "2026-10-17T11:59:00Z",
  "score_method": "Description of Sid's actual model and explanation",
  "factors": [{"name":"Heat","contribution":2.6,"unit":"score_points",
    "reading":"Heat index from a measured row","source_name":"Actual source",
    "source_url":"https://source.example/record","retrieved_at":"2026-10-17T11:59:00Z"}],
  "model": {"name":"Actual model","version":"version-id",
    "training_period":"Actual historical period","trained_at":"2026-10-17T09:00:00Z",
    "evaluation":"Actual held-out evaluation result"},
  "hazards": {
    "heat": {"reading":"Actual measured heat index","severity":"high",
      "advice":"Site-approved action","observed_at":"2026-10-17T11:59:00Z",
      "source_name":"Actual source","source_url":"https://source.example/record"}
  },
  "alert": {"site_id":"621","version":8,"status":"hold",
    "last_strike_at":"2026-10-17T12:00:00Z","distance_miles":4.2,
    "all_clear_at":"2026-10-17T12:30:00Z"},
  "flood": {"status":"unknown"}
}
```

Populate all hazard keys: `weather`, `heat`, `lightning`, `flood`, `wildfire`, `soil`, `wildlife`. A reading can be descriptive text with units. Supported severity values: `lower`, `elevated`, `high`, `unknown`. Include actual observed/retrieved timestamps and source URLs. Missing data renders unavailable. `score` must be numeric 0–10, or null; it is never estimated by the live frontend.

Site summaries use `id`, `name`, `state`, `latitude`, `longitude`, `score`, `score_updated_at` and optional `operator`/`provenance`. IDs should be strings. Site snapshots must include a monotonic integer `revision`. Increment it whenever score, hazard readings, model explanation, flood state or other snapshot content changes. Stale revisions cannot overwrite newer ones. `server_time` aligns countdown clocks.

Sid supplies baseline and signed contributions with their actual units (`score_points`, `log_odds`, SHAP units, etc.). The UI does not rename units or force contributions to sum to a score. Only supply training/evaluation claims that are true for the connected model.

Flood fields: `status` (`warning`, `normal`, `unknown`), `message`, `river_name`, `river_distance_miles`, `overnight_rain_mm`, `window_label`, `observed_at`, `rule_description`, `source_name`, `source_url`. Alan/Sid determine river association, the overnight window and flood criteria; the frontend displays the supplied decision, not a hard-coded universal rainfall threshold.

## 4. Live alerts and reconnection

The stream uses `Content-Type: text/event-stream`. Events are blank-line separated JSON data blocks:

```text
event: heartbeat
data: {"server_time":"2026-10-17T12:00:00Z"}

event: alert
data: {"site_id":"621","server_time":"2026-10-17T12:00:00Z","alert":{"site_id":"621","version":8,"status":"hold","all_clear_at":"2026-10-17T12:30:00Z","last_strike_at":"2026-10-17T12:00:00Z","distance_miles":4.2}}

event: site
data: {"site_id":"621"}

event: report
data: {"site_id":"621"}

event: briefing
data: {"site_id":"621"}

```

Flush a heartbeat at least every 15 seconds. Stream health expires after 45 seconds without a recognized event. `site` can carry a complete `site` snapshot or act as an invalidation that triggers a fresh GET. `report` and `briefing` invalidate their respective views. Send updates only to authorized viewers. The frontend fetches the selected site's snapshot again after reconnect; periodic 30-second snapshot/list refresh helps reconciliation, but is not a replacement for instant push. The HTTP stream reconnects with backoff and requests a fresh access token.

The backend computes strike-to-site distance in miles. **Each new strike within 10 miles creates/extends an absolute UTC deadline to at least 30 minutes after that strike.** Persist per-site alert state and a monotonic integer `version`; do not reset counters on process restarts. Ignore older events. Expiry alone never clears the frontend's hold. Send an explicit newer `cleared` alert only when the server confirms the hold is over. `unknown` is distinct from `cleared`. An expired/disconnected view must never imply permission to resume work. Real-time delivery while the browser is closed needs a server notification/push channel; this static frontend does not claim background push.

## 5. Photo reports and history

POST multipart fields: `site_id`, `request_id`, `category`, `description`, `latitude`, `longitude`, `photo` (binary File). Validate content and size server-side as well as client-side (JPEG/PNG/WebP, up to 8 MB). Use `request_id` as an idempotency key: retrying the same submission returns its original receipt instead of duplicating it.

Return `{id, site_id, category, description, latitude, longitude, created_at, status, photo_url, shared}`. `status` is `open`, `resolved` or `archived`. `photo_url` is an authorized HTTP(S) image URL (for example, a signed DeepSpace download URL). Refresh signed URLs in subsequent GETs. Do not return a private storage key as though it were a display URL. The receipt must contain the stored ID and matching site. Only `shared: true` produces a team-sharing confirmation; storage success alone does not confirm delivery.

Persist metadata/history in Tiger Data and the image in the team's storage. Publish a `report` event after saving it so crew tabs and the supervisor preview refresh. The demo uses IndexedDB/BroadcastChannel instead; replace it by switching to live services. A server should never set `demo: true` on live records. The viewer filters archives but does not delete or resolve reports, preserving the simple crew workflow and backend ownership.

## 6. Briefing and delivery

History records: `{id, site_id, title, valid_date, generated_at, delivery_status}`. Full records add `timezone` (IANA name), `body`, `forecast: [{name, reading, advice}]` and `sources: [{source_name, source_url}]`. Return all seven hazard forecasts with their real evidence. `valid_date` is tomorrow in the **site's** timezone, not tomorrow in UTC.

GET/PUT preferences: `{site_id, enabled, local_time: "18:00", timezone, channels: ["in_app", "email"], email, next_run_at, delivery_status}`. The UI sends only the editable fields; the backend returns its stored settings and actual job/delivery state. `email` is null when email delivery is disabled. Confirm email eligibility/permissions server-side. Validate site timezone with Sid's location data, particularly for states crossing timezone boundaries. The frontend does not infer a timezone from a state.

Alan's scheduler must generate and deliver a next-day report daily at **18:00 local site time**, adjust for daylight saving, avoid duplicates on retries and retain delivery history. A successful preferences PUT does not mean a report was sent. Return a truthful `delivery_status` and `next_run_at`. The frontend shows a DST-aware preview but never creates an actual delivery job from a browser timer.

## 7. Use the team's existing API / DeepSpace SDK instead

Set `transport: 'custom'`. In `crew-integration.js`, assign `window.PlanITCrewAPI` with the methods in `crew-contract.d.ts`. `crew-services.js` passes `{accessToken}` as the final argument; use it for authenticated calls. Map any agreed field names here. `submitReport` receives a browser File so the adapter can upload to DeepSpace and then save the returned reference through Aryan's API. Never confirm success before both image and metadata are stored.

`subscribeEvents(siteId, onEvent, onConnection, {accessToken})` may return a cleanup function or a promise for one. `siteId: null` requests supervisor-authorized events. Wrap DeepSpace events in the event objects described above. Call `onConnection(false)` on loss, `true` only after synchronization, emit heartbeats, refresh initial state and unsubscribe cleanly when a site changes. The custom adapter owns reconnecting and refreshing expiring tokens; do not keep using the originally passed token indefinitely.

## Integration acceptance

- Two real devices see the same strike, new strike reset, disconnect state and explicit server clear.
- Flood warning cites real overnight rain and river data; unknown data stays unknown.
- A phone's uploaded photo/pin appears on another device's supervisor map and survives re-login.
- A 6 PM site-local delivery arrives once with tomorrow's valid date and real evidence.
- At least 50 actual plants have real seven-hazard coverage and trained/explainable scores.
- Crew cannot access supervisor-only site lists/events; server enforces roles and site scopes.

These integration checks require the real backend. Passing local frontend tests does not prove them.
