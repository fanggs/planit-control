/* Frontend part 6
Commit: feat(crew): assemble crew workspace and supervisor preview
Why: Assemble previously tested modules into simple crew navigation and an isolated supervisor handoff, retaining alerts across views.
*/
import {config} from './crew-config.js';
import {userRoles} from './crew-routing.js';
import {HAZARD_LABELS} from './crew-integration.js';
import {initAuth,session,signIn,signOut,enterDemo,authConfigured} from './crew-auth.js';
import {services,demoAction} from './crew-services.js';
import {acceptAlert,alertView} from './crew-state.js';
import {acceptSnapshot,rankSites} from './crew-domain.js';
import {esc,sourceLink,dateLabel,hazardHTML,scorePanel,floodHTML} from './crew-ui.js';
import {icon,brandMark,contourArt} from './crew-visuals.js';
import {mountReports} from './crew-reports.js';
import {mountBriefing} from './crew-briefing.js';
const $=s=>document.querySelector(s);
const state={user:null,sites:[],site:null,view:'status',alert:null,connected:false,unsubscribe:null,loadVersion:0,clockOffset:0,lastEvent:0,viewCleanup:null,reports:null,viewVersion:0};
let messageTimer,searchTimer;
function message(text){$('#crew-message').textContent=text;$('#crew-message').classList.add('visible');clearTimeout(messageTimer);messageTimer=setTimeout(()=>$('#crew-message').classList.remove('visible'),7000);}
function cleanupView(){state.viewVersion++;state.viewCleanup?.();state.viewCleanup=null;state.reports=null;}
function loginScreen(error=''){
  cleanupView();
  const loginURL=new URL('login.html',location.href);loginURL.searchParams.set('start','1');
  const siteId=new URLSearchParams(location.search).get('site');if(siteId)loginURL.searchParams.set('site',siteId);
  $('#crew-root').innerHTML=`<main class="crew-login" id="crew-main">${brandMark()}<p class="crew-eyebrow">PLANIT CONTROL / CREW ACCESS</p><h1>A clearer picture.<br>A safer shift.</h1><p>Sign in to see your site, share observations, and plan your next shift.</p>${error?`<p class="crew-error" role="alert">${esc(error)}</p>`:''}<a class="crew-button" href="${esc(loginURL.href)}">Log in with Auth0 ↗</a><a href="index.html">← Back to PlanIT</a>${config.dataMode==='mock'?'<button class="crew-button secondary" data-action="preview">Open sample crew preview</button><small>Sample conditions. No Auth0 sign-in or live alerts.</small>':''}</main>`;
}
function unavailable(error){$('#crew-root').innerHTML=`<main class="crew-login" id="crew-main"><h1>Site data is unavailable.</h1><p>${esc(error.message)}</p><button class="crew-button" data-action="reload">Try again</button><button class="crew-button secondary" data-action="logout">Sign out</button></main>`;}
async function openWorkspace(){
  state.user=await session();if(!state.user)return loginScreen();
  if(!state.user.demo&&!userRoles(state.user,config.authRoleClaim).length)return loginScreen('Your account needs a crew or supervisor role. Ask your administrator for access.');
  $('#crew-root').innerHTML='<main class="crew-login" id="crew-main"><h1>Loading your sites…</h1></main>';
  try{state.sites=await services.listSites();if(!Array.isArray(state.sites)||!state.sites.length)throw new Error('No assigned sites returned. Ask your supervisor to check access.');
    const requested=new URLSearchParams(location.search).get('site'),preferred=state.sites.find(s=>String(s.id)===(requested||'621'))||state.sites[0];
    await loadSite(String(preferred.id));
  }catch(error){unavailable(error);}
}
async function loadSite(id){
  const version=++state.loadVersion;state.unsubscribe?.();state.unsubscribe=null;state.alert=null;state.connected=false;state.site=null;cleanupView();
  try{
    const site=await services.readSite(id);if(version!==state.loadVersion)return;
    if(!acceptSnapshot(null,site,id))throw new Error('Site response must match its ID and include a non-negative integer revision.');
    state.site=site;alignClock(site.server_time);state.alert=acceptAlert(null,site.alert,id);
    const url=new URL(location.href);url.searchParams.set('site',id);history.replaceState({},'',url);renderWorkspace();
    const unsubscribe=await services.subscribeEvents(id,event=>{
      if(version!==state.loadVersion)return;
      if(event.type!=='heartbeat'&&String(event.site_id??event.site?.id)!==String(id))return;
      state.lastEvent=Date.now();alignClock(event.server_time);
      if(event.type==='alert'){state.alert=acceptAlert(state.alert,event.alert,id);updateAlert();refreshSite(version);}
      if(event.type==='site')refreshSite(version,event.site);
      if(event.type==='report'){state.reports?.refresh();message(config.dataMode==='mock'?'Sample report updated on this browser.':'A site report was updated.');}
      if(event.type==='briefing')message('Briefing information changed. Open Briefing to refresh it.');
    },connected=>{if(version!==state.loadVersion)return;const was=state.connected;state.connected=Boolean(connected)&&navigator.onLine;if(connected)state.lastEvent=Date.now();updateAlert();if(state.connected&&!was){refreshSite(version);state.reports?.refresh();}});
    if(version!==state.loadVersion){if(typeof unsubscribe==='function')unsubscribe();return;}
    if(typeof unsubscribe==='function')state.unsubscribe=unsubscribe;
  }catch(error){if(version!==state.loadVersion)return;if(state.site){state.connected=false;updateAlert();message(error.message);}else unavailable(error);}
}
function alignClock(time){if(Number.isFinite(Date.parse(time)))state.clockOffset=Date.parse(time)-Date.now();}
async function refreshSite(version=state.loadVersion,incoming){
  const id=state.site?.id;if(!id)return;
  try{
    const next=incoming||await services.readSite(id);if(version!==state.loadVersion)return;
    if(String(next?.id)!==String(id))throw new Error('Site update did not match the selected site.');
    const accepted=acceptSnapshot(state.site,next,id);if(!accepted)throw new Error('Invalid site update received.');
    alignClock(next.server_time);state.alert=acceptAlert(state.alert,next.alert,id);
    if(accepted!==state.site){state.site=accepted;if(state.view==='status')renderStatus();}
    updateAlert();
  }catch(error){if(version===state.loadVersion)message('Site refresh failed: '+error.message);}
}
function renderWorkspace(){
  const p=state.site;cleanupView();
  $('#crew-root').innerHTML=`<header class="crew-header"><a href="index.html" class="crew-brand">${brandMark()}PlanIT <span>Control</span></a><div class="crew-header-actions">${state.user?.demo||userRoles(state.user,config.authRoleClaim).includes('supervisor')?`<a class="crew-link" href="crew-supervisor.html${state.user?.demo?'?demo=1':''}">Supervisor workspace ↗</a>`:''}<a class="crew-link" href="crew-atlas.html?site=${esc(p.id)}&amp;return_site=${esc(p.id)}">Site map ↗</a><button class="crew-link" data-action="logout">Sign out</button></div></header><main id="crew-main" class="crew-main">
    ${config.dataMode==='mock'?'<p class="crew-demo"><strong>SAMPLE DATA</strong> · Real plant locations. Synthetic conditions and scores. Reports stay on this browser; no live alerts or delivery.</p>':p.sample?'<p class="crew-demo"><strong>SAMPLE API DATA</strong> · Placeholder plants and fixed sample readings. This is not a live safety assessment.</p>':''}
    <section class="crew-section-heading crew-site-hero"><div class="crew-hero-copy"><p class="crew-eyebrow">YOUR JOB SITE</p><h1 id="crew-site-name">${esc(p.name)}</h1><p class="crew-muted">${esc(p.state)} · Plant ${esc(p.id)} · ${state.sites.length.toLocaleString()} available sites</p><p class="crew-muted"><a href="crew-atlas.html?site=${esc(p.id)}&amp;return_site=${esc(p.id)}">Open site map ↗</a></p></div><div class="crew-hero-end">${contourArt()}<button class="crew-button secondary" data-action="change-site">Change site ${icon("switch")}</button></div></section>
    <section id="crew-site-picker" class="crew-card" hidden><div class="crew-coordinate-row"><div><label for="crew-site-query">Search plants</label><input id="crew-site-query" type="search" placeholder="Plant, operator, state or ID" autocomplete="off"></div><div><label for="crew-site-region">State / territory</label><select id="crew-site-region"><option value="">All states & territories</option>${[...new Set(state.sites.map(s=>s.state))].sort().map(s=>`<option>${esc(s)}</option>`).join('')}</select></div></div><p id="crew-search-count" class="crew-muted" role="status"></p><div id="crew-site-results" class="crew-site-results"></div></section>
    <nav class="crew-nav" aria-label="Crew screens">${[['status','Site & alerts'],['reports','Crew reports'],['briefing','Briefing']].map(([view,label])=>`<button data-view="${view}" aria-pressed="${state.view===view}">${icon({status:"site",reports:"report",briefing:"briefing"}[view])}<span>${label}</span></button>`).join('')}</nav>
    <div class="crew-alert" id="crew-alert"><div class="crew-row"><h2 id="crew-alert-title" aria-live="assertive" aria-atomic="true">Checking alerts…</h2><strong id="crew-countdown" aria-label="Time remaining in lightning hold"></strong></div><p id="crew-alert-detail"></p><small id="crew-stream"></small></div><div id="crew-flood-banner"></div><section id="crew-view"></section>
    <p class="crew-footer">${config.dataMode==='mock'?`Plant reference: ${sourceLink(p.provenance)}. 60 monitored plants from Sid’s EIA-860M roster. <a href="crew-data/atlas-source.json" target="_blank" rel="noopener">Coverage & provenance ↗</a>`:`Site reference: ${sourceLink(p.provenance)}. Read each condition’s source and timestamp above.`}</p></main>`;
  $('#crew-site-query').addEventListener('input',()=>{clearTimeout(searchTimer);searchTimer=setTimeout(searchSites,120);});$('#crew-site-region').addEventListener('change',searchSites);searchSites();renderView();updateAlert();
}
function searchSites(){
  const rows=rankSites(state.sites,{query:$('#crew-site-query').value,region:$('#crew-site-region').value});
  $('#crew-search-count').textContent=`${rows.length.toLocaleString()} matches${rows.length>40?' · first 40 shown; refine your search':''}`;
  $('#crew-site-results').innerHTML=rows.slice(0,40).map(s=>`<button class="crew-site-result" data-site="${esc(s.id)}"><strong>${esc(s.name)}</strong><small>${esc(s.state)} · Plant ${esc(s.id)}</small></button>`).join('')||'<p>No matching sites.</p>';
}
function renderView(){
  cleanupView();document.querySelectorAll('[data-view]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.view===state.view)));
  if(state.view==='reports'){state.reports=mountReports($('#crew-view'),state.site,message);state.viewCleanup=()=>state.reports?.destroy();}
  else if(state.view==='briefing')state.viewCleanup=mountBriefing($('#crew-view'),state.site,message);
  else renderStatus();
}
function renderStatus(){
  if(state.view!=='status'||!$('#crew-view'))return;const p=state.site;
  const open=$('#crew-score-panel details')?.open;
  $('#crew-view').innerHTML=`<div class="crew-section-heading"><div><p class="crew-eyebrow">ONE RISK PICTURE</p><h2>Conditions around your site</h2><p class="crew-muted">Readings carry their observation time and source. Missing data stays unavailable.</p></div><button class="crew-link" data-action="refresh">Refresh</button></div>${hazardHTML(p)}<div id="crew-score-panel">${scorePanel(p)}</div>${floodHTML(p)}
    <div class="crew-quick-actions"><button class="crew-button" data-view="reports">${icon("report")} Report a hazard</button><button class="crew-button secondary" data-view="briefing">${icon("briefing")} Read tomorrow’s briefing</button></div>
    ${config.dataMode==='mock'?`<details class="crew-card crew-demo-controls"><summary>Demo scenarios</summary><p>These controls simulate backend events. They never report actual conditions.</p><label for="crew-strike-distance">Sample strike distance (miles)</label><input id="crew-strike-distance" type="number" min="0" max="100" step="0.1" value="4.2"><div class="crew-quick-actions"><button class="crew-button secondary" data-action="strike">Trigger / reset lightning hold</button><button class="crew-button secondary" data-action="clear">Simulate server clear</button><button class="crew-button secondary" data-action="flood">Trigger flood warning</button><button class="crew-button secondary" data-action="flood-off">Remove sample flood warning</button></div><small>Strikes beyond 10 miles do not trigger a hold. Timer expiry alone never clears it. Try Grand Gulf (plant 6072) for the Mississippi River scenario.</small></details>`:''}`;
  if(open)$('#crew-score-panel details').open=true;updateAlert();
}
function updateAlert(){
  if(!$('#crew-alert'))return;
  if(!navigator.onLine||Date.now()-state.lastEvent>config.api.heartbeatMs)state.connected=false;
  const view=alertView(state.alert,state.connected,Date.now()+state.clockOffset);
  $('#crew-alert').dataset.tone=view.tone;if($('#crew-alert-title').textContent!==view.title)$('#crew-alert-title').textContent=view.title;if($('#crew-alert-detail').textContent!==view.detail)$('#crew-alert-detail').textContent=view.detail;
  $('#crew-countdown').textContent=view.seconds===null?'':`${String(Math.floor(view.seconds/60)).padStart(2,'0')}:${String(view.seconds%60).padStart(2,'0')}`;
  $('#crew-stream').textContent=(state.connected?(config.dataMode==='mock'?'Sample stream connected':'Notifications connected · check reading timestamps'):'Updates disconnected · confirm with your supervisor')+(state.alert?.last_strike_at?' · Last strike: '+dateLabel(state.alert.last_strike_at):'');
  const flood=state.site?.flood;
  const banners=[];
  if(flood?.status==='warning')banners.push(`<p class="crew-flood-notice" role="alert"><strong>Flood-risk warning</strong> · ${esc(flood.message)}</p>`);
  for(const warning of state.site?.warnings||[]){if(warning.hazard_type==='flooding')continue;banners.push(`<p class="crew-flood-notice" role="alert"><strong>${esc(HAZARD_LABELS[warning.hazard_type]||'Site')} warning</strong> · ${esc(warning.message)}</p>`);}
  const bannerHTML=banners.join('');if($('#crew-flood-banner').innerHTML!==bannerHTML)$('#crew-flood-banner').innerHTML=bannerHTML;
}
document.addEventListener('click',async event=>{
  const view=event.target.closest('[data-view]');if(view&&state.site){state.view=view.dataset.view;renderView();return;}
  const chosen=event.target.closest('[data-site]');if(chosen){await loadSite(chosen.dataset.site);return;}
  const action=event.target.closest('[data-action]')?.dataset.action;
  try{
    if(action==='preview'){enterDemo();await openWorkspace();}
    if(action==='sign-in')await signIn();
    if(action==='logout'){state.loadVersion++;state.unsubscribe?.();state.unsubscribe=null;state.user=null;cleanupView();await signOut();loginScreen();}
    if(action==='reload')await openWorkspace();
    if(action==='change-site'){$('#crew-site-picker').hidden=!$('#crew-site-picker').hidden;if(!$('#crew-site-picker').hidden)$('#crew-site-query').focus();}
    if(action==='refresh')await refreshSite();
    if(action==='strike'){const distance=Number($('#crew-strike-distance').value);if(!Number.isFinite(distance)||distance<0||distance>100)throw new Error('Enter a distance from 0 to 100 miles.');const result=await demoAction('strike',state.site.id,distance);message(result.triggered?'Sample strike triggered a 30-minute hold.':'Sample strike is beyond 10 miles. No hold was triggered.');}
    if(action==='clear')await demoAction('clear',state.site.id);
    if(action==='flood'||action==='flood-off')await demoAction('flood',state.site.id,action==='flood');
  }catch(error){message(error.message);}
});
setInterval(updateAlert,1000);document.addEventListener('visibilitychange',()=>{updateAlert();if(!document.hidden&&state.site)refreshSite();});
setInterval(()=>{if(state.site&&state.user&&!document.hidden)refreshSite();},30000);
window.addEventListener('offline',()=>{state.connected=false;updateAlert();});window.addEventListener('online',()=>{if(state.user&&state.site)loadSite(String(state.site.id));});
window.addEventListener('pagehide',()=>{state.unsubscribe?.();cleanupView();});
window.addEventListener('pageshow',event=>{if(event.persisted&&state.user&&state.site)loadSite(String(state.site.id));});
async function boot(){
  if(config.themeStylesheet){const link=document.createElement('link');link.rel='stylesheet';link.href=config.themeStylesheet;link.onerror=()=>message('Shared theme unavailable. Using crew-scoped fallback styles.');document.head.insertBefore(link,document.head.querySelector('link[href="crew.css"]'));}
  try{await initAuth();if(config.dataMode==='mock'&&new URLSearchParams(location.search).get('demo')==='1')enterDemo();if(await session())await openWorkspace();else loginScreen();}catch(error){loginScreen(error.message);}
}
boot();
