import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import {createHTTPAPI} from '../crew-http.js';
const fixture=JSON.parse(await fs.readFile(new URL('./fixtures/contract-v1.1.json',import.meta.url)));
const settings={baseURL:'https://example.test/api'};
const json=(value,status=200)=>new Response(JSON.stringify(value),{status,headers:{'Content-Type':'application/json'}});
const input=()=>({site_id:'9001',category:'Wildlife',severity:'high',description:'Gator by the gate',latitude:25.431,longitude:-80.334,request_id:crypto.randomUUID(),photo:new File(['photo bytes'],'hazard.png',{type:'image/png'})});

test('photos upload first, then reports use only contract JSON fields',async()=>{
  const calls=[];
  const api=createHTTPAPI(settings,async()=>'private-token',async(url,options)=>{
    calls.push({url:url.href,...options});
    return json(url.pathname.endsWith('/photos')?{photo_key:'private-key'}:{...fixture.reports[0],photo_key:'private-key'});
  });
  const receipt=await api.submitReport({...input(),reporter_id:'forged-user',status:'resolved'});
  assert.equal(calls.length,2);assert.equal(calls[0].url,'https://example.test/api/photos');
  assert.ok(calls[0].body instanceof FormData);assert.deepEqual([...calls[0].body.keys()],['file']);
  assert.equal(calls[0].headers['Content-Type'],undefined);assert.equal(await calls[0].body.get('file').text(),'photo bytes');
  assert.equal(calls[1].headers['Content-Type'],'application/json');
  assert.deepEqual(JSON.parse(calls[1].body),{site_id:9001,hazard_type:'wildlife',severity:'high',description:'Gator by the gate',latitude:25.431,longitude:-80.334,photo_key:'private-key'});
  assert.equal(receipt.site_id,'9001');assert.equal(receipt.shared,undefined);
});
test('photo suggestions use the private upload once and never choose the final report category',async()=>{
  const calls=[];
  const report=input();
  const api=createHTTPAPI(settings,async()=>'private-token',async(url,options)=>{
    calls.push({path:url.pathname,method:options.method,auth:options.headers.Authorization});
    if(url.pathname.endsWith('/photos'))return json({photo_key:'private-key'});
    if(url.pathname.endsWith('/suggestion'))return json({suggestion:{hazard_type:'wildlife',confidence:'medium',reason:'An animal is visible.'}});
    assert.equal(JSON.parse(options.body).hazard_type,'flooding');
    return json(fixture.reports[0]);
  });
  const prepared=await api.prepareReportPhoto(report.photo,report.request_id);
  assert.equal(prepared.photo_key,'private-key');
  assert.equal(prepared.suggestion.hazard_type,'wildlife');
  await api.submitReport({...report,category:'Flooding / standing water'});
  assert.deepEqual(calls.map(call=>call.path),[
    '/api/photos','/api/photos/private-key/suggestion','/api/reports'
  ]);
  assert.ok(calls.every(call=>call.auth==='Bearer private-token'));
});
test('unavailable Gemini advice leaves the uploaded photo usable for a human-chosen category',async()=>{
  let uploads=0;
  const report=input();
  const api=createHTTPAPI(settings,async()=>'token',async(url,options)=>{
    if(url.pathname.endsWith('/photos')){uploads++;return json({photo_key:'saved-photo'});}
    if(url.pathname.endsWith('/suggestion'))return json({error:{code:'unavailable',message:'Gemini unavailable'}},503);
    assert.equal(JSON.parse(options.body).hazard_type,'heat');
    return json(fixture.reports[0]);
  });
  assert.equal((await api.prepareReportPhoto(report.photo,report.request_id)).suggestion,null);
  await api.submitReport({...report,category:'Heat'});
  assert.equal(uploads,1);
});
test('submitting while the selection upload is pending does not upload a duplicate',async()=>{
  let finishUpload,uploads=0;
  let markUploadStarted;
  const uploadStarted=new Promise(resolve=>{markUploadStarted=resolve;});
  const report=input();
  const api=createHTTPAPI(settings,async()=>'token',async(url)=>{
    if(url.pathname.endsWith('/photos')){uploads++;return new Promise(resolve=>{finishUpload=()=>resolve(json({photo_key:'saved-photo'}));markUploadStarted();});}
    if(url.pathname.endsWith('/suggestion'))return json({suggestion:null});
    return json(fixture.reports[0]);
  });
  const prepared=api.prepareReportPhoto(report.photo,report.request_id);
  await uploadStarted;
  const submitted=api.submitReport(report);
  finishUpload();
  assert.equal((await prepared).suggestion,null);
  await submitted;
  assert.equal(uploads,1);
});
test('definite rejected reports reuse the uploaded photo; successful double submits reuse the receipt',async()=>{
  let photos=0,reports=0;
  const api=createHTTPAPI({...settings,photoField:'photo'},async()=>'token',async(url,options)=>{
    if(url.pathname.endsWith('/photos')){photos++;assert.ok(options.body.has('photo'));return json({photo_key:'saved-photo'});}
    reports++;return reports===1?json({error:{code:'invalid_request',message:'Correct the metadata'}},400):json(fixture.reports[0]);
  });
  const report=input();await assert.rejects(api.submitReport(report),/Correct the metadata/);
  const saved=await api.submitReport(report);assert.equal(await api.submitReport(report),saved);
  assert.equal(photos,1);assert.equal(reports,2);
});
test('reports without photos skip uploads; uncertain writes cannot be blindly repeated',async()=>{
  let calls=0;
  const api=createHTTPAPI(settings,async()=>'token',async(url,options)=>{calls++;assert.match(url.pathname,/reports$/);assert.equal(JSON.parse(options.body).photo_key,null);throw new TypeError('network lost');});
  const report={...input(),photo:null,latitude:null,longitude:null};
  await assert.rejects(api.submitReport(report),error=>error.ambiguousWrite===true);
  await assert.rejects(api.submitReport(report),/automatic retry could create a duplicate/);assert.equal(calls,1);
});
test('protected photos use authenticated blob fetches rather than public image URLs',async()=>{
  const calls=[];
  const api=createHTTPAPI(settings,async()=>'token',async(url,options)=>{
    calls.push([url.href,options]);
    return url.pathname.includes('/photos/')?new Response(new Blob(['image'],{type:'image/png'})):json(fixture.reports);
  });
  const [report]=await api.listReports('9001');assert.ok(report.photo instanceof Blob);
  assert.equal(report.photo_url,undefined);assert.equal(calls[0][0],'https://example.test/api/reports?site_id=9001');
  assert.equal(calls[1][0],'https://example.test/api/photos/sample-photo-1');assert.equal(calls[1][1].headers.Authorization,'Bearer token');
});
test('missing photos leave reports readable and invalid images never upload',async()=>{
  const api=createHTTPAPI(settings,async()=>'token',async url=>url.pathname.includes('/photos/')?json({error:{code:'not_found',message:'Photo unavailable'}},404):json(fixture.reports));
  const [report]=await api.listReports('9001');assert.equal(report.id,fixture.reports[0].id);assert.equal(report.photo_error,'Photo unavailable');
  let uploaded=false;
  const invalid=createHTTPAPI(settings,async()=>'token',async()=>{uploaded=true;return json({});});
  await assert.rejects(invalid.submitReport({...input(),photo:new File(['x'],'bad.webp',{type:'image/webp'})}),/JPEG or PNG/);
  assert.equal(uploaded,false);
});
