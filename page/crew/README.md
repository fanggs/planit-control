# PlanIT Control — complete frontend package

Dark welcome page, role-aware Auth0 entry, crew workspace, and separate supervisor integration preview. All six challenge capabilities have frontend screens and service connections. Actual environmental feeds, trained ML, shared storage, Auth0 tenant configuration, notification delivery and 6 PM background jobs must be provided by the backend.

The visual theme uses near-black surfaces, mint/cyan accents, restrained hazard tints, original grid/contour artwork, icon navigation and a score ring. `crew-dark.css` supplies the shared dark palette inside Isaiah’s package. Category tints are independent from risk: the labeled severity badges and alert colors retain a consistent vocabulary. `crew-theme.css` keeps these changes scoped, and `crew-visuals.js` contains the original inline SVG artwork without external asset dependencies.

## Run locally

Install Node.js 20 or newer. No package installation or build is required.

```sh
node dev/serve.mjs
```

Open http://127.0.0.1:4174/ for the welcome page. **Log in** starts the Auth0 handoff; **Explore the demo** offers separate crew and supervisor previews. Read **AUTH0-HANDOFF.md** for callback URLs, role configuration and hosted-login colors, and **BACKEND-CONNECTION.md** for the contract v1.1 adapter. Supervisor preview: http://127.0.0.1:4174/crew-supervisor.html?demo=1. If port 4174 is already serving this package, reload it. To use a different port set the `PORT` environment variable first. Serve over HTTP/HTTPS; opening HTML directly as a file will not load modules or the plant catalog correctly.

## Included

1. **National site picker:** 13,446 actual EIA-derived power plant records, searchable by name, state, operator or ID. Includes all 50 states, DC and Puerto Rico in the source snapshot.
2. **Combined site picture:** weather, extreme heat, lightning, flooding, wildfire, soil saturation and wildlife cards, each with status, advice, observation time and source.
3. **Lightning alerts:** a persistent alert across all crew tabs, absolute 30-minute deadline, event ordering, reconnect/disconnect states and server-confirmed clear. Demo scenarios exercise strikes within and beyond 10 miles and reset the hold on another nearby strike.
4. **Flood warnings:** river proximity, overnight rain, observation window, rule explanation and a warning banner across crew views. Grand Gulf (6072) has a Mississippi River demonstration scenario. Real flood criteria remain backend-owned.
5. **Briefing:** latest next-day text, date, generation time, available input evidence and print view. History, delivery preferences and email controls remain hidden pending a team contract update. The backend owns the 18:00 site-local job.
6. **Photo reports:** optional JPEG/PNG up to 5 MB, preview, map click or draggable pin, accessible paired coordinates, validation, two-step upload/report state, stored receipt, open/all/resolved filters and report-map pins. Archived controls remain hidden.
7. **Supervisor preview:** national canvas-rendered map, scores sorted high-first, state/search/risk filters, paginated ranking, selected-site explanation, flood details and crew observations. Crew reports appear here in another tab in the local demo.
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

Plant locations are real references; all conditions, scores, forecasts and model details are synthetic. The location snapshot is **February 2025**, retrieved October 17, 2026. EIA's survey scope generally covers plants with at least 1 MW of combined nameplate capacity; this does not include every rooftop or small distributed generator. Provenance and exact coverage are in `crew-data/source.json`.

Demo reports and actual image files are stored in **IndexedDB**, the browser's local database. They survive reloads on this browser and origin, subject to browser storage limits. **BroadcastChannel** sends demo changes to other tabs on that same browser/origin. This is not cross-device sync, shared Tiger Data storage or a DeepSpace upload. Local demo strike deadlines are also retained. No real crews are notified. No daily delivery job is created. Real model training and flood decisions are backend responsibilities.

Auth0 needs its configured tenant and internet connection. Map tiles need OpenStreetMap connectivity; coordinate fields and site lists still work if tiles fail. Vendored Leaflet code and its license are included. No server secrets belong in this package.

## File ownership and integration

The package stays under `crew-*` and does not edit Aryan's dashboard or shared stylesheet. `crew-supervisor.html/js` is a separate, optional handoff preview. Aryan can reuse its components or keep his dashboard. Shared theme tokens are inherited when `themeStylesheet` is configured; the temporary fallback styles stay inside `.planit-crew`.

Keep `crew-data/` and `crew-vendor/` with the pages when copying them into `page/crew/`. The root `dev/` scripts are development tools, not backend services. See CREW-DEVELOPMENT.md for the staged Git integration and implementation rationale. Deployment and backend connection are separate steps.

For static hosting, publish the **contents of `page/crew/`** as the web root. Its `index.html` opens the crew login. Configure HTTPS and Auth0 origins/callbacks for the production domain. Keep the FastAPI service URL in config; a website root that returns API JSON is not a frontend deployment.

## Checks

```sh
node dev/check.mjs
node --test
node dev/check-api.mjs
```

Tests cover lightning distance/boundary/reset/order, expiry/disconnect behavior, DST-aware schedule previews, score/ranking integrity, real-site coverage, contract field mapping, upload/report sequencing, authenticated photo reads, latest briefings, error handling and DeepSpace notice refetch/reconnect/cleanup. The optional read-only API check requires Alan's local sample server at port 8010. Browser QA notes are in `VERIFICATION.md`.

See CREW-DEVELOPMENT.md for the seven commit groups, file ownership, implementation rationale and validation.
