import test from 'node:test';
import assert from 'node:assert/strict';
import {workspaceForUser, userRoles, siteParameter} from '../crew-routing.js';
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
