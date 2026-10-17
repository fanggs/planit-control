import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import {atlasRoster} from '../crew-atlas-data.js';
import {watchAtlasScores} from '../crew-atlas-realtime.js';
const roster=atlasRoster(JSON.parse(await fs.readFile(new URL('../crew-data/monitored-sites.json',import.meta.url))));
const flush=()=>new Promise(resolve=>setImmediate(resolve));

test('bulk live updates recolor only the approved map roster without an extra API request',async()=>{
  let events,connection,closes=0;const sites=[],statuses=[];
  const stop=watchAtlasScores({roster,api:{subscribeEvents(id,onEvent,onConnection){assert.equal(id,null);events=onEvent;connection=onConnection;return()=>{closes++;};},listSites(){assert.fail('Bulk snapshots already contain the authorized list.');}},onSites:rows=>sites.push(rows),onConnection:value=>statuses.push(value)});
  await flush();events({type:'site',sites:[{site_id:621,score:9},{site_id:999999,score:10}]});connection(true);
  assert.equal(sites.at(-1).length,60);assert.equal(sites.at(-1).find(s=>s.id==='621').score,9);assert.equal(sites.at(-1).some(s=>s.id==='999999'),false);assert.equal(statuses.at(-1),true);
  events({type:'site',sites:[]});assert.equal(sites.at(-1).find(s=>s.id==='621').score,null);
  stop();events({type:'site',sites:[{site_id:621,score:0}]});connection(true);assert.equal(sites.length,2);assert.equal(closes,1);
});

test('custom invalidations coalesce while loading and stale reads cannot overwrite a newer bulk snapshot',async()=>{
  let events,resolveRead,requests=0;const delivered=[];
  const stop=watchAtlasScores({roster,api:{subscribeEvents(_id,callback){events=callback;return()=>{};},listSites(){requests++;return new Promise(resolve=>{resolveRead=resolve;});}},onSites:sites=>delivered.push(sites.find(s=>s.id==='621').score),onConnection(){}});
  try{
    await flush();events({type:'site'});for(let n=0;n<50;n++)events({type:'site'});assert.equal(requests,1);
    events({type:'site',sites:[{site_id:621,score:9}]});resolveRead([{site_id:621,score:4}]);await flush();
    assert.deepEqual(delivered,[9]);assert.equal(requests,1);
  }finally{stop();}
});

test('a subscription that finishes after leaving is closed without touching the map',async()=>{
  let resolveSubscription,closes=0;
  const stop=watchAtlasScores({roster,api:{subscribeEvents(){return new Promise(resolve=>{resolveSubscription=resolve;});}},onSites(){assert.fail('Late updates must be ignored.');},onConnection(){}});
  await flush();stop();resolveSubscription(()=>{closes++;});await flush();assert.equal(closes,1);
});
