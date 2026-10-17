# PlanIT Control — complete frontend package

Dark welcome page, role-aware Auth0 entry, crew workspace, and primary 60-site 2D/3D map. All six challenge capabilities have frontend screens and service connections. Actual environmental feeds, trained ML, shared storage, Auth0 tenant configuration, notification delivery and 6 PM background jobs must be provided by the backend.

The visual theme uses near-black surfaces, mint/cyan accents, restrained hazard tints, original grid/contour artwork, icon navigation and a score ring. `crew-dark.css` supplies the shared dark palette inside Isaiah’s package. Category tints are independent from risk: the labeled severity badges and alert colors retain a consistent vocabulary. `crew-theme.css` keeps these changes scoped, and `crew-visuals.js` contains the original inline SVG artwork without external asset dependencies.

## Run locally

Install Node.js 20 or newer. No package installation or build is required.

```sh
node dev/serve.mjs
```

Open http://127.0.0.1:4174/ for the welcome page. **Log in** starts the Auth0 handoff; **Site map** opens the primary 2D/3D map; **Supervisor** opens the original crew-owned supervisor preview; **Explore the demo** offers both workspaces and the site map. Read **AUTH0-HANDOFF.md** for callback URLs, role configuration and hosted-login colors, and **BACKEND-CONNECTION.md** for the contract v1.1 adapter. Primary map: http://127.0.0.1:4174/crew-atlas.html. Supervisor: http://127.0.0.1:4174/crew-supervisor.html?demo=1. The preview serves both frontend folders and their shared assets; restart the server after upgrading its routing. If port 4174 is already serving this package, reload it. To use a different port set the `PORT` environment variable first. Serve over HTTP/HTTPS; opening HTML directly as a file will not load modules or the plant catalog correctly.

## Included

The **Site map** is the main map throughout this frontend. It uses Sid’s 60
verified plants, animated 2D/3D transitions, hazard-score colors, risk ranking,
search, inspection and phone controls. Mock mode shows labeled sample scores;
live mode uses authenticated API scores and leaves unavailable scores gray.
See **CREW-ATLAS.md** for roster refresh, controls and integration.

1. **Monitored site picker and primary map:** Sid’s 60 actual EIA-860M power plants, searchable by name, state, utility or ID, with six hazard regions. The 2D/3D map ranks and colors plants by hazard score.
2. **Combined site picture:** weather, extreme heat, lightning, flooding, wildfire, soil saturation and wildlife cards, each with status, advice, observation time and source.
3. **Lightning alerts:** a persistent alert across all crew tabs, absolute 30-minute deadline, event ordering, reconnect/disconnect states and server-confirmed clear. Demo scenarios exercise strikes within and beyond 10 miles and reset the hold on another nearby strike.
4. **Flood warnings:** river proximity, overnight rain, observation window, rule explanation and a warning banner across crew views. Grand Gulf (6072) has a Mississippi River demonstration scenario. Real flood criteria remain backend-owned.
5. **Briefing:** latest next-day text, date, generation time, available input evidence and print view. History, delivery preferences and email controls remain hidden pending a team contract update. The backend owns the 18:00 site-local job.
6. **Photo reports:** optional JPEG/PNG up to 5 MB, preview, map click or draggable pin, accessible paired coordinates, validation, two-step upload/report state, stored receipt, open/all/resolved filters and report-map pins. Archived controls remain hidden.
7. **Supervisor workspace:** the original dark dashboard with colored summary cards, search/state/risk filters, risk ranking, site overview, selected-site score/flood details and crew observations. It uses the same 60-plant roster and demo storage as the crew screen. **Open 2D / 3D map** opens the separate Atlas with the selected plant. Aryan’s dashboard files remain unchanged.
8. **Explainable 0–10 model display:** validated score, signed contributions in score points, baseline, model version, score time and forecast horizon. Mismatched totals show an unavailable explanation; missing values never become zero. Training/evaluation fields render only when supplied.
9. **Backend adapters:** authenticated contract REST requests, separate photo upload and JSON report creation, protected image reads, and an ID-notice bridge for Alan's DeepSpace source with refetch, reconnect and cleanup. No legacy `/events` request or invented pagination.
10. **Auth0 entry points:** Universal Login, callback handling and sign-out. Sample access is available only in mock mode. Supervisor live entry checks a configurable roles claim; the API must independently enforce authorization.

## Connect the backend

Read **BACKEND-CONNECTION.md** first. An adapter is a small translation layer between your team's API and the fields the screens expect.

- Set public Auth0 identifiers, API URL and route mapping in `crew-config.js`.
- Use the included HTTP adapter and connect Alan's SDK through `window.PlanITCrewRealtime`. An optional custom `window.PlanITCrewAPI` must supply the existing UI shapes.
- `crew-contract.d.ts` separates API types from UI display aliases. `crew-integration.js` translates between them; `api/CONTRACT.md` v1.1 remains authoritative.
- Confirm `api.photoField` with Aryan. The contract specifies multipart images but not the field name; the configurable default is `file`.
- Change `dataMode` to `live` only after these are configured. Live failures show errors and never substitute synthetic data.

## Local demonstration limits

Plant locations are real references; all conditions, scores, forecasts and model details are synthetic. The location roster is Sid’s **60 monitored plants** from the August 2026 EIA-860M data. Provenance and coverage are in `crew-data/atlas-source.json`.

Demo reports and actual image files are stored in **IndexedDB**, the browser's local database. They survive reloads on this browser and origin, subject to browser storage limits. **BroadcastChannel** sends demo changes to other tabs on that same browser/origin. This is not cross-device sync, shared Tiger Data storage or a DeepSpace upload. Local demo strike deadlines are also retained. No real crews are notified. No daily delivery job is created. Real model training and flood decisions are backend responsibilities.

Auth0 needs its configured tenant and internet connection. Map tiles need OpenStreetMap connectivity; coordinate fields and site lists still work if tiles fail. Vendored Leaflet code and its license are included. No server secrets belong in this package.

## File ownership and integration

The package stays under `crew-*` and does not edit Aryan's dashboard or shared stylesheet. `crew-supervisor.html/js` restores the original crew-owned preview layout. The old national plant catalog remains retired; all crew-owned demo screens use the same 60 monitored plants. Aryan’s separate dashboard is unchanged. Shared theme tokens are inherited when `themeStylesheet` is configured; the temporary fallback styles stay inside `.planit-crew`.

Keep `crew-data/` and `crew-vendor/` with the pages when copying them into `page/crew/`. The root `dev/` scripts are development tools, not backend services. See CREW-DEVELOPMENT.md for the staged Git integration and implementation rationale. Deployment and backend connection are separate steps.

For integrated static hosting, preserve the `page/` structure: `/crew/`,
`/supervisor/`, `/shared/` and `/realtime/` must be served on the same origin.
Open `/crew/index.html` for the welcome page. The original supervisor preview is included inside `/crew/`; Aryan’s separate
dashboard remains available at `/supervisor/index.html`. The local crew preview keeps root aliases
(`/index.html`, `/crew.html`, `/crew-atlas.html`) working alongside those folders.
Configure HTTPS and each workspace’s Auth0 callback/logout URLs for production.
Keep API URLs in their public configuration files.

## Checks

```sh
node dev/check.mjs
node --test
node dev/check-api.mjs
```

Tests cover lightning distance/boundary/reset/order, expiry/disconnect behavior, DST-aware schedule previews, score/ranking integrity, real-site coverage, contract field mapping, upload/report sequencing, authenticated photo reads, latest briefings, error handling and DeepSpace notice refetch/reconnect/cleanup. The optional read-only API check requires Alan's local sample server at port 8010. Browser QA notes are in `VERIFICATION.md`.

See CREW-DEVELOPMENT.md for the seven commit groups, file ownership, implementation rationale and validation.
