# Forecast-based hazard screening: correction guide

This bundle replaces the experimental method used in interval 5. Contract v1.2
now adopts it; [issue 11's operations handoff](handoffs/ISSUE-11-OPERATIONS.md)
records the verified database setup and exact deployment command. Read the recorded results in
`generated/forecast-v2/report.json` alongside this guide.

## What we calculate

The measurable outcome is whether an archived selected NWS warning or heat
advisory geometry covers a plant during the following 24 hours. The displayed
index is ten times the calibrated model probability of that outcome. A score
of 3 therefore means an estimated 30% probability of this specific warning
exposure outcome, subject to the recorded validation limits. It does not mean
a 30% probability of injury, an incident, lightning, or an animal encounter.

The selected warning classes cover heat, flooding, fire weather, severe
thunderstorms, tornadoes and high wind. Fire weather is not an actual fire
perimeter. Thunderstorm warnings do not establish lightning strikes. NWS
decisions, reporting coverage, revised archive records and forecast errors all
affect the target. A missing warning is not confirmed safety.

The challenge asks for wildlife sightings in the combined site picture, so
wildlife stays present as a separate, sourced context layer. GBIF presence-only
records do not supply defensible animal-absence or encounter labels. They do
not receive invented training negatives or an arbitrary numerical allocation.
Mandatory lightning and other stop-work alerts always override operational
decisions regardless of a low screening index.

## Evidence and dates

* Warning geometry archives: 2020–2025 and January–June 2026, partitioned by
  each of the 34 states containing the 60 monitored plants.
* Usable joint forecast/label study: January 2024–June 2026. The verified
  four-variable GFS previous-runs product does not provide complete matching
  inputs back to 2020. Downloaded older warning evidence is retained, without
  pretending it became additional forecast training examples.
* Forecast inputs: temperature, relative humidity, precipitation and wind from
  Open-Meteo's GFS fixed 48-hour lead product. Historical and live paths use
  the same feature builder, variable names and units.
* Four UTC cutoffs each day: 00, 06, 12 and 18. Missing required hours, null
  measurements and ambiguous warning intervals are counted and excluded.
* Every example links to checksummed source receipts. Source URLs, original
  retrieval times, site catalog hash, code hashes and output hash are retained.

Fixed lead is a composite of earlier forecast runs, not one run issued at the
cutoff. Even the final next-day endpoint was nominally predicted 24 hours before
the cutoff; actual original publication timestamps remain unverified. This
margin reduces availability risk without claiming an as-issued archive.
Antecedent rainfall features summarize previous **forecast** values for 24, 72
and 168 hours; they are not rain-gauge observations. Existing native IFS soil
moisture remains context rather than being substituted into the GFS schema.

Archive ZIPs, large forecast matrices and receipts stay under ignored
`data/raw/forecast-study/`. Keep them together for reproducibility. The small
checked-in `get_data/generated/forecast-study-verification.json` records coverage
and exclusions, not the full raw dataset. Spatially scanned warning-record counts
are not a census of all records in each state's ZIP.

## Training and honest evaluation

The fixed candidates are logistic regression, a shallow tree, a random forest
and gradient boosting. They are compared on temporal and unseen-county
validation sets. Candidate selection uses their mean average precision, which
measures whether positive outcomes rise toward the top of a ranking.

The chosen family is refitted on earlier development-county training and
temporal-validation windows. Calibration uses separate July–December 2025
outcomes. Final temporal and geographic tests use January–June 2026 and are
evaluated after selection. Shared warning episodes are purged from earlier
phases. Geographic partitions can still experience correlated regional storms.

A candidate passes only if its calibrated probabilities beat both constant
and seasonal baselines on average precision and Brier error on **both** final
partitions, with a positive calibration slope. This is an engineering acceptance
rule, not safety certification. Results are recorded even if the rule fails;
the runner does not tune against final-test outcomes or force a passing model.

Portable JSON contains numeric parameters rather than executable pickle.
Exported predictions are compared with the trained implementation on every
final-test example. Baseline plus signed factor contributions reconciles to
the displayed score. These path/reference-dependent explanations describe
model associations, not causal responsibility, individual injury risk, or SHAP.

## Reproduce the study

Run these commands in the Mac terminal inside `planit-control`:

```sh
.venv/bin/python -m pip install -r model/requirements.txt
.venv/bin/python -m pip install -r db/requirements-ask.txt
.venv/bin/python -m get_data.forecast_study
.venv/bin/python -m model.forecast_train
```

The source build resumes verified downloads and prevents competing builders.
Do not delete its cache merely to retry. A changed cached checksum fails. The
training policy and selection are written before final-test evaluation. Reruns
are reproducibility checks, not new independent evidence for tuning.

## Run the worker

```sh
# Download, validate and score all 60 plants, without database writes:
.venv/bin/python -m get_data.monitor --screen-only

# Also collect native IFS weather, and repeat hourly until stopped:
.venv/bin/python -m get_data.monitor --interval-seconds 3600
```

If evaluation fails, scoring requires the explicit `--allow-research` flag;
all such outputs retain research status. Stale or incomplete inputs, unknown
sites, changed static geography/elevation and dynamic inputs outside refit
support fail visibly. Dynamic extremes are not clipped into the trained range.
This can leave a site without a score; its alerts and context must remain
visible. The application must display unavailable/stale status, not substitute
zero. Known-site geography is checked against the complete input catalog;
that check uses no outcome labels.

One worker lock prevents duplicate local processes. Each poll saves original
source evidence, input snapshots, predictions and a status report under
`data/raw/runtime/`. The latest status is replaced on failures too. The worker
requires at least an hourly interval to bound public API traffic. It is a
long-running foreground process, not an installed deployment service; Alan can
call it from his owned scheduler or process manager.

## Tiger Data setup for this bundle

The earlier populated tables are preserved. Migration 003 adds original native
weather payloads, versioned model artifacts, input snapshots and a separate
screening prediction table. These new ordinary PostgreSQL tables do not undo
the four hypertables created by migration 002.

With the password-free `DATABASE_URL` already configured in your terminal:

```sh
.venv/bin/python -m db.migrate --prompt-password
```

The migration runner skips applied files and prompts privately for the owner
password. It should apply `003_model_evidence.sql`. To allow subsequent loaders
to authenticate without placing a password in shell history, use a hidden
terminal prompt:

```sh
read -rs 'PGPASSWORD?Database password (hidden): '; export PGPASSWORD
.venv/bin/python -m get_data.monitor --load
unset PGPASSWORD
```

These prompt commands use macOS zsh. Add `--allow-research` only for an explicit
research database smoke test if the recorded model did not pass evaluation.
No new screening batch is committed unless all 60 predictions validate. Stored
values are re-read inside the transaction; mismatches roll it back. Normalized
native IFS weather and its original humidity/gust/soil arrays are also saved in
one transaction when collection succeeds. Database credentials are not present
in this implementation's execution environment, so applying and checking these
new database objects on the team's service remains a user-terminal step.

## Restricted database access for Gemini /ask

```sh
.venv/bin/python -m db.access          # inspect the plan; no writes
.venv/bin/python -m db.access --apply # private owner/new-login prompts
```

The setup creates a managed `planit_ask` login, grants SELECT on seven approved
public tables, bounds query time, rejects inherited write/private-table access,
and independently tests its connection. It does not change the owner's password
or erase data. Keep the new login's password in the deployment's secret storage.

Alan's `/ask` integration must use `db.ask_query.connect()` and `execute()` with
separate `PLANIT_ASK_DATABASE_URL` (user `planit_ask`) and `PLANIT_ASK_PASSWORD`.
The query guard permits a bounded, allowlisted SELECT; writes, private reports,
catalog queries and unapproved functions fail before execution. Read-only role
defaults complement this guard; they do not replace SQL validation. The model
writes the query; the database produces the numbers.

## Team integration boundary

Alan's existing API adapters and `.env` support are present. This bundle does
not edit his routes, jobs, the shared contract or Aryan's report tables.
`model/handoffs/CONTRACT-CHANGE-PROPOSAL.md` contains the concrete replacement
semantics to agree before wiring the new score into the shared response.

Available adapters:

* `model.inference.current_prediction(connection, site_id)` returns the latest
  prototype score or explicit unavailable/stale state.
* `get_data.site_context.for_site(site_id)` exposes sourced wildlife context.
  Its 25 km map filter is not a biological safety radius. No records means
  no records in the downloaded sample, not confirmed animal absence.
* `db.ask_query` provides the restricted query path described above.

No data-only implementation can verify the team's future UI behavior, real
lightning access, scheduler deployment or contract approval. Those remain
explicit integration checks; fabricated substitutes are not inserted.

## Recorded correction results
Build: **212,417 eligible windows**, 60 plants, 2024–June 2026. There are
6,360 incomplete forecast windows and 103 ambiguous labels excluded. Archives
include 238 state/year warning partitions and 600 site/quarter forecasts.
The random forest was selected on validation. It improves ranking on both final
sets and beats the constant baseline on Brier error, but narrowly misses the
seasonal baseline on temporal Brier error. **The acceptance rule fails; research
status remains mandatory.** No threshold or model settings were changed after
these final outcomes were inspected.
| Final partition | Forest AP | Seasonal AP | Forest Brier | Seasonal Brier |
| --- | ---: | ---: | ---: | ---: |
| time_test | 0.2966 | 0.1507 | 0.082967 | 0.082646 |
| geo_test | 0.4143 | 0.1954 | 0.117841 | 0.128831 |

AP is higher-is-better; Brier error is lower-is-better. These are warning
exposure metrics, not worker-injury metrics. The calibration bins expose
remaining probability errors; good ranking does not remove them. The once-used
2026 final partitions must not be recycled as fresh evidence for model tuning.

Live verification: one real GFS collection scored **60/60** known plants, with
research status, complete provenance, matching input hashes, exact explanations
and no database writes. See `get_data/generated/screening-verification.json`.
All 89 local tests pass; package dependencies and all three migration SQL files
also pass local checks. This does not establish execution of migration 003 or
restricted login provisioning on the cloud service.
