// Auth0 SPA SDK validates the redirect/ID token and stores tokens in memory.
// The API still validates access-token signature, issuer, audience, expiry and roles.
import {expiredSessionError, isSessionExpired} from '../shared/auth-session.mjs';

export function createAuth(settings, browser = window) {
  let client;
  const configured = Boolean(settings.domain && settings.clientId && settings.audience && settings.rolesClaim);
  async function initialize() {
    if (!configured) throw new Error('Live mode needs an Auth0 domain, client ID, API audience and roles claim in config.js.');
    if (!browser.auth0?.Auth0Client) await new Promise((resolve, reject) => {
      const script = browser.document.createElement('script');
      script.src = 'https://cdn.auth0.com/js/auth0-spa-js/2.0/auth0-spa-js.production.js';
      script.onload = resolve;
      script.onerror = () => reject(new Error('Auth0 could not load. Sign-in is unavailable.'));
      browser.document.head.append(script);
    });
    client = new browser.auth0.Auth0Client({domain: settings.domain, clientId: settings.clientId,
      cacheLocation: 'memory', useRefreshTokens: true, useRefreshTokensFallback: false,
      authorizationParams: {audience: settings.audience, redirect_uri: settings.redirectUri,
        scope: 'openid profile email offline_access'}});
    const query = new URLSearchParams(browser.location.search);
    if (query.has('state') && (query.has('code') || query.has('error'))) {
      try { await client.handleRedirectCallback(); }
      finally { browser.history.replaceState({}, '', settings.redirectUri); }
    } else {
      try { await client.checkSession(); }
      catch (error) {
        if (!isSessionExpired(error)) throw error;
      }
    }
    return await client.isAuthenticated() ? client.getUser() : null;
  }
  return {configured, initialize,
    async login() { if (!client) throw new Error('Auth0 is not initialized.'); return client.loginWithRedirect(); },
    async logout() { if (client) return client.logout({logoutParams: {returnTo: settings.logoutReturnTo}}); },
    async token() {
      if (!client || !(await client.isAuthenticated())) throw expiredSessionError();
      try { return await client.getTokenSilently(); }
      catch (error) { if (isSessionExpired(error)) throw expiredSessionError(error); throw error; }
    }};
}
