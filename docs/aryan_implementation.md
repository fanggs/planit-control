# Aryan's PlanIT Control implementation

Built against `api/CONTRACT.md` v1.1 and `docs/TEAM.md`, inspected at `5b87c34`.
These files are already in the local checkout. Nothing was staged, committed,
pushed, deployed, or applied to a database. Shared `api/main.py`, the root
requirements, the contract, and Isaiah's crew files were not changed.

Important contract correction: photos now go **through our API into private
server storage**. DeepSpace transports real-time notifications, not photos.

## 1. Files and where they go

All paths below are relative to the `planit-control` repository root. The ZIP
uses these same paths. On another checkout, review before copying: do not
replace teammates' newer edits. The three existing files are updated; the
other files are additions.

| File or folder | Purpose |
| --- | --- |
| `api/schemas/hazard_report.py` | Validates request and response data; exact contract enums, coordinate pairs, safe photo references, open/resolved status. |
| `api/services/hazard_report_service.py` | SQLAlchemy queries for saving, listing, resolving, and checking attached photos. Uses the caller's session; never opens its own database or commits. |
| `db/hazard_report.sql` | One PostgreSQL table plus constraints and a newest-first lookup index. No duplicate plural-named SQL file is needed. |
| `api/auth/hazard_auth.py` | Auth0 access-token signature/issuer/audience/expiry checks and reusable crew/supervisor role checks. |
| `api/services/hazard_photo_service.py` | Validates image bytes and stores private JPEG/PNG data plus uploader metadata. |
| `api/routes/hazard_reports.py` | GET/POST `/reports`, PATCH `/reports/{id}`; authentication, transactions, and post-commit notifications. |
| `api/routes/hazard_photos.py` | POST `/photos` and authenticated GET `/photos/{photo_key}`. |
| `api/routes/hazard_errors.py` | Contract-shaped validation/auth/database errors, scoped to these routers. |
| `api/hazard_reporting.py` | One registration function Alan calls from the team's existing app. |
| `api/requirements-hazard.txt` | Necessary backend additions while retaining the root requirements. |
| `api/requirements-hazard-dev.txt` | HTTP test client and PostgreSQL SQL-parser test dependencies. |
| `page/shared/planit.css` | Shared color, spacing, typography, focus, and component tokens. Isaiah can adopt these without overwriting his screens. |
| `page/supervisor/index.html`, `app.js`, `supervisor.css` | Responsive ranked map, site detail, explainable score, reports, private photo viewing, and resolution controls. |
| `page/supervisor/domain.js` | Pure ranking, validation, score arithmetic, freshness, and countdown rules. |
| `page/supervisor/api.js` | Sample/live API adapter, bearer authentication, errors, photo blobs. |
| `page/supervisor/auth.js`, `config.js` | Auth0 browser login and public deployment settings. No client secret belongs here. |
| `page/supervisor/realtime.js` | Authenticated real-time adapter, refresh on events/reconnect, honest disconnected state. |
| `page/supervisor/sample-data/` | Copies of the team's three sample sites and related fixtures, explicitly labeled as samples. |
| `page/supervisor/tests/`, `package.json`, `dev/` | Dependency-free JavaScript tests and local preview tooling. |
| `page/supervisor/README.md` | Frontend-specific configuration, ownership, and deployment handoff. |
| `tests/test_hazard_reports.py` | Report/service/transaction/role tests using disposable SQLite fixtures. |
| `tests/test_hazard_auth_photos.py` | Signed-token verification and private-photo tests. |
| `tests/test_hazard_registration.py` | Registration guards and report-photo attachment checks. |
| `tests/test_hazard_sql.py` | PostgreSQL grammar and SQLAlchemy PostgreSQL query compilation checks. |
| `docs/aryan_implementation.md` | This handoff and setup guide. |

## 2. How the backend works

1. The phone logs in through Auth0 and obtains an **API access token**.
2. Optionally, it sends multipart field `file` to POST `/photos`. The API
   validates the actual image, saves it privately, and returns `photo_key`.
3. The phone sends report JSON to POST `/reports`, including that key if used.
4. Pydantic rejects unknown fields, invalid enums, blank text, bad coordinates,
   and unsafe photo-key characters. The client cannot supply `reporter_id`,
   IDs, status, timestamps, or resolution identity.
5. The API obtains the identity from the verified token, checks the role and
   site, and verifies that any photo was uploaded by this same identity.
6. The service inserts the report. For high severity, Alan's warning adapter
   inserts a matching warning in the **same database transaction**.
7. The route commits. Only then does it publish the contract's ID-only events.
8. Screens refetch authorized API data. Reports do not alter the ML score.

GET `/reports?site_id=6045` returns all reports for one valid site, newest first.
PATCH `/reports/{id}` accepts only `{"status":"resolved"}` and requires the
supervisor role. It sets `resolved_by` from the token and a UTC time, and clears
the matching high-report warning in the same transaction. Repeating a resolve
returns the existing result without sending duplicate change events.

The service layer does not prove authentication itself. Internal callers must
supply an already verified subject and enforce role checks before calling it.

### Direct service imports

```python
from api.schemas.hazard_report import HazardReportCreate
from api.services.hazard_report_service import save_report, get_site_reports, resolve_report

# Inside trusted backend code, with the existing synchronous SQLAlchemy Session:
body = HazardReportCreate(
    site_id=6045, hazard_type="wildlife", severity="medium",
    description="Animal near the east gate",
)
change = save_report(db, body, reporter_id=verified_principal.sub)
db.commit()  # rollback on failure; publish only after this succeeds
stored_report = change.report
reports = get_site_reports(db, 6045)
```

This example has no photo and is not high severity. If either is present,
supply the real `verify_photo` and `start_warning` adapters. Do not replace
them with functions that always approve or merely invent an alert ID.
`save_report()` returns a `ReportChange`; the HTTP response is its `.report`.

## 3. Install and database setup

From the repository root, in the team's virtual environment:

```sh
python -m pip install -r api/requirements-hazard.txt
```

The added packages provide SQLAlchemy/PostgreSQL support, JWT verification,
multipart uploads, and actual image decoding. No Gemini SDK changes are needed;
the existing root requirements already include it. Do not put credentials in
the requirements files.

Sid must confirm the database URL, PostgreSQL driver, `public` schema, and the
integer `public.sites(site_id)` primary key before applying
`db/hazard_report.sql`. This is a **one-time CREATE migration**, not an ALTER
migration or a repeatable seed script. If `hazard_reports` already exists,
inspect its schema and agree on a migration; do not drop it or run this blindly.
Sid owns creating the engine and request-scoped synchronous `Session` dependency.
This implementation has not executed SQL against the team's database.

## 4. Alan: register the new routes

First remove/replace the existing sample `GET /reports` in `api/main.py`.
Otherwise it could shadow the protected route. The registration function
deliberately refuses duplicate report/photo routes. Shared `main.py` was left
untouched for Alan to review this change.

Use this call in the **existing** application after its dependencies exist:

```python
from api.hazard_reporting import register_hazard_reporting

# These four names are integration dependencies supplied by Alan/Sid, not
# modules invented by this implementation. See their signatures below.
private_photos = register_hazard_reporting(
    app,
    get_db=get_db,
    start_warning=start_report_warning,
    clear_warning=clear_report_warning,
    publish_event=publish_event,
    photo_directory=private_photo_directory,
)
```

Required adapters:

```python
# get_db(): yield one existing sqlalchemy.orm.Session; close it afterward.
# It must not keep an outer transaction open while these routes call commit.
# An AsyncSession is NOT interchangeable with this synchronous interface.

# start_report_warning(db, report) -> alert_id
# Insert level="warning", report.site_id, report.hazard_type; record
# report.id in alerts.trigger so resolution finds precisely this warning.

# clear_report_warning(db, report) -> alert_id
# End that report's warning. Never clear a lightning or another report's alert.

# Both warning writers use the passed db, return a real alert ID, and never
# commit, open another connection, or publish independently.

# publish_event(event_name: str, payload: dict) -> None
# Synchronous delivery or durable enqueueing to Alan's DeepSpace adapter.
# Do not pass an async function directly to this synchronous interface.
```

A missing/broken high-warning adapter fails the report operation; it must not
silently save a high report without the warning. If the database commits but
event delivery fails, the HTTP write still succeeds, and a sanitized log notes
the delivery failure. This avoids inviting duplicate reports. There is no
durable outbox in this contribution: Alan must add durable retry/enqueueing if
required. The dashboard also polls and refetches on reconnect.

The report API is not idempotent for duplicate **create** requests. After an
ambiguous network failure, refresh reports before asking a user to resubmit.

For other Alan-owned endpoints, reuse `create_auth_dependency(Auth0Config.from_env())`
and `require_roles(principal, "crew", "supervisor")` from `api.auth.hazard_auth`.
The existing sample sites/alerts/briefings endpoints were not secretly changed
or secured by registering the report router.

## 5. Auth0 configuration

Server environment (actual tenant values supplied by the team):

```text
AUTH0_DOMAIN=YOUR_TENANT.auth0.com
AUTH0_AUDIENCE=YOUR_CUSTOM_API_IDENTIFIER
AUTH0_ROLES_CLAIM=https://planit-control/roles
```

Alternatively use `AUTH0_ISSUER=https://YOUR_TENANT.auth0.com/`; the exact issuer
must include its trailing slash. Tokens are checked against the tenant's JWKS,
RS256, audience, issuer, expiry, and subject. Missing configuration fails
closed, never as a demo login. Role names are exactly `crew` and `supervisor`.

Configure the roles claim in both the API **access token** (server enforcement)
and the browser ID token (UI controls). An example Auth0 post-login Action for
the team to review/configure is:

```javascript
exports.onExecutePostLogin = async (event, api) => {
  const claim = 'https://planit-control/roles';
  const roles = event.authorization?.roles || [];
  api.accessToken.setCustomClaim(claim, roles);
  api.idToken.setCustomClaim(claim, roles);
};
```

Assign users the actual roles in Auth0. Agree on the namespaced claim with
Isaiah/Alan and use the same value everywhere. A namespace under the team's
controlled domain is preferable; changing it is configuration, not a new API
field. The browser never receives a client secret. Do not trust a role from a
URL, local storage, submitted JSON, or an unverified token. See Auth0's official
[access-token validation](https://auth0.com/docs/secure/tokens/access-tokens/validate-access-tokens)
and [custom-claims guidance](https://auth0.com/docs/secure/tokens/json-web-tokens/create-custom-claims).

## 6. Private-photo operation

Set `private_photo_directory` to a dedicated **persistent private directory**
outside all frontend/static/document roots. Do not serve the entire repository
in production. Never add a StaticFiles mount or public web-server alias for
this directory. Use one shared persistent volume if there are several API
workers/instances, and back up image files and metadata together.

Each upload creates a random URL-safe key, a private `.bin` image, and a private
`.json` metadata sidecar containing its uploader, media type, size, and checksum.
Directories use mode 700 and files 600. Image filenames from the client are
not used. JPEG/PNG decoding, 5 MiB byte limit, 20-megapixel limit, maximum
10,000-pixel side, and single-frame checks reject unsafe/unsupported input.
HEIC is not accepted. Images are stored as submitted; EXIF metadata is not
stripped, so do not claim anonymization.

Before report attachment, only its uploader may preview a photo. After it is
referenced by a report, either authenticated role can view it, matching the
contract's all-site report access. Only the uploader can attach their key to
a new report. Upload carries no site ID; the report row establishes that link.
Keys are references, not credentials or public URLs.

Set a reverse-proxy request-body limit (about 6 MiB to allow multipart overhead)
and suitable rate limits. The endpoint bounds its byte read, but multipart
parsing may spool incoming data before the route executes. Unattached uploads
are not automatically deleted; agree on a retention/cleanup policy before
production, without removing files still referenced by reports.

## 7. Supervisor dashboard and shared design system

Start with `page/supervisor/config.js` in `mode: 'sample'`. This is a deliberately
read-only preview using three fixtures, not the final 60-site dataset. It does
not simulate a successful report resolution, upload, login, or live connection.
The map uses the already vendored Leaflet files under `page/crew/crew-vendor/`.
Map tiles require internet access; the ranked list and details still matter
when a basemap is unavailable. Deploy `page/shared/` and the vendored assets
with both frontend folders, not only the API.

For a simple local preview, serve only the public `page/` directory:

```sh
python -m http.server 4176 --bind 127.0.0.1 --directory page
```

Open `http://127.0.0.1:4176/supervisor/index.html`. Use this exact callback URL
in Auth0 if testing live mode with this server. Do not substitute `localhost`
or bind to `0.0.0.0`.

For live mode, change the public config to `mode: 'live'`, set `apiBase` to
`http://127.0.0.1:8000` locally (HTTPS after deployment), and enter Auth0
`domain`, SPA `clientId`, `audience`, and the agreed `rolesClaim`. Configure
Auth0 allowed callback/logout URLs and web origins for the exact origin/path
being used. Alan must allow the frontend origin plus Authorization/Content-Type
and GET/POST/PATCH in API CORS configuration. Review the official
[FastAPI CORS guide](https://fastapi.tiangolo.com/tutorial/cors/).

When the shared API is wired, its local command is:

```sh
uvicorn api.main:app --host 127.0.0.1 --port 8000
```

The dashboard ranks supplied site scores, shows the leading contributions next
to each score, and renders the selected site's full baseline + signed-factor
waterfall. It checks reconciliation within 0.05. It never fabricates missing
data as zero or lets a timer authorize resuming work. High-report warnings and
live lightning alerts stay separate from the forecast score. Stale timestamps
and sample status remain visible.

Alan's real-time bridge must expose the same interface Isaiah documented:

```javascript
window.PlanITCrewRealtime.subscribe({
  site_id: null,      // authorized all-site supervisor subscription
  accessToken,
  onEvent,           // {type: 'report.created', site_id, report_id, created_at}
  onConnection,      // true only when actually subscribed; false on disconnect
  onError
});                  // returns an unsubscribe function (or a promise of one)
```

Pass normalized event objects, not private report/photo contents. No imaginary
`/events` API endpoint was introduced. Until the bridge exists, the dashboard
shows real-time unavailable and uses periodic API refresh. Events/reconnects
refresh the ranked list and selected detail/reports. Alan must make `/sites`
return current `open_report_count` and active alerts after report writes.

Isaiah can import `../shared/planit.css` before his screen-specific CSS and
adopt its tokens/components deliberately. His crew files were not restyled.

## 8. Gemini compatibility

These schemas emit ordinary JSON, and reports remain in SQLAlchemy/PostgreSQL.
No Gemini model identifier is hard-coded here and no separate Gemini client is
created. Alan can later read authorized image bytes internally with
`private_photos.read(photo_key)` for photo tagging after enforcing access.
That low-level method is not an authorization boundary by itself.

Do not expose private files publicly to make them reachable by Gemini. Decide
with the team which photographs may be sent to an external model. Treat report
text and image text as untrusted input, not instructions. Gemini's `/ask` must
use Sid's read-only DB user and an approved view that omits reporter IDs/private
photo keys unless genuinely needed. Report tags must not become unverified
model scores or silently change the contract's hazard enum.

## 9. Testing and integration checklist

From the repository root:

```sh
python -m pip install -r api/requirements-hazard-dev.txt
python -m unittest discover -s tests -v
node --test page/supervisor/tests/*.test.mjs
```

Automated tests use fake identities or locally signed test JWTs, temporary
photo directories, and disposable SQLite data. SQL tests parse PostgreSQL DDL
and compile PostgreSQL queries, but do not prove behavior on a running
PostgreSQL/Tiger Data instance. No live Auth0 tenant, DeepSpace, Gemini, or
production database was contacted by these tests.

After Sid/Alan configure the real integrations, run this acceptance pass:

1. Confirm the five protected report/photo operations appear once in `/docs`.
2. Without a token, verify 401. With a valid token but no role, verify 403.
3. Upload an actual JPEG/PNG as `file`; copy the returned key. Reject HEIC,
   arbitrary text renamed `.jpg`, and files over 5 MiB.
4. Create a medium report for an existing site with that key. Verify status
   201, a UUID, backend identity/time, and GET `/reports` returns it.
5. Confirm another uploader cannot attach that key; both roles can view the
   photo after the report is stored. Confirm there is no public photo URL.
6. Create a high report. Check the warning and report commit together, and the
   map's report count changes without altering the score.
7. Crew PATCH must return 403. Supervisor PATCH must resolve the report and
   end only its associated warning. Retry should not emit another change.
8. Verify DeepSpace's events cause list and selected-detail refresh. Disconnect
   it, verify the disconnected indicator, reconnect, and verify a fresh fetch.
9. Check no-data, stale-score, explanation mismatch, failed API, mobile layout,
   keyboard focus, login/logout, every link, and exact deployed path/slashes.

### Still requires teammate configuration

- **Sid:** real sites, report migration review/application, SQLAlchemy session,
  alerts-table shape, DB privileges, read-only Gemini view, and real scores.
- **Alan + Aryan:** register routes, remove sample report route, connect warning
  writers and event publisher, Auth0 tenant roles/claim, CORS, private persistent
  photo volume, request limits, other-route authorization, and deployment.
- **Alan:** actual DeepSpace browser bridge and event retry strategy; live
  `/sites` aggregation; optional future Gemini photo tagging.
- **Isaiah + Aryan:** agreed design tokens, `file` multipart field, exact Auth0
  settings, and phone-to-map acceptance testing. Do not overwrite crew screens.

The new modules are implemented and locally testable. The complete live system
is not ready until these shared dependencies are connected and tested together.

### Verified in this checkout

- 53 backend tests passed with Python 3.13, FastAPI 0.143.3, Pydantic 2.14.1,
  and SQLAlchemy 2.1.5 in an isolated virtual environment.
- 16 JavaScript tests passed, including Auth0 browser configuration and the loopback-only preview server's
  direct path, trailing-slash redirects, and required static assets.
- Browser preview verified search, selecting a different site, empty filters,
  positive/negative score contributions, and disabled sample write controls.
  At 390px and 1440px viewport widths, the document had no horizontal overflow.
  No browser console errors were observed during those interactions.
- PostgreSQL SQL parsed and queries compiled. Live PostgreSQL transactions,
  concurrency, Auth0 tenant login, DeepSpace delivery, and Gemini were **not**
  exercised. Those require the team's real configuration and acceptance pass.
- The current Starlette test client emits a non-failing httpx deprecation
  warning. Failure-path tests also intentionally produce sanitized error logs.

Changes to the original three files include URL-safe photo-key validation,
positive SQL site IDs, complete (not silently truncated) site-report retrieval,
private-photo attachment lookup, and guards against accidentally passing async
warning callbacks to synchronous database operations. The added routes enforce
the contract roles, wrap errors, and publish only after commit. The registration
guard also handles FastAPI versions that store included routers lazily.
