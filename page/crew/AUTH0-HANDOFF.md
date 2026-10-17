# Welcome page and Auth0 handoff

The local UI follows: `index.html` → `login.html` → Auth0 Universal Login →
`login.html` → the account's crew or supervisor workspace.

Set the public domain, client ID and API audience in `crew-config.js`.
There are no Auth0 client secrets in frontend code. The namespaced roles claim
defaults to `https://planit-control/roles`; Alan/Aryan must confirm it and add
`crew` / `supervisor` to the validated ID token using their Auth0 configuration.
No role is accepted from a URL, storage value or public workspace picker.
Both roles default to the supervisor workspace when both are present.
An authenticated account with no supported role gets an access message.
The API must independently validate access tokens and enforce permissions.

## Auth0 application URLs

Register the full deployed URL of `login.html` as the Allowed Callback URL.
Register the full deployed URL of `index.html` as the Allowed Logout URL.
Register the application origin in Allowed Web Origins. Include the local
development origin and callback/logout URLs separately when testing locally.
Example, when publishing `page/crew/` as the website root:

| Setting | Local example |
| --- | --- |
| Callback | `http://localhost:4174/login.html` |
| Logout | `http://localhost:4174/index.html` |
| Web origin | `http://localhost:4174` |

Use HTTPS for the deployed site. A plain HTTP LAN IP preview is for UI testing;
Auth0's SPA SDK requires a secure browser context (HTTPS or loopback localhost).
The callback mounts the chosen crew-owned workspace in the same document:
`crew.html` for crew, `crew-supervisor.html` for supervisor. The existing SDK
client and its memory-only token are reused; no access token, authorization
code or arbitrary return URL is passed between pages. The verified namespaced
role claim chooses the workspace. A public link never grants a live role.

The original supervisor preview uses the crew config and adapters, including
Auth0. A reload uses the SDK’s session check; cookie restrictions may require
another explicit Universal Login. Live sign-in still needs the team’s tenant
settings and deployment checks.

Aryan’s separate `page/supervisor/` application is unchanged and keeps its own
config and Auth0 session. Main crew navigation now opens the restored original
crew-owned supervisor preview rather than that separate application.

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

Use PlanIT Control as the application name and the team's hosted logo.
Verify sign-in, any verification/MFA prompt, and sign-out on the deployed domain.

## Demo and integration limits

The demo chooser is visible only when crew `dataMode` is `mock`. The crew,
atlas and restored supervisor preview share the same 60 real plant locations
and synthetic sample scores. `?demo=1` opens the sample supervisor directly in
mock mode; it cannot bypass live Auth0 checks. Actual
Auth0 verification cannot be tested until the team supplies its application settings.
Auth0's API calls are not simulated as successful in the preview.

The HTTP adapter now maps `api/CONTRACT.md` v1.1, including numeric site IDs,
nested score explanations, two-step photo/report creation, protected photo reads
and the latest briefing endpoint. See `BACKEND-CONNECTION.md` for the default
shared DeepSpace listener and optional provider overrides. Live browser integration still requires
Auth0 settings and the backend’s photo/report routes. The shared DeepSpace provider is already connected in the default adapter.
Contract v1.1 remains authoritative.

References:
- https://auth0.com/docs/libraries/auth0-single-page-app-sdk
- https://auth0.com/docs/customize/login-pages/universal-login/customize-themes
