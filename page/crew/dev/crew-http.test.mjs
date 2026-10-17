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
  assert.equal(seen[0][1].credentials,'omit');assert.equal(seen[0][1].redirect,'error');
});
test('access tokens only go to HTTPS or 127.0.0.1, never unsafe routes or empty sessions',async()=>{
  let tokenCalls=0,fetchCalls=0;
  const token=async()=>{tokenCalls++;return 'test-token';};
  const fetcher=async()=>{fetchCalls++;return json(fixture.sites);};
  for(const baseURL of ['http://example.test/api','http://localhost:8000','ftp://example.test/api',
    'https://user:password@example.test/api','https://example.test/api?token=x','https://example.test/api#fragment']){
    await assert.rejects(createHTTPAPI({baseURL},token,fetcher).listSites(),/API URL must use HTTPS/);
  }
  await assert.rejects(createHTTPAPI({baseURL:'https://example.test/api',routes:{sites:'https://other.test/sites'}},token,fetcher).listSites(),/configured API origin/);
  assert.equal(tokenCalls,0);assert.equal(fetchCalls,0);
  const local=createHTTPAPI({baseURL:'http://127.0.0.1:8000'},token,fetcher);
  await local.listSites();assert.equal(tokenCalls,1);assert.equal(fetchCalls,1);
  await assert.rejects(createHTTPAPI(settings,async()=>'',fetcher).listSites(),/valid access token/);
  assert.equal(fetchCalls,1);
});
test('relative /api stays on a secure page origin and rejects unsafe URL forms before requesting a token',async()=>{
  const originalLocation=Object.getOwnPropertyDescriptor(globalThis,'location');
  const setPage=href=>Object.defineProperty(globalThis,'location',{configurable:true,value:href?{href}:undefined});
  let tokenCalls=0;const seen=[];
  const token=async()=>{tokenCalls++;return 'test-token';};
  const fetcher=async url=>{seen.push(url.href);return json(fixture.sites);};
  try{
    setPage('https://planit.example/crew/index.html?site=9001#map');
    await createHTTPAPI({baseURL:'/api'},token,fetcher).listSites();
    assert.equal(seen.at(-1),'https://planit.example/api/sites');
    setPage('http://127.0.0.1:4174/crew/index.html');
    await createHTTPAPI({baseURL:'/api/'},token,fetcher).listSites();
    assert.equal(seen.at(-1),'http://127.0.0.1:4174/api/sites');
    assert.equal(tokenCalls,2);

    setPage('https://planit.example/crew/index.html');
    for(const baseURL of ['//evil.test/api','/api?token=x','/api#fragment','/other','javascript:alert(1)','http://evil.test/api']){
      await assert.rejects(createHTTPAPI({baseURL},token,fetcher).listSites());
    }
    await assert.rejects(createHTTPAPI({baseURL:'/api',routes:{sites:'https://evil.test/sites'}},token,fetcher).listSites(),/configured API origin/);
    await assert.rejects(createHTTPAPI({baseURL:'/api',routes:{sites:'../admin'}},token,fetcher).listSites(),/configured API origin/);
    for(const page of ['http://localhost:4174/crew/','http://127.0.0.1.evil.test/crew/','file:///crew/index.html']){
      setPage(page);
      await assert.rejects(createHTTPAPI({baseURL:'/api'},token,fetcher).listSites(),/Relative \/api requires/);
    }
    setPage(null);
    await assert.rejects(createHTTPAPI({baseURL:'/api'},token,fetcher).listSites(),/Relative \/api requires/);
    assert.equal(tokenCalls,2);assert.equal(seen.length,2);
  }finally{
    if(originalLocation)Object.defineProperty(globalThis,'location',originalLocation);
    else delete globalThis.location;
  }
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

test('latest briefing uses its contract URL and keeps a local display key without history requests',async()=>{
  const seen=[];
  const api=createHTTPAPI(settings,async()=>'token',async url=>{
    seen.push(url.href);return json(url.pathname.includes('/sites/')?fixture.details['9001']:fixture.briefings['9001']);
  });
  await api.readSite('9001');
  const [latest]=await api.listBriefings('9001');
  assert.equal(seen[1],'https://example.test/api/briefings/9001');
  assert.equal((await api.readBriefing('9001',latest.id)).body,fixture.briefings['9001'].text);
  assert.equal(latest.valid_date,'2026-10-18');assert.equal(latest.timezone,'America/New_York');
  assert.equal(seen.length,2);assert.equal(latest.delivery_status,null);
  assert.throws(()=>api.readPreferences('9001'),/not part/);
  assert.throws(()=>api.savePreferences('9001',{}),/not part/);
});
test('missing latest briefings give an empty state, but permission failures remain errors',async()=>{
  const absent=createHTTPAPI(settings,async()=>'token',async()=>json({error:{code:'not_found',message:'No briefing'}},404));
  assert.deepEqual(await absent.listBriefings('9001'),[]);
  const denied=createHTTPAPI(settings,async()=>'token',async()=>json({error:{code:'forbidden',message:'Not allowed'}},403));
  await assert.rejects(denied.listBriefings('9001'),/Not allowed/);
});
