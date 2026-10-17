import test from 'node:test';
import assert from 'node:assert/strict';
import {alertFeedDisplay, loadDashboardFeeds} from '../feeds.js';

test('a healthy alert feed keeps its count distinct from unavailable alerts', async () => {
  const sites = [{site_id: 6045}];
  const alerts = [{id: 1}];
  assert.deepEqual(await loadDashboardFeeds({sites: async () => sites, alerts: async () => alerts}),
    {sites, alerts, alertError: null});
  assert.deepEqual(alertFeedDisplay(alerts), {count: '1', status: 'Warnings and stop-work alerts'});
  assert.deepEqual(alertFeedDisplay([]), {count: '0', status: 'No active alerts returned · feed health unconfirmed'});
});

test('an alert failure preserves healthy sites and never displays zero alerts', async () => {
  const sites = [{site_id: 6045}];
  const failure = new Error('Alert endpoint unavailable');
  const result = await loadDashboardFeeds({sites: async () => sites, alerts: async () => { throw failure; }});
  assert.equal(result.sites, sites);
  assert.equal(result.alerts, null);
  assert.equal(result.alertError, failure);
  assert.deepEqual(alertFeedDisplay(result.alerts),
    {count: 'No data', status: 'Alert feed unavailable · do not infer safety'});
});

test('a site failure still fails the overview instead of showing a misleading map', async () => {
  const failure = new Error('Site endpoint unavailable');
  await assert.rejects(loadDashboardFeeds({sites: async () => { throw failure; }, alerts: async () => []}),
    error => error === failure);
});
