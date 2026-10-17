/* Frontend part 2
Commit: feat(crew): add authenticated backend connection adapters
Why: Keep authentication and configurable network contracts separate from the UI; a failed live request must never become a synthetic success.
*/
import {config} from './crew-config.js';
let client, demo = false;
export const authConfigured = () => Boolean(config.auth.domain && config.auth.clientId);
export async function initAuth() {
  if (!authConfigured()) return;
  if (!window.auth0) await new Promise((resolve, reject) => {
    const script = document.createElement('script');
    script.src = 'https://cdn.auth0.com/js/auth0-spa-js/2.28/auth0-spa-js.production.js';
    script.onload = resolve; script.onerror = () => reject(new Error('Auth0 could not load. Check the connection and public application settings.'));
    document.head.append(script);
  });
  client = await window.auth0.createAuth0Client({
    domain:config.auth.domain, clientId:config.auth.clientId, cacheLocation:'memory',
    authorizationParams:{redirect_uri:config.auth.redirectUri, ...(config.auth.audience ? {audience:config.auth.audience} : {})}
  });
  const query = new URLSearchParams(location.search);
  if (query.has('error')) throw new Error('Sign-in was not completed. Try signing in again.');
  if (query.has('code') && query.has('state')) {
    await client.handleRedirectCallback();
    history.replaceState({}, document.title, config.auth.redirectUri);
  }
}
export async function session() {
  if (demo) return {name:'Crew preview', demo:true};
  return client && await client.isAuthenticated() ? await client.getUser() : null;
}
export async function signIn() {
  if (!client) throw new Error('Auth0 settings are not available yet.');
  await client.loginWithRedirect();
}
export function enterDemo() {
  if (config.dataMode !== 'mock') throw new Error('Sample preview is disabled in live mode.');
  demo = true;
}
export async function accessToken() {
  if (!client || !config.auth.audience) throw new Error('A signed-in session and Alan/Aryan’s API audience are required.');
  return client.getTokenSilently();
}
export async function signOut() {
  if (demo) {demo=false; return;}
  if (client) await client.logout({logoutParams:{returnTo:config.auth.redirectUri}});
}
