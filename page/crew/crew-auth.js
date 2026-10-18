/* Why: Keep the callback and workspace in one document so memory-only tokens survive. */
import {config} from './crew-config.js';
import {siteParameter} from './crew-routing.js';
import {expiredSessionError, isSessionExpired} from '../shared/auth-session.mjs';
import {reportSessionExpired, sessionExpired} from './crew-session.js';
let client, demo = false, initializing;
export const authConfigured = () => Boolean(config.auth.domain && config.auth.clientId);

export async function initAuth() {
  if (!authConfigured()) return {};
  if (initializing) return initializing;
  initializing = (async () => {
    if (!window.auth0) await new Promise((resolve, reject) => {
      const script = document.createElement('script');
      script.src = 'https://cdn.auth0.com/js/auth0-spa-js/2.0/auth0-spa-js.production.js';
      script.onload = resolve;
      script.onerror = () => reject(new Error('Secure sign-in could not load. Check your connection and try again.'));
      document.head.append(script);
    });
    client = new window.auth0.Auth0Client({
      domain: config.auth.domain, clientId: config.auth.clientId, cacheLocation: 'memory',
      useRefreshTokens: true, useRefreshTokensFallback: false,
      authorizationParams: {redirect_uri: config.auth.redirectUri,
        scope: 'openid profile email offline_access',
        ...(config.auth.audience ? {audience: config.auth.audience} : {})}
    });
    const query = new URLSearchParams(location.search);
    if (query.has('state') && (query.has('code') || query.has('error'))) {
      try {
        const result = await client.handleRedirectCallback();
        return result.appState || {};
      } finally {
        history.replaceState({}, document.title, config.auth.redirectUri);
      }
    }
    if (query.has('error')) throw new Error('Sign-in was not completed. Please try again.');
    try { await client.checkSession(); }
    catch (error) {
      // An expired session or blocked silent consent still allows top-level login.
      if (!isSessionExpired(error)) throw error;
    }
    return {};
  })();
  try { return await initializing; }
  catch (error) { initializing = undefined; client = undefined; throw error; }
}
export async function session() {
  if (demo) return {name: 'Sample preview', demo: true};
  return client && await client.isAuthenticated() ? await client.getUser() : null;
}
export async function signIn() {
  if (!client) throw new Error('Sign-in is not connected yet. Please try again later.');
  const siteId = siteParameter(new URLSearchParams(location.search).get('site'));
  await client.loginWithRedirect({appState: {siteId}});
}
export function enterDemo() {
  if (config.dataMode !== 'mock') throw new Error('Sample preview is disabled in live mode.');
  demo = true;
}
export async function accessToken() {
  if (sessionExpired()) throw expiredSessionError();
  if (!client || !config.auth.audience) throw new Error('A signed-in session and the API audience are required.');
  try { return await client.getTokenSilently(); }
  catch (error) {
    if (isSessionExpired(error)) { reportSessionExpired(error); throw expiredSessionError(error); }
    throw error;
  }
}
export async function signOut() {
  if (demo) { demo = false; location.assign(config.auth.logoutReturnTo); return; }
  if (client) await client.logout({logoutParams: {returnTo: config.auth.logoutReturnTo}});
}
