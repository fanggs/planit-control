import test from 'node:test';
import assert from 'node:assert/strict';
import {workspaceForUser, userRoles, siteParameter, workspaceURL, supervisorDashboardURL, supervisorNavigationURL, isLiveDeploymentURL} from '../crew-routing.js';
const claim = 'https://planit-control/roles';

test('verified role claims choose the workspace; unknown roles fail closed', () => {
  assert.equal(workspaceForUser({[claim]: ['crew']}, claim), 'crew');
  assert.equal(workspaceForUser({[claim]: ['supervisor']}, claim), 'supervisor');
  assert.equal(workspaceForUser({[claim]: ['crew', 'supervisor']}, claim), 'supervisor');
  assert.equal(workspaceForUser({role: 'supervisor'}, claim), null);
  assert.equal(workspaceForUser({[claim]: 'supervisor'}, claim), null);
  assert.equal(workspaceForUser({[claim]: ['admin']}, claim), null);
  assert.deepEqual(userRoles({[claim]: ['crew', 'crew', 42]}, claim), ['crew']);
});

test('login preserves only a valid plant ID, never an arbitrary redirect', () => {
  assert.equal(siteParameter('00621'), '621');
  for (const value of ['https://example.com', '../crew-supervisor.html', '-1', '1.5', '1e3', '', null, '9007199254740992']) {
    assert.equal(siteParameter(value), null);
  }
});

test('fixed workspace destinations stay separate in root and nested crew deployments',()=>{
  for(const base of ['http://127.0.0.1:4176/crew-routing.js','https://planit.example/crew/crew-routing.js','https://planit.example/demo/crew/crew-routing.js']){
    const supervisor=workspaceURL('supervisor',base),crew=workspaceURL('crew',base);
    assert.equal(supervisor.origin,new URL(base).origin);
    assert.ok(supervisor.pathname.endsWith('/crew-supervisor.html'));assert.ok(crew.pathname.endsWith('/crew.html'));
    assert.equal(supervisor.search,'');assert.equal(supervisor.hash,'');assert.notEqual(supervisor.href,crew.href);
    assert.ok(!supervisor.pathname.includes('atlas'));
  }
  assert.throws(()=>workspaceURL('https://outside.example','https://planit.example/crew/crew-routing.js'),/Unknown/);
});

test('supervisor handoff uses Aryan dashboard on the same origin without callback secrets',()=>{
  for(const base of ['http://127.0.0.1:4174/login.html?code=one-use&state=checked',
    'https://planit.example/crew/login.html?code=one-use&state=checked',
    'https://planit.example/demo/crew/login.html?returnTo=https://outside.example']){
    const target=supervisorDashboardURL(base);
    assert.equal(target.origin,new URL(base).origin);
    assert.ok(target.pathname.endsWith('/supervisor/index.html'));
    assert.equal(target.search,'');assert.equal(target.hash,'');
  }
});

test('crew and atlas navigation use the live dashboard or an explicitly local sample preview',()=>{
  for(const base of ['http://127.0.0.1:4174/crew/crew.html?site=621&code=secret',
    'https://planit.example/crew/crew-atlas.html?site=621&returnTo=https://outside.example']){
    const live=supervisorNavigationURL(base,'live');
    assert.equal(live.href,supervisorDashboardURL(base).href);
    assert.equal(live.search,'');
    const mock=supervisorNavigationURL(base,'mock');
    assert.equal(mock.origin,new URL(base).origin);
    assert.ok(mock.pathname.endsWith('/crew/crew-supervisor.html'));
    assert.equal(mock.search,'?demo=1');
  }
});

test('live crew mode is limited to the exact HTTPS deployment origin',()=>{
  assert.equal(isLiveDeploymentURL('https://foresite.work/crew/crew-config.js'),true);
  for(const url of ['http://foresite.work/crew/crew-config.js','https://www.foresite.work/crew/crew-config.js',
    'https://foresite.work.evil.test/crew/crew-config.js','http://127.0.0.1:4174/crew/crew-config.js',
    'file:///crew/crew-config.js'])assert.equal(isLiveDeploymentURL(url),false);
});
