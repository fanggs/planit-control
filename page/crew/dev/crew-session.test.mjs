import test from 'node:test';
import assert from 'node:assert/strict';
import {reportSessionExpired, sessionExpired} from '../crew-session.js';

test('a 401 displays one persistent same-origin sign-in path without leaking a token', () => {
  const nodes = [];
  const makeNode = tag => ({tag, children: [], setAttribute(key, value) { this[key] = value; },
    append(...children) { this.children.push(...children); }});
  globalThis.document = {createElement: makeNode, body: {prepend(node) { nodes.push(node); }}};
  globalThis.location = {href: 'https://foresite.work/crew/crew.html?site=621&token=do-not-copy',
    search: '?site=621&token=do-not-copy'};
  const events = [];
  globalThis.window = {dispatchEvent(event) { events.push(event.type); }};
  try {
    assert.equal(reportSessionExpired({status: 503}), false);
    assert.equal(sessionExpired(), false);
    assert.equal(reportSessionExpired({status: 401}), true);
    assert.equal(reportSessionExpired({status: 401}), true);
    assert.equal(sessionExpired(), true);
    assert.equal(nodes.length, 1);
    assert.deepEqual(events, ['planit:session-expired']);
    assert.equal(nodes[0].role, 'alert');
    const link = nodes[0].children[1];
    assert.equal(link.href, 'https://foresite.work/crew/login.html?start=1&site=621');
    assert.doesNotMatch(JSON.stringify(nodes), /do-not-copy/);
  } finally {
    delete globalThis.document; delete globalThis.location; delete globalThis.window;
  }
});
