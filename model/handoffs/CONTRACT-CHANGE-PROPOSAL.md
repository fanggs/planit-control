# Proposed ML index contract correction

Status: concrete proposal for team review; does not edit api/CONTRACT.md.

The supplied Sperry brief requires an ML 0–10 index and a combined site picture
that includes wildlife sightings. It does not prescribe 8/2 weights or a wildlife
classifier. Preserve the site's wildlife/report information while removing
unsupported encounter probabilities.

## Proposed score meaning

The weather/environment screening index is `10 × model-estimated probability
of exposure to one or more selected archived NWS warnings or heat advisories
covering the plant's coordinates during the next 24-hour target window`.

This describes a documented operational hazard signal. It is neither injury
probability nor a guarantee that unreported hazards are absent. Red-flag warnings
represent fire-weather conditions, not proof of a wildfire at a plant. Severe
thunderstorm/tornado warnings do not represent measured lightning strikes.

Training sources are fixed-lead GFS forecasts and IEM NWS warning geometries.
The forecast inputs are an explicitly documented composite of fixed 48-hour
lead estimates, not a single run issued at cutoff. Measured real-time lightning
continues to drive the existing independent stop-work rule.

## JSON and storage

- Replace the two-model 8/2 arithmetic with the single evaluated model output.
- Preserve 0–10, baseline, signed contributions, horizon, model version and UTC
  times. Add the exact target-window start/end, input snapshot/model hashes,
  quality/status and a human-readable target definition.
- Explanations identify **features** and their learned contributions. Do not
  claim that an individual feature is exclusively attributable to one hazard.
- Add `wildlife_context` to site details: dated, attributed sightings and source
  limitations; no unsupported numeric contribution. Keep crew reports alongside.
- An unavailable/stale/out-of-support prediction is null with a reason, not zero.
- Existing legacy `hazard_scores` remains untouched until the team approves the
  revised semantics. Corrected prototype results use `screening_predictions`.

## Ready integration points

1. `db.screening_read.site_screening(api.db.query, site_id)` uses Alan's existing
   SQLAlchemy query helper directly, with no competing connection setup. Missing,
   stale, invalid and unapproved research scores remain null. Explicit
   `allow_research=True` enables a labeled prototype response after agreement.
   The raw-psycopg `model.inference.current_prediction` remains a lower-level
   research helper; prefer the guarded read adapter for the proposed API layer.
2. `get_data.site_context.for_site(site_id)` returns the public, precomputed
   wildlife evidence layer with dates/uncertainty and sample limitations.
3. `db.ask_query.connect()` opens only the dedicated restricted account;
   `db.ask_query.execute(connection, sql)` permits bounded approved SELECTs.
4. `python -m get_data.monitor --load --interval-seconds 3600` runs the input,
   weather and prediction collector once prerequisites in CORRECTIONS.md pass.

Alan owns API wiring and schema changes; Aryan/Isaiah own affected screens.
Sid supplies tested data/model/storage adapters. No frontend should relabel a
research/prototype score as a scientifically established probability of injury.

## Agreement needed

Approve the target definition, removal of 8/2/two-model requirement, feature-level
explanations, wildlife as a separate evidence layer, and quality/window fields.
Then update the shared contract and wire the adapters. This proposal does not
claim a meeting has occurred or that the team has accepted these changes.
