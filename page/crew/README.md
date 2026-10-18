# ForeSite — complete frontend package

Contract v1.3 support: the screening index uses feature explanations, a visible
Prototype label and forecast window, local expiry handling, and separate GBIF
wildlife evidence. Fresh lightning and NWS checks stay distinct from the score.
Crew members can ask the authenticated `/ask` service questions. Local demos
remain labeled samples. See
`BACKEND-CONNECTION.md` for the temporary legacy API bridge and the remaining
live API/Auth0/phone acceptance steps for issue #6. The score breakdown includes
a baseline-to-final waterfall and signed feature list.

Dark welcome page, role-aware Auth0 entry, crew workspace, and primary 60-site 2D/3D map. All six challenge capabilities have frontend screens and service connections. Actual environmental feeds, trained ML, shared storage, Auth0 tenant configuration, notification delivery and 6 PM background jobs must be provided by the backend.

The visual theme uses near-black surfaces, mint/cyan accents, restrained hazard tints, original grid/contour artwork, icon navigation and a score ring. `crew-dark.css` supplies the shared dark palette inside Isaiah’s package. Category tints are independent from risk: the labeled severity badges and alert colors retain a consistent vocabulary. `crew-theme.css` keeps these changes scoped, and `crew-visuals.js` contains the original inline SVG artwork without external asset dependencies.

## Run locally

Install Node.js 20 or newer. No package installation or build is required.

```sh
node dev/serve.mjs
```

Open http://127.0.0.1:4174/ for the welcome page. **Log in** starts the Auth0 handoff; **Site map** opens the primary 2D/3D map; **Supervisor** opens Aryan's live dashboard; **Explore the demo** still offers Isaiah's sample supervisor preview. Read **AUTH0-HANDOFF.md** for callback URLs, role configuration and hosted-login colors, and **BACKEND-CONNECTION.md** for the contract v1.1 adapter. Primary map: http://127.0.0.1:4174/crew-atlas.html. Live supervisor dashboard: http://127.0.0.1:4174/supervisor/index.html. Sample supervisor preview: http://127.0.0.1:4174/crew-supervisor.html?demo=1. The preview serves both frontend folders and their shared assets; restart the server after upgrading its routing. To use a different port set the `PORT` environment variable first. Serve over HTTP/HTTPS; opening HTML directly as a file will not load modules or the plant catalog correctly.

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
7. **Ask data:** crew and supervisors may send a plain-English question to the protected `/ask` endpoint. The answer, source links, and collapsible SQL are rendered as text. Sample mode does not invoke Gemini.
8. **Supervisor workspace:** Aryan's live dashboard is the canonical destination for supervisors. Isaiah's original dark supervisor screen remains a labeled sample preview with the 60-plant roster and demo storage; its **Open 2D / 3D map** control opens the separate Atlas with the selected plant.
9. **Explainable 0–10 model display:** prototype score, signed contributions in score points, baseline, model version, score time and forecast horizon. Mismatched or absent explanations suppress the number; missing values never become zero.
10. **Backend adapters:** authenticated contract REST requests, separate photo upload and JSON report creation, protected image reads, and Alan’s shared DeepSpace listener with ID validation, batched score refresh, reconnect and cleanup. No legacy `/events` request or invented pagination.
11. **Auth0 entry points:** Universal Login, callback handling and sign-out. Sample access is available only in mock mode. Supervisor live entry checks a configurable roles claim; the API must independently enforce authorization.

## Connect the backend

Read **BACKEND-CONNECTION.md** first. An adapter is a small translation layer between your team's API and the fields the screens expect.

- Set public Auth0 identifiers, API URL and route mapping in `crew-config.js`.
- Use the included HTTP adapter and use the included default DeepSpace listener configured under `api.realtime`. An optional custom `window.PlanITCrewAPI` must supply the existing UI shapes.
- `crew-contract.d.ts` separates API types from UI display aliases. `crew-integration.js` translates between them; `api/CONTRACT.md` v1.3 remains authoritative.
- Confirm `api.photoField` with Aryan. The contract specifies multipart images but not the field name; the configurable default is `file`.
- Live mode activates only on the exact HTTPS production origin. Local previews remain samples. Live failures show errors and never substitute synthetic data. The six contract event types—including `scores.updated`—refresh crew details, reports, supervisor rankings and Atlas colors automatically.

## Local demonstration limits

Plant locations are real references; all conditions, scores, forecasts and model details are synthetic. The location roster is Sid’s **60 monitored plants** from the August 2026 EIA-860M data. Provenance and coverage are in `crew-data/atlas-source.json`.

Demo reports and actual image files are stored in **IndexedDB**, the browser's local database. They survive reloads on this browser and origin, subject to browser storage limits. **BroadcastChannel** sends demo changes to other tabs on that same browser/origin. This is not cross-device sync, shared Tiger Data storage or a DeepSpace upload. Local demo strike deadlines are also retained. No real crews are notified. No daily delivery job is created. Real model training and flood decisions are backend responsibilities.

Auth0 needs its configured tenant and internet connection. Map tiles need OpenStreetMap connectivity; coordinate fields and site lists still work if tiles fail. Vendored Leaflet code and its license are included. No server secrets belong in this package.

## File ownership and integration

The package stays under `crew-*` and does not edit Aryan's dashboard or shared stylesheet. `crew-supervisor.html/js` preserves Isaiah's sample preview layout. The old national plant catalog remains retired; all crew-owned demo screens use the same 60 monitored plants. Authenticated supervisor handoff and the welcome-page Supervisor link now open Aryan's canonical live dashboard. Shared theme tokens are imported through `themeStylesheet`; crew components keep their scoped fallback styles.

Keep `crew-data/` and `crew-vendor/` with the pages when copying them into `page/crew/`. The root `dev/` scripts are development tools, not backend services. See CREW-DEVELOPMENT.md for the staged Git integration and implementation rationale. Deployment and backend connection are separate steps.

For integrated static hosting, preserve the `page/` structure: `/crew/`,
`/supervisor/`, `/shared/` and `/realtime/` must be served on the same origin.
Open `/crew/index.html` for the welcome page. Isaiah's sample supervisor preview remains inside `/crew/`; Aryan’s live
dashboard is at `/supervisor/index.html`. The local crew preview keeps root aliases
(`/index.html`, `/crew.html`, `/crew-atlas.html`) working alongside those folders.
Configure HTTPS and each workspace’s Auth0 callback/logout URLs for production.
Keep API URLs in their public configuration files.

## Checks

```sh
node dev/check.mjs
node --test
node dev/check-api.mjs
```

Tests cover lightning distance/boundary/reset/order, expiry/disconnect behavior, DST-aware schedule previews, score/ranking integrity, real-site coverage, contract field mapping, upload/report sequencing, authenticated photo reads, latest briefings, error handling and DeepSpace notice refetch/reconnect/cleanup. The optional read-only API check targets the local API at port 8010 and expects anonymous data access to be rejected. Browser QA notes are in `VERIFICATION.md`.

See CREW-DEVELOPMENT.md for the seven commit groups, file ownership, implementation rationale and validation.
