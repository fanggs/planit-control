# Issue 11: verified database setup and collector handoff

Verified on the shared Tiger Data service on October 17, 2026:

- Migration 003 applied through the checksum-tracked migration runner. All four
  model-evidence tables exist; migrations 001/002 and existing rows were kept.
- Fresh research predictions and their exact input snapshots were committed
  and re-read for all 60 monitored plants. Stored explanations, source/model
  identity, research status and API-read freshness checks passed.
- The dedicated `planit_ask` login was provisioned and independently connected.
  Default transactions are read-only; writes and `hazard_reports` are not granted.
- The guarded query executor returned 60 fresh scored plants through that login.
  Crew-report and statistics-view queries were rejected by the guard.

## Alan: dependencies and exact hourly command

From the repository root in the backend's active Python environment:

```sh
python -m pip install -r model/requirements.txt -r db/requirements-ask.txt
python -m get_data.monitor --load --allow-research --interval-seconds 3600
```

`model/requirements.txt` includes `get_data/requirements-forecast.txt` and the
data/database dependencies, plus NumPy, SciPy and scikit-learn imported by the
portable model module. Installing only the forecast requirements is insufficient
for the current worker. Keep the existing API dependencies too.

The service environment must supply `DATABASE_URL` and `PGPASSWORD`. The collector
does not automatically load `.env`; configure the process manager's secret
environment rather than relying on a different terminal's variables. Do not
paste secret values into a service command, GitHub comment or shell history.

`--allow-research` is required for the current artifact. It permits writing
explicitly research-labeled predictions; it does not promote the model. The API
and screens must show the contract's Prototype label. Without that flag, the
current model's predictions are rejected. The command includes native IFS
weather/evidence collection as well as GFS scoring; `--screen-only` would omit
native weather collection and is not the full hourly service command.

One full poll runs, then the process waits 3600 seconds before the next poll.
The process remains in the foreground for Alan's service manager to supervise.
Use one active collector for this service. Check `data/raw/runtime/latest.json`:
`status`, `predicted_sites`, `database_loaded` and `weather_database_loaded`
describe the actual collection and separate committed phases. The API suppresses
scores when input age exceeds two hours or the target window has expired.

## Restricted /ask configuration

Sid holds the login details in a local private file and will transfer them
through a private channel. No connection URI or password is included here.
Configure both secrets in the API environment:

```text
PLANIT_ASK_DATABASE_URL
PLANIT_ASK_PASSWORD
```

Use `db.ask_query.connect()` and `db.ask_query.execute()`; never use the API's
write/owner connection for generated SQL. Approved application tables are
`sites`, `weather_readings`, `weather_forecasts`, legacy `hazard_scores`,
`alerts`, `environmental_events` and `screening_predictions`. The new screening
table is the source of current scores; the legacy score table is unused.
Filter current score questions to recent records and retain their research
status. Do not infer safety or injury probability from a low value.

Tiger's two pg_stat_statements extension views have inherited PUBLIC SELECT,
like readable system metadata. Provisioning recognizes only those verified
extension views as metadata and does not revoke other teammates' diagnostics.
The generated-query guard rejects them. Other unapproved application-table
SELECT privileges, writes and inherited roles still fail provisioning.

## Remaining work owned by Alan

Wire `site_screening` and wildlife context into the API under contract v1.2,
configure the private login, and install/run the collector service. Sid verified
the database and collector import/options, not Alan's deployed service startup.
The local setup does not change deployed configuration automatically.
