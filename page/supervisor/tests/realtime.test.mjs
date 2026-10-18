import test from 'node:test';
import assert from 'node:assert/strict';
import {connectRealtime} from '../realtime.js';
import {createDeepSpaceSource} from '../../realtime/deepspace-source.js';
import {config} from '../config.js';
const settle = () => new Promise(resolve => setImmediate(resolve));

test('valid ID notices refresh list and selected detail/reports; payload text is never trusted', async () => {
  let callbacks, cleanup = 0;
  const statuses = [], refreshed = [];
  const timers = {setTimeout: () => 1, clearTimeout: () => {}};
  const stop = connectRealtime({timers, getToken: async () => 'token', getSource: () => ({subscribe(args) {
    callbacks = args; return () => cleanup++;
  }}), onStatus: value => statuses.push(value), onInvalidate: async () => { refreshed.push('sites', 'alerts', 'selected detail', 'selected reports'); }});
  await settle();
  assert.equal(callbacks.accessToken, undefined); assert.equal(callbacks.site_id, undefined);
  callbacks.onConnection(true); await settle();
  assert.deepEqual(statuses, [false, true]);
  callbacks.onEvent({type: 'report.created', site_id: 6045, report_id: 'r', description: '<script>bad</script>'});
  await settle();
  assert.equal(refreshed.length, 8);
  callbacks.onEvent({type: 'scores.updated', site_ids: [6045], sent_at: '2026-10-17T18:00:00Z'});
  await settle();
  assert.equal(refreshed.length, 12);
  callbacks.onEvent({type: 'scores.updated', site_ids: ['6045']}); await settle();
  assert.equal(refreshed.length, 12);
  callbacks.onEvent({type: 'unrecognized.event', site_id: 6045}); await settle();
  assert.equal(refreshed.length, 12);
  callbacks.onEvent({type: 'report.created', site_id: '6045', report_id: 'r'}); await settle();
  assert.equal(refreshed.length, 12);
  stop(); callbacks.onEvent({type: 'alert.started', site_id: 6045, alert_id: 1}); await settle();
  assert.equal(refreshed.length, 12); assert.equal(cleanup, 1);
});
test('a missing realtime provider reports unavailable and schedules retry, not connected', async () => {
  const statuses = []; let retries = 0;
  const stop = connectRealtime({getSource: () => undefined, getToken: async () => 'token',
    onInvalidate: async () => assert.fail('No invented events'), onStatus: value => statuses.push(value),
    timers: {setTimeout: () => ++retries, clearTimeout: () => {}}});
  await settle(); assert.ok(statuses.every(value => value === false)); assert.equal(retries, 1); stop();
});

test('expired authentication stops retrying and asks the page for sign-in', async () => {
  let retries = 0, expiries = 0;
  const statuses = [];
  const stop = connectRealtime({getSource: () => ({subscribe() { assert.fail('No socket after expired auth'); }}),
    getToken: async () => { throw Object.assign(new Error('Login needed'), {error: 'missing_refresh_token'}); },
    onInvalidate: async () => {}, onStatus: value => statuses.push(value),
    onSessionExpired: () => { expiries++; },
    timers: {setTimeout: () => ++retries, clearTimeout: () => {}}});
  await settle();
  assert.equal(expiries, 1);
  assert.equal(retries, 0);
  assert.equal(statuses.at(-1), false);
  stop();
});

test('a burst during an in-flight refresh is coalesced into one follow-up', async () => {
  let callbacks, calls = 0;
  const finishes = [], statuses = [];
  const stop = connectRealtime({getToken: async () => 'token', getSource: () => ({subscribe(args) {
    callbacks = args; return () => {};
  }}), timers: {setTimeout: () => 1, clearTimeout: () => {}}, onStatus: value => statuses.push(value),
    onInvalidate: () => { calls++; return new Promise(resolve => finishes.push(resolve)); }});
  await settle();
  callbacks.onConnection(true); await settle();
  for (let index = 0; index < 100; index++) {
    callbacks.onEvent({type: 'report.created', site_id: 6045, report_id: `report-${index}`});
  }
  assert.equal(calls, 1);
  finishes[0](); await settle();
  assert.equal(calls, 2);
  finishes[1](); await settle();
  assert.equal(calls, 2);
  assert.equal(statuses.at(-1), true);
  stop();
});

test('a failed refresh disconnects and a reconnect refreshes before claiming live status', async () => {
  let callbacks, retry, calls = 0, cleanup = 0;
  const statuses = [];
  const stop = connectRealtime({getToken: async () => 'token', getSource: () => ({subscribe(args) {
    callbacks = args; return () => cleanup++;
  }}), timers: {setTimeout(callback, delay) { if (delay === 1000) retry = callback; return 1; }, clearTimeout() {}},
    onStatus: value => statuses.push(value), onInvalidate: async () => {
      if (++calls === 1) throw new Error('API offline');
    }});
  await settle();
  const oldCallbacks = callbacks;
  callbacks.onConnection(true); await settle();
  assert.equal(statuses.at(-1), false);
  assert.equal(cleanup, 1);
  retry(); await settle();
  oldCallbacks.onConnection(true); oldCallbacks.onEvent({type: 'report.created', site_id: 6045, report_id: 'old'});
  await settle(); assert.equal(calls, 1);
  callbacks.onConnection(true); await settle();
  assert.equal(calls, 2); assert.equal(statuses.at(-1), true);
  stop();
});

test('offline pauses retries and online reconnects with a fresh API snapshot', async () => {
  const listeners = new Map(), browser = {navigator: {onLine: false},
    addEventListener(type, callback) { listeners.set(type, callback); },
    removeEventListener(type) { listeners.delete(type); }};
  let subscriptions = 0, snapshots = 0, retries = 0, callbacks;
  const stop = connectRealtime({browser, getToken: async () => 'token',
    getSource: () => ({subscribe(value) { subscriptions++; callbacks = value; return () => {}; }}),
    onInvalidate: async () => { snapshots++; }, onStatus() {},
    timers: {setTimeout: () => ++retries, clearTimeout: () => {}}});
  await settle(); assert.equal(subscriptions, 0); assert.equal(retries, 0);
  browser.navigator.onLine = true; listeners.get('online')(); await settle();
  assert.equal(subscriptions, 1); callbacks.onConnection(true); await settle();
  assert.equal(snapshots, 1);
  browser.navigator.onLine = false; listeners.get('offline')(); await settle();
  assert.equal(retries, 1); // Only the prior opening watchdog was allocated.
  browser.navigator.onLine = true; listeners.get('online')(); await settle();
  callbacks.onConnection(true); await settle(); assert.equal(snapshots, 2);
  stop(); assert.equal(listeners.size, 0);
});

test('the configured DeepSpace bridge delivers ID notices and refreshes authorized dashboard data', async () => {
  class BridgeSocket {
    static sockets = [];
    constructor(url) { this.url = url; this.listeners = new Map(); this.sent = []; BridgeSocket.sockets.push(this); }
    addEventListener(type, handler) { this.listeners.set(type, handler); }
    send(value) { this.sent.push(JSON.parse(value)); }
    close() { this.closed = true; }
    emit(type, payload = {}) { this.listeners.get(type)?.(payload); }
  }
  const source = createDeepSpaceSource({...config.realtime, WebSocketImpl: BridgeSocket});
  let refreshes = 0;
  const statuses = [];
  const stop = connectRealtime({getSource: () => source, getToken: async () => 'private-access-token',
    onInvalidate: async () => { refreshes++; }, onStatus: value => statuses.push(value),
    timers: {setTimeout: () => 1, clearTimeout: () => {}}});
  await settle();
  const socket = BridgeSocket.sockets[0];
  assert.equal(socket.url, `wss://planit-realtime.app.space/ws/${encodeURIComponent(`app:${config.realtime.appId}`)}`);
  socket.emit('open');
  const subscription = socket.sent[0];
  assert.equal(subscription.type, 'core.subscribe');
  assert.equal(subscription.payload.query.collection, 'events');
  assert.equal(JSON.stringify(subscription).includes('private-access-token'), false);
  socket.emit('message', {data: JSON.stringify({type: 'core.query_result',
    payload: {subscriptionId: subscription.payload.subscriptionId}})});
  await settle();
  assert.equal(statuses.at(-1), true);
  assert.equal(refreshes, 1); // Reconnect refetch; historical records are not replayed as notices.
  function notify(data) {
    socket.emit('message', {data: JSON.stringify({type: 'core.record_change', payload: {
      collection: 'events', changeType: 'create', record: {data}}})});
  }
  notify({type: 'scores.updated', site_ids: '[6045]', sent_at: '2026-10-17T18:00:00Z'});
  await settle(); assert.equal(refreshes, 2);
  notify({type: 'report.created', site_id: 6045, report_id: 'report-1', sent_at: '2026-10-17T18:01:00Z'});
  await settle(); assert.equal(refreshes, 3);
  notify({type: 'new.future.event', site_id: 6045, sent_at: '2026-10-17T18:02:00Z'});
  await settle(); assert.equal(refreshes, 3);
  stop(); assert.equal(socket.closed, true);
});
