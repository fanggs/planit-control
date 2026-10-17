# Hazard reporting: Aryan's backend and supervisor handoff

This follows `api/CONTRACT.md` v1.1. A crew member uploads a private photo (if
there is one), submits a report with its returned `photo_key`, and a supervisor
can later resolve the report. **DeepSpace carries ID-only real-time notices;
it does not store photographs.** Reports do not change Sid's model score.

## Which file does what

| File | Responsibility |
| --- | --- |
| `api/schemas/hazard_report.py` | Pydantic 2 request/response validation: positive EIA site ID, seven agreed hazard types, severity, trimmed description, paired coordinates, opaque photo key, and `open`/`resolved` response state. Client JSON cannot set identity, timestamps, report ID, or status. |
| `api/services/hazard_report_service.py` | SQLAlchemy save, per-site list, resolution, and attached-photo checks using the session supplied by the API. Reporter/resolver IDs come only from a verified Auth0 subject. |
| `db/hazard_report.sql` | PostgreSQL table, constraints, site foreign key, and per-site newest-first index. Apply only to the agreed development database after Sid's foundation migration. |
| `api/services/hazard_photo_service.py` | Validates a real JPEG/PNG (5 MB maximum), writes the bytes and metadata in an owner-only private directory, and verifies upload ownership before a key is attached to a report. |
| `api/routes/hazard_photos.py` | Authenticated `POST /photos` and `GET /photos/{photo_key}`. Only the uploader can view an unattached upload; after attachment, crew and supervisors may view it through the API. |
| `api/routes/hazard_reports.py` | Authenticated `GET /reports?site_id=...`, `POST /reports`, and supervisor-only `PATCH /reports/{id}`. Commits the report and any high-severity warning together, then attempts ID-only notices after commit. |
| `api/services/hazard_photo_cleanup.py` | Dry-run helper for identifying old uploads with no report. Removal needs an explicit stopped-API assertion; do not run it against live storage during a demo. |
| `page/supervisor/` | Authenticated risk map and report/history panel. Open reports get map pins; resolved reports stay in history. Photos are fetched with a bearer token and held only in memory while the selected site is open. |

`api/main.py` already registers Aryan's report/photo routers with `api/db.py`'s
request-scoped session when `DATABASE_URL` and Auth0 settings are configured.
There is no second FastAPI application or separate report database connection.
In explicit sample mode, report writes and photo routes are intentionally absent.

## The browser/API sequence

1. The signed-in crew or supervisor page calls `POST /photos` with one multipart
   field named `file`. The API returns a random `photo_key`. Skip this step when
   there is no photo. The key is not a URL or an authorization credential.
2. The page calls `POST /reports` with `site_id`, `hazard_type`, `severity`,
   `description`, optional paired `latitude`/`longitude`, and optional
   `photo_key`. The API verifies the token role and photo uploader, writes the
   report, and returns the complete saved row. A high-severity open report also
   creates a warning alert in the same transaction.
3. The API attempts `report.created` (and, for a high-severity warning,
   `alert.started`) through DeepSpace **after** the database commit. Screens
   receive only IDs and refetch the protected API; the notice contains no photo
   bytes, reporter identity, or report text.
4. The supervisor dashboard reads `/sites`, `/sites/{site_id}` and
   `/reports?site_id=...`. `GET /photos/{photo_key}` requires an access token;
   neither the photo key nor bearer token is placed in a public `<img>` URL.
5. A supervisor sends `PATCH /reports/{id}` with `{"status":"resolved"}`.
   The API records `resolved_at` and `resolved_by`, clears the report warning,
   and attempts `report.resolved`/`alert.cleared` notices after commit. Retrying
   an already-resolved report does not publish a second resolution event.

## FastAPI imports for Alan

The integration is already in `api/main.py`. If it is moved, keep one router
registration point and pass the existing app, session dependency, warning
writers, and synchronous publisher:

```python
from api.hazard_reporting import register_hazard_reporting
from api import db
from api.realtime import publish
from api.services.hazard_warning_service import start_report_warning, clear_report_warning

register_hazard_reporting(
    app,
    get_db=db.get_db,
    start_warning=start_report_warning,
    clear_warning=clear_report_warning,
    publish_event=publish,
    photo_directory=private_photo_directory,
    auth_config=auth0_config,
)
```

For other backend code, import `save_report`, `get_site_reports`, and
`resolve_report` from `api.services.hazard_report_service`. Pass the existing
SQLAlchemy `Session` and a reporter/resolver ID taken from the validated Auth0
principal. Route code owns commit/rollback; the service does not create a new
engine or commit independently.

## Verify locally and across devices

1. Run the API on `127.0.0.1:8010` with the Git-ignored `.env` configured.
   `GET /health` should say `data: database` and report the expected site count.
   Requests to `/sites` without a token should return 401.
2. Run the frontend preview on `127.0.0.1:4174`, **not** PyCharm's
   `localhost:63342` HTML preview. The Auth0 SPA must allow the exact callback
   and web origin actually shown in the browser address bar.
3. Sign in with an assigned crew account. Upload a small JPEG/PNG, submit a
   high-severity report, and confirm the response has a server-owned reporter
   and `open` status. Refresh `/reports?site_id=...`; confirm the row persists.
   Confirm the same photo cannot be fetched without an authorized token.
4. Sign in with a supervisor account and confirm the new open-report pin,
   warning, and private photo. Resolve the report; confirm the pin disappears,
   the historical card remains, and the warning clears. Crew must receive 403
   if it attempts resolution. Also verify a report without coordinates remains
   in the list but does not create a pin.
5. Repeat on a second device only after Alan provides a reachable HTTPS API and
   frontend. `127.0.0.1` on a phone or Alan's computer refers to **that** device,
   not Aryan's Mac. Isaiah must switch `page/crew/crew-config.js` from `mock`
   to `live` and supply the authorized API base URL first. A successful local
   test does not prove cross-device delivery or Sid's score calculations.

Offline checks, without using production tokens or deleting real data:

Install the repository requirements in your project environment first (see
`README.md`), then run:

```sh
python -m unittest discover -s tests -p 'test_hazard*.py'
node --test page/supervisor/tests/*.test.mjs
node --test page/crew/dev/*.test.mjs
```

After confirming `.env` points to the **team development** Tiger Data service,
`python -m tests.manual_hazard_tiger_smoke --run-dev-db` checks a real
PostgreSQL save, read, and resolve inside one transaction that always rolls
back. It does not publish a DeepSpace event or leave a test report. This does
not substitute for an actual Auth0/browser test.

## Private storage and old unattached uploads

On a server, set `PLANIT_PRIVATE_PHOTOS_DIR` to a dedicated persistent directory
outside the frontend/static root, owned by the API process with mode `0700`.
Do not expose that directory through a web server. If a photo uploads but the
report never saves, the photo can remain unattached. The cleanup helper returns
only uploads at least 24 hours old that are not referenced by any report;
its default is **dry-run**. Removal is opt-in and must wait until all report and
photo API workers are stopped, so no in-flight report can attach a key during
cleanup. It uses the existing database session and never deletes report rows.
For an operator's read-only dry run:

```python
import os
from sqlalchemy.orm import Session
from api import db
from api.services.hazard_photo_cleanup import clean_old_unattached_photos
from api.services.hazard_photo_service import PrivatePhotoStore

store = PrivatePhotoStore(os.environ["PLANIT_PRIVATE_PHOTOS_DIR"])
with Session(db.engine()) as session:  # The app's existing engine, not a new one.
    candidates = clean_old_unattached_photos(store, session)
    print(f"{len(candidates)} old unattached photo uploads")
```

Coordinate the storage location and any maintenance window with Alan before
deployment; no cleanup has been run on the team database or real photo directory.
