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
The callback imports the chosen workspace in the same document so SDK tokens
remain in memory. Page reloads use Auth0's session check; if browser cookie
restrictions prevent renewal, the user can sign in again through Universal Login.

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

Sample workspace links are visible only when `dataMode` is `mock`. They load
synthetic conditions and never authenticate or grant API permissions. Actual
Auth0 verification cannot be tested until the team supplies its application settings.
Auth0's API calls are not simulated as successful in the preview.

The HTTP adapter now maps `api/CONTRACT.md` v1.1, including numeric site IDs,
nested score explanations, two-step photo/report creation, protected photo reads
and the latest briefing endpoint. See `BACKEND-CONNECTION.md` for Alan's
`window.PlanITCrewRealtime` bridge. Live browser integration still requires
Auth0 settings, the actual SDK provider and the backend's photo/report routes.
Contract v1.1 remains authoritative.

References:
- https://auth0.com/docs/libraries/auth0-single-page-app-sdk
- https://auth0.com/docs/customize/login-pages/universal-login/customize-themes
