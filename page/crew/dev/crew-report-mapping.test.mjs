import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createHazardReportPayload,validateReportPhoto,MAX_PHOTO_BYTES} from '../crew-report-mapping.js';
const report={site_id:'621',category:'Wildlife',severity:'high',description:'  Gator near access road  ',latitude:25.4,longitude:-80.3,request_id:'retry-id',reporter_id:'do-not-trust-client-identity',photo:new Blob(['test'])};
test('upload mapping matches the actual strict JSON creation schema',()=>{assert.deepEqual(createHazardReportPayload(report,'stored-key'),{site_id:621,hazard_type:'wildlife',severity:'high',description:'Gator near access road',latitude:25.4,longitude:-80.3,photo_key:'stored-key'});});
test('UI labels map to backend enums, with weather represented as other',()=>{assert.equal(createHazardReportPayload({...report,category:'Soil / access'}).hazard_type,'soil_saturation');assert.equal(createHazardReportPayload({...report,category:'Weather'}).hazard_type,'other');});
test('missing severity and invalid numeric IDs are rejected before upload metadata is sent',()=>{assert.throws(()=>createHazardReportPayload({...report,severity:undefined}),/severity/);assert.throws(()=>createHazardReportPayload({...report,site_id:'not-an-id'}),/ID/);assert.throws(()=>createHazardReportPayload({...report,site_id:'9007199254740993'}),/ID/);});
test('invalid coordinates, descriptions and storage keys are rejected',()=>{assert.throws(()=>createHazardReportPayload({...report,latitude:Infinity}),/latitude/);assert.throws(()=>createHazardReportPayload({...report,description:'a\0b'}),/Description/);assert.throws(()=>createHazardReportPayload(report,''),/photo key/);});
test('storage key identity matches the current backend validation',()=>{for(const key of [' key','key ','https://example.test/image.png','//example.test/image.png','data:image/png;base64,demo','key\nname','key\x7fname'])assert.throws(()=>createHazardReportPayload(report,key),/storage key/);assert.equal(createHazardReportPayload(report,'crew/621/opaque-file-key').photo_key,'crew/621/opaque-file-key');});

test('photos and coordinates are optional, but partial or invalid coordinates fail',()=>{
  const payload=createHazardReportPayload({...report,latitude:null,longitude:undefined});
  assert.equal(payload.photo_key,null);assert.equal(payload.latitude,null);assert.equal(payload.longitude,null);
  assert.throws(()=>createHazardReportPayload({...report,latitude:null}),/both/);
  assert.equal(createHazardReportPayload({...report,hazard_type:'soil_saturation'}).hazard_type,'soil_saturation');
  assert.throws(()=>createHazardReportPayload({...report,description:42}),/Description/);
});
test('image validation follows JPEG/PNG and the 5 MB upload limit',()=>{
  assert.doesNotThrow(()=>validateReportPhoto(null));
  assert.doesNotThrow(()=>validateReportPhoto(new Blob(['photo'],{type:'image/jpeg'})));
  assert.doesNotThrow(()=>validateReportPhoto(new Blob([new Uint8Array(MAX_PHOTO_BYTES)],{type:'image/png'})));
  assert.throws(()=>validateReportPhoto(new Blob(['photo'],{type:'image/webp'})),/JPEG or PNG/);
  assert.throws(()=>validateReportPhoto(new Blob([new Uint8Array(MAX_PHOTO_BYTES+1)],{type:'image/png'})),/5 MB/);
});
