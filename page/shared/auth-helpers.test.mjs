import assert from 'node:assert/strict';
import test from 'node:test';

import { supportedAuthOrigin, supportedSupervisorAuthOrigin } from './auth-origin.mjs';
import { clearResumeHint, hasResumeHint, markAuthenticated } from './auth-resume.mjs';

test('Auth0 starts only from registered origins, never an IDE preview', () => {
  assert.equal(supportedAuthOrigin('https://foresite.work/crew/login.html'), true);
  assert.equal(supportedAuthOrigin('http://127.0.0.1:4174/crew/login.html'), true);
  assert.equal(supportedAuthOrigin('http://127.0.0.1:4175/crew/login.html'), false);
  assert.equal(supportedSupervisorAuthOrigin('http://127.0.0.1:4175/supervisor/index.html'), true);
  assert.equal(supportedAuthOrigin('http://localhost:63342/planit-control/page/crew/login.html'), false);
  assert.equal(supportedAuthOrigin('http://localhost:4174/crew/login.html'), false);
  assert.equal(supportedAuthOrigin('https://foresite.work.evil.test/crew/login.html'), false);
  assert.equal(supportedAuthOrigin('https://user@foresite.work/crew/login.html'), false);
  assert.equal(supportedAuthOrigin('not a URL'), false);
});

test('navigation hint contains no credential and cannot establish authentication', () => {
  const previous = globalThis.sessionStorage;
  const values = new Map();
  globalThis.sessionStorage = {
    getItem: (key) => values.get(key) ?? null,
    setItem: (key, value) => values.set(key, value),
    removeItem: (key) => values.delete(key),
  };
  try {
    assert.equal(hasResumeHint(), false);
    markAuthenticated();
    assert.equal(hasResumeHint(), true);
    assert.deepEqual([...values.values()], ['1']);
    clearResumeHint();
    assert.equal(hasResumeHint(), false);
  } finally {
    if (previous === undefined) delete globalThis.sessionStorage;
    else globalThis.sessionStorage = previous;
  }
});

test('disabled session storage does not break sign-in or sign-out', () => {
  const previous = globalThis.sessionStorage;
  globalThis.sessionStorage = {
    getItem() { throw new Error('blocked'); },
    setItem() { throw new Error('blocked'); },
    removeItem() { throw new Error('blocked'); },
  };
  try {
    assert.equal(hasResumeHint(), false);
    assert.doesNotThrow(markAuthenticated);
    assert.doesNotThrow(clearResumeHint);
  } finally {
    if (previous === undefined) delete globalThis.sessionStorage;
    else globalThis.sessionStorage = previous;
  }
});
