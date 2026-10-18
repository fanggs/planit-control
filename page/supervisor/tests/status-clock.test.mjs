import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import {detailScreeningStatus, screeningAvailability, screeningAvailabilityChanged,
  updateWatchChips} from '../status-clock.js';

const sites = JSON.parse(await fs.readFile(new URL('../sample-data/sites.json', import.meta.url)));
const details = JSON.parse(await fs.readFile(new URL('../sample-data/site_details.json', import.meta.url)));
const first = sites[0];
const now = Date.parse('2026-10-17T18:30:00Z');

function watchNode(kind, scope = 'summary') {
  return {dataset: {watchKind: kind, watchScope: scope, watchSiteId: String(first.site_id)}, textContent: ''};
}

test('clock changes a clear lightning chip to unavailable without a new fetch', () => {
  const node = watchNode('lightning');
  const root = {querySelectorAll: () => [node]};
  const row = {...first, active_alert: null, lightning_status: {status: 'clear', checked_at: new Date(now).toISOString()}};
  updateWatchChips(root, [row], null, now);
  assert.equal(node.textContent, 'No lightning within 10 miles');
  assert.equal(node.dataset.tone, 'low');
  updateWatchChips(root, [row], null, now + 5 * 60000 + 1);
  assert.equal(node.textContent, 'Can’t confirm lightning right now');
  assert.equal(node.dataset.tone, 'unknown');
});

test('clock expires NWS no-active status but never clears an active stop-work alert', () => {
  const warnings = watchNode('warnings', 'detail');
  const lightning = watchNode('lightning', 'detail');
  const root = {querySelectorAll: () => [warnings, lightning]};
  const detail = {...details[first.site_id], site_id: first.site_id, active_alerts: [{hazard_type: 'lightning', level: 'stop_work'}],
    lightning_status: {status: 'clear', checked_at: new Date(now).toISOString()},
    warnings_status: {status: 'ok', checked_at: new Date(now).toISOString()}, environmental_events: []};
  updateWatchChips(root, [first], detail, now);
  assert.equal(warnings.textContent, 'No weather warnings right now');
  assert.equal(lightning.textContent, 'Lightning · STOP WORK');
  updateWatchChips(root, [first], detail, now + 16 * 60000);
  assert.equal(warnings.textContent, 'Can’t check weather warnings right now');
  assert.equal(warnings.dataset.tone, 'unknown');
  assert.equal(lightning.textContent, 'Lightning · STOP WORK');
});

test('clock notices local score and detail expiry without inventing database data', () => {
  const before = screeningAvailability([first], now);
  const after = screeningAvailability([first], now + 3 * 3600000);
  assert.equal(screeningAvailabilityChanged(before, after), true);
  assert.equal(after.get(first.site_id), false);
  assert.equal(detailScreeningStatus(details[first.site_id], now), 'ready');
  assert.equal(detailScreeningStatus(details[first.site_id], now + 3 * 3600000), 'stale');
  assert.equal(screeningAvailabilityChanged(after, screeningAvailability([first], now + 4 * 3600000)), false);
});
