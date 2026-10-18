import test from 'node:test';
import assert from 'node:assert/strict';
import {createAPI} from '../api.js';
import {apiBaseForPage} from '../config.js';

test('deployed supervisor API stays on its HTTPS origin; local preview uses loopback only', () => {
  assert.equal(apiBaseForPage('https://fore-site.example/supervisor/config.js'), 'https://fore-site.example/api');
  assert.equal(apiBaseForPage('https://fore-site.example/supervisor/config.js?token=bad#fragment'), 'https://fore-site.example/api');
  assert.equal(apiBaseForPage('http://127.0.0.1:4175/supervisor/config.js'), 'http://127.0.0.1:8010');
  for (const page of ['http://45.32.216.198/supervisor/config.js', 'http://localhost:4175/supervisor/config.js',
    'http://0.0.0.0:4175/supervisor/config.js', 'file:///supervisor/config.js',
    'https://user:password@fore-site.example/supervisor/config.js']) {
    assert.equal(apiBaseForPage(page), '');
  }
});

test('contract requests send bearer headers, correct paths and only the resolve status', async () => {
  const calls = [];
  const api = createAPI({base: 'http://127.0.0.1:8000', token: async () => 'verified-token',
    fetcher: async (url, options) => { calls.push({url, options}); return new Response(JSON.stringify(url.endsWith('/sites/6045')
      ? {site_id: 6045, active_alerts: []} : options.method === 'PATCH'
        ? {id: '3f6c1a2e-0000-4000-8000-000000000001', status: 'resolved'} : []),
    {status: 200, headers: {'Content-Type': 'application/json'}}); }});
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
test('resolution requires a matching committed receipt', async () => {
  const id = '3f6c1a2e-0000-4000-8000-000000000001';
  for (const receipt of [{id, status: 'open'}, {id: '00000000-0000-4000-8000-000000000002', status: 'resolved'}]) {
    const api = createAPI({base: 'https://api.example.com', token: async () => 'token',
      fetcher: async () => new Response(JSON.stringify(receipt), {status: 200})});
    await assert.rejects(api.resolve(id), /receipt could not be verified/);
  }
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

test('request timeout also aborts a JSON body stalled after successful headers', async () => {
  let bodyAborted = false;
  const api = createAPI({base: 'http://127.0.0.1:8000', token: async () => 'token', timeoutMs: 10,
    fetcher: async (_url, {signal}) => ({ok: true, json: () => new Promise((resolve, reject) => {
      signal.addEventListener('abort', () => {
        bodyAborted = true;
        reject(new DOMException('Body read aborted', 'AbortError'));
      }, {once: true});
    })})});
  await assert.rejects(api.sites(), /request timed out/);
  assert.equal(bodyAborted, true);
});

test('ask submits one trimmed question with the supervisor bearer token and validates the answer', async () => {
  let sent;
  const api = createAPI({base: 'https://example.com/api', token: async () => 'supervisor-token',
    fetcher: async (url, options) => {
      sent = {url, options};
      return new Response(JSON.stringify({answer: 'Two plants matched.', sql: 'SELECT count(*) FROM public.sites',
        sources: [{label: 'EIA', url: 'https://www.eia.gov/'}]}), {status: 200});
    }});
  assert.equal((await api.ask('  How many plants?  ')).answer, 'Two plants matched.');
  assert.equal(sent.url, 'https://example.com/api/ask');
  assert.equal(sent.options.method, 'POST');
  assert.equal(sent.options.headers.Authorization, 'Bearer supervisor-token');
  assert.deepEqual(JSON.parse(sent.options.body), {question: 'How many plants?'});
  assert.equal(sent.options.cache, 'no-store');
  assert.equal(sent.options.credentials, 'omit');
  assert.equal(sent.options.redirect, 'error');
  assert.ok(!sent.url.includes('supervisor-token'));
});

test('ask keeps cannot-answer separate from service failure and rejects malformed responses', async () => {
  const base = {base: 'https://example.com/api', token: async () => 'token'};
  const cannot = createAPI({...base, fetcher: async () =>
    new Response(JSON.stringify({answer: null, reason: 'cannot_answer'}), {status: 200})});
  assert.deepEqual(await cannot.ask('What is the CEO favorite color?'), {answer: null, reason: 'cannot_answer'});
  const unavailable = createAPI({...base, fetcher: async () =>
    new Response(JSON.stringify({error: {code: 'service_unavailable', message: 'Question service unavailable'}}), {status: 503})});
  await assert.rejects(unavailable.ask('How many plants?'), error =>
    error.status === 503 && error.code === 'service_unavailable');
  const malformed = createAPI({...base, fetcher: async () =>
    new Response(JSON.stringify({answer: '<script>bad</script>', sql: null, sources: []}), {status: 200})});
  await assert.rejects(malformed.ask('How many plants?'), /invalid answer/);
});

test('ask validates question length before fetching and has a longer timeout than site reads', async () => {
  const api = createAPI({base: 'https://example.com/api', token: async () => 'token', timeoutMs: 5,
    fetcher: async (_url, options) => await new Promise((resolve, reject) => {
      const timer = setTimeout(() => resolve(new Response(JSON.stringify({answer: 'One plant.',
        sql: 'SELECT name FROM public.sites LIMIT 1', sources: []}), {status: 200})), 20);
      options.signal.addEventListener('abort', () => { clearTimeout(timer); reject(new DOMException('Aborted', 'AbortError')); }, {once: true});
    })});
  await assert.rejects(api.ask('  '), /between 3 and 500/);
  await assert.rejects(api.ask('x'.repeat(501)), /between 3 and 500/);
  assert.equal((await api.ask('Name one plant')).answer, 'One plant.');
});
