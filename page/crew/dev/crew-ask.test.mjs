import test from 'node:test';
import assert from 'node:assert/strict';
import {createHTTPAPI} from '../crew-http.js';
import {shouldSubmitAskOnKey} from '../crew-ask.js';

const settings={baseURL:'https://foresite.work/api'};
const json=(value,status=200)=>new Response(JSON.stringify(value),{status,headers:{'Content-Type':'application/json'}});

test('Enter submits a question; Shift+Enter and IME composition retain multiline editing',()=>{
  assert.equal(shouldSubmitAskOnKey({key:'Enter'}),true);
  assert.equal(shouldSubmitAskOnKey({key:'Enter',shiftKey:true}),false);
  assert.equal(shouldSubmitAskOnKey({key:'Enter',isComposing:true}),false);
  assert.equal(shouldSubmitAskOnKey({key:'Enter',repeat:true}),false);
});

test('a crew question uses the protected read-only /ask endpoint',async()=>{
  const calls=[];
  const api=createHTTPAPI(settings,async()=>'private-token',async(url,options)=>{
    calls.push({url:url.href,method:options.method,headers:options.headers,body:JSON.parse(options.body)});
    return json({answer:'Turkey Point has the highest prototype score.',sql:'SELECT name FROM sites LIMIT 1',sources:[{label:'EIA-860M',url:'https://example.org/source'}]});
  });
  const answer=await api.ask('  Which site has the highest prototype score?  ');
  assert.match(answer.answer,/Turkey Point/);
  assert.equal(calls[0].url,'https://foresite.work/api/ask');
  assert.equal(calls[0].method,'POST');
  assert.equal(calls[0].headers.Authorization,'Bearer private-token');
  assert.deepEqual(calls[0].body,{question:'Which site has the highest prototype score?'});
});

test('cannot-answer remains distinct from a down service',async()=>{
  const cannot=createHTTPAPI(settings,async()=>'token',async()=>json({answer:null,reason:'cannot_answer'}));
  assert.deepEqual(await cannot.ask('Can you read a private crew report?'),{answer:null,reason:'cannot_answer'});
  const down=createHTTPAPI(settings,async()=>'token',async()=>json({error:{code:'service_unavailable',message:'Gemini unavailable'}},503));
  await assert.rejects(down.ask('What is the wind forecast?'),error=>error.status===503&&error.ambiguousWrite===false);
});

test('invalid input and malformed responses fail closed without showing empty answers',async()=>{
  let sent=0;
  const api=createHTTPAPI(settings,async()=>'token',async()=>{sent++;return json({answer:'',sql:'',sources:[]});});
  await assert.rejects(api.ask('x'),/3 and 500/);assert.equal(sent,0);
  await assert.rejects(api.ask('Valid question?'),/invalid answer/);assert.equal(sent,1);
  const offline=createHTTPAPI(settings,async()=>'token',async()=>{throw new TypeError('offline');});
  await assert.rejects(offline.ask('What are the highest scores?'),error=>error.ambiguousWrite===false&&error.code==='service_unavailable');
});
