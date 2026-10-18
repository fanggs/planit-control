# Proposed GitHub updates — awaiting Sid's approval

These are exact proposed comments, not already-posted updates. No joint issue
should be closed until its remaining deployment/browser checks are recorded.
Implementation and deployment instructions: `model/handoffs/ISSUES-14-22-IMPLEMENTATION.md`.

## #14

Sid's study is complete. The frozen plan is `model/studies/q3-calibration-plan.json`.
A development-selected sigmoid recalibration of the existing forest passed the
predeclared AP and Brier checks against both constant and seasonal baselines on
unused July 8–September 30, 2026 outcomes:

- Temporal, 12,224 windows: AP 0.553905 vs seasonal 0.298170; Brier 0.159326 vs 0.205836.
- Geographic, 4,077 windows: AP 0.527355 vs seasonal 0.236939; Brier 0.144714 vs 0.179556.

Candidate/report: `model/generated/forecast-v3-candidate/`. The original serving
artifact is unchanged. Candidate replay passed for all 60 recorded current inputs,
including source reconstruction, exact factor reconciliation, support and stale
checks. The support audit withholds 50/16,301 historical test windows at runtime;
study metrics include all test windows. No support bound was expanded.

Alan: review the evidence and enable `PLANIT_MODEL_DIRECTORY=model/generated/forecast-v3-candidate`
on the collector only when accepted. Keep the Prototype label; `production_approved`
remains false. Full rollout/rollback instructions are in
`model/handoffs/ISSUES-14-22-IMPLEMENTATION.md`. This measures warning/advisory
exposure, not injury probability or permission to resume work. January–June was
previously inspected and is disclosed as development data. Publication-time and
correlated-window limitations remain explicit.

## #15

Sid's collector fix is implemented and tested. `get_data/batch_store.py` commits
healthy plants independently and rolls back a failed plant without discarding
its neighbors. A plant's native-weather rows and hourly source evidence remain
in the same transaction. Screening and weather are separate phases, with explicit
requested/validated/committed/failed ID lists and committed counts.

Tests cover 60/60, 59/60, zero screening successes with weather still committing,
post-load rollback, connection failure stopping futile retries, duplicate inputs,
and later weather failure retaining saved predictions. Existing freshness,
provenance, input-support and exact-explanation guards remain in place.

A real shared-database poll committed **60 screening plants and 60 weather plants**;
`db/generated/issue-batch-verification.json` records the verification. Migration
004 is applied. Alan: deploy the updated collector and verify restart/service
health using `model/handoffs/ISSUES-14-22-IMPLEMENTATION.md`. Database-loaded flags
mean some rows committed; use committed counts for 60/60, not just those booleans.

## #16

Sid's post-commit producer and durable retry are implemented. Migration 004
creates `score_notification_outbox` and is already applied to the shared database.
Each prediction and its notice commit together. Delivery uses a separate idle
connection after commit, calls the injectable existing publisher, coalesces only
committed `site_ids`, and persists failures with 60-second exponential backoff
capped at one hour. The ongoing worker checks due notices every 30 seconds
without recollecting weather. Duplicate notices are possible and mean refetch.

Unit tests cover refusal inside an active transaction, coalesced IDs, rejection,
exceptions, bounded retry delay, duplicate identity and dispatcher contention.
An actual database rollback probe removed both temporary prediction and notice,
and blocked pre-commit publication. A real 60-site poll left **60 pending notices**.
The restricted `/ask` login cannot read the queue.

Alan's #20 checks already confirm server/bridge delivery. Confirm those existing
`DEEPSPACE_URL` and `PLANIT_NOTIFY_SECRET` values reach the collector service's
private environment and enable `PLANIT_SCORE_PUBLISHER=api.realtime:publish`.
Deployment steps are in `model/handoffs/ISSUES-14-22-IMPLEMENTATION.md`.
**Bridge delivery has not been claimed or verified locally.** After deployment,
verify outage/recovery and restart retry. Aryan: verify batch `site_ids`
trigger authenticated refetch in both browsers, including selected-site filtering
and duplicate/out-of-order notices, under #22. Keep this joint issue open until
those checks are recorded.

## #17

Sid's query-complexity fix is implemented. `db/ask_query.py` now bounds actual
SELECT nesting (5), expression nesting (32), AST nodes (1,500), query length and
representation size separately, rather than treating JSON wrapper depth as SQL
nesting. Existing table/function/type/operator allowlists, restricted login,
read-only transaction, timeout, row limit and single-SELECT rule remain intact.

All query-guard tests pass, including legitimate newest-forecast correlated
subqueries/aggregation joins, excessive nesting/size and nested restricted access.
The actual restricted database login also successfully executed plant counts
and latest forecast/score joins returning all 60 plants. Five disallowed-query
cases were rejected, and outbox access remains denied. Evidence:
`db/generated/issue17-verification.json`.

Alan: deploy/restart the API with this code and rerun the supported natural-language
question set against the live `/ask` endpoint. No login/password reset is needed.
Keep this joint issue open until the deployed endpoint check is recorded.

## #19

Sid's heat-index definitions and reproducible examples are complete:
`get_data/HEAT-INDEX.md` and `get_data/generated/heat-index-cases.json`.
The conservative implementation domain is 80–112 °F inclusive, RH 0–100%, plus
the NWS initial hot-condition screen. The upper cap is a project calculation
restriction, not a claim that hotter conditions are safe.

The fixtures distinguish available calculation, cool/not-applicable conditions,
missing temperature/humidity, above-supported temperature and initial-screen
failure. Null alone cannot distinguish these reasons. Current weather columns
omit humidity, although retained hourly evidence contains it: when the response
lacks enough information, label calculation unavailable rather than guessing.
No new API field or unsupported severity threshold was added.

Alan owns API mapping; Aryan now owns both crew and supervisor labels.
The latest sync (`4aeeec9`) includes Aryan's v1.3 supervisor status logic; verify
that deployed behavior rather than rebuilding it. Remaining crew work and live
measurement/assessment/monitoring-health verification are separate acceptance work. Keep this joint issue open until
those are verified.

## #22

Sid's data acceptance check passed at **11:09 PM EDT October 17, 2026**
(**03:09 UTC October 18**): all **60/60** monitored plants had latest screening
predictions **and their inputs** fresher than one hour. Oldest input was 3.33
minutes old. All 60 also had native weather within two hours. The real collector
poll committed 60 screening plants and 60 weather plants with post-load checks.
Evidence: `db/generated/issue-batch-verification.json`.

This check does not certify the whole demo path. Alan and Aryan still
need their assigned deployed auth/report/phone/replay/two-browser checks. The
candidate model remains undeployed pending Alan's release review, and queued
score notices await collector publisher configuration. Do not close #22 until
all owners' checks and the deployed commit are recorded.
