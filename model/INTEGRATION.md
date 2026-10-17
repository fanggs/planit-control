# Interval 7: integration and handoff

Contract v1.2 now adopts the screening response and separate wildlife context.
Migration 003, the fresh 60-site database load and restricted login have been
verified for issue 11. See [the operations handoff](handoffs/ISSUE-11-OPERATIONS.md)
for the exact collector command and setup results. The guide below preserves
the interval 7 replay checks; Alan's deployed integration remains separate.

## Verify the complete local path

From the repository root, with the data/model dependencies installed:

```sh
.venv/bin/python -m model.verify_integration
```

This command uses the most recent complete local screening run. It does not
download, train or write to the database. It checks all 60 unique plant IDs,
original forecast checksums, rebuilt features, model/report identity, exact
prediction replay, explanation reconciliation, wildlife context, research
display opt-in and stale-score suppression. It evaluates saved predictions at
their original scoring times; it does not present an old replay as live data.
The small result is saved in `model/generated/integration-verification.json`.

For a specific saved run:

```sh
.venv/bin/python -m model.verify_integration --run-directory data/raw/runtime/runs/YOUR_RUN
```

Raw runtime files are ignored by Git. On another machine without a complete
run, first collect one using the following command, then run the verifier:

```sh
.venv/bin/python -m get_data.monitor --screen-only --allow-research
```

That collection accesses public forecasts. The replay command itself is offline.
Neither command requires Gemini, an API key, or the shared database. Dependencies
and the longer operating guide are documented in `CORRECTIONS.md`.

## Alan: use your existing database adapter

`db.screening_read.site_screening` accepts the existing `api.db.query` callable.
It uses parameterized named arguments, so there is no need to unwrap the
SQLAlchemy connection or create a competing engine:

```python
from api import db
from db.screening_read import site_screening
from get_data.site_context import for_site

# In your owned API code, only after agreeing on the proposed response fields:
screening = site_screening(db.query, site_id, allow_research=True)
wildlife_context = for_site(site_id)
```

The explicit opt-in above is for a clearly labeled prototype display. Omitting
it returns `research_unapproved` with a null score for the current artifact.
The helper does not overwrite the legacy score field. Keep it as a proposed
separate `screening` response until the shared contract is updated by agreement.

Available predictions include `score`, `baseline`, signed feature `factors`,
research/prototype `status`, exact `target`, input/scoring/target times,
`snapshot_id`, `artifact_sha256` and `clears_stop_work: false`.
Unavailable responses contain null score/baseline, empty factors, status and
reason. Statuses distinguish missing, stale, invalid and unapproved research
data. Zero is a real numerical output, never a missing-data replacement.

Connection/query errors propagate to the API owner, who should return a service
error rather than turn an outage into a misleading no-data response. The query
uses the existing request/application database configuration. It never prints
credentials. Snapshot and prediction site IDs must agree.

Wildlife remains dated public evidence with sample/radius/uncertainty limits.
It does not receive an invented encounter probability. Neither this layer nor
the trained index clears lightning, flood, crew-report or other safety alerts.

## Worker status and deployment

`get_data.monitor` can perform one poll or repeat hourly. Its status explicitly
separates `database_loaded` (screening transaction) from
`weather_database_loaded` (native weather/evidence transaction). A later failure
retains the earlier transaction's actual committed status. A previous run's
success is cleared before a new poll starts. Do not interpret a partially
completed poll as one atomic transaction across both independent collections.

Alan owns installation in `jobs/` or the deployed process manager. This interval
does not start a background server, mutate cloud state or enable research scores
in the deployed application. See `CORRECTIONS.md` for the worker options.

## Checks and remaining release work

Local tests:

The owned-code suites pass **98 tests** (29 database, 52 data and 17 model).
The separate shared API suite could not import in this data/ML environment:
API dependencies including FastAPI, SQLAlchemy, PyJWT, google-genai and netCDF4
are not installed here. This is not a passing API-suite result. Run that suite
in the backend environment using its existing requirements before deployment.

```sh
.venv/bin/python -m unittest discover -s db/tests -q
.venv/bin/python -m unittest discover -s get_data/tests -q
.venv/bin/python -m unittest discover -s model/tests -q
```

The offline replay is evidence for the local source-to-response path. It does
not prove a real database write, an HTTP request, Auth0 authorization or a
deployed scheduler. Those checks remain explicit:

1. Sid applies migration 003, provisions the separate `/ask` login and verifies
   the new loaders on the shared Tiger Data service.
2. The team agrees on replacement score semantics and response fields using
   `handoffs/CONTRACT-CHANGE-PROPOSAL.md` before Alan changes the shared contract.
3. Alan wires the helper into his owned routes/jobs, handles service failures,
   and deploys the recurring worker and separate restricted query connection.
4. The team verifies actual browser/API responses, database persistence, stale
   displays and independent stop-work alerts against the deployed service.
5. Model improvements use fresh evaluation evidence. The current failed
   probability-error requirement is not removed or relabeled by integration.

Latest repository sync: Alan reports the shared database is already in use by
the deployed API. Issue #2 remains open for restricted `/ask` access; the
referenced follow-up #8 is paused. This guide does not claim those issues closed
or that teammate deployment statements were independently tested here.
