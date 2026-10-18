# ForeSite frontend

ForeSite brings environmental conditions, safety alerts, crew reports, and
next-day briefings together for utility field teams. Built for the Sperry Tech
challenge at SwampHacks XII, this frontend covers 60 monitored U.S. power plants
from the team's EIA-860M roster.

The browser interface uses HTML, CSS, and JavaScript modules. There is no
frontend build step or package installation required to preview it.

**Live site:** [foresite.work](https://foresite.work/crew/index.html)

## Workspaces and pages

| Page | Purpose |
| --- | --- |
| [`crew/index.html`](crew/index.html) | Welcome page and entry to sign-in or the local demo. |
| [`crew/login.html`](crew/login.html) | Auth0 sign-in entry and role-aware workspace routing. |
| [`crew/crew.html`](crew/crew.html) | Crew site overview, alerts/countdown, hazard reports, score explanation, questions, and briefing. |
| [`crew/crew-atlas.html`](crew/crew-atlas.html) | Main crew site map: 60 plants, search, region filters, selection, and animated 2D/3D views. |
| [`supervisor/index.html`](supervisor/index.html) | Live supervisor dashboard: ranked sites, selectable map markers, site details, reports, private photos, and report resolution. |
| [`crew/crew-supervisor.html`](crew/crew-supervisor.html) | Older crew-package supervisor preview, used as a labeled local sample. The live supervisor dashboard is the page above. |

Sign-in uses the account's assigned Auth0 roles. Crew entry favors the crew
workspace when an account has both roles; the supervisor dashboard checks for
the supervisor role separately. The API enforces permissions independently of
the buttons shown in the browser.

## Run locally

Install **Node.js 20 or newer**. From the repository root (`planit-control`):

```sh
node page/crew/dev/serve.mjs
```

This serves crew, supervisor, shared styles, and real-time modules together.

| Preview | Address |
| --- | --- |
| Welcome | <http://127.0.0.1:4174/crew/index.html> |
| Crew demo at Turkey Point (621) | <http://127.0.0.1:4174/crew/crew.html?demo=1&site=621> |
| 2D/3D site map | <http://127.0.0.1:4174/crew/crew-atlas.html?demo=1&site=621> |
| Supervisor dashboard | <http://127.0.0.1:4174/supervisor/index.html> |

The server listens only on this computer (`127.0.0.1`). It does not publish the
site or let a phone connect over Wi-Fi. Use the HTTPS live site for phone
testing. Opening HTML directly from disk or through PyCharm's HTML preview
does not provide the registered Auth0 origin.

An optional supervisor-only preview server runs on port 4175:

```sh
node page/supervisor/dev/serve.mjs
```

Open <http://127.0.0.1:4175/supervisor/index.html>. A different preview port
requires deliberate Auth0 callback/origin configuration before sign-in works.

## Demo data versus live data

| Area | Local preview | Production |
| --- | --- | --- |
| Crew screens and Atlas | `mock` mode: real plant coordinates with labeled synthetic conditions, scores, and alerts. | `live` mode only on the exact `https://foresite.work` origin; authenticated requests use `/api`. |
| Supervisor dashboard | Defaults to `live`; expects the API at `http://127.0.0.1:8010` and a supervisor login. | Authenticated requests use the same-origin `/api` proxy. |
| Reports and photos | Crew demo stores reports/photos in this browser's IndexedDB; other tabs on the same browser/origin can receive demo updates. | Reports are saved through the API; photos are private and require authorization to view. |
| Real-time updates | Crew mock mode does not subscribe to DeepSpace. | DeepSpace notices trigger authenticated API reads. |

The supervisor's separate `sample` adapter can be selected in
[`supervisor/config.js`](supervisor/config.js) for offline development; it has
three labeled sample plants. It is not automatically enabled by the crew's
`demo=1` link. Neither workspace substitutes samples when a live request fails.

Demo storage is browser-local, not shared across devices, and does not send
real alerts or schedule briefing delivery.

## What the interface shows

- **Site conditions:** weather, heat, lightning, flooding, wildfire, soil
  saturation, and wildlife, with available sources and timestamps.
- **Lightning alerts:** stop-work state and a countdown derived from the
  server's `clear_at`. A new nearby strike can restart the deadline. The
  backend owns the 10-mile/30-minute rule. Replay alerts are visibly labeled.
- **Crew reports:** hazard type, severity, description, optional photo, and a
  map pin or paired coordinates. The crew member confirms any photo category
  suggestion. Reports remain in open/resolved history.
- **Supervisor operations:** select a map marker or ranked site to inspect its
  data, view protected report photos, and resolve a report.
- **Score explanation:** a visible Prototype label, target window, baseline,
  and signed feature contributions. The index screens for selected NWS
  warnings or heat advisories in the next 24 hours; it is not an injury
  probability or permission to work.
- **Wildlife evidence:** dated, attributed sightings and limitations, separate
  from the screening index. Sightings and crew reports do not add score points.
- **Briefings:** the latest saved next-day text, generation time, and source
  evidence when supplied. The backend owns the 6 PM site-local generation job.
- **Ask about site data:** an authenticated question to `/ask`, with the answer,
  source links, and returned SQL. Gemini and database queries run on the server.

Missing or stale data shows as unavailable, never zero or safe. An empty alert
list alone does not establish lightning clearance. A countdown reaching zero
does not authorize resuming work: the interface needs the API's fresh watch
status, and safety alerts remain independent of the model index.

Atlas 3D is an animated map projection with score-height beams, not terrain or
building geometry. Plant bases stay at their mapped locations; labels can move
to avoid overlap. Motion can be disabled. Pan, zoom, filtering, and transitions
do not make per-plant score requests; scores come from bulk site-list reads.

## Backend and authentication connection

Use [`../docs/TEAM.md`](../docs/TEAM.md) for workflow and
[`../api/CONTRACT.md`](../api/CONTRACT.md) for the shared API contract (currently
v1.3). The running API's `/docs` page is the final reference for exact request
and response fields. Backend startup is documented in the
[repository README](../README.md); the local API documentation is normally at
<http://127.0.0.1:8010/docs>.

Public browser configuration lives in [`crew/crew-config.js`](crew/crew-config.js)
and [`supervisor/config.js`](supervisor/config.js). They specify the API base,
Auth0 public identifiers, role claim, and DeepSpace connection. Auth0 uses
in-memory tokens, refresh-token rotation, and the `offline_access` scope.
Expired authorization must ask the user to sign in again rather than present
old data as connected.

Core request flows:

| Request | Frontend use |
| --- | --- |
| `GET /sites`, `GET /sites/{site_id}` | Site list, map, conditions, screening explanations, and wildlife evidence. |
| `GET /alerts` | Authoritative warnings and stop-work deadlines. |
| `GET /reports?site_id=...` | Report list and hazard pins. |
| `POST /photos` then `POST /reports` | Upload an optional JPEG/PNG (maximum 5 MB), then submit JSON containing its `photo_key`. |
| `GET /photos/{photo_key}` | Authenticated private-photo viewing. |
| `PATCH /reports/{id}` | Supervisor resolution with `{"status":"resolved"}`. |
| `GET /briefings/{site_id}` | Latest saved briefing. |
| `POST /ask` | Questions about available site data. |

The photo form also supports the backend's optional
`POST /photos/{photo_key}/suggestion` helper. A suggestion never submits a
report or replaces a manual category choice.

The crew adapter translates API fields such as integer `site_id`,
`hazard_type`, `screening.factors[].feature`, and `clear_at` into the existing
screen display shapes. See [`crew/crew-contract.d.ts`](crew/crew-contract.d.ts)
and [`crew/crew-integration.js`](crew/crew-integration.js).

DeepSpace carries ID-based notices: `alert.started`, `alert.updated`,
`alert.cleared`, `report.created`, `report.resolved`, and `scores.updated`.
Screens fetch the details from the protected API and refresh after reconnect.
Photos and Auth0 tokens are not sent through the anonymous event subscription.

Client secrets, database passwords, notification secrets, and test-account
passwords must never go in frontend files or commits. Internal Auth0 audience,
role-claim, and module names may still contain `planit-control`; those are
integration identifiers, not visible branding to rename casually.

## Folder guide

| Path | Contents |
| --- | --- |
| `crew/` | Welcome/login, crew workspace, Atlas, adapters, demo storage, assets, and tests. |
| `supervisor/` | Supervisor dashboard, authenticated API client, map/report interactions, and tests. |
| `shared/` | Shared design tokens, authentication helpers, and reading-format helpers. |
| `realtime/` | Alan's shared DeepSpace listener. |
| `crew.html` | Compatibility entry that redirects into the crew package. |

Vendored mapping libraries and geographic assets have license/provenance files
under `crew/crew-vendor/` and `crew/crew-data/`. The monitored roster is
`crew/crew-data/monitored-sites.json`, derived from Sid's team data; do not add
the retired national catalog to the main map.

## Checks

Run the crew checks from `page/crew/`:

```sh
node dev/check.mjs
node --test
```

Run supervisor and shared tests from the repository root:

```sh
node --test page/supervisor/tests/*.test.mjs
node --test page/shared/*.test.mjs
```

An optional read-only local API smoke check is
`node page/crew/dev/check-api.mjs`. It expects the local API to be running and
checks anonymous-access rejection; it does not prove signed-in integration.

Before a release, test a crew-only account on a phone and a supervisor-only
account in another browser: report/photo submission, live arrival without
refresh, supervisor resolution, reconnect after sleep, and session renewal past
an access-token lifetime. Coordinate lightning replay with Alan and keep its
Replay labels visible. Automated tests do not replace these live checks.

## Hosting and current limits

Deploy the frontend as well as the API. Preserve `/crew/`, `/supervisor/`,
`/shared/`, and `/realtime/` on the same HTTPS origin, configure the `/api`
proxy, and register exact Auth0 callback/logout URLs and origins. The local
Node preview servers are development tools, not production hosting.
**Alan owns deployment; follow the current team guide before pushing or
changing authentication settings.**

Briefing email delivery/preferences, briefing history, and archived report
status are hidden pending an agreed contract change. Browsers do not collect
environmental feeds, train models, run the lightning rule, or schedule the
6 PM briefing job. Their availability depends on the backend services.
