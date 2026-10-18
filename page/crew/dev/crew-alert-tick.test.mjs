import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import vm from 'node:vm';
import {expireScreening} from '../crew-screening.js';
import {alertView} from '../crew-state.js';
import {watchPanel,floodHTML,hazardHTML,refreshHazardAges,dateLabel,esc} from '../crew-ui.js';
import {HAZARD_LABELS} from '../crew-integration.js';

// Execute the production timer callback without starting the page's auth/network boot.
const source=await fs.readFile(new URL('../crew.js',import.meta.url),'utf8');
const start=source.indexOf('function updateAlert(){');
const end=source.indexOf("\ndocument.addEventListener('click'",start);
assert.ok(start>=0&&end>start,'Find the production alert timer callback');
function harness(site=null,expired=false){
  const now=Date.now(),nodes=new Map();
  for(const id of ['crew-alert','crew-alert-title','crew-alert-detail','crew-countdown','crew-stream',
    'crew-watch-panel','crew-flood-panel','crew-conditions-grid','crew-flood-banner']){
    nodes.set('#'+id,{dataset:{},textContent:'previous text',innerHTML:'previous markup',querySelectorAll(){return [];}});
  }
  const state={site,view:'status',connected:true,lastEvent:now,clockOffset:0,conditionMarkup:null,
    alert:site?{site_id:'621',status:'hold',all_clear_at:new Date(now+30*60000).toISOString()}:null};
  const context=vm.createContext({state,$:selector=>nodes.get(selector),
    Date:class extends Date{static now(){return now;}},navigator:{onLine:true},
    config:{dataMode:'live',api:{heartbeatMs:45000}},sessionExpired:()=>expired,
    expireScreening,alertView,watchPanel,floodHTML,hazardHTML,refreshHazardAges,dateLabel,esc,HAZARD_LABELS,
    renderStatus(){assert.fail('No score expiry is expected in this fixture');}});
  vm.runInContext(source.slice(start,end),context);
  return {tick:()=>context.updateAlert(),nodes,state};
}

test('timer ignores a missing site even when old watch and conditions nodes remain mounted',()=>{
  const h=harness();
  assert.doesNotThrow(h.tick);
  for(const node of h.nodes.values()){
    assert.equal(node.innerHTML,'previous markup');assert.equal(node.textContent,'previous text');
  }
  h.state.site=undefined;
  assert.doesNotThrow(h.tick);
});

test('expired sign-in retains the current lightning hold while marking live updates paused',()=>{
  const h=harness({id:'621',score:null,hazards:{},active_alerts:[],warnings:[]},true);
  assert.doesNotThrow(h.tick);
  assert.equal(h.nodes.get('#crew-alert').dataset.tone,'hold');
  assert.equal(h.nodes.get('#crew-countdown').textContent,'30:00');
  assert.match(h.nodes.get('#crew-stream').textContent,/Signed out.*sign in again/);
  h.state.site=null;
  assert.doesNotThrow(h.tick);
});
