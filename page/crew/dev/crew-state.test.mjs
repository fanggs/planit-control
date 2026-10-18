import {test} from 'node:test';
import assert from 'node:assert/strict';
import {acceptAlert,alertView,remainingSeconds,contributionLabel} from '../crew-state.js';
const now=Date.parse('2026-10-17T12:00:00Z');
const hold=(version,minutes=30)=>({site_id:'621',version,status:'hold',all_clear_at:new Date(now+minutes*60000).toISOString()});
test('wall-clock countdown survives a sleeping tab',()=>{assert.equal(remainingSeconds(hold(1).all_clear_at,now+17*60000),13*60);});
test('new strike extends hold; old or cross-site events cannot overwrite it',()=>{const first=hold(1,20),reset=hold(2,30);assert.deepEqual(acceptAlert(first,reset,'621'),reset);assert.deepEqual(acceptAlert(reset,first,'621'),reset);assert.deepEqual(acceptAlert(reset,{...hold(3),site_id:'628'},'621'),reset);});
test('expiry and a disconnected stream never declare all-clear',()=>{assert.equal(alertView(hold(1),true,now+31*60000).tone,'hold');assert.equal(alertView({site_id:'621',version:2,status:'cleared'},false).tone,'unknown');});
test('only a newer explicit server clear can replace a hold',()=>{const cleared=acceptAlert(hold(1),{site_id:'621',version:2,status:'cleared'},'621');assert.equal(alertView(cleared,true).tone,'clear');});
test('bad deadlines and unknown status do not manufacture a valid countdown',()=>{assert.equal(remainingSeconds('invalid',now),null);assert.equal(acceptAlert(hold(1),{...hold(2),all_clear_at:'invalid'},'621').version,1);assert.equal(alertView(null,true).tone,'unknown');});
test('explanations round display values but retain signs and units',()=>{assert.equal(contributionLabel({contribution:-.8,unit:'score_points'}),'-0.80 points');assert.equal(contributionLabel({contribution:.17327775285409275,unit:'score_points'}),'+0.17 points');assert.equal(contributionLabel({contribution:.4,unit:'log_odds'}),'+0.40 log_odds');assert.equal(contributionLabel({contribution:null}),'Unavailable');});
test('recorded lightning replay is visibly labeled without presenting it as a current strike',()=>{
  const view=alertView({...hold(1),is_replay:true},true,now);
  assert.match(view.title,/REPLAY/);assert.match(view.detail,/not real lightning/);
  assert.equal(view.tone,'hold');
});
