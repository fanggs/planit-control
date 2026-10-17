/* Why: Assemble previously tested modules into simple crew navigation and an isolated supervisor handoff, retaining alerts across views. */
// Separate integration preview. This does not replace Aryan's owned dashboard files.
import {icon,brandMark,contourArt} from './crew-visuals.js';
import {config} from './crew-config.js';
import {userRoles} from './crew-routing.js';
import {initAuth,session,signIn,signOut,enterDemo,authConfigured} from './crew-auth.js';
import {services} from './crew-services.js';
import {rankSites,validScore,riskLabel} from './crew-domain.js';
import {alertView} from './crew-state.js';
import {expireScreening} from './crew-screening.js';
import {esc,scorePanel,floodHTML,makeMap,dateLabel,safeURL,scoreBadgeHTML,scoreWindowHTML,wildlifeHTML} from './crew-ui.js';
const root=document.getElementById('crew-supervisor-root');
const state={sites:[],filtered:[],map:null,layer:null,reportLayer:null,photoURLs:[],selected:null,page:0,version:0,listVersion:0,unsubscribe:null,connected:false,detailVersion:0,lastEvent:0};
let noticeTimer,filterTimer;
const previewMarkers=new Map();
const reduceMotion=matchMedia('(prefers-reduced-motion: reduce)').matches;
function syncSelection(){
  for(const [id,marker] of previewMarkers){
    const active=String(id)===state.selected,element=marker.getElement();
    element?.classList.toggle('is-selected',active);
    element?.setAttribute('aria-pressed',String(active));
    marker.setZIndexOffset(active?1000:0);
  }
  for(const row of document.querySelectorAll('[data-select-site]')){
    row.setAttribute('aria-pressed',String(row.dataset.selectSite===state.selected));
  }
}
function renderSelectedPreview(site,reports=[]){
  const panel=document.getElementById('preview-selected');
  if(!panel)return;
  const score=validScore(site.score)?site.score.toFixed(1):'—';
  const tone=!validScore(site.score)?'unknown':site.score>=7?'high':site.score>=4?'elevated':'lower';
  const reportCount=reports.filter(r=>String(r.site_id)===String(site.id)&&r.status==='open').length;
  const lightning=alertView(site.alert,state.connected);
  panel.innerHTML=`<p class="crew-eyebrow">SELECTED POWER PLANT</p>
    <div class="preview-selection-heading"><div><h2>${esc(site.name)}</h2><p>${esc(site.state)} · Plant #${esc(site.id)}</p></div><div class="preview-score" data-risk="${tone}"><strong>${score}</strong><span>/ 10</span></div></div>
    ${scoreBadgeHTML(site)}${scoreWindowHTML(site)}<div class="preview-badges"><span class="crew-pill">${esc(riskLabel(site.score))} risk</span><span class="crew-pill">${reportCount} open reports</span></div>
    <p class="preview-alert" data-tone="${esc(lightning.tone)}">${site.alert?.is_replay?'Replay · ':''}${site.demo&&site.alert?.status==='unknown'?'Lightning feed unavailable in this sample':esc(lightning.title)}</p>
    <dl class="preview-readings">${[['Weather',site.hazards?.weather],['Heat',site.hazards?.heat],['Flooding',site.hazards?.flood]].map(([name,h])=>`<div><dt>${name}</dt><dd>${esc(h?.reading??'No data')}</dd></div>`).join('')}</dl>
    <small>${site.demo?'Sample conditions · ':''}Score updated ${dateLabel(site.score_updated_at,site.timezone)}</small>
    <div class="preview-selected-actions"><button class="crew-button secondary" id="preview-inspect">Full site details ↓</button><a class="crew-link" href="crew.html?site=${encodeURIComponent(site.id)}${config.dataMode==='mock'?'&demo=1':''}">Crew view ↗</a></div>`;
  state.selectedSnapshot=site;state.selectedReports=reports;
  panel.dataset.state='ready';panel.setAttribute('aria-busy','false');
  document.getElementById('preview-inspect').onclick=()=>document.getElementById('supervisor-detail').scrollIntoView({behavior:reduceMotion?'instant':'smooth',block:'start'});
}

function message(text){const box=document.getElementById('crew-message');box.textContent=text;box.classList.add('visible');clearTimeout(noticeTimer);noticeTimer=setTimeout(()=>box.classList.remove('visible'),7000);}
function login(error=''){
  root.innerHTML=`<main class="crew-login" id="crew-main">${brandMark()}<p class="crew-eyebrow">ForeSite / SUPERVISOR ACCESS</p><h1>Know where<br>to focus.</h1><p>One secure login opens the workspace assigned to your account.</p>${error?`<p class="crew-error" role="alert">${esc(error)}</p>`:''}<a class="crew-button" href="login.html?start=1">Log in with Auth0 ↗</a><a href="index.html">← Back to ForeSite</a>${config.dataMode==='mock'?'<button class="crew-button secondary" id="supervisor-demo">Open sample supervisor preview</button>':''}</main>`;
  document.getElementById('supervisor-demo')?.addEventListener('click',()=>{enterDemo();open();});
}
function filters(){return {query:document.getElementById('supervisor-query').value,region:document.getElementById('supervisor-region').value,minimum:Number(document.getElementById('supervisor-minimum').value)};}
async function open(){
  const user=await session();if(!user)return login();
  if(!user.demo&&!userRoles(user,config.authRoleClaim).includes('supervisor'))return login('Supervisor access is required. Ask your administrator to assign the supervisor role. The backend must also enforce this permission.');
  root.innerHTML='<main class="crew-login"><h1>Loading the monitored site picture…</h1></main>';
  try{
    state.sites=await services.listSites();if(!Array.isArray(state.sites))throw new Error('Site service must return a list.');
    root.innerHTML=`<header class="crew-header"><a class="crew-brand" href="index.html">${brandMark()}</a><div class="crew-header-actions"><a class="crew-link" href="crew.html${config.dataMode==='mock'?'?demo=1':''}">Crew workspace ↗</a><button id="supervisor-logout" class="crew-link">Sign out</button></div></header><main id="crew-main" class="crew-main crew-dashboard">
      ${config.dataMode==='mock'?'<p class="crew-demo"><strong>SAMPLE DATA</strong> · 60 real monitored plant locations. Risk scores and conditions are synthetic. Reports are shared between tabs on this browser only.</p>':''}
      <div class="crew-section-heading crew-site-hero crew-supervisor-hero">${contourArt()}<div class="crew-hero-copy"><p class="crew-eyebrow">SUPERVISOR WORKSPACE</p><h1>Know where to focus.</h1><p class="crew-muted" id="supervisor-updated"></p></div><button class="crew-button secondary" id="supervisor-refresh">Refresh sites</button></div>
      <div class="crew-dashboard-stats" id="supervisor-stats"></div><section class="crew-card crew-dashboard-filters"><div><label for="supervisor-query">Find a site</label><input id="supervisor-query" type="search" placeholder="Plant, state, operator or ID"></div><div><label for="supervisor-region">State / territory</label><select id="supervisor-region"><option value="">All states & territories</option>${[...new Set(state.sites.map(s=>s.state))].sort().map(s=>`<option>${esc(s)}</option>`).join('')}</select></div><div><label for="supervisor-minimum">Risk focus</label><select id="supervisor-minimum"><option value="0">All scores</option><option value="4">Elevated & high · 4+</option><option value="7">High · 7+</option></select></div></section>
      <div class="crew-dashboard-grid"><section class="crew-card crew-map-card"><div class="crew-row"><h2>Site overview</h2><button class="crew-link" id="preview-reset-map">View all plants</button><a class="crew-link" id="supervisor-atlas-link" href="crew-atlas.html${config.dataMode==='mock'?'?demo=1':''}">Open 2D / 3D map ↗</a><span id="supervisor-stream" class="crew-pill">Connecting…</span></div><p class="crew-muted">Select a point or a ranked site to inspect it. <span class="crew-map-key">● Lower &nbsp; <b>● Elevated</b> &nbsp; <strong>● High</strong></span></p><div id="supervisor-map" class="crew-map" aria-label="Power plants ranked by risk"></div><small id="supervisor-map-status">Click a glowing dot to inspect a plant. Selected plants have a bright outer ring.</small></section><section class="crew-card crew-ranking"><aside id="preview-selected" aria-live="polite" aria-atomic="true"><p class="crew-eyebrow">SITE INSPECTOR</p><h2>Pick a plant on the map.</h2><p class="crew-muted">Its score, conditions and crew reports appear here. You can also select a plant from the ranking below.</p></aside><div class="crew-row"><h2>Risk ranking</h2><small id="supervisor-match-count"></small></div><div id="supervisor-ranked-list"></div><div class="crew-row"><button class="crew-button secondary" id="supervisor-previous">Previous</button><small id="supervisor-page"></small><button class="crew-button secondary" id="supervisor-next">Next</button></div></section></div>
      <section id="supervisor-detail"><div class="crew-card crew-empty">Select a plant to inspect its score, flood status and crew reports.</div></section><p class="crew-footer">Reference: Sid’s 60 monitored EIA-860M plants. <a href="crew-data/atlas-source.json" target="_blank" rel="noopener">Coverage & source details ↗</a>. Missing scores remain unavailable.</p></main>`;
    state.map=makeMap('supervisor-map',[38,-96],4);if(state.map){state.layer=L.layerGroup().addTo(state.map);state.reportLayer=L.layerGroup().addTo(state.map);}
    document.getElementById('supervisor-query').addEventListener('input',()=>{clearTimeout(filterTimer);filterTimer=setTimeout(()=>applyFilters(true),180);});for(const id of ['supervisor-region','supervisor-minimum'])document.getElementById(id).addEventListener('change',()=>applyFilters(true));
    document.getElementById('supervisor-refresh').onclick=refresh;
    document.getElementById('supervisor-previous').onclick=()=>{state.page--;renderRanking();};document.getElementById('supervisor-next').onclick=()=>{state.page++;renderRanking();};
    document.getElementById('supervisor-logout').onclick=async()=>{state.version++;state.unsubscribe?.();state.map?.remove();await signOut();login();};
    applyFilters();
    document.getElementById('preview-reset-map').onclick=()=>{const points=state.filtered.filter(s=>[s.latitude,s.longitude].every(Number.isFinite)).map(s=>[s.latitude,s.longitude]);if(points.length)state.map?.fitBounds(points,{padding:[28,28],maxZoom:8,animate:!reduceMotion});};
    const version=++state.version;const unsubscribe=await services.subscribeEvents(null,event=>{
      if(version!==state.version)return;state.lastEvent=Date.now();if(event.type==='site'||event.type==='alert')refresh(event.sites,event.site_ids);if(event.type==='report'&&String(event.site_id)===String(state.selected))selectSite(state.selected,false);
    },connected=>{if(version!==state.version)return;state.connected=connected;if(connected)state.lastEvent=Date.now();updateStream();});
    if(version===state.version)state.unsubscribe=unsubscribe;else unsubscribe?.();
  }catch(error){if(document.getElementById('supervisor-map'))message(error.message);else login(error.message);}
}
function updateStream(){const element=document.getElementById('supervisor-stream');if(!element)return;
  const checked=state.sites.map(s=>expireScreening(s));if(checked.some((s,i)=>s!==state.sites[i])){state.sites=checked;applyFilters();}
  const selected=expireScreening(state.selectedSnapshot);if(selected!==state.selectedSnapshot&&String(selected?.id)===String(state.selected)){state.selectedSnapshot=selected;renderSelectedPreview(selected,state.selectedReports);const panel=document.querySelector('#supervisor-detail .crew-index-card');if(panel)panel.outerHTML=scorePanel(selected);}
  if(!navigator.onLine||Date.now()-state.lastEvent>config.api.heartbeatMs)state.connected=false;element.textContent=state.connected?(config.dataMode==='mock'?'Sample updates':'Live updates'):'Updates disconnected';}
async function refresh(incoming,affectedIds){
  const version=state.version,listVersion=++state.listVersion,button=document.getElementById('supervisor-refresh');if(!button)return;button.disabled=true;
  try{const sites=Array.isArray(incoming)?incoming:await services.listSites();if(version!==state.version||listVersion!==state.listVersion)return;if(!Array.isArray(sites))throw new Error('Invalid site list.');state.sites=sites;applyFilters();if(state.selected&&(!Array.isArray(affectedIds)||affectedIds.includes(state.selected)))await selectSite(state.selected,false);}catch(error){message(error.message);}finally{if(button.isConnected&&listVersion===state.listVersion)button.disabled=false;}
}
function applyFilters(reset=false){
  if(reset)state.page=0;state.filtered=rankSites(state.sites,filters());
  const high=state.sites.filter(s=>validScore(s.score)&&s.score>=7).length,unknown=state.sites.filter(s=>!validScore(s.score)).length;
  document.getElementById('supervisor-stats').innerHTML=`<div><span class="crew-stat-icon">${icon("site")}</span><strong>${state.sites.length.toLocaleString()}</strong><span>Available plants</span></div><div><span class="crew-stat-icon">${icon("shield")}</span><strong>${high.toLocaleString()}</strong><span>High risk · 7+</span></div><div><span class="crew-stat-icon">${icon("weather")}</span><strong>${unknown.toLocaleString()}</strong><span>Scores unavailable</span></div>`;
  document.getElementById('supervisor-updated').textContent='Site list fetched '+new Date().toLocaleTimeString()+'. Read each site’s score timestamp for freshness.';
  document.getElementById('supervisor-match-count').textContent=state.filtered.length.toLocaleString()+' matches';renderRanking();
  state.layer?.clearLayers();previewMarkers.clear();
  for(const s of state.filtered){
    if(!state.map||![s.latitude,s.longitude].every(Number.isFinite))continue;
    const color=!validScore(s.score)?'#829087':s.score>=7?'#f6997b':s.score>=4?'#e8bd6c':'#8dd1a2';
    const marker=L.marker([s.latitude,s.longitude],{
      title:s.name+' · '+s.state,alt:'Select '+s.name+' · '+s.state,
      icon:L.divIcon({className:'preview-plant-marker',iconSize:[28,28],iconAnchor:[14,14],html:'<span style="--plant-color:'+color+'"></span>'})
    }).on('click',()=>selectSite(s.id)).addTo(state.layer);
    const label=document.createElement('span');label.textContent=s.name+' · '+(validScore(s.score)?s.score.toFixed(1)+'/10':'Score unavailable');
    marker.bindTooltip(label,{direction:'top',offset:[0,-10]});previewMarkers.set(String(s.id),marker);
  }
  syncSelection();
  if(reset&&state.map){const points=state.filtered.filter(s=>[s.latitude,s.longitude].every(Number.isFinite)).map(s=>[s.latitude,s.longitude]);if(points.length)state.map.fitBounds(points,{padding:[25,25],maxZoom:11});}
}
function renderRanking(){
  const pages=Math.max(1,Math.ceil(state.filtered.length/30));state.page=Math.max(0,Math.min(state.page,pages-1));
  document.getElementById('supervisor-ranked-list').innerHTML=state.filtered.slice(state.page*30,state.page*30+30).map((s,i)=>`<button class="crew-ranked-site" data-risk="${validScore(s.score)?(s.score>=7?"high":s.score>=4?"elevated":"lower"):"unknown"}" data-select-site="${esc(s.id)}"><span class="crew-rank">${state.page*30+i+1}</span><span><strong>${esc(s.name)}</strong><small>${esc(s.state)} · ${riskLabel(s.score)} risk</small>${scoreBadgeHTML(s)}${scoreWindowHTML(s)}</span><b>${validScore(s.score)?s.score.toFixed(1):'—'}</b></button>`).join('')||'<p class="crew-empty">No sites match these filters.</p>';
  syncSelection();
  document.getElementById('supervisor-page').textContent=`${state.page+1} / ${pages}`;document.getElementById('supervisor-previous').disabled=state.page===0;document.getElementById('supervisor-next').disabled=state.page===pages-1;
}
async function selectSite(id,focus=true){
  const atlas=document.getElementById('supervisor-atlas-link');if(atlas)atlas.href=`crew-atlas.html?site=${encodeURIComponent(id)}${config.dataMode==='mock'?'&demo=1':''}`;
  state.selected=String(id);const version=++state.detailVersion,target=document.getElementById('supervisor-detail');
  syncSelection();
  const preview=document.getElementById('preview-selected');
  preview.setAttribute('aria-busy','true');
  if(focus){
    const item=state.sites.find(s=>String(s.id)===String(id));
    preview.innerHTML='<p class="crew-eyebrow">SELECTED POWER PLANT</p><h2>'+esc(item?.name||'Loading plant…')+'</h2><p class="crew-muted">Loading conditions and reports…</p>';
    target.innerHTML='<section class="crew-card">Loading selected site…</section>';
    const index=state.filtered.findIndex(s=>String(s.id)===String(id));
    if(index>=0){state.page=Math.floor(index/30);renderRanking();const row=document.querySelector('.crew-ranked-site[aria-pressed="true"]'),list=document.getElementById('supervisor-ranked-list');if(row)list.scrollTop+=row.getBoundingClientRect().top-list.getBoundingClientRect().top-list.clientHeight/2+row.clientHeight/2;}
  }
  try{
    const [p,reports]=await Promise.all([services.readSite(id),services.listReports(id)]);if(version!==state.detailVersion||!target.isConnected)return;
    if(String(p?.id)!==String(id))throw new Error('Selected site did not match the response.');
    renderSelectedPreview(p,reports);
    if(focus)(innerWidth<=760?preview:document.querySelector('.crew-dashboard-grid')).scrollIntoView({block:'start',behavior:reduceMotion?'instant':'smooth'});
    if(focus&&state.map&&[p.latitude,p.longitude].every(Number.isFinite))state.map.flyTo([p.latitude,p.longitude],Math.max(5,state.map.getZoom()),{animate:!reduceMotion,duration:.65});
    state.reportLayer?.clearLayers();state.photoURLs.forEach(URL.revokeObjectURL);state.photoURLs=[];
    for(const r of reports){
      if(!state.map||String(r.site_id)!==String(id)||![r.latitude,r.longitude].every(Number.isFinite))continue;
      const popup=document.createElement('div'),heading=document.createElement('strong'),description=document.createElement('p');heading.textContent=r.category;description.textContent=r.description;popup.append(heading,description);
      let photo=safeURL(r.photo_url);if(r.photo instanceof Blob){photo=URL.createObjectURL(r.photo);state.photoURLs.push(photo);}if(photo){const image=document.createElement('img');image.src=photo;image.alt='Crew-reported '+r.category;image.style.cssText='width:160px;max-height:140px;object-fit:cover';popup.append(image);}
      L.circleMarker([r.latitude,r.longitude],{radius:10,color:'#a44532',weight:3,fillColor:'#fff',fillOpacity:1}).bindPopup(popup).addTo(state.reportLayer);
    }
    target.innerHTML=`<div class="crew-section-heading"><div><p class="crew-eyebrow">SELECTED SITE</p><h2>${esc(p.name)} · ${esc(p.state)}</h2><small>Score updated: ${dateLabel(p.score_updated_at,p.timezone)}</small></div><a class="crew-button" href="crew.html?site=${encodeURIComponent(id)}${config.dataMode==='mock'?'&demo=1':''}">Open crew site ↗</a></div>${scorePanel(p)}${floodHTML(p)}${wildlifeHTML(p)}<section class="crew-card"><h2>Crew observations</h2>${reports.length?reports.filter(r=>String(r.site_id)===String(id)).slice(0,10).map(r=>`<article class="crew-factor"><strong>${esc(r.category)}</strong><p>${esc(r.description)}</p><small>${dateLabel(r.created_at)} · ${esc(r.status)} · ${r.demo?'Local sample':'Stored report'}</small></article>`).join(''):'<p>No crew reports have been returned for this site.</p>'}</section>`;
  }catch(error){if(version===state.detailVersion&&target.isConnected){preview.setAttribute('aria-busy','false');preview.innerHTML='<h2>Site data unavailable</h2><p>'+esc(error.message)+'</p>';}if(version===state.detailVersion&&target.isConnected)target.innerHTML=`<section class="crew-card"><h2>Selected site unavailable</h2><p>${esc(error.message)}</p><button class="crew-button secondary" data-select-site="${esc(id)}">Try again</button></section>`;}
}
document.addEventListener('click',event=>{const site=event.target.closest('[data-select-site]');if(site)selectSite(site.dataset.selectSite);});
setInterval(updateStream,1000);setInterval(()=>{if(document.getElementById('supervisor-map')&&!document.hidden)refresh();},30000);
window.addEventListener('offline',()=>{state.connected=false;updateStream();});window.addEventListener('online',refresh);window.addEventListener('pagehide',()=>{state.unsubscribe?.();state.map?.remove();});
window.addEventListener('pageshow',event=>{if(event.persisted)open();});
async function boot(){
  if(config.themeStylesheet){const link=document.createElement('link');link.rel='stylesheet';link.href=config.themeStylesheet;document.head.insertBefore(link,document.head.querySelector('link[href="crew.css"]'));}
  try{await initAuth();if(config.dataMode==='mock'&&new URLSearchParams(location.search).get('demo')==='1')enterDemo();if(await session()){await open();const id=new URLSearchParams(location.search).get('site');if(state.sites.some(s=>s.id===id))await selectSite(id,false);}else login();}catch(error){login(error.message);}
}
export const ready=boot();
