# Model experiments

The corrected forecast-based pipeline and operating instructions are in
[CORRECTIONS.md](CORRECTIONS.md). The report below preserves the original interval
5 experiment; its realized-weather inputs are not used by the new live scorer.
The interval 7 response adapter, offline replay and remaining deployment steps
are in [INTEGRATION.md](INTEGRATION.md).

## Original interval 5 experiment

We trained real models, but **none met the predeclared acceptance rule** in this
first experiment. No production hazard score or new weather/wildlife weighting
is created. The team's shared API contract remains unchanged.

## What was trained

| Candidate | Purpose |
| --- | --- |
| Constant prior | Always predicts the training-set report frequency |
| Month-only logistic regression | Checks how much ranking comes from seasonality alone |
| Shallow decision tree | At most four levels; at least 40 training windows per leaf |
| Logistic regression | Standardized weather features, regularized coefficients |
| Random forest | 128 trees, depth at most eight, at least 30 windows per leaf |

Settings are fixed, with seed `20261017`. There is no automated parameter search,
class reweighting, synthetic oversampling, or adjustment toward an 8/2 ratio.
These are a small candidate comparison, not a search for the globally best model.

All candidates are saved as numeric JSON, avoiding executable pickle artifacts.
Each export was checked against its trained Python model on all training and
validation windows. Maximum allowed prediction difference is `1e-12`.

## What the number means

The binary target is **an applicable NOAA weather-event report overlapping the
next 24-hour window in the plant's county or an intersecting forecast zone**.
Zero means no applicable report in the downloaded extracts. It does not mean
confirmed safety. This is not an injury outcome or a plant-specific incident label.

The input windows here use ERA5 realized weather during that same outcome window.
This measures weather/report associations. It does **not** establish the accuracy
of next-day predictions using forecasts. The separate 2026 forecast pilot stays
unopened by the experiment runner. Historical publication timing remains unverified.

GBIF wildlife sightings have no reliable absence or encounter labels, so no
wildlife classifier is trained by inventing negative examples. Soil moisture is
an input; soil saturation has no direct target label here. Crew reports and
mandatory lightning alerts remain separate.

## Inputs and leakage controls

The twelve input columns are fixed by `get_data.history_features.FEATURES`.
They cover temperature, humidity, wind/gust, rain, shallow soil moisture,
conditional heat index, and month. IDs, geography, reports, event severity,
injuries, deaths and episode IDs never enter the predictor matrix.

Unknown targets and missing core inputs are excluded: 77 unknown labels and
seven windows with invalid/missing soil values, leaving 17,136 eligible rows.
Out-of-domain heat index remains missing. Its training-set median and missingness
indicator are fitted within each pipeline; these are model preprocessing,
not replacement observations written back to the database. Scaling is also
fitted on training only.

The loader checks the historical artifact checksum, builder code fingerprints,
site catalog, feature schema, provenance references, eligibility and duplicate
windows before fitting. The current study has one plant per county.

County roles are assigned by a deterministic hash within each hazard region,
without consulting labels: 36 development, 12 geographic validation and 12
geographic test counties. All windows for a county share its role.

| Partition | Dates in 2025 | Windows | Positive reports |
| --- | --- | ---: | ---: |
| Training, development counties | March 19–July 28 | 4,718 | 238 |
| Temporal validation, development counties | August 1–September 27 | 2,075 | 98 |
| Geographic validation, unseen counties | August 1–September 27 | 691 | 45 |
| Temporal test, development counties | October 1–December 30 | 3,264 | 105 |
| Geographic test, different unseen counties | October 1–December 30 | 1,092 | 39 |

Other windows are deliberately unused. Date gaps separate phases, and any event
or episode shared with a later partition is purged from the earlier partition.
No rows needed episode purging in this recorded run. Geography validation/test
are disjoint counties, but their storms may still be correlated; they do not
represent independent years of evidence.

## Results

Average precision (AP) measures how well reports rise toward the top of a ranking;
higher is better. Brier score measures probability error; lower is better.
We report both because good ranking alone does not establish reliable probability
values. See the [scikit-learn metrics documentation](https://scikit-learn.org/stable/modules/model_evaluation.html).

| Candidate | Temporal AP | Geographic AP | Temporal Brier | Geographic Brier |
| --- | ---: | ---: | ---: | ---: |
| Constant prior | 0.0472 | 0.0651 | 0.0450 | 0.0611 |
| Month-only | 0.0625 | 0.0875 | 0.0457 | 0.0608 |
| Shallow tree | 0.0583 | 0.0986 | 0.0466 | 0.0611 |
| Logistic regression | 0.0783 | 0.1871 | 0.0460 | 0.0588 |
| Random forest | 0.0879 | 0.1004 | 0.0451 | 0.0617 |

The acceptance rule requires a weather candidate to beat both baseline AP values
and the constant baseline's Brier score **on each validation set**. Qualified
candidates would be ranked by mean AP, then mean Brier. This is an explicit
engineering criterion, not a scientifically established safety requirement.
No candidate qualifies; the runner records `selected_candidate: null` and does
not create `selected-candidate.json`.

Logistic regression has the highest average AP across the two validation sets.
It is a promising ranking candidate, but its temporal probability error exceeds
the constant baseline. Random forest has the strongest temporal AP but worse
geographic probability error. The shallow tree does not beat month-only temporal
ranking. We did not relax the acceptance rule after seeing these results.

Selection is written to disk before final-test prediction. Since there is no
qualified weather model, only the two baselines receive final-test evaluation.
The trained weather candidates' final tests and the separate forecast-pilot
rows remain unevaluated. The baselines' final tests have now been inspected;
do not treat them as fresh validation for future changes.

The JSON report also includes ROC AUC, probability calibration bins, region
breakdowns, a fixed 0.5 diagnostic threshold and daily top-10% review results.
Neither threshold is an approved alert policy. With few positives, default
classification accuracy would be misleading, so it is not the headline result.

## What features look useful

We measured AP changes after permuting one feature at a time on validation
rows, five repeats, for each weather model. For logistic regression, **mean
humidity, heat index, wind gust, wind speed and soil moisture** have positive
importance in both validation sets. Their ordering differs between sets.

These are association diagnostics, not proof of causation or optimal features.
Correlated features can substitute for each other; repeating the permutation
does not provide independent-dataset confidence intervals. Do not translate
these values into hazard contributions or use them to change weights directly.
The full per-model values are in `generated/experiment-results.json`.

## Run and inspect

From the Mac terminal inside `planit-control`:

```sh
.venv/bin/python -m pip install -r model/requirements.txt
.venv/bin/python -m model.experiments
.venv/bin/python -m unittest discover -s model/tests -v
```

The experiment uses the already cached historical build; it does not redownload
weather, use Gemini, or access the database. Source downloads must exist locally
for a fresh checkout: build them using `get_data/HISTORY.md` first. Dependencies
are scoped under `model/`; shared API requirements are untouched.

| File | Purpose |
| --- | --- |
| `data.py` | Verified input loading, county roles, date splits, event/episode purging |
| `experiments.py` | Training, validation-only selection, evaluation, JSON export |
| `generated/experiment-results.json` | Recorded metrics, configuration, hashes and limits |
| `generated/candidates/*.json` | Five trained research artifacts; promotion disabled |
| `tests/test_experiments.py` | Leakage, selection, metric, preprocessing and export checks |
| `data/raw/model/runs/<timestamp>/` | Local full run: selection record, artifacts and baseline test predictions |

The report preserves data/manifest/site hashes, code hashes, package versions,
county assignments, class counts, candidate hashes and limitations. It does not
save credentials. A rerun repeats the same fixed experiment; it is not fresh
evidence or permission to tune against the test results.

## What must improve before deployment

More years and seasons, forecast-matched inputs with verified issue availability,
better event geography and reporting coverage, and proper out-of-sample
probability calibration are the next evidence needs. Wildlife requires suitable
presence/absence or effort-aware data and a defined outcome. Adding arbitrary
weights would not solve these gaps.

Interval 6 can implement exact explanations and guarded offline inference for
the research artifacts, but must preserve their unvalidated status. No trained
candidate from this run is approved for a public probability or combined 0–10
score. A replacement for the current 8/2 API semantics still needs team agreement.

Method references: [splitting grouped and time-dependent data](https://scikit-learn.org/stable/modules/cross_validation.html),
[avoiding preprocessing leakage](https://scikit-learn.org/stable/common_pitfalls.html).
