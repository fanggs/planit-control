# db/

Tiger Data (PostgreSQL + time-series) schema and migrations. Run commands from
the repository root.

## Setup

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
on October 17, 2026, using PostgreSQL 18.6 and TimescaleDB 2.30.2. Hypertable
conversion and restricted Gemini login setup remain pending.

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
This first migration uses ordinary PostgreSQL tables; it does **not** enable
extensions or convert tables into hypertables. Confirm the installed Tiger Data
version and privileges before that separate setup. Do not assume hypertables
exist merely because the database is hosted on Tiger Data.

`validation.py` checks external-row provenance, timezone-aware timestamps,
nonempty loads, required columns, and finite, reconciled score explanations.
Loaders must invoke it before writing and run source-specific checks afterward.
Optional missing measurements remain null. SQL adds keys, foreign keys, ranges,
and timestamp constraints. Score-factor reconciliation currently happens in
Python, so every future score writer must call `validate_score`.

The restricted Gemini login is a later database setup step, pending database
access and Alan's approved table/view allowlist. Do not grant it all tables:
crew reports contain identity and private photo references. No login or cloud
privilege changes happen in this interval.
