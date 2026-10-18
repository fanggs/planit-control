import test from 'node:test';
import assert from 'node:assert/strict';
import {spawn} from 'node:child_process';
import {fileURLToPath} from 'node:url';

test('preview serves direct and trailing-slash entries, modules, shared styles and vendor assets', async t => {
  const server = spawn(process.execPath, [fileURLToPath(new URL('../dev/serve.mjs', import.meta.url))], {
    env: {...process.env, PORT: '0'}, stdio: ['ignore', 'pipe', 'pipe']});
  t.after(() => server.kill());
  const base = await new Promise((resolve, reject) => {
    const timeout = setTimeout(() => reject(new Error('Preview did not start')), 5000);
    server.once('error', reject);
    server.stdout.on('data', data => {
      const match = String(data).match(/http:\/\/127\.0\.0\.1:\d+/);
      if (match) { clearTimeout(timeout); resolve(match[0]); }
    });
    server.stderr.on('data', data => { clearTimeout(timeout); reject(new Error(String(data))); });
  });
  for (const path of ['/', '/supervisor/index.html', '/supervisor/', '/supervisor/app.js', '/supervisor/config.js',
    '/shared/planit.css', '/crew/crew-vendor/leaflet.js', '/realtime/deepspace-source.js', '/supervisor/sample-data/sites.json']) {
    assert.equal((await fetch(base + path)).status, 200, path);
  }
  const dashboard = await (await fetch(base + '/supervisor/')).text();
  assert.match(dashboard, /PlanIT Control for Sperry Tech/);
  assert.match(dashboard, /<form id="ask-form"/);
  assert.match(dashboard, /id="ask-question"[^>]*disabled required/);
  assert.match(dashboard, /id="ask-result"[^>]*hidden/);
  const redirect = await fetch(base + '/supervisor', {redirect: 'manual'});
  assert.equal(redirect.status, 308); assert.equal(redirect.headers.get('location'), '/supervisor/');
  assert.equal((await fetch(base + '/.env')).status, 404);
  assert.equal((await fetch(base + '/supervisor/config.js', {method: 'POST'})).status, 405);
});
