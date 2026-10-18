import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import {assessScore, featureLabel, summaryScore, summaryScreening, rankSites, freshness, countdown, coordinates, openReportPins,
  isReplayAlert, lightningDisplay, siteHasReplayAlert, validNotice, hasSupervisorRole, safeSourceURL,
  warningsDisplay, wildlifeSummary} from '../domain.js';
const sites = JSON.parse(await fs.readFile(new URL('../sample-data/sites.json', import.meta.url)));
const details = JSON.parse(await fs.readFile(new URL('../sample-data/site_details.json', import.meta.url)));
const sampleNow = Date.parse('2026-10-17T18:30:00Z');

test('all shipped sample prototype screenings reconcile and retain signed feature contributions', () => {
  assert.equal(sites.length, 3);
  for (const detail of Object.values(details)) {
    const score = assessScore(detail.screening, sampleNow);
    assert.equal(score.status, 'ready');
    assert.ok(score.steps.some(step => step.kind === 'decrease'));
    assert.ok(Math.abs(score.total - detail.screening.score) < 1e-8);
    assert.equal(detail.screening.clears_stop_work, false);
  }
  assert.equal(featureLabel('rain_total_24h_in'), 'Rain over 24 hours');
  assert.equal(featureLabel('month_cos'), 'Time of year (2)');
  assert.equal(featureLabel('heat_index_max_f_missing'), 'Heat index not available');
});
test('screening uses exact feature reconciliation and rejects missing safety metadata', () => {
  const model = {...details[9001].screening, score: 4.05, baseline: 4,
    factors: [{feature: 'heat_index_max_f', contribution: .05}]};
  assert.equal(assessScore(model, sampleNow).status, 'ready');
  assert.equal(assessScore({...model, factors: []}, sampleNow).status, 'invalid');
  assert.equal(assessScore({...model, score: 4.051}, sampleNow).status, 'mismatch');
  assert.equal(assessScore({...model, factors: [{hazard_type: 'heat', contribution: .05}]}, sampleNow).status, 'invalid');
  assert.equal(assessScore({...model, clears_stop_work: true}, sampleNow).status, 'invalid');
  assert.equal(assessScore({...model, valid_until: null}, sampleNow).status, 'invalid');
});
test('missing or malformed scores stay unknown; a real zero remains zero', () => {
  const good = sites[0];
  for (const score of [null, undefined, NaN, Infinity, -1, 11, '0']) assert.equal(summaryScore({...good, score}, sampleNow), null);
  assert.equal(summaryScore({...good, score: 0}, sampleNow), 0);
  assert.equal(summaryScore({...good, score_status: 'stale'}, sampleNow), null);
  assert.equal(summaryScore({...good, scored_at: null}, sampleNow), null);
  assert.equal(summaryScore({...good, top_factors: null}, sampleNow), null);
  assert.equal(summaryScore({...good, top_factors: []}, sampleNow), null);
  assert.equal(assessScore(null, sampleNow).status, 'no_data');
  assert.equal(assessScore({score: null, status: 'stale', reason: 'Old inputs'}, sampleNow).message, 'Old inputs');
  assert.equal(assessScore({...details[9001].screening, score: 0, baseline: 0,
    factors: [{feature: 'wind_max_mph', contribution: 0}]}, sampleNow).status, 'ready');
  assert.equal(assessScore(details[9001].screening, Date.parse('2026-10-18T19:00:00Z')).status, 'stale');
  assert.equal(summaryScore(good, Date.parse('2026-10-18T19:00:00Z')), null);
});
test('a locally expired research summary says stale instead of research under No data', () => {
  const current = summaryScreening(sites[0], sampleNow);
  assert.equal(current.status, 'research');
  assert.equal(current.score, sites[0].score);
  const expired = summaryScreening(sites[0], sampleNow + 3 * 3600000);
  assert.deepEqual(expired, {score: null, status: 'stale'});
  assert.deepEqual(summaryScreening({...sites[0], score_status: 'no_data'}, sampleNow),
    {score: null, status: 'no_data'});
  assert.deepEqual(summaryScreening({...sites[0], top_factors: null}, sampleNow),
    {score: null, status: 'invalid'});
  assert.deepEqual(summaryScreening({...sites[0], score_status: {unexpected: true}}, sampleNow),
    {score: null, status: 'invalid'});
});
test('rank/search/filter preserve no-data state and do not change site data', () => {
  const unknown = {...sites[0], site_id: 9999, name: 'Unknown plant', score: null,
    score_status: 'no_data', scored_at: null, top_factors: null};
  const rows = [unknown, ...sites];
  assert.equal(rankSites(rows, {allowHistorical: true}).at(-1), unknown);
  assert.equal(rankSites(rows, {search: 'california', allowHistorical: true}).length, 1);
  assert.equal(rankSites(rows, {filter: 'no-data', allowHistorical: true}).length, 1);
  assert.equal(rankSites(sites, {filter: 'reports', allowHistorical: true}).length, 1);
  assert.equal(rows[0], unknown);
});
test('only fresh explicit lightning clear and NWS ok may produce clear/no-active text', () => {
  const checked_at = '2026-10-17T18:29:00Z';
  assert.equal(lightningDisplay(null, sampleNow).status, 'unknown');
  assert.equal(lightningDisplay({status: 'unknown', checked_at}, sampleNow).status, 'unknown');
  assert.equal(lightningDisplay({status: 'clear', checked_at}, sampleNow).status, 'clear');
  assert.equal(lightningDisplay({status: 'clear', checked_at}, sampleNow + 6 * 60000).status, 'unknown');
  assert.equal(lightningDisplay({status: 'stop_work', checked_at: null}, sampleNow).status, 'stop_work');
  assert.equal(lightningDisplay({status: 'clear', checked_at}, sampleNow, true).status, 'stop_work');
  assert.equal(warningsDisplay(null, [], sampleNow).status, 'unknown');
  assert.equal(warningsDisplay({status: 'unknown', checked_at}, [], sampleNow).status, 'unknown');
  assert.equal(warningsDisplay({status: 'ok', checked_at}, [], sampleNow).text, 'No weather warnings right now');
  assert.equal(warningsDisplay({status: 'ok', checked_at}, [], sampleNow + 16 * 60000).status, 'unknown');
  const active = {event_kind: 'nws_warning', starts_at: '2026-10-17T18:00:00Z', ends_at: '2026-10-17T19:00:00Z',
    title: 'Rip Current Statement issued October 17 at 7:32PM EDT by NWS Miami FL'};
  const upcoming = {...active, starts_at: '2026-10-17T19:00:00Z'};
  assert.equal(warningsDisplay({status: 'ok', checked_at}, [active], sampleNow).text,
    '1 weather alert: Rip Current Statement');
  assert.equal(warningsDisplay({status: 'ok', checked_at}, [active, {...active, title: 'Rip Current Statement issued later'}],
    sampleNow).text, '2 weather alerts: Rip Current Statement');  // an NWS update is named once
  assert.equal(warningsDisplay({status: 'ok', checked_at}, [upcoming], sampleNow).text, 'No weather warnings right now');
});
test('wildlife sightings remain evidence with no inferred encounter probability', () => {
  assert.match(wildlifeSummary(details[9001].wildlife_context), /past sightings? nearby \(not live\)/);
  assert.match(wildlifeSummary(details[9002].wildlife_context), /doesn’t mean there are no animals/);
  assert.match(wildlifeSummary(details[9003].wildlife_context), /aren’t available/);
  assert.equal(details[9001].wildlife_context.numeric_score_contribution, null);
});
test('only open reports with coordinates become active map pins', () => {
  const open = {id: 'current', status: 'open', latitude: 25, longitude: -80};
  const resolved = {id: 'history', status: 'resolved', latitude: 25, longitude: -80};
  const missingPosition = {id: 'unplaced', status: 'open', latitude: null, longitude: -80};
  assert.deepEqual(openReportPins([resolved, missingPosition, open]), [open]);
});
test('an expired countdown never gives all-clear; missing timestamp is unavailable', () => {
  const now = Date.parse('2026-10-17T18:35:00Z');
  assert.equal(countdown('2026-10-17T18:34:00Z', now), 'Awaiting server clearance');
  assert.equal(countdown(null, now), 'Clear time unavailable');
  assert.equal(freshness(null, now).stale, true);
  assert.equal(freshness('2026-10-16T18:00:00Z', now).stale, true);
});
test('replay labels require the explicit alert flag and matching active site alert', () => {
  const site = {site_id: 621, active_alert: {hazard_type: 'lightning', level: 'stop_work'}};
  const replay = {site_id: 621, hazard_type: 'lightning', level: 'stop_work',
    trigger: {strike_id: 'opaque-provider-id', is_replay: true}};
  assert.equal(isReplayAlert(replay), true);
  assert.equal(siteHasReplayAlert(site, [replay]), true);
  assert.equal(isReplayAlert({...replay, trigger: {strike_id: 'replay-looking-id'}}), false);
  assert.equal(siteHasReplayAlert(site, [{...replay, site_id: 622}]), false);
  assert.equal(siteHasReplayAlert(site, [{...replay, level: 'warning'}]), false);
  assert.equal(siteHasReplayAlert(site, null), false);
  assert.equal(siteHasReplayAlert({...site, active_alert: null}, [replay]), false);
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
