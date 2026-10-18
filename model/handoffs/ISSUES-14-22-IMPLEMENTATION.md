# Sid's completed issue work and deployment handoff

Verified October 17, 2026, 11:09 PM EDT (October 18, 03:09 UTC).
Latest sync: `50acc17` includes the live same-origin crew configuration and
updated team ownership: Aryan now owns both frontends and demo-readiness work;
Isaiah has no separate active deliverable. The contract's login integration note
now reflects live deployed `/api` reads; score semantics are unchanged. Alan
reports supervisor status handling complete and crew lightning/NWS handling
deployed. Crew heat-index/wildlife labels and unassessed severity chips remain
Aryan's work. Alan's #20 diagnosis confirms server/bridge delivery works; expired
Auth0 sign-in is tracked in #20/#23. No data rebuild or password reset is needed.

This handoff covers Sid's owned code. It does not certify frontend deployment,
bridge delivery, the full demo path, injury risk, or safety clearance.

## Results

| Issue | Sid's result | Evidence | Remaining owner action |
| --- | --- | --- | --- |
| #14 | Predeclared recalibration candidate passed both required metrics on both unused Q3 partitions. Current serving model preserved. | `model/studies/q3-calibration-plan.json`; `model/generated/forecast-v3-candidate/report.json` and `integration-verification.json` | Alan reviews and explicitly deploys candidate with rollback. Keep visible Prototype label. |
| #15 | Healthy plants commit independently; score and native-weather phases are independent; failed sites/counts are explicit. | `get_data/batch_store.py`; `get_data/tests/test_partial_batches.py`; live verification below | Alan deploys collector and verifies service health after restart. |
| #16 | Prediction plus durable notice commit atomically; publisher runs only after commit, coalesces IDs and retries failed delivery. Migration 004 applied. | `db/score_notifications.py`; its tests; real rollback probe | Alan confirms existing bridge environment reaches collector and enables publisher. Aryan verify browser refetch in #22. |
| #17 | SELECT/expression depth and total nodes bounded separately; supported joins/subqueries work using actual restricted login. | `db/tests/test_query_complexity.py`; `db/generated/issue17-verification.json` | Alan deploys API change and reruns the supported natural-language questions. |
| #19 | Heat-index domain, missingness reasons and concrete fixtures supplied. | `get_data/HEAT-INDEX.md`; `get_data/generated/heat-index-cases.json` | Alan maps API values; Aryan finishes crew labels and verifies both frontends. |
| #22 | 60/60 latest screening rows and their inputs were within one hour; 60 sites had recent native weather. | `db/generated/issue-batch-verification.json` | Alan and Aryan finish their separate authenticated, phone, replay and two-browser checks. |

Current NWS ingestion is already Alan's deployed `jobs/nws.py` work (#18).
This change does not add a competing environmental-warning collector. Restricted
credentials were already delivered and verified; no account reset/rebuild is needed.

## What the new model does

The existing 128-tree forest and its feature calculation remain frozen. A
sigmoid probability recalibration was fitted to earlier 2026 development data,
chosen from four methods using April–June development and geographic-validation
results, then refitted under the frozen plan. January–June 2026 had already been
inspected previously and is explicitly development evidence for this study.

The final, unused period was July 8–September 30, 2026. Original development
counties form the temporal test; original geographic-test counties form the
geographic test. Shared warning identities are purged from earlier phases.
Selection uses no reserved outcome values. No 8/2 split or hand-selected hazard
weights were introduced. All sources, hashes, exclusions and calibration bins
are retained in the study report and local raw-data manifests.

| Test | Candidate AP ↑ | Seasonal AP ↑ | Candidate Brier ↓ | Seasonal Brier ↓ |
| --- | --- | --- | --- | --- |
| Temporal: 12,224 windows | 0.553905 | 0.298170 | 0.159326 | 0.205836 |
| Geographic: 4,077 windows | 0.527355 | 0.236939 | 0.144714 | 0.179556 |

The candidate also beat the constant-prior baseline in both metrics. Passing
means meeting this retrospective study's rule. It does not establish injury
probabilities or independent prospective safety validation. Windows overlap;
nearby plants share weather. Original forecast publication times are still
unverified. The geographic counties were tested previously for January–June,
although their Q3 outcomes were unused. Maintain the Prototype label.

Runtime support restrictions remain intact: 50 of 16,301 historical test windows
had a feature outside original training support and would be withheld at runtime.
Reported study metrics include all eligible test windows; they must not be
presented as the metrics of only the runtime-supported subset. All **60 current
recorded plant inputs** passed the candidate's support, source reconstruction,
explanation, response, and stale-value checks. Maximum explanation error was
1.11e-16 score units. No unsupported threshold was expanded to obtain coverage.

Candidate hash: `0d9889fe29e7004041f1d9e12905e128beda983cb6be028e06cf37d2fc8e42c5`.
Rollback/current model hash: `207c76d8ab9b0eb7387f17ce07c82fd348f70d667c9a5215aac737943e42b808`.
`validation_passed=true` on candidate; `production_approved=false`. This is a
validated prototype candidate, not an automatically approved production model.

## Alan: deploy the collector and API changes

1. Review this branch/commit and candidate evidence, then pull it into the
   existing server checkout. Preserve its ignored secret files and existing
   service configuration. Do not create another database or load the plant
   catalog again.
2. Use the existing collector service's Python environment and private database
   credentials. Dependencies are `model/requirements.txt` and
   `db/requirements-ask.txt`; no new dependency was added by this batch.
3. Before starting the updated collector, run from the checkout:

   ```sh
   python -m db.migrate
   ```

   Migration 004 is **already applied to the shared database** and this command
   should verify/skip it. It creates an ordinary transactional outbox, not a
   Timescale hypertable. Never edit an applied migration or grant `/ask` access
   to the outbox. It contains only plant IDs and delivery metadata.
4. Inspect the existing unit before changing it:

   ```sh
   sudo systemctl cat planit-collector
   ```

   Keep its working directory, Python executable, database environment,
   `--load`, `--allow-research`, and `--interval-seconds 3600`. The research flag
   is retained so rollback to v2 remains usable. The worker keeps hourly polling
   anchored to poll start; notification retries do not redownload weather.
5. Alan already verified the server/bridge settings in #20. Confirm the
   **collector service**, not only the API service, inherits the existing private `DEEPSPACE_URL` and `PLANIT_NOTIFY_SECRET`. The values must
   match `api/realtime.py` and the bridge. Keep them in the service's private
   environment file/secret store, never GitHub or a command pasted into chat.
   Enable its existing publisher with:

   ```ini
   Environment=PLANIT_SCORE_PUBLISHER=api.realtime:publish
   ```

   This dynamically imports just the publisher module when explicitly enabled;
   collection remains usable without API configuration. Alternatively append
   `--publisher api.realtime:publish` to the existing collector command.
6. **After explicitly accepting the candidate**, set the collector environment:

   ```ini
   Environment=PLANIT_MODEL_DIRECTORY=model/generated/forecast-v3-candidate
   ```

   This relative path assumes the existing service WorkingDirectory is the
   repository root; confirm that in step 4. An absolute path to that same
   directory also works. The default remains v2 unless configured. The directory
   must contain matching `model.json` and `report.json`. The collector verifies
   their canonical artifact hash before using them.
7. Apply your unit/environment changes and restart:

   ```sh
   sudo systemctl daemon-reload
   sudo systemctl restart planit-collector
   sudo systemctl restart planit-api
   sudo systemctl status planit-collector --no-pager
   ```

   Inspect sanitized service logs locally. Do not paste secret environment
   output. API restart loads the corrected SQL guard; collector restart loads
   the new isolation/outbox behavior and explicitly selected model.
8. Check `data/raw/runtime/latest.json` **on the server**. Requested, validated,
   committed and failed IDs are separate for screening/weather. `database_loaded`
   means some screening rows committed; it does not mean 60/60. Require committed
   counts/ID sets for complete coverage. Root status may be `partial`; it must
   never relabel a failed plant safe or fabricate a current timestamp.
9. With the publisher configured, inspect `notifications.status`. `delivered`
   means the bridge publisher returned true, not that either browser displayed
   an update. `pending_retry` means rows remain durably queued. Retries are due
   after 60, 120, 240… seconds, capped at one hour; the worker checks every 30
   seconds between hourly collections. At most 100 due outbox entries are
   coalesced per dispatch. `busy`, `idle`, `not_configured` and `error` are distinct.
   A one-shot collector does one delivery pass; use the ongoing service for retries.
10. Verify #22's two-browser path with Aryan. Payload shape is exactly
    `scores.updated` plus `site_ids` for committed plants. Both clients refetch
    authoritative API data. Repeated/late notices must not overwrite newer
    values. Exercise a bridge outage and restart: predictions stay saved and
    pending rows retry after recovery. Do not delete pending notices to hide
    a configuration failure.

**Rollback:** remove/unset `PLANIT_MODEL_DIRECTORY` (and any explicit
`--model-directory` argument), retain `--allow-research`, and restart the
collector. This restores unchanged v2. Leave migration 004 in place: the updated
collector requires it even when using v2. Leave successful/pending delivery
history intact. No database rebuild or model retraining is needed.

## Verification and reproduction

Owned tests:

```sh
python -m unittest discover -s db/tests -v
python -m unittest discover -s get_data/tests -v
python -m unittest discover -s model/tests -v
```

The live batch committed 60 screening predictions plus their queued notices,
60 native-weather readings and 2,880 forecast rows with retained hourly evidence.
An actual outer-transaction rollback probe removed both its temporary prediction
and notice; the dispatcher rejected an active pre-commit transaction. The
restricted login passed the legitimate latest-forecast/score joins and could
not read the outbox. No real bridge notification was sent during these probes.
At verification there were 60 pending notices, awaiting collector publisher
configuration. This is intentional pending delivery, not proof of live delivery.

Recorded-input candidate verification (offline, does not deploy):

```sh
python -m model.verify_candidate
```

The experiment is already complete. Do not rerun it to tune against Q3. Its
runner refuses a second final evaluation while the recorded report exists.
Source download and training entry points, for reproduction in an independent
checkout with the same frozen policy, are `get_data.followup_data` and
`model.followup`. Changing policy requires a new reserved study, not relabeling
these outcomes unused again.
