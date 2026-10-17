// Public browser settings only. Never place client secrets or API keys here.
export const config = Object.freeze({
  mode: 'sample', // Change to 'live' after the backend and Auth0 are configured.
  apiBase: 'http://127.0.0.1:8000',
  requestTimeoutMs: 20000,
  pollMs: 30000,
  staleAfterMinutes: 60, // Display advisory; this is not a safety/alert rule.
  auth: {
    domain: '',
    clientId: '',
    audience: '',
    rolesClaim: 'https://planit-control/roles',
    redirectUri: new URL('index.html', import.meta.url).href,
    logoutReturnTo: new URL('index.html', import.meta.url).href
  }
});
