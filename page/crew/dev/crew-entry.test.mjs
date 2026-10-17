import test from 'node:test';
import assert from 'node:assert/strict';
import {mountWorkspace} from '../crew-workspaces.js';
import {workspaceForUser} from '../crew-routing.js';
const claim='https://planit-control/roles';

test('crew and legacy sample supervisor workspaces can mount without forwarding callback secrets',async()=>{
  for(const role of ['crew','supervisor']){
    const root={id:'crew-access-root'},document={getElementById:()=>root};
    let destination,loaded,finished=false;
    const history={replaceState(_state,_title,url){destination=String(url);}};
    const load=async path=>{loaded=path;assert.equal(root.id,role==='supervisor'?'crew-supervisor-root':'crew-root');return {ready:Promise.resolve().then(()=>{finished=true;})};};
    const workspace=workspaceForUser({[claim]:[role]},claim);
    await mountWorkspace(workspace,{baseURL:'http://127.0.0.1:4177/login.html?code=one-use&state=checked&returnTo=https://outside.example',siteId:'621',document,history,load});
    const name=role==='supervisor'?'crew-supervisor':'crew';
    assert.equal(destination,`http://127.0.0.1:4177/${name}.html?site=621`);
    assert.equal(loaded,`./${name}.js`);assert.equal(finished,true);
    assert.equal(document.title,'ForeSite · '+(role==='supervisor'?'Supervisor':'Crew'));
  }
});
test('a URL role cannot select a workspace without a verified claim or trigger a module load',async()=>{
  let loaded=false;
  const workspace=workspaceForUser({role:'supervisor'},claim);
  assert.equal(workspace,null);
  await assert.rejects(mountWorkspace(workspace,{baseURL:'https://planit.example/login.html?role=supervisor',load:()=>{loaded=true;}}),/Unknown workspace/);
  assert.equal(loaded,false);
});
