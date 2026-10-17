# Crew backend connection — contract v1.1

`api/CONTRACT.md` is the source of truth. An **adapter** translates API data into the existing screen fields. The HTTP adapter now implements v1.1; internal display aliases are retained so the screens and local demo keep working.

## Configure a live connection

In `crew-config.js`, supply the public Auth0 domain, client ID, API audience and API `baseURL`, then set `dataMode: 'live'` and retain `transport: 'http'`. See `AUTH0-HANDOFF.md` for callback URLs. The API must allow the frontend origin and validate the bearer access token on every protected request. Keep secrets out of frontend settings.

Default mode remains `mock`. Live errors never substitute synthetic conditions. The sample API's `model_version: 'sample'` is labeled as sample data rather than a trained model.

## Field translations

| Contract field | Existing screen field |
| --- | --- |
| `site_id` integer | `id` / selected site ID string |
| `utility` | `operator` |
| Nested detail `score.score` | Numeric `score` |
| `scored_at` | `score_updated_at` |
| Factor `hazard_type` | Readable factor `name`; canonical type is also retained |
| `flooding`, `soil_saturation` | Display cards `flood`, `soil` |
| Report `hazard_type` | Display `category` |
| Alert `level: 'stop_work'` | Lightning display `status: 'hold'` |
| Alert `clear_at`, `last_trigger_at`, `trigger.distance_mi` | `all_clear_at`, `last_strike_at`, `distance_miles` |
| Briefing `text`, `for_date` | `body`, `valid_date` |

Outbound requests always use contract names and numeric site IDs. Weather stays a display card; its report category maps to `other`, never a `weather` hazard type. Contributions remain signed score points. Baseline plus contributions must match the score within 0.05; inconsistent explanations show an unavailable message. Scores are never estimated by the live frontend. Report warnings sit beside the score and do not change it.

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
| `GET /photos/{photo_key}` | Fetches the protected image as a blob for an object URL; no public photo URL is assumed. |
| `POST /reports` | JSON with numeric `site_id`, `hazard_type`, `severity`, `description`, optional paired coordinates and `photo_key`. |
| `GET /briefings/{site_id}` | One latest briefing; 404 renders no briefing, other errors remain errors. |

**Confirm with Aryan:** the contract does not name the multipart image field. `api.photoField` defaults to `file` and can be changed without editing the form.

The browser never sends `reporter_id`, status, creation time or a raw image inside report JSON. Those values are server-owned. A successful photo upload is reused if report creation is definitively rejected and retried. A timeout/connection loss after a write is treated as uncertain: check existing reports before submitting again. Local request IDs prevent duplicate in-flight submissions in the same page session; the contract does not promise server idempotency.

Archived status, briefing history, preferences and email controls are hidden by default, with their postponed code retained. Do not enable them or build endpoints until the team agrees a contract update. Crew screens do not resolve reports; `PATCH /reports/{id}` remains supervisor-owned.

## Alan's DeepSpace bridge

The adapter no longer opens `/events`. Alan supplies `window.PlanITCrewRealtime` before starting the workspace (or `api.realtimeSource` when constructing an HTTP adapter in tests). This is a local frontend integration interface, not a proposed backend endpoint:

```js
window.PlanITCrewRealtime = {
  async subscribe({site_id, accessToken, onEvent, onConnection, onError}) {
    // Use the team's actual DeepSpace SDK here.
    // site_id is numeric (or null for an authorized all-site subscription).
    // Forward each contract notice as {type: eventName, ...payload}.
    // Call onConnection(true) only when the SDK subscription is connected.
    // Call onConnection(false) / onError(error) on connection loss.
    // Return a function that removes listeners and unsubscribes.
    return () => {};
  }
};
```

The empty function above documents the interface only; it is not installed or treated as a working connection. Never put DeepSpace server keys in this hook.

Recognized notices: `alert.started`, `alert.updated`, `alert.cleared`, `report.created`, `report.resolved`, with the contract's IDs. The adapter validates and filters IDs, then fetches details from the API. It does not trust the optional notice deadline as an authoritative snapshot. Report notices also refresh the report list. Reconnection obtains a fresh token, resynchronizes the site and active alerts, and uses backoff. Site changes and sign-out remove the old subscription and timers.

Without a provider, the screen stays disconnected. Connection heartbeats mean notification transport health only; they do not prove the lightning feed is healthy. A countdown reaching zero is not permission to resume. A matching `alert.cleared` notice plus a fresh API response without the hold can clear it; an absent alert on an ordinary snapshot stays unknown. A later nearby strike extends the deadline, and older responses cannot shorten it.

An optional custom `window.PlanITCrewAPI` can still replace the HTTP adapter using the UI types in `crew-contract.d.ts`; it must perform the same contract translation and token handling itself.

## Verification and remaining team work

From `page/crew/`:

```sh
node dev/check.mjs
node --test
node dev/check-api.mjs
```

The last command is a read-only check against Alan's local API at `http://localhost:8010`. It requires `/health` to identify the server as sample data. Set `PLANIT_API_BASE_URL` for a different sample server. Its sample bearer value is not a real Auth0 token or a production authentication check.

At verification, the sample server served sites, detail, alerts, briefings and reports. It did not yet register photo upload/view or report creation routes. Those flows are covered by simulated HTTP tests, pending real endpoint integration. Auth0 settings and Alan's SDK bridge are still needed for live browser testing. Test two devices, a new-strike reset, disconnect/reconnect, explicit clear, protected photo visibility and a persisted report once those services are ready. Briefing scheduling and 6 PM delivery remain backend responsibilities.

Aryan owns the supervisor dashboard. `crew-supervisor.html/js` now opens the primary 60-site map as a compatibility entry. Aryan’s separate dashboard is unchanged.
