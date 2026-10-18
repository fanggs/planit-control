# Alan handoff: Auth0 renewal, live notices, and final signed-in test

This is the handoff for [#19](https://github.com/fanggs/planit-control/issues/19), [#20](https://github.com/fanggs/planit-control/issues/20), [#22](https://github.com/fanggs/planit-control/issues/22), and [#23](https://github.com/fanggs/planit-control/issues/23). It supplements `api/CONTRACT.md`; it does not change the wire contract. Do not put access tokens, publisher secrets, photos, or private report text in GitHub comments or browser logs.

## Deployment order

1. Aryan pushes the reviewed frontend commits. Alan pulls the new commit and deploys the static `page/` files together. Do not deploy only one JavaScript module: both apps now import `page/shared/auth-session.mjs`, and the crew and supervisor screens share the heat-index wording helper.
2. In the Auth0 **development** tenant, confirm the PlanIT SPA has refresh-token rotation on, zero-second rotation overlap, and the API `https://planit-control.aasi/api` has **Allow Offline Access** on. Keep `page/crew/crew-auth.js` and `page/supervisor/auth.js` at `cacheLocation: 'memory'`; do not put refresh tokens in local storage. The SPA requests `offline_access` and disables the silent-iframe fallback.
   Aryan enabled and saved API **Allow Offline Access** in the development tenant on 2026-10-18. This verifies the tenant setting, not that an existing browser session has a refresh token or that renewal survives an access-token lifetime.
3. After the deploy, every tester signs out and signs back in once. Old sessions do not acquire refresh tokens retroactively. A new page/document also loses the memory-only token. The crew workspace and atlas now have their own exact callback URLs and can use a top-level Auth0 SSO handoff if silent recovery is blocked. With an active Auth0 session, the deployed HTTPS site should return without another credential prompt, although it is still a full-page round trip; an expired session requires sign-in again. Loopback callbacks may still show Auth0's consent screen because they are not verifiable public origins. Never diagnose this as a dead API or silently show sample data. This is not token persistence or a single-document SPA.
   Alan's existing account has both `crew` and `supervisor` in the development tenant; the additional role appears in app tokens only after he signs out and back in. His old token may still show `crew` alone.
4. Alan verifies the deployed API and `planit-realtime` bridge use the same public bridge URL/app ID. Keep `PLANIT_NOTIFY_SECRET` only in server/job environments. The frontend sends bearer tokens only to the API; the anonymous notice socket receives IDs, never photos, report bodies, tokens, or the publisher secret.

## Trace one notice through both browsers (#20)

Use one designated development site and a clearly labeled private test report. Record the deployed Git SHA and approximate UTC time; coordinate with Alan before publishing an alert/replay. In two signed-in browsers, open DevTools → Network and filter by `WS`, `/api/`, and `planit-realtime`. Record status codes and event type/ID only.

| Hop | Alan checks | Aryan checks |
| --- | --- | --- |
| Database commit | Report/alert/score change is committed; no test insert is left ambiguous | Crew POST receipt has the agreed site/report ID |
| Publisher | `api/realtime.py` returns true or logs a sanitized failure; bridge URL and secret match | No publisher secret in page source or Network requests |
| Bridge | `events` record accepted; `site_id`, `report_id`/`alert_id`, or `site_ids` match `api/CONTRACT.md` | WebSocket opens and `core.query_result` confirms the `events` subscription; an empty collection is not an error |
| Browser | No bridge error or proxy/origin block | `core.record_change` triggers an authorized `/api/sites/{id}`, `/api/alerts`, `/api/reports`, or `/api/sites` refetch, then a visible update |

The notification indicator describes **transport only**. Weather/lightning/NWS freshness is separate. A quiet site should remain connected without fake hazard activity; the crew heartbeat starts only after a confirmed subscription. On offline/online recovery both apps reconnect and refetch authoritative API state. An expired Auth0 session stops the reconnect loop and asks for sign-in, while retaining a warning that displayed data may be stale. A missing/stale hazard feed never becomes an all-clear because the socket reconnected.

The crew and supervisor listeners also close when their document becomes hidden and reconnect with an authorized refetch when it becomes visible. Test a background/foreground cycle on both devices; returning to a tab must not duplicate a subscription or show “connected” until the new snapshot succeeds.

If the notice does not reach a browser, isolate the first missing hop. HTTP 401 means renew/sign in; HTTP 403 means role/API policy; a failed WebSocket handshake or missing `core.query_result` points to bridge/origin/protocol configuration; a bridge record with no refetch points to event shape or site-ID filtering. Do not print the Authorization header or private payload while diagnosing.

## Conditions acceptance (#19)

Compare crew cards and supervisor detail against the same signed-in `/api/sites/{id}` response. The weather and soil cards show measurements with units, source, and observation time while stating that no safety severity was inferred. Below 80 °F, the implemented heat-index formula is not applicable; above 112 °F it is outside its supported range; a null index in the middle of that range is unavailable, not safe. The API does not yet expose humidity or an explicit null reason, so the UI must not claim a more precise cause. Lightning uses `lightning_status` and active holds; flood/fire-weather use `warnings_status` and actual active event types. A failed or stale check is unavailable even if the event list is empty. Historical wildlife sightings are not live encounter clearance. Test real zero readings, an existing lightning hold, a cancelled NWS warning, and disconnected notifications independently.

The crew condition cards now show the site-local reading time and its age. Their 5-minute lightning and 15-minute NWS clear states are re-evaluated against the clock, including when a refresh fails. A stop-work card continues to show the authoritative hold. An alert does not inherit a source link from an unrelated watch or warning; its own matching event may supply a link.

## Final phone + supervisor run (#22)

This is a **post-deploy, two-person** test, not a unit-test substitute. Alan coordinates the designated development site and labeled replay; Aryan uses the supervisor account in a second signed-in browser; a crew tester uses a real phone. Do not post screenshots that reveal private report text or photos.

- Phone: sign in; select the designated site; check lightning state/reason, conditions and source times, Prototype screening target/factors, wildlife limitations, and tomorrow's briefing. Submit one high-severity private test report with a photo. Confirm the receipt and private retrieval. A crew PATCH to resolve must receive 403.
- Supervisor: without manually refreshing, see the report and warning; check the map score/Prototype label; resolve it; verify the crew view updates without refresh. Ask one `/ask` question and verify answer, source links, and SQL.
- Alan: run only the labeled Turkey Point replay; verify stop-work countdown on both screens and authoritative clear after 30 quiet minutes. Verify any *actual* NWS warning from `/alerts` without inventing one. Restart `planit-api` and verify persistence. Logged-out data routes return 401.
- Sid: confirm 60/60 current screening rows and collector freshness within the agreed one-hour window.
- Auth renewal: with Alan coordinating a harmless test notice, verify a newly signed-in session remains live beyond an access-token lifetime. Then test a deliberately expired/revoked session: both apps stop reconnecting and show a sign-in action, never a false connected indicator or unmarked sample fallback. Restore any temporary tenant lifetime setting immediately and record old/new values.

Only mark #22 complete after the deployed SHA, two-device observations, and sanitized result for each item are recorded. Local commits alone cannot satisfy this acceptance test.

## Verification already available before the phone run

On 2026-10-18, local frontend syntax and JavaScript tests passed; 142 Python tests passed with the hazard-dev and forecast dependency sets in a disposable virtual environment. These cover condition-state and expiry fixtures, browser visibility/reconnect cleanup, API authorization, reports, and private-photo behavior, but are not proof of the deployed two-device path. The loopback preview now serves imported `.mjs` modules and opens the clearly labeled sample crew workspace without depending on the Auth0 CDN. The signed-in supervisor site at `https://foresite.work/supervisor/` showed 60 sites and a connected notice channel; its `/ask` panel answered a read-only Florida plant-count question with an EIA source and SQL. That observation predates deployment of the current crew/reconnect edits. A real crew-signed-in phone was not available, so the private photo, crew-only 403, cross-browser report/resolve, labeled replay and renewal-over-lifetime checks remain open.
