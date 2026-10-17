# Auth0 handoff for PlanIT Control

Auth0 signs people in. PlanIT's API decides what each signed-in person may do.
The browser receives an **ID token** for its workspace display and an **access
token** for API requests. The API validates the access token's signature,
issuer, audience, expiry and `sub` before trusting its roles. A role shown by
the page is never authorization by itself.

## Tenant setup (requires an Auth0 administrator)

1. Create an Auth0 **Single Page Application** for the PlanIT website. Copy its
   public domain and client ID. Do not put a client secret in browser code.
2. Create an Auth0 **API** with RS256 signing. Choose one stable API identifier
   (audience); the frontend and backend must use exactly the same value.
3. Create roles named exactly `crew` and `supervisor`, then assign them to the
   appropriate test users. The API allows either role to read sites, alerts,
   reports and photos or submit reports; only `supervisor` resolves a report.
4. Create a **Post-Login Action** using `api/auth/roles_action.js`. Deploy it and
   add it to the tenant's Login flow. The Action copies assigned Auth0 roles to
   the `https://planit-control/roles` claim in **both** token types. Merely
   committing the file does not install the Action in Auth0.
5. Add the website's exact callback, logout and web-origin URLs to the SPA's
   allowlists. For the supervisor's loopback preview they are callback/logout
   `http://127.0.0.1:4175/supervisor/index.html` and web origin
   `http://127.0.0.1:4175`. Use HTTPS on the deployed website. Isaiah must add
   the crew login URLs for the same SPA if it handles both workspaces.

Auth0 documentation: [SPA SDK](https://auth0.com/docs/libraries/auth0-single-page-app-sdk),
[custom claims](https://auth0.com/docs/secure/tokens/json-web-tokens/create-custom-claims),
[roles](https://auth0.com/docs/manage-users/access-control/configure-core-rbac/rbac-users/assign-roles-to-users).

## Values to connect in the repository

| Location | Public value needed |
| --- | --- |
| Backend environment | `AUTH0_DOMAIN` (tenant host), `AUTH0_AUDIENCE` (API identifier), optional `AUTH0_ROLES_CLAIM` if the team changes the default |
| `page/supervisor/config.js` | SPA domain, client ID, API audience, role-claim name; set `mode: 'live'` only when the API is protected and reachable |
| `page/crew/crew-config.js` | Same SPA/API values; Isaiah changes `dataMode` to `live` after crew integration |
| API CORS | Exact HTTPS frontend origin, plus exact `http://127.0.0.1` development origin when needed; Alan owns the app configuration |

The Auth0 domain is a host such as `example.us.auth0.com`, not a callback URL.
`AUTH0_ISSUER` may be supplied instead as its exact `https://.../` issuer.
The API audience is **not** the SPA client ID. Never commit `.env`, tokens,
private keys, or a client secret.

## What is already in code

- `hazard_auth.py` validates an Auth0 API access token against tenant JWKS and
  requires its namespaced role claim; it rejects invalid/missing tokens.
- Aryan's report/photo routers require `crew` or `supervisor`; only supervisors
  may resolve reports. The verified `sub` supplies `reporter_id`/`resolved_by`.
- The supervisor page uses Auth0 Universal Login, keeps tokens in memory, and
  sends the access token in a bearer header for live API requests.

**Still a team integration step:** `api/main.py` currently serves sample GETs
without Auth0 and does not register the report/photo routers. Alan must wire
the validator to the main routes, remove the conflicting sample `/reports`,
provide the shared database/alert callbacks, and set exact CORS origins. Sid
must provide the database and report table. Until then, do not present a sample
preview as a protected live service.

## Acceptance check with a configured tenant and API

1. A signed-out request to a protected API route returns 401; an invalid or
   wrong-audience token also returns 401.
2. A `crew` access token can read/submit a report but gets 403 on resolving it.
3. A `supervisor` access token can read and resolve reports. The response uses
   the verified token's `sub`, never a client-supplied reporter ID.
4. Sign in on the supervisor page: the identity appears, the map loads through
   authenticated API calls, private photos load only through authorized GETs,
   and Sign out returns to the configured page.
5. Repeat through Isaiah's crew login after its shared handoff is connected.
   Check a report appears on another signed-in browser, not just one local tab.

Offline Action test: `node --test tests/auth0_roles_action.test.mjs`. The
backend's signed-JWT and route tests are in `tests/test_hazard_auth_photos.py`
and `tests/test_hazard_registration.py`; they do not replace a real-tenant test.
