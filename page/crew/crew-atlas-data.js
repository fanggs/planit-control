import {validScore} from './crew-domain.js';

// Match the crew score bands. A missing reading never becomes a safe score.
export const RISK_BANDS=Object.freeze([
  {key:'lower',label:'Lower',range:'0–3.9',color:'#8dd1a2'},
  {key:'elevated',label:'Elevated',range:'4–6.9',color:'#e8bd6c'},
  {key:'high',label:'High',range:'7–10',color:'#f6997b'},
  {key:'unknown',label:'No score',range:'Unavailable',color:'#829087'}
]);
export function atlasRisk(score){return RISK_BANDS[!validScore(score)?3:score>=7?2:score>=4?1:0];}
export function atlasRank(sites){return sites.slice().sort((a,b)=>(validScore(b.score)?b.score:-1)-(validScore(a.score)?a.score:-1)||a.name.localeCompare(b.name));}
export const REGIONS=Object.freeze({
  western_wildfire:{label:'Western wildfire',short:'West'},
  southwest_heat:{label:'Southwest heat',short:'Southwest'},
  plains_storms:{label:'Plains storms',short:'Plains'},
  mississippi_valley:{label:'Mississippi Valley',short:'Mississippi'},
  florida_gulf:{label:'Florida & Gulf',short:'Gulf'},
  eastern_storms:{label:'Eastern storms',short:'East'}
});

export function atlasRoster(rows) {
  if(!Array.isArray(rows)||rows.length!==60)throw new Error('The atlas requires Sid’s complete 60-site roster.');
  const ids=new Set(),counts=new Map();
  const sites=rows.map(s=>{
    if(!Number.isSafeInteger(s.site_id)||s.site_id<=0||ids.has(s.site_id)||!s.is_monitored||!REGIONS[s.hazard_region]||!s.name||!Number.isFinite(s.latitude)||!Number.isFinite(s.longitude)||s.latitude<24||s.latitude>50||s.longitude< -125||s.longitude> -66)throw new Error('The monitored plant roster is invalid.');
    ids.add(s.site_id);counts.set(s.hazard_region,(counts.get(s.hazard_region)||0)+1);
    return {...s,id:String(s.site_id),score:null,score_updated_at:null,active_alert:null};
  });
  if([...counts.values()].some(n=>n!==10)||counts.size!==6)throw new Error('The roster must contain ten plants in each of six regions.');
  return sites;
}

// The verified roster supplies identities and geography. API rows may add risk
// data, but cannot add plants or replace Sid's location/name with another record.
export function atlasSummaries(roster,rows) {
  const summaries=new Map((Array.isArray(rows)?rows:[]).map(s=>[String(s.id??s.site_id),s]));
  return roster.map(site=>{
    const raw=summaries.get(site.id);
    return {...site,score:validScore(raw?.score)?raw.score:null,
      score_updated_at:raw?.score_updated_at??raw?.scored_at??null,
      active_alert:raw?.active_alert??null};
  });
}

export function atlasFilter(sites,{query='',region=''}={}) {
  const q=query.trim().toLowerCase();
  return sites.filter(s=>(!region||s.hazard_region===region)&&(!q||[s.name,s.id,s.state,s.utility,s.county].some(v=>String(v??'').toLowerCase().includes(q))));
}

export function atlasPoint(x,y,z,camera,width,height) {
  const cx=width/2,cy=height/2,a=x-cx,b=y-cy,c=Math.cos(camera.yaw),s=Math.sin(camera.yaw);
  return [cx+camera.panX+(a*c-b*s)*camera.zoom,
    cy+camera.panY+((a*s+b*c)*Math.cos(camera.tilt)-z*Math.sin(camera.tilt))*camera.zoom];
}
export function atlasZoom(camera,zoom,width,height,anchor=[width/2,height/2]) {
  const scale=zoom/camera.zoom;
  return {zoom,panX:camera.panX*scale+(1-scale)*(anchor[0]-width/2),panY:camera.panY*scale+(1-scale)*(anchor[1]-height/2)};
}
export const atlasEase=t=>t<.5?4*t*t*t:1-(-2*t+2)**3/2;

// A marker's position depends only on its coordinates, score height and camera.
// Selection changes its appearance, never the geometry of nearby plants.
export function atlasPins(positions,camera,width,height,selectedId) {
  return positions.map(({site,xy})=>{
    const beam=validScore(site.score)?site.score*10:52;
    const base=atlasPoint(...xy,0,camera,width,height);
    const [x,y]=atlasPoint(...xy,beam*Math.min(1,width/900),camera,width,height);
    return {site,base,x,y,selected:site.id===selectedId};
  });
}

// Move text boxes only. When space runs out, keep higher-priority labels and
// omit the rest; all plants remain selectable through the searchable list.
export function layoutAtlasLabels(labels,width,height) {
  const placed=[],margin=8,gap=10;
  for(const label of labels.slice().sort((a,b)=>b.priority-a.priority||a.id.localeCompare(b.id))) {
    const {w,h,anchorX,anchorY}=label;
    if(w>width-margin*2||h>height-margin*2||anchorX<0||anchorX>width||anchorY<0||anchorY>height)continue;
    const candidates=[
      [anchorX-w/2,anchorY-h-gap],[anchorX-w/2,anchorY+gap],
      [anchorX+gap,anchorY-h/2],[anchorX-w-gap,anchorY-h/2],
      [anchorX-w/2,anchorY-h*2-gap*2],[anchorX-w/2,anchorY+h+gap*2]
    ];
    for(const [cx,cy] of candidates) {
      const x=Math.max(margin,Math.min(width-w-margin,cx)),y=Math.max(margin,Math.min(height-h-margin,cy));
      if(anchorX>x-gap/2&&anchorX<x+w+gap/2&&anchorY>y-gap/2&&anchorY<y+h+gap/2)continue;
      if(placed.some(p=>x<p.x+p.w+4&&x+w+4>p.x&&y<p.y+p.h+4&&y+h+4>p.y))continue;
      placed.push({...label,x,y});break;
    }
  }
  return placed;
}
