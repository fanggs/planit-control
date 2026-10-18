import test from 'node:test';
import assert from 'node:assert/strict';
import {lightningWatch,warningsWatch} from '../crew-watch.js';
import {alertView} from '../crew-state.js';
import {watchPanel,floodHTML} from '../crew-ui.js';
import {createContractMapper} from '../crew-integration.js';

const now=Date.parse('2026-10-18T02:00:00Z');
const iso=delta=>new Date(now+delta).toISOString();
const event={event_kind:'nws_warning',hazard_type:'flooding',starts_at:iso(-60000),ends_at:iso(60000)};

test('lightning is clear only while its explicit check is fresh; stop-work wins',()=>{
  assert.equal(lightningWatch(null,[],now).status,'unknown');
  assert.equal(lightningWatch({status:'clear',checked_at:iso(-60000)},[],now).status,'clear');
  assert.equal(lightningWatch({status:'clear',checked_at:iso(-300001)},[],now).status,'unknown');
  assert.equal(lightningWatch({status:'clear',checked_at:iso(1000)},[],now).status,'unknown');
  assert.equal(lightningWatch({status:'clear',checked_at:iso(-60000)},[{hazard_type:'lightning',level:'stop_work'}],now).status,'stop_work');
});

test('NWS absence is meaningful only after a recent successful check',()=>{
  assert.equal(warningsWatch({status:'ok',checked_at:iso(-60000)},[],now).text,'No active NWS alerts');
  assert.equal(warningsWatch({status:'ok',checked_at:iso(-60000)},[event],now).count,1);
  assert.match(warningsWatch({status:'ok',checked_at:iso(-60000)},[{...event,title:'Flood Warning issued October 18 at 1:00AM EDT'}],now).text,
    /^1 active NWS alert: Flood Warning$/);
  assert.equal(warningsWatch({status:'ok',checked_at:iso(-900001)},[],now).status,'unknown');
  assert.equal(warningsWatch({status:'unknown',checked_at:iso(-60000)},[],now).status,'unknown');
  assert.equal(warningsWatch({status:'ok',checked_at:iso(-60000)},[{...event,starts_at:'broken'}],now).status,'unknown');
});

test('a stale watch cannot turn a cleared alert into an all-clear',()=>{
  const alert={site_id:'621',version:1,status:'cleared'};
  assert.equal(alertView(alert,true,now,{status:'clear',checked_at:iso(-60000)}).tone,'clear');
  assert.equal(alertView(alert,true,now,{status:'clear',checked_at:iso(-300001)}).tone,'unknown');
  assert.equal(alertView(alert,true,now,{status:'stop_work',checked_at:iso(-60000)}).tone,'hold');
});

test('crew cards distinguish a checked empty NWS feed from an unavailable one',()=>{
  const site={lightning_status:{status:'clear',checked_at:iso(-60000)},warnings_status:{status:'ok',checked_at:iso(-60000)},environmental_events:[],active_alerts:[],timezone:'UTC',flood:{status:'normal',message:'No active NWS flood warning was returned.'}};
  assert.match(watchPanel(site,now),/Lightning watch clear/);
  assert.match(watchPanel(site,now),/No active NWS alerts/);
  assert.match(floodHTML(site,now),/No active NWS flood warning/);
  assert.match(watchPanel(site,now+16*60000),/NWS warning status unavailable/);
  assert.match(floodHTML(site,now+16*60000),/Flood status unavailable/);
});

test('the v1.3 detail mapper preserves watch evidence and never infers clear from no alert',()=>{
  const raw={site_id:621,name:'Turkey Point',state:'FL',timezone:'UTC',active_alerts:[],environmental_events:[],recent_reports:[],screening:null,
    lightning_status:{status:'unknown',checked_at:null,reason:'Feed unavailable'},warnings_status:{status:'unknown',checked_at:null}};
  const mapper=createContractMapper({now:()=>now});
  const unavailable=mapper.site(raw);
  assert.equal(unavailable.alert.status,'unknown');assert.equal(unavailable.flood.status,'unknown');
  assert.equal(unavailable.lightning_status.reason,'Feed unavailable');
  raw.lightning_status={status:'clear',checked_at:iso(-60000)};
  raw.warnings_status={status:'ok',checked_at:iso(-60000)};
  const checked=mapper.site(raw);
  assert.equal(checked.alert.status,'cleared');assert.equal(checked.flood.status,'normal');
  raw.environmental_events=[{...event,starts_at:iso(60000),ends_at:iso(120000),title:'Upcoming flood warning'}];
  const upcoming=mapper.site(raw);
  assert.equal(upcoming.flood.status,'normal');
  assert.equal(warningsWatch(raw.warnings_status,raw.environmental_events,now).count,0);
});
