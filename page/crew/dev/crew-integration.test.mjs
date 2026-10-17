import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import {createContractMapper, mapSiteSummary, mapReport} from '../crew-integration.js';
const fixture=JSON.parse(await fs.readFile(new URL('./fixtures/contract-v1.1.json',import.meta.url)));
const clone=value=>structuredClone(value);

test('contract summaries and nested scores map into the existing screen shape',()=>{
  const summary=mapSiteSummary(fixture.sites[0]);
  assert.equal(summary.id,'9001');assert.equal(summary.site_id,9001);assert.equal(summary.score,8.2);
  assert.equal(summary.score_updated_at,'2026-10-17T18:00:00Z');
  const site=createContractMapper().site(clone(fixture.details['9001']));
  assert.equal(site.operator,'Sample Utility');assert.equal(site.score,8.2);assert.equal(site.baseline,2.4);
  assert.equal(site.score_reconciles,true);assert.equal(site.model.version,'sample');assert.match(site.score_method,/Sample API/);
  assert.equal(site.factors.find(f=>f.hazard_type==='flooding').contribution,-1.5);
  assert.equal(site.factors[0].unit,'score_points');assert.equal(site.server_time,null);
});
test('hazard cards preserve API units, zero readings and missing data without invented thresholds',()=>{
  const mapper=createContractMapper(), raw=clone(fixture.details['9002']);
  const site=mapper.site(raw);
  assert.match(site.hazards.soil.reading,/0.47 m³\/m³/);assert.match(site.hazards.weather.reading,/3.4 in \/ 24 h/);
  assert.equal(site.flood.status,'warning');assert.equal(site.flood.overnight_rain_mm,null);
  assert.equal(site.flood.river_distance_miles,null);assert.equal(site.flood.rainfall_reading,'3.4 in');
  raw.latest_weather.precip_24h_in=0;raw.latest_weather.heat_index_f=null;raw.score=null;
  const missing=mapper.site(raw);
  assert.match(missing.hazards.weather.reading,/0 in/);assert.match(missing.hazards.heat.reading,/No data/);
  assert.equal(missing.score,null);assert.deepEqual(missing.factors,[]);assert.equal(missing.baseline,null);
});
test('only actual lightning stop-work alerts create holds, not report or flood warnings',()=>{
  const mapper=createContractMapper();
  const site=mapper.site(clone(fixture.details['9001']));
  assert.equal(site.alert.status,'hold');assert.equal(site.alert.all_clear_at,'2026-10-17T18:34:00Z');
  assert.equal(site.alert.last_strike_at,'2026-10-17T18:04:00Z');assert.equal(site.alert.distance_miles,6.2);
  assert.equal(site.warnings[0].hazard_type,'wildlife');
  assert.equal(mapper.site(clone(fixture.details['9002'])).alert.status,'unknown');
  assert.equal(mapper.site(clone(fixture.details['9003'])).alert.status,'unknown');
});
test('request order and same-alert deadlines cannot roll back a newer hold',()=>{
  const mapper=createContractMapper(), raw=clone(fixture.details['9001']);
  const oldRevision=mapper.nextRevision(), newRevision=mapper.nextRevision();
  raw.active_alerts[0].clear_at='2026-10-17T18:45:00Z';
  const newer=mapper.site(raw,newRevision);
  assert.equal(mapper.site(clone(fixture.details['9001']),oldRevision),newer);
  assert.equal(mapper.site(clone(fixture.details['9001'])).alert.all_clear_at,'2026-10-17T18:45:00Z');
});
test('clear notifications need the matching lightning alert and a fetched snapshot without holds',()=>{
  const mapper=createContractMapper(), raw=clone(fixture.details['9001']);
  mapper.site(raw);raw.active_alerts=[];
  assert.equal(mapper.site(raw,undefined,{clearedAlertId:102}).alert.status,'unknown');
  assert.equal(mapper.site(raw,undefined,{clearedAlertId:101}).alert.status,'cleared');
  raw.active_alerts=clone(fixture.details['9001'].active_alerts);
  assert.equal(mapper.site(raw,undefined,{clearedAlertId:101}).alert.status,'hold');
});
test('report and latest briefing mapping retain contract fields without fabricated delivery evidence',()=>{
  const report=mapReport(fixture.reports[0]);assert.equal(report.site_id,'9001');assert.equal(report.category,'Wildlife');
  assert.equal(report.photo_url,undefined);assert.equal(report.photo_key,'sample-photo-1');assert.equal(report.shared,undefined);
  const mapper=createContractMapper();mapper.site(clone(fixture.details['9001']));
  const briefing=mapper.briefing(fixture.briefings['9001'],9001);
  assert.equal(briefing.body,fixture.briefings['9001'].text);assert.equal(briefing.valid_date,'2026-10-18');
  assert.equal(briefing.timezone,'America/New_York');assert.equal(briefing.delivery_status,null);assert.deepEqual(briefing.forecast,[]);
  assert.throws(()=>mapper.briefing(fixture.briefings['9001'],9002),/different site/);
});
