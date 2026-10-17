import test from 'node:test';
import assert from 'node:assert/strict';

const claim='https://planit-control/roles';
let user={[claim]:['supervisor']},redirect,callbacks=0;
const nodes=new Map();
globalThis.location={href:'http://127.0.0.1:4177/login.html?code=one-use&state=checked',search:'?code=one-use&state=checked',replace(url){redirect=url;}};
globalThis.document={title:'PlanIT',getElementById(id){if(!nodes.has(id))nodes.set(id,{id,hidden:false,disabled:false,addEventListener(){}});return nodes.get(id);}};
globalThis.history={replaceState(_state,_title,url){location.href=String(url);location.search=new URL(url).search;}};
globalThis.window={auth0:{Auth0Client:class{
  async handleRedirectCallback(){callbacks++;return {appState:{siteId:'621',returnTo:'https://outside.example'}};}
  async isAuthenticated(){return true;}
  async getUser(){return user;}
  async getTokenSilently(){throw new Error('Tokens must not be transferred to another page.');}
}}};
const {config}=await import('../crew-config.js');config.auth.domain='example.auth0.com';config.auth.clientId='public-example';

test('a verified supervisor callback opens the independent dashboard without forwarding callback parameters or tokens',async()=>{
  const entry=await import('../crew-entry.js?supervisor-test');await entry.ready;
  assert.equal(callbacks,1);assert.equal(redirect,'http://127.0.0.1:4177/supervisor/index.html');
  assert.equal(nodes.get('crew-access-root'),undefined);
});
test('a URL role cannot send an account without a verified role to the dashboard',async()=>{
  redirect=undefined;user={role:'supervisor'};
  location.href='http://127.0.0.1:4177/login.html?role=supervisor';location.search='?role=supervisor';
  const entry=await import('../crew-entry.js?no-role-test');await entry.ready;
  assert.equal(redirect,undefined);assert.match(nodes.get('login-status').textContent,/no workspace role/);
  assert.equal(nodes.get('login-signout').hidden,false);
});
