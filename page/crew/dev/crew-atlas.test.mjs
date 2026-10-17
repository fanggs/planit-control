import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import {REGIONS,atlasRisk,atlasRank,atlasRoster,atlasSummaries,atlasFilter,atlasPoint,atlasZoom,atlasEase,atlasPins,layoutAtlasLabels} from '../crew-atlas-data.js';
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
test('pointer-anchored zoom preserves the geographic point under the pointer',()=>{
  const camera={tilt:.98,yaw:-.14,zoom:2,panX:10,panY:20};
  const screen=atlasPoint(410,280,30,camera,1000,600),next={...camera,...atlasZoom(camera,5,1000,600,screen)};
  const zoomed=atlasPoint(410,280,30,next,1000,600);
  assert.ok(Math.hypot(screen[0]-zoomed[0],screen[1]-zoomed[1])<1e-8);
});

test('crowded plant dots stay at their projected coordinates regardless of selection or filtering',()=>{
  const positions=Array.from({length:10},(_,i)=>({site:{id:String(i+1),score:5},xy:[180,220]}));
  const original=structuredClone(positions);
  for(const tilt of [0,.98]){
    const camera={tilt,yaw:-.14,zoom:2,panX:10,panY:20};
    const first=atlasPins(positions,camera,400,450,'1'),next=atlasPins(positions,camera,400,450,'10');
    for(let i=0;i<positions.length;i++){
      const expected=atlasPoint(180,220,50*400/900,camera,400,450);
      assert.deepEqual([first[i].x,first[i].y],expected);
      assert.deepEqual([next[i].x,next[i].y],expected);
      assert.deepEqual(first[i].base,atlasPoint(180,220,0,camera,400,450));
    }
    const filtered=atlasPins(positions.slice(1).reverse(),camera,400,450,'10');
    for(const pin of filtered){const prior=first.find(p=>p.site.id===pin.site.id);assert.deepEqual([pin.x,pin.y,pin.base],[prior.x,prior.y,prior.base]);}
    assert.equal(first[0].selected,true);assert.equal(next[0].selected,false);
  }
  assert.deepEqual(positions,original);
});

test('only labels spread, with selected labels first, no collisions and unchanged anchors',()=>{
  const labels=Array.from({length:6},(_,i)=>({id:String(i),w:100,h:24,anchorX:180,anchorY:220,priority:i===5?2:0}));
  const original=structuredClone(labels),placed=layoutAtlasLabels(labels,400,450);
  assert.equal(placed[0].id,'5');assert.ok(placed.length>1);
  assert.ok(placed.every(p=>p.anchorX===180&&p.anchorY===220&&p.x>=8&&p.y>=8&&p.x+p.w<=392&&p.y+p.h<=442));
  for(let i=0;i<placed.length;i++)for(const other of placed.slice(i+1)){
    const p=placed[i];assert.equal(p.x<other.x+other.w&&p.x+p.w>other.x&&p.y<other.y+other.h&&p.y+p.h>other.y,false);
  }
  assert.deepEqual(labels,original);
  const narrow=layoutAtlasLabels(labels,140,90);assert.ok(narrow.length<labels.length);
  assert.deepEqual(layoutAtlasLabels([{...labels[0],anchorX:-20}],400,450),[]);
});
test('all 60 actual coordinates project into the national view',async()=>{
  await import('../crew-vendor/d3-7.9.0.min.js');
  const geography=JSON.parse((await fs.readFile(new URL('../crew-data/atlas-us-states.json',import.meta.url),'utf8')).replace(/^\uFEFF/,''));
  const mainland={type:'FeatureCollection',features:geography.features.filter(f=>!['02','15','60','66','69','72','78'].includes(f.id))};
  const projection=globalThis.d3.geoAlbersUsa().fitExtent([[20,40],[1000,600]],mainland);
  assert.equal(atlasRoster(snapshot).filter(s=>projection([s.longitude,s.latitude])?.every(Number.isFinite)).length,60);
});

test('hazard colors respect exact band boundaries and never label missing readings as lower risk',()=>{
  for(const score of [0,1,3.9])assert.equal(atlasRisk(score).key,'lower');
  for(const score of [4,5.7,6.99])assert.equal(atlasRisk(score).key,'elevated');
  for(const score of [7,8.2,10])assert.equal(atlasRisk(score).key,'high');
  for(const score of [null,undefined,NaN,-1,11,'8'])assert.equal(atlasRisk(score).key,'unknown');
  assert.equal(new Set([0,4,7,null].map(s=>atlasRisk(s).color)).size,4);
});
test('primary map ranks by risk with true zero ahead of missing scores and stable name ties',()=>{
  const rows=[{name:'Missing',score:null},{name:'Zero',score:0},{name:'Z',score:8},{name:'A',score:8},{name:'Bad',score:12}];
  assert.deepEqual(atlasRank(rows).map(s=>s.name),['A','Z','Zero','Bad','Missing']);
  assert.equal(rows[0].name,'Missing');
});
