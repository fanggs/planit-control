# Crew backend connection — contract v1.2

`api/CONTRACT.md` is the source of truth. An **adapter** translates API data into the existing screen fields. The adapter accepts v1.2 `screening`, feature contributions and separate `wildlife_context`, while retaining a visibly labeled bridge for the earlier API responses.

## Screening migration and demo readiness (#6)

- `crew-screening.js` validates status, signed contributions, exact reconciliation,
  input freshness and the forecast window. `research` and `validated_prototype`
  display as **Prototype**, with their target window. Unavailable or expired
  scores display **No data**; an actual numeric zero remains zero.
- The v1.2 screening value takes precedence even when it is explicitly null.
  It never falls back to a legacy number or clears a lightning stop-work alert.
- Legacy API scores remain readable as **Legacy API score** or **Sample score**
  during rollout. A legacy number is never relabeled as a v1.2 model output.
- Bulk site responses currently do not specify forecast-window fields. The map
  preserves those fields when supplied, otherwise shows **Forecast window: not
  supplied**. It does not infer a window or fetch 60 individual site details.
- Wildlife sightings show recorded dates, sources, distances, uncertainty and
  limitations separately from scores and crew reports. An empty record list is
  never treated as confirmed wildlife absence.
- Local demo conditions stay synthetic and use feature-shaped sample factors.
  The homepage explains v1.2. A waterfall chart remains deferred at Isaiah's
  direction; signed contributions are available in the existing details list.
- At implementation time, both local and public `/openapi.json` still expose
  the earlier `score` / `hazard_type` schema. Alan must finish the v1.2 API
  schema and response integration; do not change `api/` from the crew work.
- Alan confirmed #7 is complete: Auth0 accepts the production callbacks and test users are ready. Phone acceptance is still pending. The crew callback is
  `https://foresite.work/crew/login.html`, logout URL
  `https://foresite.work/crew/index.html`, origin `https://foresite.work`, and a
  test account from Aryan with the crew role. Verify the supervisor separately with
  Aryan. Do not close #6 solely because adapter tests pass.

## Configure a live connection

In `crew-config.js`, supply the public Auth0 domain, client ID, API audience and API `baseURL`, then set `dataMode: 'live'` and retain `transport: 'http'`. See `AUTH0-HANDOFF.md` for callback URLs. The API must allow the frontend origin and validate the bearer access token on every protected request. Keep secrets out of frontend settings.

Default mode remains `mock`. Live errors never substitute synthetic conditions. The sample API's `model_version: 'sample'` is labeled as sample data rather than a trained model.

## Field translations

| Contract field | Existing screen field |
| --- | --- |
| `site_id` integer | `id` / selected site ID string |
| `utility` | `operator` |
| Detail `screening.score` (v1.2), or legacy `score.score` | Numeric `score` |
| `scored_at` | `score_updated_at` |
| Factor `feature` (v1.2), or legacy `hazard_type` | Readable factor `name`; source key is also retained |
| `flooding`, `soil_saturation` | Display cards `flood`, `soil` |
| Report `hazard_type` | Display `category` |
| Alert `level: 'stop_work'` | Lightning display `status: 'hold'` |
| Alert `clear_at`, `last_trigger_at`, `trigger.distance_mi` | `all_clear_at`, `last_strike_at`, `distance_miles` |
| Briefing `text`, `for_date` | `body`, `valid_date` |

Outbound requests always use contract names and numeric site IDs. Weather stays a display card; its report category maps to `other`, never a `weather` hazard type. Contributions remain signed score points. Baseline plus contributions must reconcile with the score (floating-point tolerance only for v1.2; 0.05 for the legacy format); inconsistent explanations show an unavailable message. Scores are never estimated by the live frontend. Report warnings sit beside the score and do not change it.

Readings retain actual units, observation times and provenance when supplied. Rolling 24-hour precipitation is labeled as such, not as overnight rain. Missing river association, training metrics, delivery status and readings remain unavailable. Revisions and alert versions are local request-order counters, not new backend requirements. No server clock or lightning-feed health is invented.

## HTTP requests

All calls request a fresh Auth0 bearer token. List responses follow the contract's arrays; there is no invented pagination or `/events` endpoint.

| Request | Behavior |
| --- | --- |
| `GET /sites` | Maps summaries for the site picker. |
| `GET /sites/{site_id}` | Unpacks score, weather, active alerts, events and recent reports. |
| `GET /alerts` | Refreshes authoritative alert details after a realtime notice/reconnect. |
| `GET /reports?site_id={site_id}` | Maps open/resolved reports; fetches attached photos with authorization. |
| `POST /photos` | Multipart JPEG/PNG, at most 5 MB; returns `{photo_key}`. |
| `POST /photos/{photo_key}/suggestion` | Optional authenticated Gemini suggestion for the uploader's private photo. `suggestion: null` leaves the category unselected; the crew member makes the final choice. This additive route is not required for basic contract v1.1 reporting. |
| `GET /photos/{photo_key}` | Fetches the protected image as a blob for an object URL; no public photo URL is assumed. |
| `POST /reports` | JSON with numeric `site_id`, `hazard_type`, `severity`, `description`, optional paired coordinates and `photo_key`. |
| `GET /briefings/{site_id}` | One latest briefing; 404 renders no briefing, other errors remain errors. |

The backend upload route names the multipart field `file`; `api.photoField`
defaults to that value. In live HTTP mode, choosing a photo uploads it once,
then requests a suggestion. A manual category choice always wins, and a late
suggestion from a replaced photo is ignored. The same upload key is reused
when the report is submitted. Selecting and abandoning a photo can leave an
unattached private upload; Aryan's cleanup helper handles old orphans safely.

The browser never sends `reporter_id`, status, creation time or a raw image inside report JSON. Those values are server-owned. A successful photo upload is reused if report creation is definitively rejected and retried. A timeout/connection loss after a write is treated as uncertain: check existing reports before submitting again. Local request IDs prevent duplicate in-flight submissions in the same page session; the contract does not promise server idempotency.

Archived status, briefing history, preferences and email controls are hidden by default, with their postponed code retained. Do not enable them or build endpoints until the team agrees a contract update. Crew screens do not resolve reports; `PATCH /reports/{id}` remains supervisor-owned.

## DeepSpace live updates

The default HTTP adapter now lazily imports Alan’s shared
`../realtime/deepspace-source.js` listener. Public connection settings are in
`crew-config.js` under `api.realtime` and match the shared contract. No global
hook is required. Mock mode keeps browser-only demo events and never opens a
DeepSpace WebSocket. Serve the `page/` folder structure so `/realtime/` exists;
the crew local preview already supports that route.

Recognized notices are `alert.started`, `alert.updated`, `alert.cleared`,
`report.created`, `report.resolved` and `scores.updated`. The last one carries
`{site_ids: [...]}` rather than a single `site_id`. Unknown event types and
invalid or unrelated IDs are ignored.

DeepSpace carries public IDs only. The adapter checks the Auth0 session before
listening, but sends no bearer token to the anonymous WebSocket. All actual
site details, scores, reports and private photos still use the authorized API.
Notice scores or deadlines never replace an API response.

For the selected crew site, relevant notices fetch fresh site detail and
alerts; report notices also refresh the visible report list. Global supervisor
and Atlas subscriptions fetch one bulk site list. Their UI event includes
`sites` and the affected `site_ids`, so rankings and map colors update without
a duplicate list request. The supervisor refreshes its selected detail when
that plant is affected. API read failures leave notifications disconnected.

Bursts of score notices are coalesced: at most one score refresh is in flight
and one is queued. The affected IDs merge while waiting. Alert and report
events retain their ordering. A confirmed reconnect fetches a fresh snapshot
to recover changes missed offline. Retries use backoff; leaving a screen closes
the subscription and ignores late source loads, responses and messages.

Notification connection status describes the WebSocket and API refresh, not
the health of the lightning observation feed. A countdown reaching zero is not
permission to resume. Only a matching `alert.cleared` notice with a fresh API
response lacking the hold confirms clearance. Existing holds cannot be
shortened by older responses.

Advanced integrations can still supply `api.realtimeSource` to `createHTTPAPI`,
or provide `window.PlanITCrewRealtime`. A source implements
`subscribe({site_id,onEvent,onConnection,onError})` and returns an unsubscribe
function (or a promise of one). Overrides do not receive Auth0 tokens.
`window.PlanITCrewAPI` can still replace the complete HTTP adapter when custom
transport is selected; it must implement the UI types in `crew-contract.d.ts`.

## Verification and remaining team work

From `page/crew/`:

```sh
node dev/check.mjs
node --test
node dev/check-api.mjs
```

The last command is a read-only security smoke check against the local API at `http://127.0.0.1:8010`. It checks that `/health` responds and anonymous `GET /sites` returns 401, or fail-closed 503 when Auth0 is not configured. Set `PLANIT_API_BASE_URL` to another `http://127.0.0.1` port if needed. It never sends a bearer token and does not prove real Auth0 login.

At verification, the sample server served sites, detail, alerts, briefings and reports. It did not yet register photo upload/view or report creation routes. Those flows are covered by simulated HTTP tests, pending real endpoint integration. The shared listener is now wired and its public subscription handshake was verified. Auth0 settings and the database-backed API are still needed for end-to-end live browser testing. Test two devices, a new-strike reset, disconnect/reconnect, explicit clear, protected photo visibility and a persisted report once those services are ready. Briefing scheduling and 6 PM delivery remain backend responsibilities.

Aryan owns the supervisor dashboard. `crew-supervisor.html/js` restores the original crew-owned supervisor preview, sharing crew Auth0, adapters, demo scores and the 60 monitored plants. It links to the separate `crew-atlas.html` 2D/3D map. Aryan’s dashboard files remain unchanged.
