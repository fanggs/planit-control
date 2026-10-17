/* Why: Keep authentication and configurable network contracts separate from the UI; a failed live request must never become a synthetic success. */
// Isaiah-owned frontend settings. Public identifiers only. Never put a client secret here.
export const config = {
  dataMode: 'mock', // Switch to 'live' after configuring Auth0 and the HTTP or custom adapter.
  transport: 'http', // 'custom' uses window.PlanITCrewAPI; 'http' uses crew-http.js.
  features: {briefingPreferences: false, briefingHistory: false, archivedReports: false},
  api: {
    baseURL: '', // For example https://api.your-domain.example; public URL, never secrets.
    timeoutMs: 20000,
    heartbeatMs: 45000,
    realtime: {baseURL: 'https://planit-realtime.app.space', appId: 'app_01M557EC8CQY7VDN5253P86ZBN'},
    photoField: 'file', // Confirm the multipart field name with Aryan; v1.1 does not specify it.
    routes: {
      sites: '/sites', site: '/sites/{id}',
      alerts: '/alerts', reports: '/reports',
      photos: '/photos', photo: '/photos/{photo_key}',
      briefing: '/briefings/{id}'
    }
  },
  // UI access is convenience only; the API must independently enforce permissions.
  authRoleClaim: 'https://planit-control/roles',
  themeStylesheet: '../shared/planit.css', // Shared tokens; crew components remain scoped.
  auth: {
    domain: 'dev-qtlneoet2ty1xxbc.us.auth0.com',
    clientId: 'HsFNjn2AmnjYmXW8XcTXVWrhJDvxrjQd',
    audience: 'https://planit-control.aasi/api', // Alan/Aryan's API identifier, required for API access tokens.
    // Register this exact callback and the home logout URL in the Auth0 application.
    redirectUri: new URL('login.html', location.href).href,
    logoutReturnTo: new URL('index.html', location.href).href
  }
};
