import {test} from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import {hazards,distanceMiles,strikeDeadline,nextSixPM,validScore,rankSites,acceptSnapshot} from '../crew-domain.js';
test('lightning radius includes ten miles and excludes farther strikes',()=>{
  const site={latitude:30,longitude:-80},strike=miles=>({latitude:30+miles/3958.7613*180/Math.PI,longitude:-80,occurred_at:'2026-10-17T12:00:00Z'});
  assert.ok(Math.abs(distanceMiles(site,strike(10))-10)<1e-9);
  assert.equal(strikeDeadline(site,strike(10)),'2026-10-17T12:30:00.000Z');
  assert.equal(strikeDeadline(site,strike(10.0001)),null);
  assert.equal(strikeDeadline(site,{...strike(1),latitude:100}),null);
});
test('a late old strike does not shorten an existing hold',()=>{const site={latitude:30,longitude:-80};assert.equal(strikeDeadline(site,{...site,occurred_at:'2026-10-17T12:00:00Z'},{all_clear_at:'2026-10-17T12:40:00Z'}),'2026-10-17T12:40:00.000Z');});
test('6 PM preview follows site time and daylight saving changes',()=>{
  assert.equal(nextSixPM('America/New_York',Date.parse('2026-02-01T15:00:00Z')),'2026-02-01T23:00:00.000Z');
  assert.equal(nextSixPM('America/Chicago',Date.parse('2026-07-01T15:00:00Z')),'2026-07-01T23:00:00.000Z');
  assert.equal(nextSixPM('America/New_York',Date.parse('2026-03-08T00:00:00Z')),'2026-03-08T22:00:00.000Z');
  assert.equal(nextSixPM('America/New_York',Date.parse('2026-11-01T00:00:00Z')),'2026-11-01T23:00:00.000Z');
  assert.equal(nextSixPM('made/up'),null);
});
test('ranking puts missing or invalid scores last and supports search, region and risk',()=>{
  const sites=[{id:'1',name:'A',state:'Florida',score:null},{id:'2',name:'B',state:'Florida',score:9},{id:'3',name:'C',state:'Texas',score:11},{id:'4',name:'D',state:'Florida',score:5}];
  assert.deepEqual(rankSites(sites).map(s=>s.id),['2','4','1','3']);
  assert.deepEqual(rankSites(sites,{region:'Florida',minimum:7}).map(s=>s.id),['2']);
  assert.equal(rankSites(sites,{query:'Texas'}).length,1);assert.equal(validScore('8'),false);assert.equal(validScore(0),true);
});
test('site revisions prevent stale or cross-site responses from replacing state',()=>{const previous={id:'1',revision:4};assert.equal(acceptSnapshot(previous,{id:'2',revision:8},'1'),previous);assert.equal(acceptSnapshot(previous,{id:'1',revision:3},'1'),previous);assert.equal(acceptSnapshot(previous,{id:'1',revision:5},'1').revision,5);});
test('monitored reference meets coverage and coordinate invariants',async()=>{
  const rows=JSON.parse(await fs.readFile(new URL('../crew-data/monitored-sites.json',import.meta.url)));
  assert.equal(rows.length,60);assert.equal(new Set(rows.map(r=>r.site_id)).size,rows.length);
  assert.equal(new Set(rows.map(r=>r.hazard_region)).size,6);assert.equal(hazards.length,7);
  assert.ok(rows.every(r=>r.site_id&&r.name&&Number.isFinite(r.latitude)&&Number.isFinite(r.longitude)&&Math.abs(r.latitude)<=90&&Math.abs(r.longitude)<=180));
});
