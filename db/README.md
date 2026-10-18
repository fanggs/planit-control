# db/

Latest update: migration 004 adds the ordinary transactional score-notification outbox and is verified on the shared service. The restricted `/ask` login has no access to it. See [verification and deployment instructions](../model/handoffs/ISSUES-14-22-IMPLEMENTATION.md).

Tiger Data (PostgreSQL + time-series) schema and migrations. Run commands from
the repository root.

## Setup

For local PostgreSQL/PL/pgSQL parser tests, install `db/requirements-dev.txt`.
These syntax tests do not claim that a migration has executed on a real service.

Install `db/requirements.txt` inside the project's virtual environment. Configure
`DATABASE_URL` through your local environment or secret manager; the runner does
not load `.env` automatically. Never put the connection string in source control
or paste it into a terminal command that will be saved in history.

```sh
python -m db.migrate --list
python -m db.migrate --check
python -m db.migrate
python -m unittest discover -s db/tests -v
```

`--check` connects with a 15-second timeout and reads PostgreSQL/TimescaleDB
versions and the number of public tables inside a read-only transaction. It
does not run migrations. Failure messages identify common login, URI, network,
SSL and schema errors without echoing driver text or connection secrets.
If a copied URI omits its password, run `python -m db.migrate --check
--prompt-password` in an interactive terminal. Enter the database password saved
when the service was created. Hidden input is supplied directly to the driver,
overriding URI/environment password settings; it is not printed or saved.
Use the same `--prompt-password` flag without `--check` to apply migrations
when the connection URI omits the password.

Sid confirmed a successful foundation migration and verified site/weather loads
on October 17, 2026, using PostgreSQL 18.6 and TimescaleDB 2.30.2. Sid also
reported applying migration 002. Migration 003 and the restricted Gemini login
were subsequently applied and independently verified on the shared service for
issue 11. See `generated/issue11-verification.json` and
`../model/handoffs/ISSUE-11-OPERATIONS.md` for the verified setup and worker flags.

The runner records SHA-256 checksums, skips already applied migrations, rejects
edited applied files, serializes migration processes with a database lock, and
applies each file in a transaction. Add a new numbered migration for later
changes. Run against an empty development database first. It deliberately fails
if conflicting existing tables exist; inspect them rather than replacing data.

`001_foundation.sql` creates Sid's nine contract tables. Next, Aryan's separately
owned `db/hazard_report.sql` can be applied once by its owner: it depends on
`sites`. It is not included in this migration runner. Event IDs are text because
external providers use string identifiers; a single event can cover many sites,
so its key is `(id, site_id)`. Forecast uniqueness includes the issue time to
preserve successive forecast runs instead of overwriting history.

Time-series primary keys include their time column to support TimescaleDB.
`001_foundation.sql` creates ordinary PostgreSQL tables. `002_hypertables.sql`
then converts readings, forecasts, strikes and scores using their existing time
columns, without changing `001` or removing its populated rows. Sites and the
other tables stay ordinary tables. TimescaleDB must already be installed; this
migration does not install extensions or alter cloud privileges.

## Apply the hypertable conversion

In the same Mac terminal with `DATABASE_URL` configured:

```sh
.venv/bin/python -m db.migrate --prompt-password
```

Enter the database password in the hidden prompt. The runner skips the already
applied foundation and should print `Applied 002_hypertables.sql`. The conversion
uses the [generalized TimescaleDB API](https://www.tigerdata.com/docs/reference/timescaledb/hypertables/create_hypertable),
requires version 2.13+, and was prepared for Sid's reported 2.30.2 service.
It migrates existing rows, uses seven-day chunks, takes the referenced-table
lock first, and checks that all four expected time dimensions exist before
committing. Lock acquisition is bounded to 15 seconds and execution to five
minutes. Pause concurrent loaders while applying it; a failed conversion rolls
back that migration and leaves its migration marker unapplied. The runner will
retry it next time. SQL and PL/pgSQL syntax were checked locally; real-service
execution still needs confirmation.

`db/history_store.py` loads only GBIF observations and historical NOAA events,
with parameterized upserts and post-load field comparisons. Large experimental
weather matrices stay in the local historical dataset, separate from live feeds.

`validation.py` checks external-row provenance, timezone-aware timestamps,
nonempty loads, required columns, and finite, reconciled score explanations.
Loaders must invoke it before writing and run source-specific checks afterward.
Optional missing measurements remain null. SQL adds keys, foreign keys, ranges,
and timestamp constraints. Score-factor reconciliation currently happens in
Python, so every future score writer must call `validate_score`.

The restricted Gemini login setup is implemented in `access.py`; it must be
applied from an interactive terminal with the owner's connection configured.
Its seven-table application allowlist excludes crew identities and photo references. Alan can
use `ask_query.py` to validate generated SELECT queries and execute them through
the separate restricted login. Neither module silently uses the application's
write account. See [the correction guide](../model/CORRECTIONS.md) for setup.

Migration `003_model_evidence.sql` adds private model snapshots, model artifacts,
screening predictions and original weather payloads. It preserves humidity,
gust and soil arrays with their original units and evidence. It does not alter
the team's current score contract. The loaders compare stored values inside
transactions and raise on a mismatch; real-service execution remains a distinct
integration check.
