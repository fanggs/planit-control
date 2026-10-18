// Public browser settings only. Never place client secrets or API keys here.
// The deployed dashboard uses the API proxy on its own HTTPS origin. A local
// preview keeps the separate 127.0.0.1 API port; public HTTP fails closed.
export function apiBaseForPage(pageURL) {
  const page = new URL(pageURL);
  if (page.username || page.password) return '';
  if (page.protocol === 'http:' && page.hostname === '127.0.0.1') {
    return 'http://127.0.0.1:8010';
  }
  return page.protocol === 'https:' ? new URL('/api', page).href : '';
}

export const config = Object.freeze({
  mode: 'live', // The labeled sample adapter remains available for offline development.
  apiBase: apiBaseForPage(import.meta.url),
  requestTimeoutMs: 20000,
  pollMs: 30000,
  staleAfterMinutes: 120, // hourly readings: an hour old is normal // Display advisory; this is not a safety/alert rule.
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
