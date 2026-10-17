// Read-only smoke check for Alan's sample server; never sends a report or alters data.
import assert from 'node:assert/strict';
import {createHTTPAPI} from '../crew-http.js';
const baseURL=process.env.PLANIT_API_BASE_URL||'http://localhost:8010';
const health=await fetch(new URL('/health',baseURL),{signal:AbortSignal.timeout(5000)});
assert.ok(health.ok,'The API must be running.');
assert.equal((await health.json()).data,'sample','This check is only for the explicitly labeled sample server.');
const api=createHTTPAPI({baseURL},async()=>'sample-contract-check');
const sites=await api.listSites();assert.ok(sites.length);
const first=sites[0],site=await api.readSite(first.id);
assert.equal(site.id,first.id);assert.equal(typeof site.score,'number');assert.equal(site.score_reconciles,true);
assert.equal(site.alert.status,'hold');assert.equal(site.alert.distance_miles,6.2);
const reports=await api.listReports(first.id);assert.ok(reports.every(r=>r.site_id===first.id));
const [latest]=await api.listBriefings(first.id);assert.ok(latest);
const briefing=await api.readBriefing(first.id,latest.id);assert.ok(briefing.body);assert.equal(briefing.valid_date,'2026-10-18');
const floodSite=await api.readSite('9002');assert.equal(floodSite.flood.status,'warning');assert.equal(floodSite.flood.overnight_rain_mm,null);
console.log(JSON.stringify({sampleSites:sites.length,selectedSite:site.id,score:site.score,baseline:site.baseline,
  factorSum:site.factors.reduce((sum,f)=>sum+f.contribution,0),clear_at:site.alert.all_clear_at,
  reports:reports.length,protectedPhotoRoute:reports[0]?.photo?'available':'not yet available',
  briefingDate:briefing.valid_date,briefingTextReceived:Boolean(briefing.body),floodWarning:floodSite.flood.status},null,2));
