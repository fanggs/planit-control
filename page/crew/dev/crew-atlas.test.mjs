import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import {REGIONS,atlasRoster,atlasSummaries,atlasFilter,atlasPoint,atlasZoom,atlasEase,spreadAtlasPins} from '../crew-atlas-data.js';
const snapshot=JSON.parse(await fs.readFile(new URL('../crew-data/monitored-sites.json',import.meta.url)));

test('atlas snapshot matches Sid’s exact 60 monitored plants and six ten-plant regions',async()=>{
  const provided=JSON.parse(await fs.readFile(new URL('../../../get_data/generated/sites.json',import.meta.url)));
  assert.deepEqual(snapshot,provided);
  const roster=atlasRoster(snapshot);assert.equal(roster.length,60);assert.equal(new Set(roster.map(s=>s.id)).size,60);
  for(const region of Object.keys(REGIONS))assert.equal(roster.filter(s=>s.hazard_region===region).length,10);
  assert.equal(roster.find(s=>s.id==='621').name,'Turkey Point');
  assert.ok(roster.every(s=>s.score===null));assert.ok(roster.some(s=>s.id==='67769'));
});
test('incomplete, duplicate, unmonitored or geographically invalid rosters fail visibly',()=>{
  assert.throws(()=>atlasRoster(snapshot.slice(1)),/60-site/);
  for(const changes of [{site_id:snapshot[1].site_id},{is_monitored:false},{latitude:null},{longitude:-150},{hazard_region:'unknown'}]){
    const rows=structuredClone(snapshot);Object.assign(rows[0],changes);assert.throws(()=>atlasRoster(rows),/invalid/);
  }
});
test('API data cannot add plants or replace verified metadata, and missing scores never become zero',()=>{
  const roster=atlasRoster(snapshot);
  const merged=atlasSummaries(roster,[{site_id:9,name:'Untrusted name',latitude:0,score:0,scored_at:'2026-10-17T18:00:00Z'},{id:'88',score:12},{site_id:999999,score:10}]);
  assert.equal(merged.length,60);assert.equal(merged[0].name,'Copper');assert.equal(merged[0].latitude,31.7569);assert.equal(merged[0].score,0);
  assert.equal(merged.find(s=>s.id==='88').score,null);assert.equal(merged.some(s=>s.site_id===999999),false);
  assert.ok(merged.filter(s=>s.id!=='9').every(s=>s.score===null));
  assert.ok(atlasSummaries(roster,[]).every(s=>s.score===null));
});
test('search and region filtering remain within the approved roster',()=>{
  const roster=atlasRoster(snapshot);
  assert.equal(atlasFilter(roster,{query:'El Paso Electric'}).some(s=>s.id==='9'),true);
  assert.equal(atlasFilter(roster,{query:'67769'})[0].name,'Rock Creek Wind');
  assert.equal(atlasFilter(roster,{region:'florida_gulf'}).length,10);
  assert.equal(atlasFilter(roster,{query:'no-such-plant'}).length,0);
});
test('the transition preserves plant identity while smoothly raising the vertical dimension',()=>{
  const flat={tilt:0,yaw:0,zoom:1,panX:0,panY:0};
  assert.deepEqual(atlasPoint(400,200,60,flat,1000,600),[400,200]);
  let previous=0;
  for(let i=0;i<=100;i++){const k=atlasEase(i/100);assert.ok(k>=previous&&k>=0&&k<=1);previous=k;}
  const raised=atlasPoint(400,200,60,{...flat,tilt:.98},1000,600),ground=atlasPoint(400,200,0,{...flat,tilt:.98},1000,600);
  assert.equal(raised[0],ground[0]);assert.ok(raised[1]<ground[1]);assert.equal(atlasEase(0),0);assert.equal(atlasEase(1),1);
});
test('pointer-anchored zoom and shared-location pin spreading preserve location anchors',()=>{
  const camera={tilt:.98,yaw:-.14,zoom:2,panX:10,panY:20};
  const screen=atlasPoint(410,280,30,camera,1000,600),next={...camera,...atlasZoom(camera,5,1000,600,screen)};
  const zoomed=atlasPoint(410,280,30,next,1000,600);
  assert.ok(Math.hypot(screen[0]-zoomed[0],screen[1]-zoomed[1])<1e-8);
  const pins=Array.from({length:10},(_,i)=>({site:{site_id:i+1},x:180,y:220,selected:i===0}));
  const spread=spreadAtlasPins(pins,400,450);
  assert.equal(spread.length,10);assert.equal(new Set(spread.map(p=>`${p.x}:${p.y}`)).size,10);
  assert.ok(spread.every(p=>p.anchorX===180&&p.anchorY===220));assert.deepEqual(pins[0],{site:{site_id:1},x:180,y:220,selected:true});
});
test('all 60 actual coordinates project into the national view',async()=>{
  await import('../crew-vendor/d3-7.9.0.min.js');
  const geography=JSON.parse((await fs.readFile(new URL('../crew-data/atlas-us-states.json',import.meta.url),'utf8')).replace(/^\uFEFF/,''));
  const mainland={type:'FeatureCollection',features:geography.features.filter(f=>!['02','15','60','66','69','72','78'].includes(f.id))};
  const projection=globalThis.d3.geoAlbersUsa().fitExtent([[20,40],[1000,600]],mainland);
  assert.equal(atlasRoster(snapshot).filter(s=>projection([s.longitude,s.latitude])?.every(Number.isFinite)).length,60);
});
