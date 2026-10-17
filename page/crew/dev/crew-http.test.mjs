import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import {createHTTPAPI} from '../crew-http.js';
const fixture=JSON.parse(await fs.readFile(new URL('./fixtures/contract-v1.1.json',import.meta.url)));
const settings={baseURL:'https://example.test/api'};
const json=(value,status=200)=>new Response(JSON.stringify(value),{status,headers:{'Content-Type':'application/json'}});

test('HTTP reads contract arrays without invented pagination and preserves prefix and authentication',async()=>{
  const seen=[];const api=createHTTPAPI(settings,async()=>'test-token',async(url,options)=>{seen.push([url.href,options]);return json(fixture.sites);});
  const sites=await api.listSites();assert.equal(sites[0].id,'9001');assert.equal(sites.length,3);
  assert.equal(seen[0][0],'https://example.test/api/sites');assert.equal(seen[0][1].headers.Authorization,'Bearer test-token');
});
test('site detail requests validate identity and map the full nested score',async()=>{
  const api=createHTTPAPI(settings,async()=>'token',async()=>json(fixture.details['9001']));
  assert.equal((await api.readSite('9001')).score,8.2);
  await assert.rejects(api.readSite('9002'),/different site_id/);
  await assert.rejects(api.readSite('invalid'),/site_id/);
});
test('out-of-order HTTP responses cannot overwrite a later request',async()=>{
  let release;let calls=0;
  const api=createHTTPAPI(settings,async()=>'token',async()=>++calls===1?new Promise(resolve=>{release=()=>resolve(json(fixture.details['9001']));}):json({...fixture.details['9001'],name:'Latest response'}));
  const older=api.readSite('9001');await new Promise(resolve=>setImmediate(resolve));
  const latest=await api.readSite('9001');release();
  assert.equal((await older).name,latest.name);assert.equal(latest.name,'Latest response');
});
test('contract error code and message survive; live failures do not use sample data',async()=>{
  const api=createHTTPAPI(settings,async()=>'token',async()=>json({error:{code:'not_found',message:'Site 9001 not found'}},404));
  await assert.rejects(api.readSite('9001'),error=>error.code==='not_found'&&error.status===404&&error.message==='Site 9001 not found');
  const forbidden=createHTTPAPI(settings,async()=>'token',async()=>new Response('',{status:403}));await assert.rejects(forbidden.listSites(),/permission/);
  const invalid=createHTTPAPI({...settings,baseURL:''},async()=>'token');await assert.rejects(invalid.listSites(),/baseURL/);
});
