Migration 003 is applied on the shared service. All four model-evidence tables
exist, and fresh research predictions for all 60 monitored plants were committed
and re-read with exact explanation and identity checks. The API read adapter's
freshness checks pass for those stored rows.

The dedicated `planit_ask` login is created and independently verified: read-only
transactions, SELECT on the seven approved application tables (including
`screening_predictions`), no application writes and no `hazard_reports` access.
The guarded query executor confirmed 60 fresh scored plants through this login.
The credentials are held locally for private transfer, not included here.

Alan, the exact server setup is:

```sh
python -m pip install -r model/requirements.txt -r db/requirements-ask.txt
python -m get_data.monitor --load --allow-research --interval-seconds 3600
```

Supply `DATABASE_URL` and `PGPASSWORD` through the service's secret environment;
the collector does not automatically read `.env`. The API's separate restricted
connection uses `PLANIT_ASK_DATABASE_URL` and `PLANIT_ASK_PASSWORD`. Full model
requirements are needed because the worker imports NumPy/SciPy/scikit-learn;
forecast requirements alone are insufficient. `--allow-research` is necessary
for this artifact and retains the research status and required Prototype label.

`model/handoffs/ISSUE-11-OPERATIONS.md` records the checks and deployment details.
All 98 data/database/model tests pass, and installed dependencies are consistent.
The provisioning check now recognizes the provider-installed statistics views
as system metadata; generated queries still cannot access them. No shared
diagnostic grants or existing application data were removed.

Database setup is ready for the API wiring in #9. Running the collector as a
deployed service remains Alan's step; it has not been started by this setup.
