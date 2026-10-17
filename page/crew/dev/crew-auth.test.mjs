import test from 'node:test';
import assert from 'node:assert/strict';

// Exercise our callback behavior with an SDK double, without using a real tenant or token.
globalThis.location = {href: 'http://127.0.0.1:4174/login.html?code=one-use&state=checked', search: '?code=one-use&state=checked'};
globalThis.document = {title: 'PlanIT'};
let replaced, options, instances = 0, callbacks = 0, loginOptions;
globalThis.history = {replaceState(_state, _title, url) { replaced = url; }};
const user = {sub: 'sample-user', 'https://planit-control/roles': ['supervisor']};
globalThis.window = {auth0: {Auth0Client: class {
  constructor(value) { instances++; options = value; }
  async handleRedirectCallback() { callbacks++; return {appState: {siteId: '621'}}; }
  async checkSession() { throw new Error('A callback must not start silent login first.'); }
  async isAuthenticated() { return true; }
  async getUser() { return user; }
  async loginWithRedirect(value) { loginOptions = value; }
}}};
const {config} = await import('../crew-config.js');
config.auth.domain = 'example.auth0.com';
config.auth.clientId = 'public-example-id';
const auth = await import('../crew-auth.js');

test('callback is consumed once and the same in-memory client serves the workspace', async () => {
  const first = await auth.initAuth();
  const second = await auth.initAuth();
  assert.deepEqual(first, {siteId: '621'});
  assert.deepEqual(second, first);
  assert.equal(instances, 1);
  assert.equal(callbacks, 1);
  assert.equal(options.cacheLocation, 'memory');
  assert.equal(replaced, 'http://127.0.0.1:4174/login.html');
  assert.equal(await auth.session(), user);
});

test('login carries a plant selection without trusting a requested role or return URL', async () => {
  location.search = '?site=6072&role=supervisor&returnTo=https://example.com';
  await auth.signIn();
  assert.deepEqual(loginOptions, {appState: {siteId: '6072'}});
});

test('an unsuccessful callback removes its one-use parameters and does not create a session', async () => {
  location.search = '?error=access_denied&state=checked';
  window.auth0.Auth0Client = class {
    async handleRedirectCallback() { throw new Error('Sign-in was canceled.'); }
  };
  const failedAuth = await import('../crew-auth.js?failed-callback');
  await assert.rejects(failedAuth.initAuth(), /canceled/);
  assert.equal(replaced, 'http://127.0.0.1:4174/login.html');
  assert.equal(await failedAuth.session(), null);
});

test('an expired silent session still permits an explicit Auth0 sign-in', async () => {
  location.search = '';
  let redirected = false;
  window.auth0.Auth0Client = class {
    async checkSession() { throw Object.assign(new Error('Session expired'), {error: 'login_required'}); }
    async isAuthenticated() { return false; }
    async loginWithRedirect() { redirected = true; }
  };
  const expiredAuth = await import('../crew-auth.js?expired-session');
  await expiredAuth.initAuth();
  assert.equal(await expiredAuth.session(), null);
  await expiredAuth.signIn();
  assert.equal(redirected, true);
});
