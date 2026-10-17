import test from 'node:test';
import assert from 'node:assert/strict';
globalThis.location={href:'http://127.0.0.1:4177/crew.html?demo=1',search:'?demo=1'};
globalThis.BroadcastChannel=undefined;
const {config}=await import('../crew-config.js');
let sockets=0;
config.api.realtime.WebSocketImpl=class{constructor(){sockets++;throw new Error('Demo mode must stay local.');}};
const {services}=await import('../crew-services.js');
test('default demo subscriptions keep browser events and never open the configured DeepSpace socket',async()=>{
  const connections=[];assert.equal(config.dataMode,'mock');
  const stop=await services.subscribeEvents('621',()=>{},value=>connections.push(value));
  try{assert.deepEqual(connections,[true]);assert.equal(sockets,0);}finally{stop();}
});
