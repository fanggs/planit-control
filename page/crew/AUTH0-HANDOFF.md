# Welcome page and Auth0 handoff

The UI follows `/crew/index.html` → `/crew/login.html` → Auth0 Universal
Login → the account's crew or supervisor workspace. A signed-in crew member
moving to the crew map may make a brief top-level Auth0 round trip so the new
HTML document gets its own memory-only token. With a valid Auth0 session this
normally needs no second credential prompt.

Set the public domain, client ID and API audience in `crew-config.js`.
There are no Auth0 client secrets in frontend code. The namespaced roles claim
defaults to `https://planit-control/roles`; Alan/Aryan must confirm it and add
`crew` / `supervisor` to the validated ID token using their Auth0 configuration.
No role is accepted from a URL, storage value or public workspace picker.
Both roles default to the supervisor workspace when both are present.
An authenticated account with no supported role gets an access message.
The API must independently validate access tokens and enforce permissions.

## Auth0 application URLs

The development PlanIT Auth0 SPA has these exact crew callback URLs. Keep the
supervisor callback `/supervisor/index.html` as well. The matching logout URLs
are `/crew/index.html` and `/supervisor/index.html`; Allowed Web Origins are
`https://foresite.work` and `http://127.0.0.1:4174`.

| Origin | Exact crew callback paths |
| --- | --- |
| `https://foresite.work` | `/crew/login.html`, `/crew/crew.html`, `/crew/crew-atlas.html` |
| `http://127.0.0.1:4174` | `/crew/login.html`, `/crew/crew.html`, `/crew/crew-atlas.html` |

The same preview server hosts the supervisor dashboard at
`http://127.0.0.1:4174/supervisor/index.html`. Do not use PyCharm's built-in
`localhost:63342` preview for Auth0: that callback is intentionally not
registered. Open the actual development server on `127.0.0.1:4174`, or use
`https://foresite.work`. A different port or path is a different callback.

Use HTTPS for the deployed site. Keep local previews on `127.0.0.1` only;
Auth0's SPA SDK requires a secure browser context (HTTPS or loopback 127.0.0.1).
Each callback returns to the exact page that requested sign-in, preserving its
token in that page's memory. A verified `supervisor` role opens the canonical
`/supervisor/index.html` dashboard and establishes a separate Auth0 SDK
session there. The handoff carries no access token, role, or arbitrary return
URL. A per-tab boolean may request a top-level SSO handoff after a full-page
navigation; it is never treated as proof of identity or permission. If the
Auth0 session has expired, the user must sign in again. Never work around this
by putting tokens in URLs or browser storage.
On loopback, Auth0 may still show its **Authorize App** consent screen during
this round trip because a local callback is not a verifiable public origin.
The `https://foresite.work` handoff is the meaningful no-repeat-prompt test;
do not disable consent or broaden callback URLs merely to hide the local prompt.

Isaiah’s `crew-supervisor.html` remains a labeled sample preview for the
offline demo and direct development checks. The welcome page’s Supervisor
navigation opens Aryan’s live dashboard. `crew-config.js` now imports the
shared `page/shared/planit.css` design tokens without replacing crew styles.

The crew local preview server also serves `/supervisor/`, `/shared/` and
`/realtime/` for integrated testing; those existing routes remain available.

## Match Auth0's hosted page to the app

The hosted Auth0 page cannot inherit this repository's stylesheet. In the Auth0
tenant's Branding → Universal Login customization, use these theme values:

| Purpose | Color |
| --- | --- |
| Page background | `#080B0C` |
| Widget background | `#101716` |
| Main text | `#EDF3F1` |
| Secondary text | `#A2B1AD` |
| Primary button | `#A7EDC9` |
| Button text | `#0A1911` |
| Borders | `#293532` |
| Error text | `#FFB9AA` |

Use ForeSite as the application name and the team's hosted logo.
Verify sign-in, any verification/MFA prompt, and sign-out on the deployed domain.

## Demo and integration limits

The demo chooser is visible only when crew `dataMode` is `mock`. The crew,
atlas and restored supervisor preview share the same 60 real plant locations
and synthetic sample scores. `?demo=1` opens the sample supervisor directly in
mock mode; it cannot bypass live Auth0 checks. Actual
Auth0 verification cannot be tested until tenant callback URLs, roles, and
account assignments are configured.
Auth0's API calls are not simulated as successful in the preview.

The HTTP adapter now maps `api/CONTRACT.md` v1.1, including numeric site IDs,
nested score explanations, two-step photo/report creation, protected photo reads
and the latest briefing endpoint. See `BACKEND-CONNECTION.md` for the default
shared DeepSpace listener and optional provider overrides. The backend's
photo/report routes are registered in database mode; a real-tenant,
cross-device browser test is still required. The shared DeepSpace provider is
already connected in the default adapter.
Contract v1.1 remains authoritative.

References:
- https://auth0.com/docs/libraries/auth0-single-page-app-sdk
- https://auth0.com/docs/customize/login-pages/universal-login/customize-themes
