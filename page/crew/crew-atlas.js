import {config} from './crew-config.js';
import {brandMark} from './crew-visuals.js';
import {validScore} from './crew-domain.js';
import {esc,dateLabel} from './crew-ui.js';
import {REGIONS,RISK_BANDS,atlasRisk,atlasRank,atlasRoster,atlasSummaries,atlasFilter,atlasPoint,atlasZoom,atlasEase,spreadAtlasPins} from './crew-atlas-data.js';

const $=selector=>document.querySelector(selector),canvas=$('#atlas-canvas'),ctx=canvas.getContext('2d');
const reduced=matchMedia('(prefers-reduced-motion: reduce)'),abort=new AbortController();
const on=(target,type,fn,options={})=>target.addEventListener(type,fn,{...options,signal:abort.signal});
const camera={tilt:0,yaw:0,zoom:1,panX:0,panY:0};
const state={roster:[],sites:[],visible:[],selected:'621',hover:null,mode:'2d',motion:!reduced.matches,scoreState:'locations'};
const query=new URLSearchParams(location.search),initialSite=query.get('return_site');
const returnId=/^[1-9]\d*$/.test(initialSite||'')?initialSite:'621';
let d3,geography,projection,ground=[],grid,width=0,height=0,ratio=1,positions=[],hits=[],raf=0,animation,pulse=0,drag,pinch,sourceAPI;
const touches=new Map();
const selected=()=>state.sites.find(s=>s.id===state.selected);
const point=(x,y,z=0)=>atlasPoint(x,y,z,camera,width,height);
function announce(text){$('#atlas-announcement').textContent=text;}
function saveView(){const url=new URL(location.href);url.searchParams.set('site',state.selected);url.searchParams.set('view',state.mode);url.searchParams.set('return_site',returnId);history.replaceState({},'',url);}
function pose(mode=state.mode){return {tilt:mode==='3d'?.98:0,yaw:mode==='3d'?-.14:0,zoom:1,panX:0,panY:mode==='3d'?height*.055:0};}
function request(){if(!raf&&!document.hidden)raf=requestAnimationFrame(draw);}
function move(to){
  if(!state.motion||reduced.matches){Object.assign(camera,to);animation=null;request();return;}
  animation={from:{...camera},to:{...camera,...to},start:performance.now(),duration:1050};request();
}
function build(){
  if(!d3||!geography)return;
  const nextW=canvas.clientWidth,nextH=canvas.clientHeight;if(nextW<20||nextH<20)return;
  let anchor;
  if(width&&(width!==nextW||height!==nextH)&&camera.zoom>1){
    const closest=positions.reduce((best,p)=>{const xy=point(...p.xy),distance=Math.hypot(xy[0]-width/2,xy[1]-height/2);return distance<best.distance?{site:p.site,xy,distance}:best;},{distance:Infinity});
    if(closest.site)anchor={site:closest.site,u:closest.xy[0]/width,v:closest.xy[1]/height};animation=null;
  }
  width=nextW;height=nextH;ratio=Math.min(devicePixelRatio||1,2);canvas.width=width*ratio;canvas.height=height*ratio;ctx.setTransform(ratio,0,0,ratio,0,0);
  const collection={type:'FeatureCollection',features:geography.features.filter(f=>!['02','15','60','66','69','72','78'].includes(f.id))};
  const extent=height<500&&width>600?[[width*.27,40],[width-35,height-30]]:width>1100?[[width*.24,height*.16],[width*.84,height*.85]]:width>900?[[width*.27,height*.2],[width*.94,height*.81]]:[[20,height*.28],[width-20,height*.72]];
  projection=d3.geoAlbersUsa().fitExtent(extent,collection);
  const path=d3.geoPath(projection);
  ground=collection.features.map(f=>({path:new Path2D(path(f)),name:f.properties.name,center:path.centroid(f)}));
  grid=new Path2D(path(d3.geoGraticule().extent([[-126,24],[-66,50]]).step([5,5])()));
  if(anchor){const xy=projection([anchor.site.longitude,anchor.site.latitude]);if(xy){const [x,y]=point(...xy);camera.panX+=width*anchor.u-x;camera.panY+=height*anchor.v-y;}}
  rebuildPositions();
}
function rebuildPositions(){
  if(!projection)return;
  positions=state.visible.map(site=>({site,xy:projection([site.longitude,site.latitude])})).filter(p=>p.xy?.every(Number.isFinite));
  canvas.dataset.mappedPlants=positions.length;request();
}
function draw(now){
  raf=0;if(!projection)return;
  let active=false;
  if(animation){const t=Math.min(1,(now-animation.start)/animation.duration),ease=atlasEase(t);for(const key of Object.keys(camera))camera[key]=animation.from[key]+(animation.to[key]-animation.from[key])*ease;if(t>=1)animation=null;else active=true;}
  const wave=pulse?Math.min(1,(now-pulse)/1200):1;
  if(pulse&&wave<1)active=true;else pulse=0;
  ctx.clearRect(0,0,width,height);
  const c=Math.cos(camera.yaw),s=Math.sin(camera.yaw),cos=Math.cos(camera.tilt);
  ctx.save();ctx.transform(c*camera.zoom,s*cos*camera.zoom,-s*camera.zoom,c*cos*camera.zoom,...point(0,0));
  ctx.fillStyle='#172a22';ctx.strokeStyle='#3a5548';ctx.lineWidth=.65/camera.zoom;
  for(const feature of ground){ctx.fill(feature.path);ctx.stroke(feature.path);}
  ctx.strokeStyle='#b7f7d415';ctx.lineWidth=.5/camera.zoom;ctx.stroke(grid);
  const names=new Set(['California','Texas','Montana','Florida','New York','Colorado','Mississippi','Washington']);
  ctx.font=`${8/Math.max(1,camera.zoom*.55)}px ui-monospace,monospace`;ctx.textAlign='center';ctx.fillStyle='#9bb0a477';
  if(width>700)for(const feature of ground)if(names.has(feature.name)&&feature.center.every(Number.isFinite))ctx.fillText(feature.name.toUpperCase(),...feature.center);
  ctx.restore();
  const pins=positions.map(p=>{
    const beam=validScore(p.site.score)?p.site.score*10:52;
    const base=point(...p.xy),cap=point(...p.xy,beam*Math.min(1,width/900));
    return {site:p.site,base,x:cap[0],y:cap[1],selected:p.site.id===state.selected};
  });
  hits=spreadAtlasPins(pins,width,height);
  // Lines and halos are local canvas effects. No frame can request API data.
  for(const p of hits){
    const color=atlasRisk(p.site.score).color;
    ctx.save();ctx.strokeStyle=color;ctx.lineWidth=p.selected?1.6:1;ctx.globalAlpha=p.selected?.9:.5;
    ctx.beginPath();ctx.moveTo(...p.base);ctx.lineTo(p.anchorX,p.anchorY);ctx.stroke();
    if(p.displaced){ctx.globalAlpha=.4;ctx.lineWidth=.7;ctx.beginPath();ctx.moveTo(p.anchorX,p.anchorY);ctx.lineTo(p.x,p.y);ctx.stroke();}
    ctx.globalAlpha=.3;ctx.beginPath();ctx.ellipse(p.base[0],p.base[1],p.selected?6:3,(p.selected?6:3)*Math.max(.3,cos),0,0,Math.PI*2);ctx.stroke();ctx.restore();
  }
  const ordered=hits.slice().sort((a,b)=>Number(a.selected)-Number(b.selected));
  for(const p of ordered){
    const color=atlasRisk(p.site.score).color,hot=p.site.id===state.hover||p.selected,r=hot?4.8:3.2;
    ctx.save();ctx.shadowColor=color;ctx.shadowBlur=hot?14:7;ctx.strokeStyle=color;ctx.fillStyle='#101916';ctx.lineWidth=hot?1.7:1;
    ctx.beginPath();ctx.arc(p.x,p.y,r,0,Math.PI*2);ctx.fill();ctx.stroke();
    if(validScore(p.site.score)){ctx.beginPath();ctx.arc(p.x,p.y,hot?2.4:1.5,0,Math.PI*2);ctx.fillStyle=color;ctx.fill();}
    ctx.shadowBlur=0;
    if(hot){ctx.globalAlpha=.6;ctx.lineWidth=.8;ctx.beginPath();ctx.arc(p.x,p.y,r+5+(pulse&&p.selected?Math.sin(wave*Math.PI)*7:0),0,Math.PI*2);ctx.stroke();}
    ctx.restore();
  }
  const labels=ordered.filter(p=>p.selected||p.site.id===state.hover||camera.zoom>2.3).sort((a,b)=>Number(a.selected)-Number(b.selected));
  const seen=[];
  for(const p of labels.slice(-Math.min(width<700?3:6,labels.length))){
    ctx.save();ctx.font='500 10px system-ui';let text=p.site.name;const max=Math.min(230,width-36);
    while(ctx.measureText(text).width>max-18&&text.length>8)text=text.slice(0,-2)+'…';
    const w=ctx.measureText(text).width+18,h=24,x=Math.max(8,Math.min(width-w-8,p.x-w/2)),y=Math.max(8,Math.min(height-h-8,p.y-34));
    const overlaps=seen.some(a=>x<a.x+a.w&&x+w>a.x&&y<a.y+h&&y+h>a.y);
    if(!overlaps||p.selected||p.site.id===state.hover){ctx.fillStyle='#0c1712ee';ctx.strokeStyle=atlasRisk(p.site.score).color+'77';ctx.lineWidth=.6;ctx.beginPath();ctx.roundRect(x,y,w,h,6);ctx.fill();ctx.stroke();ctx.fillStyle='#e4ecee';ctx.textAlign='left';ctx.fillText(text,x+9,y+16);seen.push({x,y,w});}ctx.restore();
  }
  canvas.dataset.view=state.mode;canvas.dataset.zoom=camera.zoom.toFixed(2);canvas.dataset.transitioning=String(Boolean(animation));
  $('#atlas-compass-needle').style.transform=`rotate(${-camera.yaw*180/Math.PI}deg)`;
  $('#atlas-view-status').textContent=animation?`TRANSITIONING TO ${state.mode.toUpperCase()}`:state.mode==='3d'?'3D PERSPECTIVE':'2D GEOGRAPHIC VIEW';
  if(active)request();
}
function renderList(){
  $('#atlas-result-count').textContent=`${state.visible.length} / 60`;
  $('#atlas-plants').innerHTML=state.visible.map(s=>`<button class="atlas-plant" data-plant="${s.id}" aria-pressed="${s.id===state.selected}" style="--risk:${atlasRisk(s.score).color}" data-risk="${atlasRisk(s.score).key}"><span class="atlas-plant-dot" aria-hidden="true"></span><span><span class="atlas-plant-name">${esc(s.name)}</span><span class="atlas-plant-meta">${esc(s.state)} · EIA ${s.site_id} · ${REGIONS[s.hazard_region].short}</span></span><span class="atlas-plant-score" aria-label="${atlasRisk(s.score).label} hazard score">${validScore(s.score)?s.score.toFixed(1):'—'}</span></button>`).join('')||'<p class="atlas-empty">No matching monitored plants. Try a state, utility or plant name.</p>';
  $('#atlas-risk-key').innerHTML=RISK_BANDS.map(r=>`<div class="atlas-risk-key-row" style="--risk:${r.color}"><i aria-hidden="true"></i><span>${r.label} <small>${r.range}</small></span><strong>${state.visible.filter(s=>atlasRisk(s.score).key===r.key).length}</strong></div>`).join('');
  $('#atlas-mobile-risk').innerHTML=RISK_BANDS.map(r=>`<span style="color:${r.color}" title="${r.range}">${state.visible.filter(s=>atlasRisk(s.score).key===r.key).length} ${r.label.toLowerCase()}</span>`).join('<span aria-hidden="true"> · </span>');
}
function crewLink(id){const url=new URL('crew.html',location.href);url.searchParams.set('site',id);if(config.dataMode==='mock')url.searchParams.set('demo','1');return url.href;}
function renderInspection(){
  const site=selected();if(!site)return;
  $('#atlas-inspection').innerHTML=`<p class="atlas-eyebrow">SELECTED PLANT / ${esc(REGIONS[site.hazard_region].label.toUpperCase())}</p><h2>${esc(site.name)}</h2><p class="atlas-selected-meta">${esc(site.county)}, ${esc(site.state)} · EIA ${site.site_id}</p><p class="atlas-selected-utility">${esc(site.utility)}</p><div class="atlas-selected-score" style="--risk:${atlasRisk(site.score).color}"><strong>${validScore(site.score)?site.score.toFixed(1):'—'}</strong><div><small>${validScore(site.score)?atlasRisk(site.score).label.toUpperCase()+' HAZARD INDEX / 10':'HAZARD SCORE UNAVAILABLE'}</small><small>${validScore(site.score)?(config.dataMode==='mock'?'Sample score · ':'Scored ')+esc(dateLabel(site.score_updated_at,site.timezone)):'Verified location · no score inferred'}</small></div><button class="atlas-detail-button" data-atlas-action="focus">Locate ↗</button></div><a class="atlas-open-site" href="${esc(crewLink(site.id))}">Open crew site <span aria-hidden="true">↗</span></a>`;
}
function selectSite(id,{focus=false}={}){
  if(!state.sites.some(s=>s.id===String(id)))return;
  state.selected=String(id);renderList();renderInspection();saveView();
  const site=selected();announce(`${site.name}, ${site.state}. ${REGIONS[site.hazard_region].label}. ${validScore(site.score)?'Hazard score '+site.score+' out of 10.':'Hazard score unavailable.'}`);
  if(state.motion&&!reduced.matches)pulse=performance.now();
  if(focus&&projection){const xy=projection([site.longitude,site.latitude]);if(xy){const [x,y]=point(...xy),zoom=Math.max(camera.zoom,2.6),scale=zoom/camera.zoom;move({zoom,panX:(camera.panX+width/2-x)*scale,panY:(camera.panY+height/2-y)*scale});}}
  request();
}
function filter(){
  state.visible=atlasRank(atlasFilter(state.sites,{query:$('#atlas-search').value,region:$('#atlas-region').value}));
  if(state.visible.length&&!state.visible.some(s=>s.id===state.selected))state.selected=state.visible[0].id;
  renderList();renderInspection();rebuildPositions();announce(`${state.visible.length} of 60 monitored plants match your filters.`);
}
function switchMode(mode){state.mode=mode;document.querySelectorAll('[data-atlas-mode]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.atlasMode===mode)));move({...pose(mode),zoom:camera.zoom,panX:camera.panX,panY:camera.panY});saveView();}
function overview(){state.hover=null;move(pose());}
function xy(e){const rect=canvas.getBoundingClientRect();return [e.clientX-rect.left,e.clientY-rect.top];}
function closest(x,y){return hits.reduce((best,p)=>{const distance=Math.hypot(p.x-x,p.y-y);return distance<best.distance?{site:p.site,distance}:best;},{distance:23}).site;}
on($('#atlas-search'),'input',filter);on($('#atlas-region'),'change',filter);
on(document,'click',event=>{
  const plant=event.target.closest('[data-plant]');if(plant){selectSite(plant.dataset.plant,{focus:true});return;}
  const mode=event.target.closest('[data-atlas-mode]');if(mode){switchMode(mode.dataset.atlasMode);return;}
  const action=event.target.closest('[data-atlas-action]')?.dataset.atlasAction;
  if(action==='overview')overview();
  if(action==='motion'){$('#atlas-motion').checked=!state.motion;motion();}
  if(action==='focus')selectSite(state.selected,{focus:true});
  if(action==='in'||action==='out')move(atlasZoom(camera,Math.max(.65,Math.min(14,camera.zoom*(action==='in'?1.5:1/1.5))),width,height));
});
on($('#atlas-toggle-panel'),'click',()=>{
  if(innerWidth<=900){$('#atlas-sidebar').classList.toggle('atlas-mobile-open');const open=$('#atlas-sidebar').classList.contains('atlas-mobile-open');$('#atlas-toggle-panel').setAttribute('aria-expanded',String(open));if(open)$('#atlas-search').focus();}
  else {document.body.classList.toggle('atlas-hidden-panel');$('#atlas-toggle-panel').setAttribute('aria-expanded',String(!document.body.classList.contains('atlas-hidden-panel')));}
});
function motion(){state.motion=$('#atlas-motion').checked&&!reduced.matches;if(animation)Object.assign(camera,animation.to);animation=null;pulse=0;$('#atlas-motion').disabled=reduced.matches;$('#atlas-motion').checked=state.motion;const button=$('[data-atlas-action="motion"]');button.setAttribute('aria-pressed',String(state.motion));button.disabled=reduced.matches;request();}
on($('#atlas-motion'),'change',motion);on(reduced,'change',()=>{$('#atlas-motion').checked=!reduced.matches;motion();});
on(canvas,'pointerdown',e=>{
  canvas.setPointerCapture(e.pointerId);touches.set(e.pointerId,xy(e));animation=null;
  if(touches.size===1)drag={start:xy(e),previous:xy(e),moved:false};
  if(touches.size===2){const [a,b]=[...touches.values()];pinch={distance:Math.hypot(a[0]-b[0],a[1]-b[1]),center:[(a[0]+b[0])/2,(a[1]+b[1])/2],view:{...camera}};if(drag)drag.moved=true;}
});
on(canvas,'pointermove',e=>{
  const p=xy(e);
  if(!touches.has(e.pointerId)){const hover=closest(...p)?.id??null;if(hover!==state.hover){state.hover=hover;canvas.style.cursor=hover?'pointer':'grab';request();}return;}
  touches.set(e.pointerId,p);
  if(pinch&&touches.size>=2){const [a,b]=[...touches.values()],distance=Math.hypot(a[0]-b[0],a[1]-b[1]),center=[(a[0]+b[0])/2,(a[1]+b[1])/2],zoom=Math.max(.65,Math.min(14,pinch.view.zoom*distance/Math.max(1,pinch.distance)));Object.assign(camera,atlasZoom(pinch.view,zoom,width,height,pinch.center));camera.panX+=center[0]-pinch.center[0];camera.panY+=center[1]-pinch.center[1];request();return;}
  if(!drag)return;const dx=p[0]-drag.previous[0],dy=p[1]-drag.previous[1];if(Math.hypot(p[0]-drag.start[0],p[1]-drag.start[1])>5)drag.moved=true;
  if(drag.moved){if(e.shiftKey&&state.mode==='3d'){camera.yaw+=dx*.004;camera.tilt=Math.max(.2,Math.min(1.15,camera.tilt+dy*.003));}else{camera.panX+=dx;camera.panY+=dy;}drag.previous=p;request();}
});
on(canvas,'pointerup',e=>{if(drag&&!drag.moved&&!pinch){const site=closest(...xy(e));if(site)selectSite(site.id);}touches.delete(e.pointerId);pinch=null;if(!touches.size)drag=null;else if(drag){drag.previous=[...touches.values()][0];drag.moved=true;}});
on(canvas,'pointercancel',()=>{touches.clear();drag=null;pinch=null;});on(canvas,'pointerleave',()=>{state.hover=null;request();});
on(canvas,'wheel',e=>{e.preventDefault();animation=null;Object.assign(camera,atlasZoom(camera,Math.max(.65,Math.min(14,camera.zoom*Math.exp(-e.deltaY*.001))),width,height,xy(e)));request();},{passive:false});
on(canvas,'keydown',e=>{
  const step={ArrowLeft:[35,0],ArrowRight:[-35,0],ArrowUp:[0,35],ArrowDown:[0,-35]}[e.key];
  if(step){e.preventDefault();move({panX:camera.panX+step[0],panY:camera.panY+step[1]});}
  if(['+','=','-'].includes(e.key)){e.preventDefault();move(atlasZoom(camera,Math.max(.65,Math.min(14,camera.zoom*(e.key==='-'?.8:1.25))),width,height));}
  if(['n','p'].includes(e.key.toLowerCase())&&state.visible.length){e.preventDefault();const index=state.visible.findIndex(s=>s.id===state.selected),direction=e.key.toLowerCase()==='n'?1:-1;selectSite(state.visible[(index+direction+state.visible.length)%state.visible.length].id);}
  if(e.key==='Escape')overview();
});
on(document,'visibilitychange',()=>{if(document.hidden){cancelAnimationFrame(raf);raf=0;if(animation)Object.assign(camera,animation.to);animation=null;pulse=0;}else request();});
const resize=new ResizeObserver(build);resize.observe(canvas);
on(window,'pagehide',()=>{cancelAnimationFrame(raf);raf=0;});on(window,'pageshow',e=>{if(e.persisted)build();});
async function refreshScores(){
  const button=$('#atlas-data-refresh');button.disabled=true;
  try{
    if(config.dataMode==='live'&&!sourceAPI){const auth=await import('./crew-auth.js');await auth.initAuth();const user=await auth.session();const {userRoles}=await import('./crew-routing.js');if(!user||!userRoles(user,config.authRoleClaim).length){button.textContent='Sign in for scores ↗';button.onclick=()=>{location.href='login.html?start=1&site='+encodeURIComponent(state.selected);};throw new Error('Sign in to load scores. Location data remains available.');}sourceAPI=(await import('./crew-services.js')).services;}
    sourceAPI??=(await import('./crew-services.js')).services;
    state.sites=atlasSummaries(state.roster,await sourceAPI.listSites());state.scoreState='connected';filter();
    const scored=state.sites.filter(s=>validScore(s.score)).length;$('#atlas-data-status').textContent=config.dataMode==='mock'?`SAMPLE SCORES · ${scored} REAL PLANT LOCATIONS`:`EIA LOCATIONS / ${scored} OF 60 SCORES AVAILABLE`;button.textContent='Refresh scores ↻';
  }catch(error){state.sites=atlasSummaries(state.roster,[]);state.scoreState='unavailable';filter();$('#atlas-data-status').textContent='VERIFIED LOCATIONS / SCORE FEED UNAVAILABLE';announce(error.message);}
  finally{button.disabled=false;}
}
on($('#atlas-data-refresh'),'click',()=>{if(!$('#atlas-data-refresh').onclick)refreshScores();});
async function getJSON(path){const response=await fetch(new URL(path,import.meta.url));if(!response.ok)throw new Error('A required map data file could not be loaded.');return response.json();}
async function boot(){
  try{
    state.roster=atlasRoster(await getJSON('./crew-data/monitored-sites.json'));state.sites=state.roster.slice();state.visible=atlasRank(state.sites);
    state.selected=state.sites.some(s=>s.id===query.get('site'))?query.get('site'):'621';
    $('.atlas-brand-icon').innerHTML=brandMark();
    $('#atlas-sample-note').hidden=config.dataMode!=='mock';
    $('#atlas-region').insertAdjacentHTML('beforeend',Object.entries(REGIONS).map(([key,r])=>`<option value="${key}">${r.label}</option>`).join(''));
    const crewURL=new URL('crew.html',location.href);crewURL.searchParams.set('site',returnId);if(config.dataMode==='mock')crewURL.searchParams.set('demo','1');$('#atlas-crew-link').href=crewURL.href;
    $('#atlas-toggle-panel').setAttribute('aria-expanded',String(innerWidth>900));renderList();renderInspection();motion();
    const [,states]=await Promise.all([import('./crew-vendor/d3-7.9.0.min.js'),getJSON('./crew-data/atlas-us-states.json')]);d3=globalThis.d3;geography=states;build();$('#atlas-loading').hidden=true;
    if(query.get('view')==='3d')switchMode('3d');saveView();
    $('#atlas-data-refresh').hidden=false;await refreshScores();
  }catch(error){$('#atlas-loading').hidden=false;$('#atlas-loading').textContent=error.message+' The plant list remains available if the roster loaded.';announce(error.message);}
}
boot();
