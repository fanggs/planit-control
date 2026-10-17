# Sid's seven implementation intervals

Each interval ends with checks and a normal local commit, followed by Sid's
review. Publishing to the team repository is a separate approval step.

1. Database foundation: contract tables, migration tracking, provenance and score
   validation. Real database execution awaits a configured development connection.
2. EIA plant ingestion: current workbook discovery, generator-to-plant grouping,
   reproducible 60-site selection, geographic checks and provenance.
3. Live conditions: weather readings and issued forecasts, explicit provider
   semantics, unit conversions, missingness and post-load checks.
4. Historical evidence: NOAA event geography/time normalization, weather joins,
   wildlife observation ingestion, reproducible labeled datasets and coverage.
5. Model experiments: define a measurable outcome supported by collected labels;
   compare a simple baseline, shallow tree, logistic regression and a stronger
   candidate with time/geographic holdouts, leakage checks and imbalance metrics.
6. Explainable scoring: exact additive contributions on the displayed scale,
   versioned artifacts, input coverage checks and batch inference.
7. Integration: database adapters for Alan, end-to-end checks, operating guide,
   limitations and team handoff.

## Model direction

Sid explicitly rejected choosing or defending an 8/2 weather/wildlife weighting.
Experiments will not optimize toward that ratio. Accuracy must be measured
against a stated target and held-out evidence; it cannot be promised in advance.
NOAA event occurrence is not an injury label, and GBIF presence records alone
cannot establish absence or an encounter probability. Missing labels, readings,
credentials and unsupported features will never be invented.

The team's current `api/CONTRACT.md` still specifies 8/2 and two small trees.
This document records Sid's requested experimental direction, not team approval
of a replacement contract. Preserve the shared JSON shape where appropriate;
do not publish replacement score semantics until the team agrees. Crew reports
and mandatory stop-work alerts stay separate from the trained score.
