import test from 'node:test';
import assert from 'node:assert/strict';
import {changeSelectedSite, markDetailStale, bindPageLifecycle} from '../lifecycle.js';

test('a replacement selected site starts without the previous site details or private reports', () => {
  const state = {selected: 6045, detail: {site_id: 6045}, detailStale: true,
    reports: [{site_id: 6045, photo_key: 'private'}]};
  assert.equal(changeSelectedSite(state, 100), true);
  assert.deepEqual(state, {selected: 100, detail: null, detailStale: false, reports: []});
});

test('same-site refresh preserves last known data, while no sites clears it', () => {
  const detail = {site_id: 6045}, reports = [{site_id: 6045}];
  const state = {selected: 6045, detail, detailStale: false, reports};
  assert.equal(changeSelectedSite(state, 6045), false);
  assert.equal(state.detail, detail); assert.equal(state.reports, reports);
  assert.equal(markDetailStale(state, 6045), true);
  assert.equal(state.detailStale, true);
  assert.equal(state.detail, detail); assert.equal(state.reports, reports);
  assert.equal(markDetailStale(state, 100), false);
  assert.equal(changeSelectedSite(state, null), true);
  assert.deepEqual(state, {selected: null, detail: null, detailStale: false, reports: []});
});

test('a failed first load cannot mark missing or another site detail as cached data', () => {
  const state = {selected: 6045, detail: null, detailStale: false, reports: []};
  assert.equal(markDetailStale(state, 6045), false);
  state.detail = {site_id: 100};
  assert.equal(markDetailStale(state, 6045), false);
  assert.equal(state.detailStale, false);
});

test('page hiding cleans up; only a cached restoration reloads and re-runs authentication', () => {
  const listeners = new Map();
  let cleaned = 0, reloaded = 0;
  const browser = {location: {reload() { reloaded++; }},
    addEventListener(type, listener) { listeners.set(type, listener); },
    removeEventListener(type, listener) { if (listeners.get(type) === listener) listeners.delete(type); }};
  const unbind = bindPageLifecycle({browser, onHide: () => cleaned++});
  listeners.get('pageshow')({persisted: false}); assert.equal(reloaded, 0);
  listeners.get('pagehide')({persisted: true}); assert.equal(cleaned, 1);
  listeners.get('pageshow')({persisted: true}); assert.equal(reloaded, 1);
  unbind(); assert.equal(listeners.size, 0);
});
