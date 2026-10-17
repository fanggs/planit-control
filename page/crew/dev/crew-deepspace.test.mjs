import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import {createHTTPAPI} from '../crew-http.js';
import {createCrewRealtimeProvider} from '../crew-realtime-source.js';
import {subscribeContractEvents} from '../crew-integration.js';
const fixture=JSON.parse(await fs.readFile(new URL('./fixtures/contract-v1.1.json',import.meta.url)));
const flush=()=>new Promise(resolve=>setImmediate(resolve));
class Socket{
  static all=[];
  listeners=new Map();sent=[];closed=false;
  constructor(url){this.url=url;Socket.all.push(this);Socket.onCreate?.(this);}
  addEventListener(type,listener){const listeners=this.listeners.get(type)||[];listeners.push(listener);this.listeners.set(type,listeners);}
  emit(type,event={}){for(const listener of this.listeners.get(type)||[])listener(event);}
  send(value){this.sent.push(JSON.parse(value));}
  close(){this.closed=true;this.emit('close');}
  message(type,payload){this.emit('message',{data:JSON.stringify({type,payload})});}
}

test('the default HTTP path loads Alan’s actual protocol, refetches API scores, and never sends a bearer token to DeepSpace',async()=>{
  Socket.all=[];let signalSocket;const socketReady=new Promise(resolve=>{signalSocket=resolve;});Socket.onCreate=signalSocket;const events=[],status=[],requests=[];let score=8.2;
  const api=createHTTPAPI({baseURL:'https://api.example',realtime:{baseURL:'https://planit-realtime.app.space',appId:'app_01M557EC8CQY7VDN5253P86ZBN',WebSocketImpl:Socket}},async()=>'private-test-token',async(url,options)=>{
    assert.equal(options.headers.Authorization,'Bearer private-test-token');requests.push(url.pathname);
    const detail=structuredClone(fixture.details['9001']);detail.score.score=score;detail.score.factors[0].contribution+=score-8.2;
    return new Response(JSON.stringify(url.pathname==='/alerts'?fixture.alerts:detail),{headers:{'Content-Type':'application/json'}});
  });
  const stop=api.subscribeEvents('9001',event=>events.push(event),value=>status.push(value));
  try{
    // Wait for the actual listener to create its socket, without polling the filesystem import.
    const socket=await new Promise((resolve,reject)=>{
      const deadline=setTimeout(()=>reject(new Error('The default listener did not create a socket.')),2000);
      socketReady.then(value=>{clearTimeout(deadline);resolve(value);});
    });
    assert.equal(Socket.all.length,1);socket.emit('open');
    assert.equal(socket.sent[0].type,'core.subscribe');assert.equal(socket.sent[0].payload.query.collection,'events');
    assert.equal(socket.url,'wss://planit-realtime.app.space/ws/app%3Aapp_01M557EC8CQY7VDN5253P86ZBN');
    assert.ok(!JSON.stringify(socket.sent).includes('private-test-token'));
    socket.message('core.query_result',{subscriptionId:socket.sent[0].payload.subscriptionId,records:[{data:{type:'scores.updated',site_ids:'[9001]'}}]});await flush();
    assert.equal(status.at(-1),true);assert.equal(events.at(-1).site.score,8.2);
    score=9.1;socket.message('core.record_change',{collection:'events',changeType:'create',record:{data:{type:'scores.updated',site_ids:'[9001]'}}});await flush();
    assert.equal(events.at(-1).site.score,9.1);assert.equal(requests.length,4);
    const count=requests.length;
    socket.message('core.record_change',{collection:'events',changeType:'update',record:{data:{type:'scores.updated',site_ids:'[9001]'}}});
    socket.message('core.record_change',{collection:'events',changeType:'create',record:{data:{type:'scores.updated',site_ids:'invalid'}}});await flush();assert.equal(requests.length,count);
    stop();assert.equal(socket.closed,true);
    socket.message('core.record_change',{collection:'events',changeType:'create',record:{data:{type:'scores.updated',site_ids:'[9001]'}}});await flush();assert.equal(requests.length,count);
  }finally{stop();Socket.onCreate=undefined;}
});

test('provider overrides remain supported and a failed source import is retried',async()=>{
  let loads=0;const source={subscribe(){}},settings={realtime:{baseURL:'https://bridge.example',appId:'public-app'}};
  const provider=createCrewRealtimeProvider(settings,{getBrowser:()=>({}),loadSource:async()=>{loads++;if(loads===1)throw new Error('temporary import failure');return {createDeepSpaceSource:()=>source};}});
  await assert.rejects(provider(),/temporary/);assert.equal(await provider(),source);assert.equal(await provider(),source);assert.equal(loads,2);
  const override={subscribe(){}};settings.realtimeSource=override;assert.equal(await provider(),override);
  assert.equal(await createCrewRealtimeProvider({},{getBrowser:()=>({PlanITCrewRealtime:source})})(),source);
  await assert.rejects(createCrewRealtimeProvider({},{getBrowser:()=>({})})(),/URL and app ID/);
});

test('leaving while the shared source loads cancels authentication and any late subscription',async()=>{
  let resolveSource,tokens=0,subscriptions=0;
  const loading=new Promise(resolve=>{resolveSource=resolve;});
  const stop=subscribeContractEvents({siteId:'9001',getSource:()=>loading,getToken:async()=>{tokens++;},readSite:async()=>({}),listSites:async()=>[],onEvent(){assert.fail('An abandoned screen must not update.');},onConnection(){}});
  stop();resolveSource({subscribe(){subscriptions++;return()=>{};}});await flush();
  assert.equal(tokens,0);assert.equal(subscriptions,0);
});
