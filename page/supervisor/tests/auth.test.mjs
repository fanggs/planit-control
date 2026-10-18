import test from 'node:test';
import assert from 'node:assert/strict';
import {createAuth, shouldResumeSignIn} from '../auth.js';

const settings = {domain: 'example.auth0.com', clientId: 'public-client', audience: 'https://planit-api',
  rolesClaim: 'https://planit-control/roles', redirectUri: 'http://127.0.0.1:4175/supervisor/index.html',
  logoutReturnTo: 'http://127.0.0.1:4175/supervisor/index.html'};
function fixture(search = '', authenticated = true, href = settings.redirectUri) {
  const calls = [];
  class Auth0Client {
    constructor(options) { calls.push(['options', options]); }
    async checkSession() { calls.push(['check']); }
    async handleRedirectCallback() { calls.push(['validated-callback']); }
    async isAuthenticated() { return authenticated; }
    async getUser() { return {sub: 'auth0|verified', [settings.rolesClaim]: ['supervisor']}; }
    async getTokenSilently() { return 'validated-access-token'; }
    async loginWithRedirect() { calls.push(['login']); }
    async logout(options) { calls.push(['logout', options]); }
  }
  return {calls, browser: {
    auth0: {Auth0Client}, location: {search, href},
    history: {replaceState(...args) { calls.push(['history', ...args]); }}
  }};
}
test('Auth0 uses memory tokens and the validated SDK identity, not role query strings', async () => {
  const {browser, calls} = fixture('?role=supervisor');
  const auth = createAuth(settings, browser);
  assert.equal((await auth.initialize()).sub, 'auth0|verified');
  assert.equal(await auth.token(), 'validated-access-token');
  assert.equal(calls[0][1].cacheLocation, 'memory');
  assert.equal(calls[0][1].useRefreshTokens, true);
  assert.equal(calls[0][1].useRefreshTokensFallback, false);
  assert.match(calls[0][1].authorizationParams.scope, /offline_access/);
  assert.equal(calls[0][1].authorizationParams.audience, settings.audience);
  assert.deepEqual(calls[1], ['check']);
});
test('a missing rotated refresh token requires a new interactive sign-in', async () => {
  const {browser} = fixture();
  browser.auth0.Auth0Client.prototype.getTokenSilently = async () => {
    throw Object.assign(new Error('No refresh token'), {error: 'missing_refresh_token'});
  };
  const auth = createAuth(settings, browser);
  await auth.initialize();
  await assert.rejects(auth.token(), error => error.code === 'session_expired' && error.status === 401);
});
test('redirect callbacks are validated by the SDK and callback parameters are removed', async () => {
  const {browser, calls} = fixture('?code=authorization-code&state=state');
  await createAuth(settings, browser).initialize();
  assert.equal(calls[1][0], 'validated-callback');
  assert.equal(calls[2][0], 'history');
  assert.equal(calls[2].at(-1), settings.redirectUri);
});
test('missing configuration or sign-in blocks live tokens', async () => {
  await assert.rejects(createAuth({...settings, audience: ''}, fixture().browser).initialize(), /Live mode needs/);
  const auth = createAuth(settings, fixture('?role=supervisor', false).browser);
  assert.equal(await auth.initialize(), null);
  await assert.rejects(auth.token(), /Sign in/);
});
test('sign-in refuses IDE previews and unregistered callback paths before loading Auth0', async () => {
  const {browser, calls} = fixture('', false, 'http://localhost:63342/planit-control/page/supervisor/index.html');
  const auth = createAuth(settings, browser);
  assert.equal(auth.configured, false);
  await assert.rejects(auth.initialize(), /preview/);
  await assert.rejects(auth.login(), /preview/);
  assert.deepEqual(calls, []);
  assert.equal(createAuth({...settings, redirectUri: 'http://127.0.0.1:4175/supervisor/'}, fixture().browser).configured, false);
});
test('failed Auth0 callbacks clean the URL and leave a usable retry', async () => {
  const {browser, calls} = fixture('?error=access_denied&state=state', false);
  browser.auth0.Auth0Client.prototype.handleRedirectCallback = async () => { throw new Error('Authorization denied'); };
  const auth = createAuth(settings, browser);
  await assert.rejects(auth.initialize(), /Authorization denied/);
  assert.equal(calls.find(entry => entry[0] === 'history').at(-1), settings.redirectUri);
  await auth.login();
  assert.ok(calls.some(entry => entry[0] === 'login'));
});
test('top-level sign-in handoff is requested only for an explicit start or a navigation hint', () => {
  assert.equal(shouldResumeSignIn('?start=1', false), true);
  assert.equal(shouldResumeSignIn('', true), true);
  assert.equal(shouldResumeSignIn('?start=0', false), false);
  assert.equal(shouldResumeSignIn('?code=abc&state=xyz', false), false);
});
