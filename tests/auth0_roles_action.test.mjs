import test from 'node:test';
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';

const {onExecutePostLogin} = createRequire(import.meta.url)('../api/auth/roles_action.js');
const CLAIM = 'https://planit-control/roles';

async function claimsFor(event) {
  const idToken = new Map();
  const accessToken = new Map();
  await onExecutePostLogin(event, {
    idToken: {setCustomClaim: (name, value) => idToken.set(name, value)},
    accessToken: {setCustomClaim: (name, value) => accessToken.set(name, value)},
  });
  return {idToken, accessToken};
}

test('assigned PlanIT roles are copied to both tokens without duplicates', async () => {
  const {idToken, accessToken} = await claimsFor({authorization: {
    roles: ['crew', 'admin', 'supervisor', 'crew'],
  }});
  assert.deepEqual(idToken.get(CLAIM), ['crew', 'supervisor']);
  assert.deepEqual(accessToken.get(CLAIM), ['crew', 'supervisor']);
  assert.equal(idToken.size, 1);
  assert.equal(accessToken.size, 1);
});

test('missing assigned roles fail closed and user metadata cannot grant access', async () => {
  for (const event of [
    {user: {user_metadata: {roles: ['supervisor']}}},
    {authorization: {roles: 'supervisor'}, user: {app_metadata: {roles: ['crew']}}},
    {authorization: {roles: ['Admin']}},
  ]) {
    const {idToken, accessToken} = await claimsFor(event);
    assert.deepEqual(idToken.get(CLAIM), []);
    assert.deepEqual(accessToken.get(CLAIM), []);
  }
});
