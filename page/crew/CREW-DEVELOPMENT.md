# Crew frontend: implementation parts and commit rationale

These commits organize an already-developed frontend into reviewable implementation parts. They are being created now, with normal Git timestamps. They do not reconstruct or backdate the original development session. The rationale below explains observable design decisions, tradeoffs and checks.

All new application/tooling files live under `page/crew/`. `page/crew.html` is a small entry redirect. Existing team files, backend schema, supervisor dashboard and shared styles are not overwritten. The supervisor in this package is a separate integration preview that Aryan can adopt or replace.

Commit history records each implementation part and its message; application comments keep only useful technical rationale. Third-party Leaflet files and machine-readable JSON remain intact. More specific comments explain why deadlines, event ordering, explicit server clears, upload retries and unit preservation matter.

| Part | Commit message | Files / responsibility | Why this boundary helps |
|---|---|---|---|
| 1 | `feat(crew): establish national sites and safety state` | Domain/state functions, actual plant data, package/dev tooling, core tests | Tests deadlines, ordering, timezone previews and data coverage before screens depend on them. |
| 2 | `feat(crew): add authenticated backend connection adapters` | Public config, Auth0, HTTP/SSE adapter, custom adapter hook, UI types, transport tests | Changes to service URLs and authentication stay outside rendering; errors never silently swap in fake data. |
| 3 | `feat(crew): isolate persistent demo data from live services` | Mock service, IndexedDB storage, service switch | Demonstration state is explicit and reproducible; no local save claims team delivery. |
| 4 | `feat(crew): add accessible hazard and score components` | Scoped CSS, reusable UI helpers, vendored Leaflet/license | Shared visuals and evidence rendering are consistent without taking ownership of the team's design system. |
| 5 | `feat(crew): add photo reporting and next-day briefing flows` | Report/photo/pin/history view, briefing/preferences view, strict report mapper and tests | Storage confirmation, deduplication and scheduling boundaries are visible in both code and UI. |
| 6 | `feat(crew): assemble crew workspace and supervisor preview` | Crew entry/navigation, persistent alerts, separate supervisor map/ranking, root crew redirect | Expose the screens after their dependencies exist, keeping the app's navigation small. |
| 7 | `docs(crew): document decisions and backend integration` | This walkthrough, setup, backend handoff and validation notes | A teammate can understand the choices and connect the actual backend without reading the chat. |
| Follow-up | `fix(crew): match current photo storage key validation` | Report mapper, regression test and current-schema documentation | A team update tightened storage-key validation; the frontend rejects URLs and preserves opaque keys exactly. |
| Visual update | `feat(crew): add a colorful field-inspired visual theme` | Scoped theme, original SVG icons/contours, hazard cards, score ring and navigation accents | Category colors help scanning while severity badges and alert colors stay consistent; no additional features or remote asset requests are needed. |

## Decisions worth explaining to a judge or teammate

- **Absolute countdown deadline:** derive remaining time from UTC timestamps, rather than subtracting one each second. A sleeping browser tab then resumes with the right remaining duration.
- **Monotonic versions:** accept only newer state for the correct site. A delayed message must not overwrite a newer lightning hold.
- **Explicit server clear:** 00:00 is not an all-clear. Keep the hold until the server confirms a newer cleared state; missing connectivity stays visible.
- **Separate readings and index:** the model supplies the 0–10 score and its explanation; the UI retains source times, signs and units without inventing missing values or forcing contributions to sum.
- **Stable report request ID:** an upload retry should return the same stored receipt, not create a duplicate report.
- **Strict report payload:** `crew-report-mapping.js` matches the actual `api/schemas/hazard_report.py` creation fields at the fetched baseline. Upload first, then use the stored `photo_key`. The backend supplies identity, IDs, timestamps and review status.
- **Explicit severity:** the worker chooses low/medium/high. The adapter does not silently guess the report's severity from a synthetic score.
- **Site timezone:** daily 18:00 belongs to the job site's timezone, not the phone's. The frontend previews it; a backend job handles actual generation and delivery while the browser is closed.
- **Isolated package:** keeping `package.json` and dev tooling under `page/crew/` avoids changing the module settings of another teammate's files under `page/`.

## Review and checks

Run from this folder:

```sh
node dev/check.mjs
node --test
node dev/serve.mjs
```

Core/transport/report-mapping tests validate behavior rather than UI copy. The checks are also run against each committed snapshot, so untracked files cannot accidentally hide a missing dependency. Live Auth0, backend storage, environmental feeds, trained ML and scheduled delivery still require team configuration. Current status belongs in VERIFICATION.md and BACKEND-CONNECTION.md.

For source attribution, the plant-data provenance is in `crew-data/atlas-source.json`; vendored Leaflet keeps its original license. No CivicLens source, private team handoff documents, credentials, database files or raw secret configuration are included in these commits.


## Dark welcome and Auth0 entry

The welcome page follows the sparse, near-black composition of the supplied Deepsec reference, with original PlanIT copy and code-native grid/network artwork. `crew-dark.css` keeps the same palette across login, crew, reports, briefings, and the separate supervisor preview. Severity wording stays visible independently of color.

`crew-entry.js` consumes the Auth0 callback and chooses the workspace from the account’s configured role claim. It imports the workspace in the same document, preserving the memory-only SDK session. Unknown roles get an access message; query parameters cannot grant roles. The backend remains responsible for authorization. See AUTH0-HANDOFF.md for application URLs and hosted-login branding.


## DeepSpace integration

Issue #1 is implemented in the default HTTP adapter. Public listener settings
are in `crew-config.js`; `crew-realtime-source.js` imports the shared listener
only when live subscriptions start. `scores.updated` supports batch IDs and
coalesced refetches. Global listeners deliver bulk snapshots to the supervisor
preview and Atlas. Demo mode stays local. Commit-message comments were removed
from application sources while retaining useful implementation rationale.

The external bridge accepted a read-only subscription during verification.
Full authenticated live browser testing still requires the team’s Auth0 and API
configuration. No events were published by the connectivity check.
