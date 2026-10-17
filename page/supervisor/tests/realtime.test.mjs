import test from 'node:test';
import assert from 'node:assert/strict';
import {connectRealtime} from '../realtime.js';
const settle = () => new Promise(resolve => setImmediate(resolve));

test('valid ID notices refresh list and selected detail/reports; payload text is never trusted', async () => {
  let callbacks, cleanup = 0;
  const statuses = [], refreshed = [];
  const timers = {setTimeout: () => 1, clearTimeout: () => {}};
  const stop = connectRealtime({timers, getToken: async () => 'token', getSource: () => ({subscribe(args) {
    callbacks = args; return () => cleanup++;
  }}), onStatus: value => statuses.push(value), onInvalidate: async () => { refreshed.push('sites', 'alerts', 'selected detail', 'selected reports'); }});
  await settle();
  assert.equal(callbacks.accessToken, 'token'); assert.equal(callbacks.site_id, null);
  callbacks.onConnection(true); await settle();
  assert.deepEqual(statuses, [false, true]);
  callbacks.onEvent({type: 'report.created', site_id: 6045, report_id: 'r', description: '<script>bad</script>'});
  await settle();
  assert.equal(refreshed.length, 8);
  callbacks.onEvent({type: 'report.created', site_id: '6045', report_id: 'r'}); await settle();
  assert.equal(refreshed.length, 8);
  stop(); callbacks.onEvent({type: 'alert.started', site_id: 6045, alert_id: 1}); await settle();
  assert.equal(refreshed.length, 8); assert.equal(cleanup, 1);
});
test('a missing realtime provider reports unavailable and schedules retry, not connected', async () => {
  const statuses = []; let retries = 0;
  const stop = connectRealtime({getSource: () => undefined, getToken: async () => 'token',
    onInvalidate: async () => assert.fail('No invented events'), onStatus: value => statuses.push(value),
    timers: {setTimeout: () => ++retries, clearTimeout: () => {}}});
  await settle(); assert.ok(statuses.every(value => value === false)); assert.equal(retries, 1); stop();
});
