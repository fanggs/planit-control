# Frontend verification — October 17, 2026

## New 60-plant Field Atlas

- `node dev/check.mjs`: passed. `node --test`: **53 passed, 0 failed**.
- Seven atlas tests verify the exact snapshot against Sid's current
  `get_data/generated/sites.json`, six regions with ten plants each, all 60
  projected coordinates, invalid-roster rejection, API score allowlisting,
  unavailable values, filters, interpolation, pointer-anchored zoom and pin spread.
- Browser: 60 list rows / 60 mapped sites in both 2D and 3D. The transition
  entered its animated state and completed with the same 60 sites. Disabling
  Motion switched modes immediately. No console errors appeared in the atlas.
- Search located Rock Creek Wind (EIA 67769). Region filtering returned 10 / 60;
  clearing filters restored 60 / 60. Selecting a row showed its actual metadata.
- Crew navigation round trip preserved Choctaw County (55706) as the return site
  while the atlas used only its approved roster. Unsupported IDs cannot add map
  sites; a direct map visit defaults to Turkey Point (621).
- Checked desktop 1280 × 720 / 1440 × 1000, phone 390 × 900 / 320 × 740, and
  landscape 844 × 390. All 60 mapped locations loaded; no page overflow appeared.
  Phone search drawer, view controls and motion toggle worked.
- Default configuration uses actual location metadata and no invented scores.
  Hollow beacons have a documented fixed display height. No live API, Auth0
  configuration, real-device gestures or DeepSpace delivery are claimed by these
  browser checks. Live scores use the existing authenticated bulk adapter.
- Only `page/crew/` changed. The supervisor app and shared contract are untouched.
  See `CREW-ATLAS.md` for roster refresh and integration instructions.

## Contract v1.1 adapter update — current checks

- `node dev/check.mjs`: application JavaScript syntax passed.
- `node --test`: **46 passed, 0 failed**.
- `node dev/check-api.mjs`: read-only checks passed against Alan's running sample API. Three site summaries; site 9001 mapped to score 8.2, baseline 2.4, signed factors totaling 5.8, lightning deadline 2026-10-17T18:34:00Z, one report and a 2026-10-18 briefing. Site 9002 retained its flood warning.
- Photo upload/view and report creation are absent from the sample server at this check. Simulated HTTP tests cover multipart then JSON sequencing, protected image blobs, retries and uncertain receipts; they do not prove live storage or sharing.
- DeepSpace tests cover ID filtering, authoritative API refetch, new deadlines, matching clearance, report invalidation, reconnect token refresh and cleanup. Alan's actual SDK source is still required; the frontend no longer requests `/events`.
- Browser demo: a nearby strike started 30:00; the hold persisted across crew tabs. A report without a photo or coordinates saved locally and displayed as a site-level report. Open/all/resolved filters rendered without archived status. The latest briefing rendered without preferences or email controls.
- Phone check at 390 × 844: client and scroll widths both 375 px, with no horizontal overflow. Screenshot: `crew-contract-mobile.png` in the delivered outputs. Viewport override was reset.
- Only files under `page/crew/` changed. Supervisor preview files, backend and shared contract were not edited. Default mock mode remains available. Auth0 and actual DeepSpace delivery require team configuration.

The notes below describe earlier versions and historical checks. Superseded endpoint, preference, pagination and SSE descriptions do not describe the current adapter; see `BACKEND-CONNECTION.md`.

## Color theme update

- Browser checks at 1280 × 1000, 390 × 844 and 320 × 740 viewport settings; document widths matched scroll widths, with no horizontal overflow.
- All seven hazard cards have distinct category tints and decorative icons. Their risk badges retain readable severity labels and consistent colors.
- Checked hazard-card text against each category tint; minimum sampled contrast is 4.92:1 after darkening source captions.
- Verified report navigation, photo/category/severity/pin controls and briefing navigation at phone size. Lightning and flood warnings remained visible across views; a sample strike reset the displayed countdown to 30:00.
- Verified the supervisor's desktop map/ranking columns and its stacked phone layout. The original national preview received a matching palette as a separate local artifact.
- Browser console reported no errors in the final crew view. Original SVG artwork requires no additional network requests. Temporary viewport overrides were reset.
- Screenshots beside the package: `planit-colorful-desktop.png`, `planit-colorful-mobile.png`, `planit-colorful-supervisor.png` and `planit-colorful-preview.png`.

## Automated

`node --test`: **22 passed, 0 failed** after report-schema alignment. `node dev/check.mjs`: all application JavaScript syntax checks passed.

The original 17 tests are retained. Five more tests check the current strict backend report payload: enum/ID conversion, an explicit severity choice, omission of client identity and retry ID from JSON, invalid coordinates/description/storage keys, and preservation of opaque key identity with rejection of URLs/control characters. The new selector is a small form extension; live submission still needs the actual upload/report endpoints.

Coverage: 10-mile lightning boundary, distant-strike exclusion, old strike/deadline handling, countdown after tab sleep, ordered per-site alerts, explicit server clear, disconnected/unknown states, DST transitions for 6 PM previews, ranking with missing/out-of-range scores, monotonic site revisions, 60 unique monitored plant references with valid coordinates, bearer authentication, cursor pagination, multipart photo upload, permission errors and fragmented/multiline SSE messages.

## Browser checks with the local sample adapter

- Searched the national catalog for Grand Gulf, selected it and confirmed the selected site's name/ID/state changed.
- A 12-mile sample strike did not trigger a hold; a 4.2-mile strike displayed STOP WORK and 30:00.
- Another crew tab received the active hold and decreasing countdown through the browser-local event channel.
- All seven hazard categories rendered with source/time fields and an explainable score panel.
- The sample Mississippi River flood warning remained visible while navigating to briefings and reports.
- Briefing preferences used America/Chicago for Grand Gulf; saving showed a local-only receipt rather than claiming delivery.
- Selected a test image (a UI screenshot, not a real hazard), changed the report pin's latitude, reviewed and submitted. The photo, description, pin and report ID appeared in history.
- Navigated/reloaded and reopened reports: the saved photo and coordinates remained available.
- Historical check of the now-retired national preview: it showed the previous national catalog, a paginated ranking and search filters. Selected Grand Gulf; its saved report appeared in the site observations. The report marker's map popup displayed its description and retained photo.
- Desktop at a 1280 × 900 viewport: 1265 px document width after scrollbar, no horizontal overflow; map and ranking used separate columns.
- Crew at a 390 × 844 viewport: 375 px document width after scrollbar, no horizontal overflow. Supervisor narrow layout also stacked the filters and map/ranking.

Screenshots are delivered beside the package: `planit-complete-preview.png`, `planit-complete-mobile.png` and `planit-complete-supervisor.png`. Temporary viewport overrides were reset after checking.

## Not verified against a live team backend

Auth0 login/role claims, API CORS, actual feeds/10-mile server decisions, DeepSpace cross-device updates/storage, real trained model/evaluation, real flood detection, actual scheduled/email/background-push delivery, physical-phone camera behavior, production hosting/domain/HTTPS and team repository integration. These need the team's services/configuration. The local sample is not evidence that these backend functions are operating.


## Dark welcome and role routing — October 17, 2026

- 28 behavior tests pass, including role selection, rejected arbitrary redirect parameters, single-use callback handling, in-memory SDK reuse, and expired-session login. The Auth0 cases use an SDK double; no real tenant verification is claimed.
- JavaScript syntax checks pass.
- Browser checked: welcome → login; unconfigured sign-in state; sample crew and supervisor access; report form/map controls; briefing navigation; home links. No console errors in the exercised crew flow.
- Dark surfaces checked on both workspaces and form controls. Existing stop-work, warning and unavailable states remain distinct.
- Welcome verified at desktop, 390 × 844 and 320 × 740. Supervisor, report form and briefing verified at 390 px. No horizontal overflow in these checks.
- Hosted Auth0 branding and real login remain pending team-provided public application settings. Live API adapter alignment with CONTRACT v1.1 is still required.


## Primary map update · October 17, 2026

- `node dev/check.mjs`: passed. `node --test`: 56 passed, none failed.
- Desktop and 390 × 844 phone previews: exactly 60 mapped plants; hazard-score
  colors and ranking agree with crew demo scores. No horizontal phone overflow.
- Selected Rock Creek Wind (67769), opened its crew view, and confirmed its
  name, sample score 9.4, timezone, provenance, and 60-site picker.
- Tested 2D → 3D → 2D transitions, phone plant-list expansion and six-region
  filter (10 plants), then cleared it (60 plants).
- The retired crew-supervisor URL now mounts the primary map and preserves
  the selected plant and view. The phone home-page Site map link opens it.
- No browser console errors in the final preview. Live Auth0/API operation
  was not exercised; demo scores are explicitly synthetic.
- Aryan’s dashboard and all files outside page/crew were untouched.


## Supervisor navigation restored · October 17, 2026

- `node dev/check.mjs`: passed. `node --test`: 60 passed, none failed.
- Regression checks cover the real login entry: verified supervisors navigate
  to `/supervisor/index.html`, callback parameters/tokens are not forwarded,
  and a URL role cannot route an account without a supported verified claim.
- The crew preview server now serves both workspace folders and shared assets
  on one origin, with legacy root aliases retained. HTTP tests cover the routes,
  directory redirects, blocked repository/hidden paths, GET/HEAD and rejected POST.
- Browser preview on port 4177: welcome Supervisor link opens Aryan’s dashboard;
  its Crew workspace link returns to the crew welcome page. Phone navigation
  works from welcome → 60-site map → crew demo → supervisor dashboard.
- Supervisor currently shows its own three-site labeled, read-only contract
  sample. The separate primary map still shows Sid’s 60 real plant locations.
- Live Auth0 single sign-on was not exercised: both workspace configurations
  still require the team’s tenant setup. No supervisor/shared/API files changed.
- Restart old preview processes to enable the sibling routes; the process that
  was already on port 4176 still has its original routing until restarted.
