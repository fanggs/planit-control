# Data ingestion

Interval 2 implements EIA plant ingestion. Weather and historical/model datasets
are later intervals; this command does not generate scores or modify the API.

## Start here

Run from the repository root (`planit-control`). The environment is local and
ignored by git. It does not replace the shared API's dependency list.

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r get_data/requirements.txt
.venv/bin/python -m get_data.sites
.venv/bin/python -m unittest discover -s get_data/tests -v
.venv/bin/python -m unittest discover -s db/tests -v
```

Open **`get_data/generated/sites.json`** to see all 60 real plants. The adjacent
**`sites-validation.json`** records source URLs, actual download times, SHA-256
checksums, dependency versions, counts, rejected-data summaries and checks.
These are real external data, not the API's sample fixtures. API routes still
need Alan's database integration before these plants appear in the live app.

The command discovers the newest workbook linked by the [official EIA monthly
inventory](https://www.eia.gov/electricity/data/eia860m/index.php). On October 17,
2026 that is **August 2026**, released September 24. It checks the workbook's
title and headers rather than assuming a fixed column position. `--vintage
2026-08` asserts the expected latest month; it deliberately fails if discovery
finds a different month. It is not a historical-download selector.

Raw workbooks, Census archives, download receipts, and the full rejected-plant
list stay under ignored `data/raw/eia/`. A verified cache preserves the original
retrieval time. `--refresh` re-downloads; it does not pretend cached data was
retrieved again. Keep receipts with raw files for repeatability. A changed cache
checksum fails visibly. The checked-in 60-site output remains usable offline.

## One row per plant

Only the workbook's `Operating` sheet is read, and only generators with status
`(OP) Operating` are retained. Standby, out-of-service, planned, retired and
Puerto Rico sheets are excluded. Generators are grouped by **Plant ID**, never
Generator ID. Duplicate generator IDs, conflicting plant names/states/counties
or coordinates, missing identity/type/utility and invalid coordinates are
rejected and logged. Coordinates are not averaged.

`plant_type` is the sorted set of operating-generator `Technology` labels joined
by `; `. `utility` similarly summarizes the source's `Entity Name` labels; it
describes reporting entities, not inferred ownership shares. The output retains
the source plant name, state, county and location, and sets `operating_status`
to `OP`.

County FIPS is a five-character string, including leading zeroes. It comes from
an exact state-plus-normalized-name match to the [2026 Census county
gazetteer](https://www.census.gov/geographies/reference-files/time-series/geo/gazetteer-files.html).
Normalization handles punctuation, administrative suffixes and Saint/St; it does
not guess spelling corrections or ambiguous multi-county entries. Connecticut's
old EIA county names do not map directly to current planning regions, so those
candidates are rejected. Older NOAA county codes will require a separate,
vintage-aware join. The validation manifest records Census lineage in addition
to each site's primary EIA provenance.

Timezones come from timezonefinder's local polygons and the plant's coordinates,
with both code and polygon-data versions pinned. They are checked against IANA
timezone names; no state-wide timezone shortcut is used. Coordinate validation
checks finite values and contiguous-US bounds; it does not independently verify
that the plant lies inside its reported county or a particular parcel.

## Reproducible selection rule

The scope is the contiguous 48 states plus DC. The following mutually exclusive
groups are **demo coverage groups**, not official hazard classifications and
not risk-model weights:

| Group | States |
| --- | --- |
| florida_gulf | FL, AL, MS, LA |
| mississippi_valley | AR, MO, IL, IA, MN, WI, KY, TN |
| western_wildfire | CA, OR, WA, ID |
| southwest_heat | AZ, NM, NV, UT, CO |
| plains_storms | TX, OK, KS, NE, SD, ND, MT, WY |
| eastern_storms | CT, DE, GA, IN, ME, MD, MA, MI, NH, NJ, NY, NC, OH, PA, RI, SC, VT, VA, WV, DC |

Select exactly ten from each group. First include the required verified demo
plants below. For a group without one, start with the lowest plant ID. Repeatedly
add the candidate farthest from its nearest already selected plant, using
great-circle distance; lower plant ID breaks ties. This spreads the sites
geographically and is independent of workbook row order. Missing demo plants or
insufficient candidates stop the load. A future inventory can legitimately
change which plants are selected; the checked-in output and source checksums
capture this build. This demo selection is not a representative training sample.

| EIA ID | Plant | Coverage and evidence |
| --- | --- | --- |
| 621 | Turkey Point, FL | Everglades area; [FPL's mitigation-bank description](https://www.fpl.com/environment/wildlife/mitigation-bank-history.html) |
| 1925 | Prairie Island, MN | Mississippi River; [Xcel environmental report](https://xcelenergy.com/staticfiles/xe/Corporate/Corporate%20PDFs/002PrairieIslandER_04.24.08%28Web%29.pdf) |
| 6072 | Grand Gulf, MS | Mississippi River; [Entergy's plant description](https://www.entergy.com/blog/grand-gulf-nuclear-station-mississippi-success-story-begins-another-chapter) |
| 437 | Edward C Hyatt, CA | Butte County wildfire geography; [CAL FIRE historical incidents](https://www.fire.ca.gov/incidents/2018) |
| 445 | Shasta, CA | Shasta County wildfire geography; [CAL FIRE Carr Fire record](https://www.fire.ca.gov/incidents/2018/7/23/carr-fire/) |

California selections establish county-level demo coverage, not evidence that
either plant currently faces fire or lies inside a specific fire perimeter.
Turkey Point's operator documents **American crocodiles** at the plant; the
contract's wildlife species list does not currently include them. This is a
coverage question for the later wildlife work, not a reason to invent a sighting
or silently change the shared species list.

## Optional database load

First configure the development `DATABASE_URL` securely and apply the foundation
with `python -m db.migrate` (see `db/README.md`). Neither command automatically
loads a `.env` file; a deployment/terminal must supply the environment variable.
Use a PostgreSQL connection URI, not a SQLAlchemy `postgresql+psycopg` URI.
Then run:

```sh
.venv/bin/python -m get_data.sites --load
```

Without `--load`, no database connection or cloud writes occur. The loader
validates all 60 rows before opening a transaction. It locks competing catalog
loads, upserts by EIA plant ID using parameters, refuses to downgrade a newer
catalog, and marks older unselected sites unmonitored without deleting their
history or report references. Before committing, it re-reads and validates all
monitored rows and compares every stored field with the intended catalog. A
failed check rolls back the transaction. Re-running does not duplicate plants.

No database connection is configured in this checkout yet, so actual database
execution, reload idempotency and transaction rollback remain integration checks
to run against Tiger Data. The 60-site export and offline validation are ready.
