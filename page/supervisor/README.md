# Aryan's supervisor workspace

This is Aryan's dashboard, separate from Isaiah's files in `page/crew/`. It follows
`api/CONTRACT.md` v1.1. The default is an explicitly labeled, read-only sample
preview containing **3 sample plants**, copied from the team's `api/samples/`.
Sample timestamps are preserved; they are not made to appear fresh.

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
| `api.js` | Authenticated requests using exact contract paths; separate read-only sample adapter. |
| `domain.js` | Pure score/ranking/freshness/coordinate/event validation functions. |
| `realtime.js` | Alan's DeepSpace adapter boundary, reconnect and authorized refetch. |
| `app.js` | Page interactions, Leaflet markers, waterfall, reports and private-photo rendering. |
| `sample-data/*.json` | Exact sample sites/details/reports/alerts copied from `api/samples/`. |
| `dev/serve.mjs` | Loopback-only static preview server, including trailing-slash handling. |
| `tests/*.test.mjs` | Node built-in tests; no npm dependencies. |
| `package.json` | ES-module declaration and optional `npm test`/`npm run dev` shortcuts. |

The site list sorts by score descending and puts missing scores last. It shows
top signed factors alongside every summary score. Clicking a list entry or map
marker loads the full explanation. The waterfall starts at the baseline, then
adds/subtracts each factor, and ends at the score. If the full-precision sum is
off by more than 0.05, the panel displays an error instead of a misleading
chart. Zero is a valid score; missing/invalid data is not converted to zero.

Reports are displayed separately from model scores, with pins only when both
coordinates exist. Live private photos are requested with the bearer token and
rendered from an in-memory Blob URL. Tokens and photo keys are never placed in
public image URLs or query strings. Blob URLs are revoked when the selected
detail changes or the page closes. Only JPEG/PNG responses under 5 MB are shown.

The resolution button calls `PATCH /reports/{id}` with exactly
`{"status":"resolved"}`. The API must independently authorize this operation.
The UI awaits success and then reloads the site list, alerts, site detail and
reports. It never adjusts the score after a report event.

## Connect live data and Auth0

1. Alan must register the report/photo router and supply authenticated API
   access to sites, site details, alerts and reports. Sid's database and the
   report table must be ready. The existing sample API is not a production
   integration and must not be presented as one.
2. Edit `config.js`: choose `mode: 'live'`, set the API base, and set the Auth0
   public `domain`, `clientId`, API `audience` and agreed namespaced `rolesClaim`.
   Never add a client secret. Local API URLs must use `http://127.0.0.1`; deployed
   API URLs must use HTTPS. Configure the API's CORS allowlist for the exact
   frontend origin and allow the Authorization header.
3. In the Auth0 SPA application, register the exact callback and logout URLs
   in `config.auth`, and the frontend origin in Allowed Web Origins. Locally
   the default callback/logout URL is
   `http://127.0.0.1:4175/supervisor/index.html`, with origin
   `http://127.0.0.1:4175`. For deployment these derive from the deployed module
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

## DeepSpace handoff to Alan

Before `app.js` initializes live mode, supply the existing frontend boundary
`window.PlanITCrewRealtime`. It is shared by convention with the crew frontend;
this dashboard does not invent a new `/events` API.

```js
window.PlanITCrewRealtime = {
  async subscribe({site_id, accessToken, onEvent, onConnection, onError}) {
    // site_id is null for the supervisor's all-sites subscription.
    // Use the team's authenticated DeepSpace connection here.
    // onConnection(true) only after the provider confirms a live connection.
    // onEvent({type: 'report.created', report_id: '...', site_id: 6045,
    //          created_at: '2026-10-17T18:00:00Z'});
    // Report disconnects/errors through onConnection(false)/onError(error).
    // Return a function that closes this subscription and removes listeners.
    return () => { /* unsubscribe */ };
  }
};
```

This is an interface illustration, not a working DeepSpace implementation.
Alan owns the SDK/provider implementation, channel authorization and token
refresh within that provider. Publish only after the database transaction has
committed. Supported event types are `report.created`, `report.resolved`,
`alert.started`, `alert.updated`, and `alert.cleared`. Payloads supply only the
contract's IDs/timestamps. Each accepted event and reconnect refetches the
site list, active alerts, selected site detail and reports from the API. UI text
never comes from the event payload.

Without the provider, the dashboard honestly says live events are unavailable
and polls every 30 seconds. Polling does not count as a live connection.

## Shared design handoff to Isaiah

The shared stylesheet is `page/shared/planit.css`. Isaiah can set
`themeStylesheet: '../shared/planit.css'` in his own `crew-config.js`, or add a
stylesheet link himself. The root `--planit-*` variables are available across
the app. Component styles use opt-in `planit-*` classes. Existing `.crew-*`
selectors and scoped variables are not overridden, so Isaiah can adopt tokens
incrementally without replacing his screens.

## Remaining shared integration decisions

- **Lightning feed health:** contract v1.1 does not expose it. The UI says health
  is unavailable; zero active alerts does not prove a live feed or safe weather.
- **Replay metadata:** v1.1 omits a dedicated replay flag on alert responses.
  Known `replay-` strike IDs or supplied `trigger.is_replay: true` are labeled.
  Alan must supply an agreed explicit replay indication for every replayed
  alert before demonstrating live/replay mode; the frontend cannot infer it
  from opaque strike IDs. All fixture data remains labeled SAMPLE.
- **Freshness:** a reading's own timestamp is shown in the site's timezone.
  The 60-minute stale badge is a UI advisory, configurable in `config.js`, not
  a safety threshold. Reaching a countdown of zero says “Awaiting server
  clearance”; only the backend ends an active stop-work alert.
- **Deployment:** Alan must deploy the frontend and shared/local Leaflet files,
  including the `crew/crew-vendor` dependency and the linked crew workspace.
  Serve the supervisor directory's index for both direct and trailing-slash
  paths. Click the crew link, filters, markers, sign-in/out, photo and resolve
  flows on a phone before the expo.
- **Live verification:** the included tests verify browser-independent logic
  and a local preview. Real Auth0, PostgreSQL, private photos and DeepSpace need
  a configured integration test with Alan and Sid; no successful deployment or
  real provider connection is implied by the sample preview.
