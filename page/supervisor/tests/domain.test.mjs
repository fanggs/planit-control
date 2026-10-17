import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import {assessScore, summaryScore, rankSites, freshness, countdown, coordinates,
  validNotice, hasSupervisorRole, safeSourceURL} from '../domain.js';
const sites = JSON.parse(await fs.readFile(new URL('../sample-data/sites.json', import.meta.url)));
const details = JSON.parse(await fs.readFile(new URL('../sample-data/site_details.json', import.meta.url)));

test('all shipped sample scores reconcile and retain negative contributions', () => {
  assert.equal(sites.length, 3);
  for (const detail of Object.values(details)) {
    const score = assessScore(detail.score, detail.site_id);
    assert.equal(score.status, 'ready');
    assert.ok(score.steps.some(step => step.kind === 'decrease'));
    assert.ok(Math.abs(score.total - detail.score.score) < .05);
  }
});
test('the contract tolerance uses original values, not rounded display values', () => {
  const model = {site_id: 1, score: 4.05, baseline: 4, factors: [], scored_at: '2026-10-17T18:00:00Z'};
  assert.equal(assessScore(model, 1).status, 'ready');
  assert.equal(assessScore({...model, score: 4.051}, 1).status, 'mismatch');
  assert.equal(assessScore({...model, site_id: 2}, 1).status, 'invalid');
});
test('missing or malformed scores stay unknown; a real zero remains zero', () => {
  const good = sites[0];
  for (const score of [null, undefined, NaN, Infinity, -1, 11, '0']) assert.equal(summaryScore({...good, score}), null);
  assert.equal(summaryScore({...good, score: 0}), 0);
  assert.equal(summaryScore({...good, scored_at: null}), null);
  assert.equal(summaryScore({...good, top_factors: null}), null);
  assert.equal(assessScore(null, 1).status, 'no_data');
});
test('rank/search/filter preserve no-data state and do not change site data', () => {
  const unknown = {...sites[0], site_id: 9999, name: 'Unknown plant', score: null, scored_at: null, top_factors: null};
  const rows = [unknown, ...sites];
  assert.equal(rankSites(rows).at(-1), unknown);
  assert.equal(rankSites(rows, {search: 'california'}).length, 1);
  assert.equal(rankSites(rows, {filter: 'no-data'}).length, 1);
  assert.equal(rankSites(sites, {filter: 'reports'}).length, 1);
  assert.equal(rows[0], unknown);
});
test('an expired countdown never gives all-clear; missing timestamp is unavailable', () => {
  const now = Date.parse('2026-10-17T18:35:00Z');
  assert.equal(countdown('2026-10-17T18:34:00Z', now), 'Awaiting server clearance');
  assert.equal(countdown(null, now), 'Clear time unavailable');
  assert.equal(freshness(null, now).stale, true);
  assert.equal(freshness('2026-10-16T18:00:00Z', now).stale, true);
});
test('reject invalid coordinates, unrecognized notices, forged role strings and unsafe links', () => {
  assert.equal(coordinates({latitude: 0, longitude: 0})[0], 0);
  assert.equal(coordinates({latitude: 90.1, longitude: 0}), null);
  assert.equal(coordinates({latitude: 10}), null);
  assert.equal(validNotice({type: 'score.safe', site_id: 1}), false);
  assert.equal(validNotice({type: 'report.created', site_id: '1', report_id: 'x'}), false);
  assert.equal(validNotice({type: 'report.created', site_id: 1, report_id: 'x'}), true);
  assert.equal(validNotice({type: 'scores.updated', site_ids: [1, 6045], sent_at: '2026-10-17T18:00:00Z'}), true);
  for (const site_ids of [[], ['1'], [0], [1, null], '1']) {
    assert.equal(validNotice({type: 'scores.updated', site_ids}), false);
  }
  assert.equal(hasSupervisorRole({roles: 'supervisor'}, 'roles'), false);
  assert.equal(hasSupervisorRole({roles: ['supervisor']}, 'roles'), true);
  assert.equal(safeSourceURL('javascript:alert(1)'), null);
  assert.equal(safeSourceURL('https://user:password@example.com'), null);
  assert.equal(safeSourceURL('https://api.weather.gov/alerts'), 'https://api.weather.gov/alerts');
});
