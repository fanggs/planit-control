// Public browser settings only. Never place client secrets or API keys here.
export const config = Object.freeze({
  mode: 'sample', // Change to 'live' after the backend and Auth0 are configured.
  apiBase: 'http://127.0.0.1:8010',
  requestTimeoutMs: 20000,
  pollMs: 30000,
  staleAfterMinutes: 60, // Display advisory; this is not a safety/alert rule.
  realtime: {
    baseURL: 'https://planit-realtime.app.space',
    appId: 'app_01M557EC8CQY7VDN5253P86ZBN'
  },
  auth: {
    domain: 'dev-qtlneoet2ty1xxbc.us.auth0.com',
    clientId: 'HsFNjn2AmnjYmXW8XcTXVWrhJDvxrjQd',
    audience: 'https://planit-control.aasi/api',
    rolesClaim: 'https://planit-control/roles',
    redirectUri: new URL('index.html', import.meta.url).href,
    logoutReturnTo: new URL('index.html', import.meta.url).href
  }
});
