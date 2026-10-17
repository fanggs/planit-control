import test from 'node:test';
import assert from 'node:assert/strict';
import {createAuth} from '../auth.js';

const settings = {domain: 'example.auth0.com', clientId: 'public-client', audience: 'https://planit-api',
  rolesClaim: 'https://planit-control/roles', redirectUri: 'http://127.0.0.1:4175/supervisor/index.html',
  logoutReturnTo: 'http://127.0.0.1:4175/supervisor/index.html'};
function fixture(search = '', authenticated = true) {
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
    auth0: {Auth0Client}, location: {search},
    history: {replaceState(...args) { calls.push(['history', ...args]); }}
  }};
}
test('Auth0 uses memory tokens and the validated SDK identity, not role query strings', async () => {
  const {browser, calls} = fixture('?role=supervisor');
  const auth = createAuth(settings, browser);
  assert.equal((await auth.initialize()).sub, 'auth0|verified');
  assert.equal(await auth.token(), 'validated-access-token');
  assert.equal(calls[0][1].cacheLocation, 'memory');
  assert.equal(calls[0][1].authorizationParams.audience, settings.audience);
  assert.deepEqual(calls[1], ['check']);
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
