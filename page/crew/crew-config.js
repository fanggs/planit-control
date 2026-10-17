/* Frontend part 2
Commit: feat(crew): add authenticated backend connection adapters
Why: Keep authentication and configurable network contracts separate from the UI; a failed live request must never become a synthetic success.
*/
// Isaiah-owned frontend settings. Public identifiers only. Never put a client secret here.
export const config = {
  dataMode: 'mock', // Switch to 'live' after configuring Auth0 and the HTTP or custom adapter.
  transport: 'http', // 'custom' uses window.PlanITCrewAPI; 'http' uses crew-http.js.
  api: {
    baseURL: '', // For example https://api.your-domain.example; public URL, never secrets.
    timeoutMs: 20000,
    heartbeatMs: 45000,
    routes: {
      sites: '/sites', site: '/sites/{id}',
      reports: '/reports', briefings: '/sites/{id}/briefings',
      briefing: '/sites/{id}/briefings/{briefing_id}',
      preferences: '/sites/{id}/briefing-preferences', events: '/events'
    }
  },
  // UI access is convenience only; the API must independently enforce permissions.
  authRoleClaim: 'https://planit-control/roles',
  themeStylesheet: null, // Aryan supplies the actual shared stylesheet URL; do not edit his file.
  auth: {
    domain: '',
    clientId: '',
    audience: '', // Alan/Aryan's API identifier, required for API access tokens.
    // Register this exact callback and the home logout URL in the Auth0 application.
    redirectUri: new URL('login.html', location.href).href,
    logoutReturnTo: new URL('index.html', location.href).href
  }
};
