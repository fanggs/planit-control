# Historical evidence: interval 4

This interval builds the datasets for model experiments. It does not train a
model, select weights, calculate a hazard score, or change the shared contract.

## Run it

From the `planit-control` Mac terminal, with the project dependencies installed:

```sh
# Small source/format test first.
.venv/bin/python -m get_data.history --site-id 621 --forecast-step 48 --wildlife-per-taxon 30
# Full default study: all 60 sites.
.venv/bin/python -m get_data.history
```

The default build uses about 1,020 weather requests before retries, plus a small
number of NOAA/NWS/GBIF requests. Starts are throttled, downloads have timeouts,
and checksummed source caches avoid repeating downloads. Do not use `--refresh`
unless you intend to retrieve new source versions. Larger sampling settings use
more requests; inspect provider limits before increasing them.

`data/raw/history/latest.json` records `building`, `ok`, `partial` or `failed`.
Each build preserves its own directory under `data/raw/history/builds/`:

| File | Contents |
| --- | --- |
| `weather-reanalysis-examples.jsonl` | One retrospective 24-hour example per site/day |
| `weather-forecast-pilot.jsonl` | A separate sample built from named historical forecast runs |
| `environmental-events.json` | NOAA event reports matched to study counties/sites |
| `unresolved-noaa-geography.json` | Reports whose geography cannot safely be resolved |
| `wildlife-observations.json` | GBIF presence records and their date/location/licensing metadata |
| `validation.json` | Source ledger, checksums, coverage, class counts, failures and limits |

These larger changing files stay local and are ignored by git. Small recorded
examples and a verification summary live in `get_data/generated/`. Original
downloaded responses, retrieval receipts and quarantine details remain under
`data/raw/history/sources/`. An existing successful build is never substituted
for a failed new build. Rerunning resumes from verified cached sources.

## Weather inputs

The retrospective dataset covers **2025-03-19 through 2025-12-30**. It uses
[ERA5 reanalysis through Open-Meteo](https://open-meteo.com/en/docs/historical-weather-api):
an estimate of past realized conditions. It is useful for learning associations
between conditions and reports. It was not a forecast available at the cutoff.

The separate forecast pilot uses the same native ECMWF IFS model family as
the live collector, with the [Single Runs API](https://open-meteo.com/en/docs/single-runs-api).
It samples every third day from **2026-05-13 through 2026-06-29**; the last sampled
day is June 27. Dates are selected before inspecting event outcomes. This is
960 examples for 60 sites, rather than outcome-selected storm days. The start is
after the documented May 12 IFS cycle change, avoiding earlier hindcast runs.

Each example has a UTC-noon cutoff and the following 24 hourly endpoints:
13:00 through next-day 12:00. A forecast uses the explicitly requested 00 UTC
run. The twelve-hour delay is a **declared availability assumption**: original
publication times have not been independently verified. It is not valid to
claim that initialization time proves a forecast was publicly available.

The feature builder derives maximum/minimum temperature, mean/minimum humidity,
maximum wind and gust, maximum hourly and total 24-hour precipitation, mean
0–7 cm soil moisture, an optional in-domain heat-index maximum, and cyclical
month. Units match the live pipeline. Entire incomplete measurement windows
become null; partial averages and zero-filled rain totals are not used. Invalid
historical cells are quarantined as null while original values remain intact.
The live weather parser remains strict.

These are **candidate features**, not a claim that all twelve are optimal.
Antecedent rain, static terrain/fuels and other research candidates need matching
live availability and comparable history before inclusion. Adding extra columns
without that evidence would introduce misleading inputs.

## What the target means

The source is [NOAA Storm Events](https://www.ncei.noaa.gov/pub/data/swdi/stormevents/csvfiles/).
An example is positive when a documented event overlaps its target window in
the plant's county or a public forecast zone intersecting that county. It is
**county context**, not proof of an event inside a plant or an injury outcome.

The explicit event scope is Heat, Excessive Heat, Lightning, Flood, Flash Flood,
Coastal Flood, Lakeshore Flood, Storm Surge/Tide, Wildfire, Thunderstorm Wind,
High Wind and Strong Wind. Wind events map to `other`; a thunderstorm-wind
report is not relabeled as a measured lightning strike. Soil saturation has no
direct label here, and wildlife has no outcome label in this weather dataset.

A zero means **no applicable report in these published extracts**. It does not
prove absence of hazardous conditions. Unknown geographic coverage produces a
null label instead of a confident negative. Per-hazard labels, event IDs and
episode IDs remain alongside the features for auditing and safe evaluation;
they must never become predictor inputs.

The 2025 NOAA file spans January–December; the downloaded 2026 file spans only
January–June. The pilot ends within that coverage, rather than inventing zero
events in unpublished months. Revisions, underreporting and geographic reporting
bias remain limitations even for fully downloaded annual extracts.

## Geography and timestamps

NOAA distinguishes county codes (`C`), public forecast-zone codes (`Z`), and
marine codes (`M`). The same digits do not identify the same place. Zoned events
use dated [NWS zone-to-county crosswalks](https://www.weather.gov/gis/ZoneCounty),
effective March 18, 2025 and April 16, 2026. County matches retain five-digit
FIPS strings. Unknown zones and events spanning a geography change are retained
for uncertainty masking. Effective-date boundary windows cannot create confident
negative labels. The training start follows the first supported crosswalk.

The 2025 crosswalk contains five rows with conflicting zone columns. Neither
column is guessed to be correct: both ambiguous identifiers are quarantined.
The 2026 NOAA extract also contains two relevant records with `CZ_TYPE = 5`,
which is not a documented discriminator; they remain unresolved. Detailed IDs
and source values are preserved in the audit artifacts.

Event times use the offset actually supplied in NOAA's `CZ_TIMEZONE`, including
explicit daylight-time offsets where present. We never apply a second IANA DST
conversion. `2400` rolls to the following midnight; malformed times fail visibly.

## Wildlife evidence

[GBIF](https://techdocs.gbif.org/en/openapi/v1/occurrence) queries cover 2020–2025
US presence records for American alligator, the two cottonmouth species,
copperhead, and the Crotalus/Sistrurus rattlesnake genera. Taxonomy is resolved
with scientific name, rank and family constraints, and its response is retained.
The default caps retrieval at 600 records per taxon; this is a documented API
subset, not random sampling, survey effort, or a complete occurrence census.

Retained records preserve original dataset IDs, license, occurrence links,
observation basis, uncertainty and raw event dates. Missing coordinate uncertainty
stays unknown. The declared quality filter excludes reported uncertainty over
10 km; that is not a wildlife safety radius. Date-only or timezone-free values
use an explicitly marked UTC calendar-day anchor, not an invented exact time.
Their original calendar dates remain available for location/month analysis.

Presence-only sightings cannot supply reliable absence labels or encounter/
injury probabilities. No wildlife negatives, fabricated effort, or 8/2 split are
created. American crocodile coverage at Turkey Point still needs team agreement.

## Model experiments come next

The recorded full build contains 17,220 retrospective examples (885 positives,
77 unknown labels) and 960 forecast-pilot examples (48 positives). It retains
2,654 GBIF observations. Seven retrospective windows have missing soil-moisture
features after invalid source cells were quarantined. There are only eight
lightning-positive retrospective examples and **no lightning-positive pilot
examples**; this pilot cannot establish lightning-specific predictive skill.
The committed verification summary records exact counts and source checksums.

Use the retrospective set for association-model development and chronological/
geographic validation. Keep the 2026 forecast pilot separate for a later test;
do not repeatedly tune features or hyperparameters against it. Group sites that
share county/time labels and purge overlapping events/episodes around splits.
Training-only preprocessing must not learn from validation/test rows.

Reanalysis validation alone is not forecast validation. Even the forecast pilot
has limited seasonal coverage and unverified historical publication latency.
The manifest therefore sets `model_promotion_eligible` to false. Experiments can
measure performance under these stated limits; production readiness is not
established by this data build.

## Optional database load

```sh
.venv/bin/python -m get_data.history --load
```

This uses the same terminal's `DATABASE_URL` and `PGPASSWORD`. It loads only
wildlife observations and historical site events into existing contract tables,
with validation and a post-load comparison in one transaction. It does not
load the large experimental weather matrices into live tables or overwrite
current conditions. A failed build does not attempt a database write.

The historical loader and new hypertable migration still require a real-service
execution check. No historical database changes are made by a plain data build.
