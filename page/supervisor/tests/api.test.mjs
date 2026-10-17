import test from 'node:test';
import assert from 'node:assert/strict';
import {createAPI} from '../api.js';

test('contract requests send bearer headers, correct paths and only the resolve status', async () => {
  const calls = [];
  const api = createAPI({base: 'http://127.0.0.1:8000', token: async () => 'verified-token',
    fetcher: async (url, options) => { calls.push({url, options}); return new Response(JSON.stringify(url.endsWith('/sites/6045')
      ? {site_id: 6045, active_alerts: []} : []), {status: 200, headers: {'Content-Type': 'application/json'}}); }});
  await api.sites(); await api.detail(6045); await api.reports(6045); await api.alerts();
  await api.resolve('3f6c1a2e-0000-4000-8000-000000000001');
  assert.deepEqual(calls.map(call => new URL(call.url).pathname + new URL(call.url).search),
    ['/sites', '/sites/6045', '/reports?site_id=6045', '/alerts', '/reports/3f6c1a2e-0000-4000-8000-000000000001']);
  for (const {url, options} of calls) {
    assert.equal(options.headers.Authorization, 'Bearer verified-token');
    assert.equal(options.cache, 'no-store'); assert.equal(options.redirect, 'error');
    assert.equal(options.credentials, 'omit'); assert.ok(!url.includes('verified-token'));
  }
  assert.equal(calls.at(-1).options.method, 'PATCH');
  assert.deepEqual(JSON.parse(calls.at(-1).options.body), {status: 'resolved'});
});
test('a failed live request cannot turn into a sample success', async () => {
  const api = createAPI({base: 'https://api.example.com', token: async () => 'token', fetcher: async () =>
    new Response(JSON.stringify({error: {code: 'forbidden', message: 'Supervisor role required'}}), {status: 403})});
  await assert.rejects(api.sites(), /Supervisor role required/);
  const missingToken = createAPI({base: 'https://api.example.com', token: async () => '', fetcher: () => assert.fail('No request without a token')});
  await assert.rejects(missingToken.sites(), /valid access token/);
});
test('private photo response is a blob with bearer auth; traversal and HTML are rejected', async () => {
  let captured;
  const api = createAPI({base: 'https://api.example.com', token: async () => 'token', fetcher: async (url, options) => {
    captured = {url, options}; return new Response(new Uint8Array([1, 2, 3]), {headers: {'Content-Type': 'image/png'}});
  }});
  assert.equal((await api.photo('safe-token_123')).type, 'image/png');
  assert.equal(captured.url, 'https://api.example.com/photos/safe-token_123');
  assert.equal(captured.options.headers.Authorization, 'Bearer token');
  assert.throws(() => api.photo('../secret'), /Invalid private photo key/);
  const bad = createAPI({base: 'https://api.example.com', token: async () => 'token', fetcher: async () =>
    new Response('<script>bad</script>', {headers: {'Content-Type': 'text/html'}})});
  await assert.rejects(bad.photo('safe'), /not an allowed JPEG\/PNG/);
});
test('local API configuration permits only the requested loopback host', () => {
  for (const base of ['http://localhost:8000', 'http://0.0.0.0:8000', 'http://example.com', 'https://u:p@example.com']) {
    assert.throws(() => createAPI({base, token: async () => 't'}), /API URL/);
  }
});
