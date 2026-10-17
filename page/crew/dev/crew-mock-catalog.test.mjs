import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';

test('demo map and crew details share only Sid’s 60 plants, scores and site timezones',async()=>{
  const rows=JSON.parse(await fs.readFile(new URL('../crew-data/monitored-sites.json',import.meta.url)));
  const originalFetch=globalThis.fetch,originalChannel=globalThis.BroadcastChannel;
  // This test needs no cross-tab channel or network. Catch accidental legacy reads.
  globalThis.BroadcastChannel=undefined;
  globalThis.fetch=async url=>{assert.equal(new URL(url).pathname.endsWith('/crew-data/monitored-sites.json'),true);return {ok:true,json:async()=>rows};};
  try{
    const {mockAPI}=await import('../crew-mocks.js');
    const sites=await mockAPI.listSites();
    assert.deepEqual(sites.map(s=>Number(s.id)),rows.map(s=>s.site_id));
    const wind=await mockAPI.readSite('67769');
    assert.equal(wind.name,'Rock Creek Wind');assert.equal(wind.demo,true);
    assert.equal(wind.score,sites.find(s=>s.id==='67769').score);
    for(const source of rows){const detail=await mockAPI.readSite(source.site_id);assert.equal(detail.timezone,source.timezone);assert.equal(detail.provenance.source_url,source.source_url);}
    await assert.rejects(mockAPI.readSite('999999'),/Unknown plant/);
    const briefs=await mockAPI.listBriefings('67769');assert.match(briefs[0].valid_date,/^\d{4}-\d{2}-\d{2}$/);
    sites[0].score=99;assert.notEqual((await mockAPI.listSites())[0].score,99);
  }finally{globalThis.fetch=originalFetch;globalThis.BroadcastChannel=originalChannel;}
});
