import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createHTTPAPI,createSSEDecoder} from '../crew-http.js';
const settings={baseURL:'https://example.test/api',routes:{sites:'/sites',site:'/sites/{id}',reports:'/reports',preferences:'/sites/{id}/briefing-preferences'}};
const json=value=>new Response(JSON.stringify(value),{status:200,headers:{'Content-Type':'application/json'}});
test('HTTP adapter preserves API prefix, bearer token, and paginated site coverage',async()=>{
  const seen=[];const api=createHTTPAPI(settings,async()=>'test-token',async(url,options)=>{seen.push([url.href,options]);return json(url.searchParams.has('cursor')?{items:[{id:'2'}]}:{items:[{id:'1'}],next_cursor:'page-two'});});
  assert.equal((await api.listSites()).length,2);assert.equal(seen[0][0],'https://example.test/api/sites?limit=1000');assert.equal(seen[0][1].headers.Authorization,'Bearer test-token');assert.match(seen[1][0],/cursor=page-two/);
});
test('reports use multipart binary photo plus a stable request ID',async()=>{
  let sent;const api=createHTTPAPI(settings,async()=>'token',async(url,options)=>{sent=options;return json({id:'receipt',site_id:'621'});});
  await api.submitReport({site_id:'621',request_id:'stable-id',photo:new File(['test photo'],'hazard.png',{type:'image/png'}),latitude:25.4,longitude:-80.3});
  assert.equal(sent.method,'POST');assert.equal(sent.headers['Content-Type'],undefined);assert.equal(sent.body.get('request_id'),'stable-id');assert.equal(sent.body.get('photo').type,'image/png');assert.equal(await sent.body.get('photo').text(),'test photo');
});
test('failed live requests throw; no synthetic success or sample fallback',async()=>{
  const api=createHTTPAPI(settings,async()=>'token',async()=>new Response('',{status:403}));await assert.rejects(api.readSite('621'),/permission/);
  const invalid=createHTTPAPI({...settings,baseURL:''},async()=>'token');await assert.rejects(invalid.listSites(),/baseURL/);
});
test('SSE decoder handles fragmented CRLF, multiple events and multiline JSON',()=>{
  const events=[],parse=createSSEDecoder(event=>events.push(event));parse('event: alert\r');parse('\ndata: {"site_id":"621",\r\ndata: "alert":{"version":2}}\r\n\r');parse('\nevent: heartbeat\ndata: {"server_time":"now"}\n\n');
  assert.equal(events.length,2);assert.equal(events[0].type,'alert');assert.equal(events[0].alert.version,2);assert.equal(events[1].type,'heartbeat');
});
test('repeated pagination cursor fails instead of silently omitting sites',async()=>{const api=createHTTPAPI(settings,async()=>'token',async()=>json({items:[],next_cursor:'same'}));await assert.rejects(api.listSites(),/repeated/);});
