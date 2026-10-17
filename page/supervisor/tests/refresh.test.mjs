import test from 'node:test';
import assert from 'node:assert/strict';
import {createRefreshQueue} from '../refresh.js';
const settle = () => new Promise(resolve => setImmediate(resolve));

test('a burst shares one follow-up refresh without overlapping the active fetch', async () => {
  const finishes = [];
  let active = 0, peak = 0;
  const refresh = createRefreshQueue(async () => {
    peak = Math.max(peak, ++active);
    await new Promise(resolve => finishes.push(resolve));
    active--;
  });
  const first = refresh();
  await settle();
  const burst = Array.from({length: 100}, () => refresh());
  assert.ok(burst.every(promise => promise === burst[0]));
  assert.notEqual(first, burst[0]);
  assert.equal(finishes.length, 1);
  finishes[0](); await first; await settle();
  assert.equal(finishes.length, 2);
  finishes[1](); await Promise.all(burst);
  assert.equal(peak, 1);
});

test('a failed fetch rejects its callers, runs its pending refresh and remains reusable', async () => {
  let fail, calls = 0;
  const refresh = createRefreshQueue(async () => {
    calls++;
    if (calls === 1) await new Promise((_resolve, reject) => { fail = reject; });
    return calls;
  });
  const first = refresh();
  const rejected = assert.rejects(first, /offline/);
  await settle();
  const followup = refresh();
  fail(new Error('offline'));
  await rejected;
  assert.equal(await followup, 2);
  assert.equal(await refresh(), 3);
});

test('a refresh requested by a completed caller is not lost', async () => {
  let calls = 0;
  const refresh = createRefreshQueue(() => ++calls);
  assert.equal(await refresh().then(() => refresh()), 2);
});
