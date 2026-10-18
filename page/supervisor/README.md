# Aryan's supervisor workspace

This is Aryan's dashboard, separate from Isaiah's files in `page/crew/`. It follows
`api/CONTRACT.md` v1.3. The default is now **live API mode**: a supervisor
must sign in before site data is requested. The separate sample adapter and
its **3 labeled sample plants** remain in the code for offline development,
but are never substituted when a live request fails.

## Start and test

From the repository root, with Node.js 18 or newer installed:

```sh
node page/supervisor/dev/serve.mjs
```

Open `http://127.0.0.1:4175/supervisor/index.html`. The preview listens only on
`127.0.0.1` and serves only `page/`. `/supervisor/` works, and `/supervisor`
redirects to the trailing-slash address so relative links work. Set `PORT` to
change the port; the listener address cannot be overridden. Do not open the
HTML as a `file://` URL, because browser modules and fixture requests need HTTP.

```sh
node --test page/supervisor/tests/*.test.mjs
```

This checkout's desktop environment has no `node` command on PATH. Its available
Node executable is:
`/Users/aryannimmagadda/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node`.
Use that executable in place of `node`, or install Node locally.

## Files and responsibilities

| File | Purpose |
| --- | --- |
| `index.html` | Accessible page shell, local Leaflet assets, labeled filters and map/list/detail regions. |
| `supervisor.css` | Responsive supervisor layout and component styles. |
| `../shared/planit.css` | Shared colors, typography, spacing, buttons, chips and focus styles. |
| `config.js` | Public mode, API base, Auth0 identifiers and polling/freshness settings. |
| `auth.js` | Auth0 SPA SDK sign-in/callback/sign-out, memory-only access tokens. |
| `api.js` | Authenticated requests using exact contract paths, including `POST /ask`; separate read-only sample adapter. |
| `domain.js` | Pure prototype screening, watch-status, ranking, freshness, coordinate and event validation functions. |
| `status-clock.js` | Degrades expired lightning/NWS checks and locally stale screening displays without waiting for a successful API fetch. |
| `realtime.js` | DeepSpace notice handling, reconnect and authorized API refetch. |
| `refresh.js` | One active refresh plus one pending refresh, shared across burst callers. |
| `photo-cache.js` | In-memory private photo URLs retained across same-site refreshes and revoked when no longer needed. |
| `lifecycle.js` | Clear old selection state and reload cached history restores before restarting live work. |
| `app.js` | Page interactions, Leaflet markers, waterfall, reports and private-photo rendering. |
| `sample-data/*.json` | Labeled historical sample sites/details/reports/alerts, extended with v1.3 watch statuses and wildlife evidence for UI preview. |
| `dev/serve.mjs` | Loopback-only static preview server, including trailing-slash handling. |
| `tests/*.test.mjs` | Node built-in tests; no npm dependencies. |
| `package.json` | ES-module declaration and optional `npm test`/`npm run dev` shortcuts. |

The site list sorts by the **prototype screening index** and puts unavailable
predictions last. Each shown number has a visible Prototype label, two signed
model-feature contributions, and the generic NWS-warning/heat-advisory target.
The list API does not yet return exact `valid_from` / `valid_until`, so list and
map ask the user to open the site detail for those exact dates. The detail uses
`screening` (not legacy `score`) and shows its target and validity window.
The waterfall starts at the baseline, adds/subtracts feature contributions,
and ends at the index. It hides a result that fails the model's 1e-8
reconciliation check. Features are not one-to-one hazards. A genuine zero is
shown; null, unknown statuses, invalid data and locally expired predictions
are not presented as zero. Sample mode intentionally permits its clearly
labeled historical timestamps; live mode expires a cached summary after two
hours and the full detail when its inputs are over two hours old or its target
window ends. This screening is not an injury probability or work clearance.

`lightning_status` is independent: only a recent explicit `clear` check can
display “Lightning watch clear,” and an active stop-work alert always wins.
Missing or old checks show “Lightning data unavailable.” In the detail,
`warnings_status: ok` must be recent before an empty active NWS event list can
say “No active NWS alerts”; upcoming events are shown separately. Wildlife
context is dated, attributed GBIF-style evidence shown beside—not inside—the
model score. No sightings never means absence and no encounter probability or
wildlife score points are inferred.
The page clock removes those reassuring labels as soon as their checks expire,
even while API refreshes are failing. It also changes a locally expired
research score to **stale**, rather than displaying “No data” beside the old
`research` status.

Reports are displayed separately from model scores, with pins only when both
coordinates exist and the report is still open; resolved reports stay in the
history panel without looking like active map hazards. Live private photos are requested with the bearer token and
rendered from an in-memory Blob URL. Tokens and photo keys are never placed in
public image URLs or query strings. Viewed photos stay open through routine
same-site refreshes. Blob URLs are revoked when the selected site changes, a
photo disappears from its report list, or the page closes. Only JPEG/PNG
responses under 5 MB are shown.

The resolution button calls `PATCH /reports/{id}` with exactly
`{"status":"resolved"}`. The API must independently authorize this operation.
The UI awaits success and then reloads the site list, alerts, site detail and
reports. It never adjusts the score after a report event.

## Ask about site data

The supervisor question box calls `POST /ask` only after Auth0 supplies a
supervisor session. It sends a trimmed 3–500-character question in JSON with
the same bearer token as other API reads; it never puts a token or question in
the URL. Gemini and the restricted read-only SQL login run on the API, not in
the browser. The question request has a 30-second timeout without lengthening
ordinary site reads. Example buttons fill the input but do not submit it.

A successful answer displays the plain-text explanation, HTTPS-only source
links, and the SQL inside a collapsed disclosure. The answer and query are
rendered as text, never executable HTML. `cannot_answer`, temporary service
unavailability, timeout, and expired authorization are shown as distinct
states; an Ask failure does not replace the site map or imply that missing
data is safe. The labeled sample preview does not call Gemini or invent an
answer. This UI does not authorize SQL by itself: the API must keep validating
the access token, database role and query guard described in the contract.

## Diagnosing “No screening data”

The site list and recent weather loading proves the authenticated API is
reachable, but not that fresh screening predictions exist. In the browser's
Network tab, inspect an authenticated `GET /api/sites` response without copying
its bearer token. If a site has a numeric `score`, `score_status: "research"`,
and feature-based `top_factors`, the dashboard should show a **Prototype**
number; if it does not, that is a frontend rendering bug. If `score` is `null`,
read `score_status` (`no_data`, `stale`, `invalid`, or `research_unapproved`)
and the detail response's `screening.reason`. A `stale` response means the API
has deliberately hidden a prediction whose input snapshot is older than two
hours or whose target window ended; it is not a zero score. The data collector
and its deployment are Sid's and Alan's integration responsibility. Do not
replace nulls with old values or sample scores to make the map look populated.

## Connect live data and Auth0

1. Run the API with `DATABASE_URL`, `PGPASSWORD`, and valid Auth0 settings.
   Leave `PLANIT_DATA` unset or set it to `database`; `sample` still serves
   fixtures and intentionally does not register report/photo writes. The
   report table and private photo directory must be ready.
2. `config.js` already selects `mode: 'live'` and has the public local API/Auth0
   identifiers. Confirm the tenant's agreed role claim before browser testing.
   Never add a client secret. Local API URLs must use `http://127.0.0.1`; deployed
   API URLs must use HTTPS. Configure the API's CORS allowlist for the exact
   frontend origin and allow the Authorization header. The public `realtime`
   URL and app ID already match the team contract; keep the bridge's notify
   secret on the backend only.
3. In the Auth0 SPA application, register the exact callback and logout URLs
   in `config.auth`, and the frontend origin in Allowed Web Origins. Locally
   the default callback/logout URL is
   `http://127.0.0.1:4175/supervisor/index.html`, with origin
   `http://127.0.0.1:4175`. Isaiah’s shared preview serves this dashboard at
   `http://127.0.0.1:4174/supervisor/index.html`; allow that exact callback and
   origin too when following the crew-to-supervisor navigation. For deployment these derive from the deployed module
   URL. Auth0 must allow the chosen development callback; use an HTTPS local
   proxy on 127.0.0.1 if the tenant's settings require it.
4. Auth0 must add the agreed role array to the ID token for UI gating, and to
   the access token for the API. For a supervisor, the claim value is
   `["supervisor"]`. The backend verifies the access token independently.
   The UI never takes a role from a query parameter or localStorage.
5. Sign in. An incomplete Auth0 config, failed SDK load, missing role or failed
   live request blocks the operation and displays an error. It does not fall
   back to sample data.

`auth.js` loads the same Auth0 SPA SDK 2.0 CDN endpoint used by the team's crew
app. Its tokens stay in memory. Deployed CSP must allow the Auth0 SDK CDN,
configured tenant, API and basemap tile origins. Prefer a pinned, team-reviewed
SDK version when Alan prepares the deployment asset policy.

## DeepSpace real-time notices

In live mode, `app.js` imports Alan's `page/realtime/deepspace-source.js`
directly and uses the public bridge URL and app ID in `config.js`. The WebSocket
listens anonymously to ID-only notices. The Auth0 access token is used for API
refetches and is never sent to DeepSpace. There is no `/events` API endpoint.

The dashboard accepts `report.created` with `site_id` and `report_id` (no
`created_at`), `report.resolved`, the three alert notices, and `scores.updated`
with positive integer `site_ids`. The bridge adds `sent_at`. Unknown event
types are ignored. Each accepted notice and reconnect refetches the site list,
active alerts, selected site detail and reports from the authorized API. UI
text never comes from the notice payload. The backend publishes notices only
after the database transaction commits.

If the bridge connection is unavailable, the dashboard shows that state and
polls every 30 seconds. Polling does not count as a live connection.
If `/alerts` fails while `/sites` succeeds, the map stays available but the
alert count reads **No data**, with a warning that missing alerts do not mean
safe conditions. If site detail or reports fail to refresh, the last successful
data stays visible with an explicit stale-data warning until refreshed.
Refresh bursts are coalesced, not added to an unbounded request queue. A notice
received during a fetch still requests one follow-up fetch. A stalled JSON body
remains subject to the configured API timeout even after headers arrive.

If refresh removes the selected site, its old details, photos, reports and pins
are cleared before loading a replacement. A failed replacement load shows an
unavailable message rather than another site's data. A browser Back/Forward
Cache restore reloads the page, reruns the Auth0 session check and restarts
updates; the paused page never claims an active connection while its timers
are stopped.

## Shared design handoff to Isaiah

The shared stylesheet is `page/shared/planit.css`. Isaiah can set
`themeStylesheet: '../shared/planit.css'` in his own `crew-config.js`, or add a
stylesheet link himself. The root `--planit-*` variables are available across
the app. Component styles use opt-in `planit-*` classes. Existing `.crew-*`
selectors and scoped variables are not overridden, so Isaiah can adopt tokens
incrementally without replacing his screens.

## Remaining shared integration decisions

- **Summary target-window gap:** contract v1.3 requires the target window on
  every score screen, but `GET /sites` omits its exact dates. The list and map
  show the 24-hour target description and ask users to open the detail for the
  exact dates. Alan should add `valid_from` and `valid_until` to `/sites` if the
  team wants exact dates in list and map.
- **Feed health:** the API exposes `lightning_status` on list/detail and
  `warnings_status` in detail. The UI requires fresh explicit checks to say
  lightning is clear or no NWS alerts are active; zero alert rows alone is not
  proof of safety. A known stop-work alert overrides a conflicting clear field.
- **Replay metadata:** the updated contract requires `trigger.is_replay: true`
  on replayed alerts. The site detail, ranked list and map popup label matching
  active alerts as REPLAY using the full `/alerts` response; opaque strike IDs
  are not treated as proof. Replay speed changes the server's `clear_at`, which
  the countdown displays without assuming a fixed 30 minutes. If `/alerts`
  fails, an overview alert's replay status is unknown because `/sites` omits
  that flag. All fixture data remains labeled SAMPLE. Live replay is visible
  only after the dashboard is connected to the authenticated API.
- **Freshness:** a reading's own timestamp is shown in the site's timezone.
  The 60-minute reading-age badge is a UI advisory, configurable in `config.js`.
  Screening and watch statuses have the stricter contract cutoffs described
  above. Reaching a countdown of zero says “Awaiting server clearance”; only
  the backend ends an active stop-work alert.
- **Deployment:** Alan must deploy the frontend and shared/local Leaflet files,
  including the `crew/crew-vendor` dependency, `page/realtime/` source and the
  linked crew workspace.
  Serve the supervisor directory's index for both direct and trailing-slash
  paths. Click the crew link, filters, markers, sign-in/out, photo and resolve
  flows on a phone before the expo.
- **Live verification:** the included tests verify browser-independent logic
  and a local preview. Real Auth0, PostgreSQL, private photos and DeepSpace need
  a configured integration test with Alan and Sid; no successful deployment or
  real provider connection is implied by the sample preview.
