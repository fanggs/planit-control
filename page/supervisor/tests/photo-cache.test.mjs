import test from 'node:test';
import assert from 'node:assert/strict';
import {createPhotoCache} from '../photo-cache.js';

test('viewed private photos survive same-site refresh but removed keys are revoked', () => {
  const revoked = [];
  let created = 0;
  const cache = createPhotoCache({createURL: () => `blob:private-${++created}`, revokeURL: url => revoked.push(url)});
  assert.equal(cache.remember('report-one', {}), 'blob:private-1');
  assert.equal(cache.remember('report-one', {}), 'blob:private-1');
  cache.retain(['report-one', 'report-two']);
  assert.equal(cache.get('report-one'), 'blob:private-1');
  assert.deepEqual(revoked, []);
  cache.retain(['report-two']);
  assert.equal(cache.get('report-one'), null);
  assert.deepEqual(revoked, ['blob:private-1']);
  assert.equal(cache.remember('report-two', {}), 'blob:private-2');
  cache.clear();
  assert.deepEqual(revoked, ['blob:private-1', 'blob:private-2']);
});
