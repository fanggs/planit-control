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
python -m db.migrate
python -m unittest discover -s db/tests -v
```

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
