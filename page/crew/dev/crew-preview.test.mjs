import test from 'node:test';
import assert from 'node:assert/strict';
import {once} from 'node:events';
import {createPreviewServer} from './preview-server.mjs';

test('one preview origin serves both workspaces and their dependencies without exposing the repository',async()=>{
  const server=createPreviewServer();server.listen(0,'127.0.0.1');await once(server,'listening');
  const base=`http://127.0.0.1:${server.address().port}`;
  try{
    for(const route of ['/','/index.html','/crew.html','/crew-atlas.html','/crew/index.html','/crew/crew.html','/supervisor/index.html','/supervisor/app.js','/supervisor/sample-data/sites.json','/shared/planit.css','/shared/auth-session.mjs','/shared/environment-readings.mjs','/realtime/deepspace-source.js']){
      const response=await fetch(base+route);assert.equal(response.status,200,route);await response.text();
      if(route.endsWith('.mjs'))assert.match(response.headers.get('content-type'),/text\/javascript/,route);
    }
    const redirect=await fetch(base+'/supervisor?test=1',{redirect:'manual'});assert.equal(redirect.status,308);assert.equal(redirect.headers.get('location'),'/supervisor/?test=1');
    for(const route of ['/supervisor/','/crew/'])assert.equal((await fetch(base+route)).status,200);
    for(const route of ['/api/CONTRACT.md','/docs/TEAM.md','/.env','/.git/config','/supervisor/%2e%2e%2f%2e%2e%2fapi/CONTRACT.md','/supervisor/%2e%2e%5c%2e%2e%5capi/CONTRACT.md'])assert.notEqual((await fetch(base+route)).status,200,route);
    assert.equal((await fetch(base+'/index.html',{method:'POST'})).status,405);
    const head=await fetch(base+'/supervisor/index.html',{method:'HEAD'});assert.equal(head.status,200);assert.equal(await head.text(),'');
  }finally{server.closeAllConnections();await new Promise(resolve=>server.close(resolve));}
});
