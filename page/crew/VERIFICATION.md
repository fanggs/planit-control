# Frontend verification — October 17, 2026

## Automated

`node --test`: **22 passed, 0 failed** after report-schema alignment. `node dev/check.mjs`: all application JavaScript syntax checks passed.

The original 17 tests are retained. Five more tests check the current strict backend report payload: enum/ID conversion, an explicit severity choice, omission of client identity and retry ID from JSON, invalid coordinates/description/storage keys, and preservation of opaque key identity with rejection of URLs/control characters. The new selector is a small form extension; live submission still needs the actual upload/report endpoints.

Coverage: 10-mile lightning boundary, distant-strike exclusion, old strike/deadline handling, countdown after tab sleep, ordered per-site alerts, explicit server clear, disconnected/unknown states, DST transitions for 6 PM previews, ranking with missing/out-of-range scores, monotonic site revisions, 13,446 unique plant references with valid coordinates, bearer authentication, cursor pagination, multipart photo upload, permission errors and fragmented/multiline SSE messages.

## Browser checks with the local sample adapter

- Searched the national catalog for Grand Gulf, selected it and confirmed the selected site's name/ID/state changed.
- A 12-mile sample strike did not trigger a hold; a 4.2-mile strike displayed STOP WORK and 30:00.
- Another crew tab received the active hold and decreasing countdown through the browser-local event channel.
- All seven hazard categories rendered with source/time fields and an explainable score panel.
- The sample Mississippi River flood warning remained visible while navigating to briefings and reports.
- Briefing preferences used America/Chicago for Grand Gulf; saving showed a local-only receipt rather than claiming delivery.
- Selected a test image (a UI screenshot, not a real hazard), changed the report pin's latitude, reviewed and submitted. The photo, description, pin and report ID appeared in history.
- Navigated/reloaded and reopened reports: the saved photo and coordinates remained available.
- The supervisor preview showed all 13,446 sites, a paginated ranking and search filters. Selected Grand Gulf; its saved report appeared in the site observations. The report marker's map popup displayed its description and retained photo.
- Desktop at a 1280 × 900 viewport: 1265 px document width after scrollbar, no horizontal overflow; map and ranking used separate columns.
- Crew at a 390 × 844 viewport: 375 px document width after scrollbar, no horizontal overflow. Supervisor narrow layout also stacked the filters and map/ranking.

Screenshots are delivered beside the package: `planit-complete-preview.png`, `planit-complete-mobile.png` and `planit-complete-supervisor.png`. Temporary viewport overrides were reset after checking.

## Not verified against a live team backend

Auth0 login/role claims, API CORS, actual feeds/10-mile server decisions, DeepSpace cross-device updates/storage, real trained model/evaluation, real flood detection, actual scheduled/email/background-push delivery, physical-phone camera behavior, production hosting/domain/HTTPS and team repository integration. These need the team's services/configuration. The local sample is not evidence that these backend functions are operating.
