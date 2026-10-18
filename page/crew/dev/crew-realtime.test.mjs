import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import {createHTTPAPI} from '../crew-http.js';
import {subscribeContractEvents} from '../crew-integration.js';
const fixture=JSON.parse(await fs.readFile(new URL('./fixtures/contract-v1.1.json',import.meta.url)));
const json=value=>new Response(JSON.stringify(value),{headers:{'Content-Type':'application/json'}});
const flush=()=>new Promise(resolve=>setImmediate(resolve));
function clock(){
  let id=0;const timeouts=new Map(),intervals=new Map();
  return {timeouts,intervals,setTimeout(fn,ms){const key=++id;timeouts.set(key,{fn,ms});return key;},clearTimeout(key){timeouts.delete(key);},setInterval(fn,ms){const key=++id;intervals.set(key,{fn,ms});return key;},clearInterval(key){intervals.delete(key);},next(){const [key,value]=timeouts.entries().next().value;timeouts.delete(key);value.fn();}};
}
function harness(){
  const timers=clock(),events=[],connections=[],requests=[],callbacks=[];
  let closes=0,tokens=0,alerts=structuredClone(fixture.alerts),fail=false;
  const details=structuredClone(fixture.details['9001']),sites=structuredClone(fixture.sites);
  const source={subscribe(options){callbacks.push(options);return()=>{closes++;};}};
  const api=createHTTPAPI({baseURL:'https://example.test',realtimeSource:source,timers},async()=>`token-${++tokens}`,async url=>{
    requests.push(url.pathname);if(fail)throw new TypeError('API unavailable');
    return json(url.pathname==='/alerts'?alerts:url.pathname==='/sites'?sites:details);
  });
  return {api,timers,events,connections,requests,callbacks,details,sites,get closes(){return closes;},get tokens(){return tokens;},get alerts(){return alerts;},set alerts(value){alerts=value;},set fail(value){fail=value;}};
}
test('ID-only notices refetch details; unrelated sites and old custom event names are ignored',async()=>{
  const h=harness(),stop=h.api.subscribeEvents('9001',e=>h.events.push(e),c=>h.connections.push(c));
  await flush();h.callbacks[0].onConnection(true);await flush();
  assert.equal(h.connections.at(-1),true);assert.equal(h.events.at(-1).site.alert.status,'hold');
  assert.equal(h.callbacks[0].site_id,9001);assert.equal(h.callbacks[0].accessToken,undefined);assert.ok(h.tokens>=3);
  const count=h.requests.length;
  h.callbacks[0].onEvent({type:'alert.updated',site_id:9002,alert_id:103,clear_at:'2026-10-17T19:00:00Z'});
  h.callbacks[0].onEvent({type:'alert',site_id:9001,alert:{status:'cleared'}});await flush();
  assert.equal(h.requests.length,count);
  h.alerts=structuredClone(fixture.alerts);h.alerts[0].clear_at='2026-10-17T19:00:00Z';
  h.callbacks[0].onEvent({type:'alert.updated',site_id:9001,alert_id:101,clear_at:'1900-01-01T00:00:00Z'});await flush();
  assert.equal(h.events.at(-1).site.alert.all_clear_at,'2026-10-17T19:00:00Z');
  assert.ok(!h.requests.includes('/events'));stop();
});
test('only a fetched matching lightning clearance clears the hold; report notices refresh reports',async()=>{
  const h=harness(),stop=h.api.subscribeEvents('9001',e=>h.events.push(e),c=>h.connections.push(c));
  await flush();h.callbacks[0].onConnection(true);await flush();
  h.alerts=[];
  h.callbacks[0].onEvent({type:'alert.cleared',site_id:9001,alert_id:102});await flush();
  assert.equal(h.events.at(-1).site.alert.status,'unknown');
  h.callbacks[0].onEvent({type:'alert.cleared',site_id:9001,alert_id:101});await flush();
  assert.equal(h.events.at(-1).site.alert.status,'cleared');
  h.callbacks[0].onEvent({type:'report.created',site_id:9001,report_id:fixture.reports[0].id,created_at:fixture.reports[0].created_at});await flush();
  assert.equal(h.events.at(-1).type,'report');assert.equal(h.events.at(-1).report,undefined);
  stop();
});
test('reconnect gets a fresh token and snapshot; cleanup stops retries, heartbeats and late events',async()=>{
  const h=harness(),stop=h.api.subscribeEvents('9001',e=>h.events.push(e),c=>h.connections.push(c));
  await flush();h.callbacks[0].onConnection(true);await flush();
  assert.equal(h.timers.intervals.size,1);
  for(const {fn} of h.timers.intervals.values())fn();assert.equal(h.events.at(-1).type,'heartbeat');
  h.callbacks[0].onError();assert.equal(h.connections.at(-1),false);assert.equal(h.closes,1);
  assert.equal(h.timers.intervals.size,0);assert.equal([...h.timers.timeouts.values()][0].ms,1000);
  const previousTokens=h.tokens;h.timers.next();await flush();assert.equal(h.callbacks.length,2);assert.ok(h.tokens>previousTokens);assert.equal(h.callbacks[1].accessToken,undefined);
  h.callbacks[1].onConnection(true);await flush();assert.equal(h.connections.at(-1),true);
  stop();const count=h.events.length;
  h.callbacks[1].onEvent({type:'alert.started',site_id:9001,alert_id:101});await flush();
  assert.equal(h.events.length,count);assert.equal(h.timers.timeouts.size,0);assert.equal(h.timers.intervals.size,0);assert.equal(h.closes,2);
});
test('API failures keep notifications disconnected and an unconfigured provider never requests /events',async()=>{
  const h=harness(),stop=h.api.subscribeEvents('9001',e=>h.events.push(e),c=>h.connections.push(c));
  await flush();h.fail=true;h.callbacks[0].onConnection(true);await flush();
  assert.equal(h.connections.at(-1),false);assert.equal(h.events.length,0);stop();
  const timers=clock();let requested=false;const connections=[];
  const api=createHTTPAPI({baseURL:'https://example.test',timers},async()=>'token',async()=>{requested=true;return json([]);});
  const close=api.subscribeEvents('9001',()=>{},value=>connections.push(value));await flush();
  assert.equal(requested,false);assert.equal(connections.at(-1),false);assert.equal(timers.timeouts.size,1);
  close();assert.equal(timers.timeouts.size,0);
});

test('expired authentication stops the crew reconnect loop',async()=>{
  const timers=clock(),connections=[];
  const stop=subscribeContractEvents({siteId:'621',timers,
    getSource:()=>({subscribe(){assert.fail('No socket after expired auth');}}),
    getToken:async()=>{throw Object.assign(new Error('Login needed'),{error:'missing_refresh_token'});},
    readSite:async()=>({}),listSites:async()=>[],onEvent(){},onConnection:value=>connections.push(value)});
  await flush();
  assert.equal(timers.timeouts.size,0);
  assert.equal(connections.at(-1),false);
  stop();
});

test('offline pauses crew retries and online refetches before connected',async()=>{
  const timers=clock(),listeners=new Map(),browser={navigator:{onLine:false},
    addEventListener(type,handler){listeners.set(type,handler);},removeEventListener(type){listeners.delete(type);}};
  let callbacks,reads=0;const connections=[];
  const stop=subscribeContractEvents({siteId:null,timers,browser,
    getSource:()=>({subscribe(value){callbacks=value;return()=>{};}}),getToken:async()=>'token',
    readSite:async()=>({}),listSites:async()=>{reads++;return[];},onEvent(){},onConnection:value=>connections.push(value)});
  await flush();assert.equal(callbacks,undefined);assert.equal(timers.timeouts.size,0);
  browser.navigator.onLine=true;listeners.get('online')();await flush();
  callbacks.onConnection(true);await flush();assert.equal(reads,1);assert.equal(connections.at(-1),true);
  browser.navigator.onLine=false;listeners.get('offline')();assert.equal(connections.at(-1),false);
  browser.navigator.onLine=true;listeners.get('online')();await flush();callbacks.onConnection(true);await flush();
  assert.equal(reads,2);assert.equal(connections.at(-1),true);
  stop();assert.equal(listeners.size,0);
});

test('hidden crew document closes its listener and a visible document refetches once before reconnecting',async()=>{
  const timers=clock(),listeners=new Map(),document={hidden:false,
    addEventListener(type,handler){listeners.set(`document:${type}`,handler);},
    removeEventListener(type){listeners.delete(`document:${type}`);}},
    browser={document,navigator:{onLine:true},
    addEventListener(type,handler){listeners.set(type,handler);},removeEventListener(type){listeners.delete(type);}};
  const callbacks=[],events=[],connections=[];
  let closes=0,reads=0,tokens=0;
  const stop=subscribeContractEvents({siteId:'9001',browser,timers,
    getSource:()=>({subscribe(value){callbacks.push(value);return()=>{closes++;};}}),
    getToken:async()=>`token-${++tokens}`,
    readSite:async()=>({id:'9001',revision:++reads}),listSites:async()=>[],
    onEvent:event=>events.push(event),onConnection:value=>connections.push(value)});
  try{
    await flush();assert.equal(callbacks.length,1);
    callbacks[0].onConnection(true);await flush();
    assert.equal(reads,1);assert.equal(connections.at(-1),true);
    document.hidden=true;
    assert.equal(typeof listeners.get('document:visibilitychange'),'function');
    listeners.get('document:visibilitychange')();await flush();
    assert.equal(closes,1);assert.equal(connections.at(-1),false);
    assert.equal(timers.timeouts.size,0);assert.equal(timers.intervals.size,0);
    const before=events.length;
    callbacks[0].onEvent({type:'report.created',site_id:9001,report_id:'old-report'});
    callbacks[0].onConnection(true);await flush();
    assert.equal(reads,1);assert.equal(events.length,before);
    document.hidden=false;listeners.get('document:visibilitychange')();await flush();
    assert.equal(callbacks.length,2);assert.ok(tokens>=2);
    callbacks[1].onConnection(true);await flush();
    assert.equal(reads,2);assert.equal(connections.at(-1),true);
    listeners.get('document:visibilitychange')();await flush();
    assert.equal(callbacks.length,2,'a duplicate visible event must not open another listener');
  }finally{stop();}
  assert.equal(closes,2);assert.equal(timers.timeouts.size,0);assert.equal(timers.intervals.size,0);
  assert.equal(listeners.size,0);
  callbacks[1].onEvent({type:'report.created',site_id:9001,report_id:'after-stop'});await flush();
  assert.equal(reads,2);
});

test('score batches update the selected site from the API and ignore unrelated or malformed ID lists',async()=>{
  const h=harness(),stop=h.api.subscribeEvents('9001',e=>h.events.push(e),c=>h.connections.push(c));
  try{
    await flush();h.callbacks[0].onConnection(true);await flush();const count=h.requests.length;
    for(const site_ids of [undefined,null,[],[9002],['9001'],[9001,-1],[9001,1.5],[9001,Number.MAX_SAFE_INTEGER+1]])h.callbacks[0].onEvent({type:'scores.updated',site_ids});
    await flush();assert.equal(h.requests.length,count);
    h.details.score.score=8.8;h.details.score.factors[0].contribution+=.6;
    for(let n=0;n<50;n++)h.callbacks[0].onEvent({type:'scores.updated',site_ids:[9001,9001],score:10});
    await flush();assert.equal(h.requests.length,count+2);
    assert.equal(h.events.at(-1).site.score,8.8);assert.equal(h.events.at(-1).site.score_reconciles,true);
  }finally{stop();}
});

test('global listeners refetch one bulk list for scores, alerts and reports, including reconnect recovery',async()=>{
  const h=harness(),stop=h.api.subscribeEvents(null,e=>h.events.push(e),c=>h.connections.push(c));
  try{
    await flush();h.callbacks[0].onConnection(true);await flush();assert.deepEqual(h.requests,['/sites']);
    h.sites[0].score=9;
    for(let n=0;n<50;n++)h.callbacks[0].onEvent({type:'scores.updated',site_ids:[9001,n%2?9002:9003]});
    await flush();assert.equal(h.requests.length,2);assert.equal(h.events.at(-1).sites[0].score,9);
    assert.deepEqual(new Set(h.events.at(-1).site_ids),new Set(['9001','9002','9003']));
    const notices=[{type:'alert.started',alert_id:101},{type:'alert.updated',alert_id:101},{type:'alert.cleared',alert_id:101},{type:'report.created',report_id:'report-id'},{type:'report.resolved',report_id:'report-id'}];
    for(const notice of notices){h.callbacks[0].onEvent({...notice,site_id:9001});await flush();assert.equal(h.events.at(-1).type,'site');assert.deepEqual(h.events.at(-1).site_ids,['9001']);}
    assert.ok(h.requests.every(path=>path==='/sites'));assert.equal(h.requests.length,7);
    h.callbacks[0].onConnection(false);h.sites[0].score=null;h.timers.next();await flush();h.callbacks[1].onConnection(true);await flush();
    assert.equal(h.events.at(-1).sites[0].score,null);assert.equal(h.connections.at(-1),true);
  }finally{stop();}
});

test('a socket that closes before acknowledgement retries immediately and does not duplicate handshake snapshots',async()=>{
  const h=harness(),stop=h.api.subscribeEvents('9001',e=>h.events.push(e),c=>h.connections.push(c));
  try{
    await flush();h.callbacks[0].onConnection(false);assert.equal(h.closes,1);assert.equal([...h.timers.timeouts.values()][0].ms,1000);
    h.timers.next();await flush();h.callbacks[1].onConnection(true);h.callbacks[1].onConnection(true);await flush();
    assert.equal(h.requests.length,2);assert.equal(h.timers.intervals.size,1);
  }finally{stop();}
});

test('score bursts during a slow read allow only one active and one pending score refresh',async()=>{
  const timers=clock(),reads=[],delivered=[];let callbacks,blocked=false;
  const stop=subscribeContractEvents({siteId:'621',timers,getSource:()=>({subscribe(value){callbacks=value;return()=>{};}}),getToken:async()=>'token',
    readSite:async()=>{if(!blocked)return {id:'621',score:1};return new Promise(resolve=>reads.push(resolve));},listSites:async()=>[],onEvent:event=>delivered.push(event),onConnection(){}});
  try{
    await flush();callbacks.onConnection(true);await flush();blocked=true;
    callbacks.onEvent({type:'scores.updated',site_ids:[621]});await flush();assert.equal(reads.length,1);
    for(let n=0;n<100;n++)callbacks.onEvent({type:'scores.updated',site_ids:[621]});await flush();assert.equal(reads.length,1);
    reads[0]({id:'621',score:2});await flush();assert.equal(reads.length,2);
    reads[1]({id:'621',score:3});await flush();assert.equal(reads.length,2);assert.equal(delivered.at(-1).site.score,3);
  }finally{stop();}
});
