import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import {screeningDetail,screeningSummary,expireScreening,scoreBadgeText,featureLabel} from '../crew-screening.js';
import {createContractMapper,mapSiteSummary} from '../crew-integration.js';
import {createHTTPAPI} from '../crew-http.js';
import {scorePanel,scoreWaterfall,wildlifeHTML,scoreBadgeHTML,scoreWindowHTML} from '../crew-ui.js';
import {atlasRoster,atlasSummaries} from '../crew-atlas-data.js';
const legacy=JSON.parse(await fs.readFile(new URL('./fixtures/contract-v1.1.json',import.meta.url)));
const roster=atlasRoster(JSON.parse(await fs.readFile(new URL('../crew-data/monitored-sites.json',import.meta.url))));
const epoch=Date.parse('2026-10-18T00:00:00Z');
const iso=ms=>new Date(ms).toISOString();

test('missing heat-index feature has a readable label without changing its contribution',()=>{
  assert.equal(featureLabel('heat_index_max_f_missing'),'Heat index not available');
  const raw=screening();raw.factors[0].feature='heat_index_max_f_missing';
  const mapped=screeningDetail(raw,epoch);
  assert.equal(mapped.factors[0].name,'Heat index not available');
  assert.equal(mapped.factors[0].contribution,raw.factors[0].contribution);
  assert.equal(mapped.score,raw.score);
});
function screening(now=epoch){return {score:6.4,baseline:2.1,status:'research',
  factors:[{feature:'rain_total_24h_in',contribution:2.6},{feature:'wind_max_mph',contribution:1.2},{feature:'heat_index_max_f',contribution:.9},{feature:'month_cos',contribution:-.4}],
  target:'NWS warning or heat advisory covering the plant within the next 24 hours',
  captured_at:iso(now-60000),scored_at:iso(now-30000),valid_from:iso(now),valid_until:iso(now+86400000),
  artifact_sha256:'a'.repeat(64),snapshot_id:'b'.repeat(64),clears_stop_work:false};}
function detail(now=epoch){return {...structuredClone(legacy.details['9001']),screening:screening(now),wildlife_context:{site_id:9001,status:'recorded_sightings',radius_km:25,
  radius_meaning:'Map context filter, not a safety boundary',limitations:'Presence-only sample; no sightings does not mean absence.',
  encounter_probability:null,numeric_score_contribution:null,sightings:[{species:'American alligator',observed_calendar_date:'2025-09-11',observed_at:'2025-09-11T00:00:00Z',distance_km:19.2,coordinate_uncertainty_m:5,source_name:'GBIF',source_url:'https://www.gbif.org/occurrence/123'}]}};}

test('v1.2 screening takes priority over legacy scores and retains signed feature explanations and evidence',()=>{
  const site=createContractMapper({now:()=>epoch}).site(detail());
  assert.equal(site.score,6.4);assert.equal(site.baseline,2.1);assert.equal(site.score_status,'research');
  assert.equal(site.score_reconciles,true);assert.equal(site.factors[0].name,'Rain over 24 hours');
  assert.equal(site.factors[3].contribution,-.4);assert.equal(site.factors[0].hazard_type,undefined);
  assert.equal(site.valid_until,iso(epoch+86400000));assert.equal(site.alert.status,'hold');
  assert.equal(site.alert.all_clear_at,'2026-10-17T18:34:00Z');
  assert.equal(site.wildlife_context.encounter_probability,null);assert.equal(site.wildlife_context.numeric_score_contribution,null);
  assert.equal(site.wildlife_context.sightings[0].observed_calendar_date,'2025-09-11');
});
test('explicitly missing or withheld screening never falls back to the legacy score or clears lightning',()=>{
  for(const status of ['no_data','stale','invalid','research_unapproved']){
    const raw=detail();raw.screening={score:8.2,status,reason:'Feed withheld',factors:[]};
    const site=createContractMapper({now:()=>epoch}).site(raw);
    assert.equal(site.score,null);assert.equal(site.score_status,status);assert.equal(site.baseline,null);assert.deepEqual(site.factors,[]);
    assert.equal(site.alert.status,'hold');
  }
  const raw=detail();raw.screening=null;assert.equal(createContractMapper({now:()=>epoch}).site(raw).score,null);
});
test('expiry, future timestamps, malformed contributions and mismatched sums suppress only the score',()=>{
  const changes=[{captured_at:iso(epoch-7200001)},{valid_until:iso(epoch-1)},{scored_at:iso(epoch+1)},
    {baseline:9},{clears_stop_work:true},{status:'approved'},
    {factors:[{hazard_type:'heat',contribution:4.3}]},{factors:[{feature:'heat_index_max_f',contribution:NaN}]}];
  for(const change of changes){
    const raw=detail();Object.assign(raw.screening,change);
    const site=createContractMapper({now:()=>epoch}).site(raw);
    assert.equal(site.score,null,JSON.stringify(change));assert.equal(site.alert.status,'hold');
    assert.match(site.score_status,/stale|invalid/);
  }
  const valid=screeningDetail(screening(),epoch),expired=expireScreening(valid,epoch+7200001);
  assert.equal(valid.score,6.4);assert.equal(expired.score,null);assert.equal(expired.score_status,'stale');
});
test('a real zero remains a prototype zero, with readable future feature names',()=>{
  const raw=screening();raw.score=0;raw.baseline=.4;raw.factors=[{feature:'month_cos',contribution:-.4}];
  assert.equal(screeningDetail(raw,epoch).score,0);assert.equal(scoreBadgeText(screeningDetail(raw,epoch)),'Prototype');
  assert.equal(featureLabel('new_forecast_feature'),'New forecast feature');
});
test('summary metadata supports the contract list without inventing a forecast window',()=>{
  const raw={...legacy.sites[0],...screening(),score_status:'research'};
  raw.top_factors=raw.factors.slice(0,2);
  delete raw.status;delete raw.captured_at;delete raw.valid_from;delete raw.valid_until;
  const summary=mapSiteSummary(raw,{now:epoch});
  assert.equal(summary.score,6.4);assert.equal(summary.valid_from,null);assert.equal(summary.score_status,'research');
  assert.equal(summary.top_factors[0].name,'Rain over 24 hours');
  assert.match(scoreWindowHTML(summary),/Next 24 hours.*exact window available in site details/);
  assert.equal(screeningSummary({...raw,score_status:'stale'},epoch).score,null);
  assert.equal(mapSiteSummary({...raw,top_factors:[]},{now:epoch}).score,null);
});
test('HTTP adapter accepts v1.2 detail from the authorized endpoint',async()=>{
  const seen=[],raw=detail(Date.now());
  const api=createHTTPAPI({baseURL:'https://api.example'},async()=>'test-token',async(url,options)=>{
    seen.push([url.pathname,options.headers.Authorization]);return new Response(JSON.stringify(raw),{headers:{'Content-Type':'application/json'}});
  });
  const site=await api.readSite('9001');assert.equal(site.score,6.4);assert.equal(site.factors[0].feature,'rain_total_24h_in');
  assert.deepEqual(seen,[['/sites/9001','Bearer test-token']]);
});
test('UI shows Prototype, the target window, signed contributions and a reconciled waterfall',()=>{
  const site=createContractMapper().site(detail(Date.now())),html=scorePanel(site),wildlife=wildlifeHTML(site);
  assert.match(html,/>Prototype</);assert.match(html,/Forecast window:/);assert.doesNotMatch(html,/Forecast window: not supplied/);
  assert.match(html,/Rain over 24 hours/);assert.match(html,/-0.40 points/);assert.match(html,/doesn’t predict injuries/);
  assert.match(html,/crew-waterfall/);assert.match(html,/Baseline/);assert.match(html,/Final index/);
  assert.doesNotMatch(html,/<svg/);assert.match(wildlife,/2025-09-11/);assert.match(wildlife,/GBIF/);assert.match(wildlife,/19.2 km/);
  assert.match(wildlife,/location accurate to about 5 m/);assert.match(wildlife,/not what’s here today/);
  assert.match(wildlifeHTML({}),/aren’t available.*doesn’t mean there are no animals/);
  assert.match(wildlifeHTML({wildlife_context:{status:'no_records_in_sample',sightings:[]}}),/No past sightings.*doesn’t mean there are no animals/);
  assert.match(scoreBadgeHTML({demo:true,score:4}),/Sample score/);
  assert.equal(scoreWaterfall({...site,score_reconciles:false}),'');
});
test('map merges retain prototype metadata and prevent stale or null scores from becoming zero',()=>{
  const raw={site_id:621,...screening(Date.now()),score_status:'research'};
  raw.top_factors=raw.factors.slice(0,2);
  raw.lightning_status={status:'clear',checked_at:new Date().toISOString()};
  const [site]=atlasSummaries([roster.find(s=>s.id==='621')],[raw]);
  assert.equal(site.score,6.4);assert.equal(site.score_status,'research');assert.equal(site.valid_until,raw.valid_until);
  assert.equal(site.top_factors[0].name,'Rain over 24 hours');assert.equal(site.lightning_status.status,'clear');
  assert.equal(site.name,'Turkey Point');
  assert.equal(atlasSummaries([site],[{...raw,score_status:'stale'}])[0].score,null);
  assert.equal(atlasSummaries([site],[{...raw,score:null}])[0].score,null);
});
test('existing API format remains readable and explicitly labeled during backend migration',()=>{
  const site=createContractMapper().site(structuredClone(legacy.details['9001']));
  assert.equal(site.score,8.2);assert.equal(site.sample,true);assert.equal(scoreBadgeText(site),'Sample score');
  const summary=mapSiteSummary(legacy.sites[0]);assert.equal(summary.score_status,'legacy');assert.equal(scoreBadgeText(summary),'Legacy API score');
});
