/* Why: Use scoped styles and reusable evidence-aware components so crew screens remain consistent without replacing the shared design system. */
import {hazards,validScore,riskLabel} from './crew-domain.js';
import {contributionLabel} from './crew-state.js';
import {icon} from './crew-visuals.js';
import {expireScreening,scoreBadgeText} from './crew-screening.js';
import {lightningWatch,warningsWatch} from './crew-watch.js';
import {displayHazards} from './crew-integration.js';
export const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
export function safeURL(value){try{const u=new URL(value);return ['https:','http:'].includes(u.protocol)?u.href:null;}catch{return null;}}
export function sourceLink(s){const url=safeURL(s?.source_url);return url?`<a href="${esc(url)}" target="_blank" rel="noopener noreferrer">${esc(s.source_name||'Source')} ↗</a>`:esc(s?.source_name||'Source unavailable');}
export function dateLabel(value,zone){if(!Number.isFinite(Date.parse(value)))return 'Unavailable';try{return new Date(value).toLocaleString(undefined,{timeZone:zone||undefined,dateStyle:'medium',timeStyle:'short'});}catch{return 'Timezone unavailable';}}
export function ageLabel(value,now=Date.now()){
  const observed=Date.parse(value);
  if(!Number.isFinite(observed))return 'Age unavailable';
  const elapsed=now-observed;
  if(elapsed < -60000)return 'Timestamp is in the future';
  if(elapsed < 60000)return 'Just now';
  const minutes=Math.floor(elapsed/60000);
  if(minutes<60)return `${minutes} min ago`;
  const hours=Math.floor(minutes/60);
  return hours<24?`${hours} h ago`:`${Math.floor(hours/24)} d ago`;
}
export function scoreHTML(score){
  const valid=validScore(score);
  // The ring depicts the supplied score; it never estimates missing data.
  const color=!valid?'#a0aaa2':score>=7?'#efab87':score>=4?'#e8bf72':'#9bdbac';
  return `<div class="crew-score-ring" style="--score-sweep:${valid?score*36:0}deg;--score-color:${color}"><strong class="crew-score">${valid?score.toFixed(1):'—'}<small>/ 10</small></strong></div>`;
}
export function hazardHTML(site,now=Date.now(),{includeAge=true}={}){
  // Re-evaluate live watch checks against the clock. A failed refresh must not
  // leave an old "clear" card visible after its 5/15-minute validity ends.
  const current=Object.hasOwn(site,'latest_weather')&&Array.isArray(site.active_alerts)
    ? displayHazards(site,site.active_alerts,now):site.hazards;
  return `<div class="crew-hazard-grid">${hazards.map(([key,name,help])=>{
    const h=current?.[key];
    const severity=['lower','elevated','high'].includes(h?.severity)?h.severity:null;
    // A measurement or missing feed is not itself a severity assessment.
    return `<article class="crew-hazard" data-hazard="${key}" data-severity="${severity||'unassessed'}"><div class="crew-hazard-top"><span class="crew-hazard-icon">${icon(key)}</span>${h?.is_replay?'<span class="crew-pill">REPLAY</span>':''}${severity?`<span class="crew-pill">${esc(severity)}</span>`:''}</div><h3>${name}</h3><strong>${esc(h?.reading??'Reading unavailable')}</strong><p>${esc(h?.advice||help)}</p><small>${sourceLink(h)}<br>${esc(h?.time_label||'Observed')}: ${dateLabel(h?.observed_at,site.timezone)} · <span data-observed-at="${esc(h?.observed_at||'')}">${includeAge?esc(ageLabel(h?.observed_at,now)):''}</span></small></article>`;
  }).join('')}</div>`;
}
export function refreshHazardAges(root,now=Date.now()){
  for(const element of root.querySelectorAll('[data-observed-at]')){
    const next=ageLabel(element.getAttribute('data-observed-at'),now);
    if(element.textContent!==next)element.textContent=next;
  }
}
export function scoreBadgeHTML(site){return `<span class="crew-score-badge" data-score-status="${esc(site?.score_status||'no_data')}">${esc(scoreBadgeText(site))}</span>`;}
export function topFactorsHTML(site){return Array.isArray(site?.top_factors)&&site.top_factors.length
  ? `<span class="crew-top-factors">${site.top_factors.slice(0,2).map(f=>`${esc(f.name)} ${esc(contributionLabel(f))}`).join(' · ')}</span>`
  : '<span class="crew-top-factors">Explanation available in site details</span>';}
export function scoreWindowHTML(site){return `<p class="crew-score-window">Forecast window: ${site.valid_from&&site.valid_until?`${dateLabel(site.valid_from,site.timezone)} – ${dateLabel(site.valid_until,site.timezone)}`:'Next 24 hours · exact window available in site details'}${site.timezone?' · '+esc(site.timezone):''}</p>`;}
export function watchPanel(site,now=Date.now()){
  const lightning=lightningWatch(site.lightning_status,site.active_alerts,now);
  const warnings=warningsWatch(site.warnings_status,site.environmental_events,now);
  const replay=site.active_alerts?.some(alert=>alert.hazard_type==='lightning'&&alert.level==='stop_work'&&alert.trigger?.is_replay===true);
  return `<section class="crew-card crew-watch" aria-label="Live safety watch status"><p class="crew-eyebrow">LIVE SAFETY CHECKS</p><h2>What we’re watching right now</h2>
    <div class="crew-watch-grid"><div data-watch-tone="${lightning.status}"><strong>${replay?'REPLAY · ':''}${esc(lightning.text)}</strong><p>${replay?'A recorded storm played back for the demo, not real lightning.':esc(site.lightning_status?.reason||'Watching for lightning within 10 miles of the site.')}</p><small>Checked ${dateLabel(site.lightning_status?.checked_at,site.timezone)} · ${sourceLink(site.lightning_status)}</small></div>
    <div data-watch-tone="${warnings.status}"><strong>${esc(warnings.text)}</strong><p>${warnings.status==='ok'?'Checked with the National Weather Service for this site.':'We couldn’t reach the National Weather Service, so we can’t confirm there are no warnings.'}</p><small>Checked ${dateLabel(site.warnings_status?.checked_at,site.timezone)} · ${sourceLink(site.warnings_status)}</small></div></div></section>`;
}
export function scoreWaterfall(site){
  if(!validScore(site?.score)||!Number.isFinite(site.baseline)||site.score_reconciles!==true||!site.factors?.length)return '';
  let running=site.baseline;
  const steps=[{name:'Starting point',start:0,end:running,value:running}];
  for(const factor of site.factors){const next=running+factor.contribution;
    steps.push({name:factor.name,start:running,end:next,value:factor.contribution});running=next;}
  steps.push({name:'Final score',start:0,end:site.score,value:site.score});
  const min=Math.min(0,...steps.flatMap(step=>[step.start,step.end]));
  const max=Math.max(10,...steps.flatMap(step=>[step.start,step.end]));
  const span=max-min||10;
  return `<div class="crew-waterfall" role="img" aria-label="Baseline and signed feature contributions reconcile to ${esc(site.score)} out of 10">
    ${steps.map((step,index)=>{const left=100*(Math.min(step.start,step.end)-min)/span;
      const width=Math.max(1,100*Math.abs(step.end-step.start)/span);
      const tone=index===0?'baseline':index===steps.length-1?'total':step.value<0?'down':'up';
      const amount=index===0||index===steps.length-1?step.value.toFixed(2):contributionLabel({contribution:step.value,unit:'score_points'});
      return `<div class="crew-waterfall-row" data-tone="${tone}"><span>${esc(step.name)}</span><div class="crew-waterfall-track"><i style="left:${left}%;width:${width}%"></i></div><b>${esc(amount)}</b></div>`;}).join('')}</div>`;
}
export function scorePanel(input){
  const site=expireScreening(input),modern=['research','validated_prototype'].includes(site.score_status),available=validScore(site.score);
  return `<section class="crew-card crew-index-card"><div class="crew-row"><div><p class="crew-eyebrow">HAZARD SCORE · ${riskLabel(site.score)}</p><h2>Understand your site’s score</h2>${scoreBadgeHTML(site)}</div>${scoreHTML(site.score)}</div>
    ${!available?`<p class="crew-muted"><strong>No data</strong> · ${esc(site.score_reason||'No score is available for this site right now.')}</p>`:''}
    ${scoreWindowHTML(site)}<p class="crew-muted">Updated: ${dateLabel(site.score_updated_at,site.timezone)}</p>
    <p class="crew-muted"><strong>What this score means:</strong> how likely the National Weather Service is to issue a warning or heat advisory for this site in the next 24 hours, from 0 (very unlikely) to 10 (very likely). It doesn’t predict injuries.</p>
    ${modern?'<p class="crew-muted"><strong>Early-stage estimate.</strong> A low score doesn’t mean it’s safe. Always follow active alerts.</p>':''}
    <details open><summary>What pushed the score?</summary>${scoreWaterfall(site)}${available&&site.factors?.length&&site.score_reconciles!==false?site.factors.map(f=>`<article class="crew-factor"><div class="crew-row"><strong>${esc(f.name)}</strong><b>${esc(contributionLabel(f))}</b></div>${f.reading?`<p>${esc(f.reading)}</p>`:''}<small>${f.feature?'Model explanation':sourceLink(f)} · ${dateLabel(f.scored_at||f.retrieved_at,site.timezone)}</small></article>`).join(''):'<p>We can’t show what pushed the score right now.</p>'}
    <p class="crew-muted">${available&&Number.isFinite(site.baseline)?`It starts from a typical score of ${esc(site.baseline.toFixed(2))}, and each factor adds or takes away points. `:''}A lower score never cancels a safety alert.</p>
    <h3>Model information</h3><p class="crew-muted">${esc(site.model?.name||'Model details unavailable')} · ${site.score_status==='research'?'Research prototype':site.score_status==='validated_prototype'?'Validated prototype':esc(scoreBadgeText(site))}${site.captured_at?'<br>Weather data from: '+dateLabel(site.captured_at,site.timezone):''}</p></details></section>`;
}
// Common names first; the scientific name stays for anyone looking it up.
const SPECIES={'Sistrurus miliarius':'Pygmy rattlesnake','Agkistrodon piscivorus':'Cottonmouth (water moccasin)',
  'Agkistrodon conanti':'Florida cottonmouth','Alligator mississippiensis':'American alligator','Agkistrodon contortrix':'Copperhead'};
export function speciesName(species){
  if(typeof species!=='string'||!species.trim())return 'Animal not identified';
  return SPECIES[species]?`${SPECIES[species]} (${species})`:species;
}
export function wildlifeHTML(site){
  const context=site.wildlife_context,rows=Array.isArray(context?.sightings)?context.sightings:[];
  return `<section class="crew-card crew-wildlife-evidence"><p class="crew-eyebrow">WILDLIFE NEAR THIS SITE</p><h2>Dangerous animals seen nearby</h2>
    <p class="crew-muted">Past sightings reported${Number.isFinite(context?.radius_km)?` within ${esc(context.radius_km)} km (${esc(Math.round(context.radius_km*0.621))} mi)`:' near the site'}. They show what lives in the area, not what’s here today. If you see one, report it.</p>
        ${rows.length?rows.slice(0,20).map(row=>`<article class="crew-factor"><strong>${esc(speciesName(row.species))}</strong><p>Seen ${esc(row.observed_calendar_date||row.event_date_raw||dateLabel(row.observed_at,'UTC'))}${Number.isFinite(row.distance_km)?' · '+esc(row.distance_km.toFixed(1))+' km ('+esc((row.distance_km*0.621).toFixed(1))+' mi) away':''}</p><small>${sourceLink({...row,source_name:'GBIF sighting record'})}${Number.isFinite(row.coordinate_uncertainty_m)?' · location accurate to about '+esc(row.coordinate_uncertainty_m>=1000?(row.coordinate_uncertainty_m/1000).toFixed(1)+' km':Math.round(row.coordinate_uncertainty_m)+' m'):''}</small></article>`).join(''):`<p>${context?.status==='no_records_in_sample'?'No past sightings recorded nearby. That doesn’t mean there are no animals.':'Sighting records aren’t available right now. That doesn’t mean there are no animals.'}</p>`}
    <p class="crew-muted">Not seeing an animal listed doesn’t mean there are none; records depend on where people report.${context?.context_built_at?' Updated '+dateLabel(context.context_built_at,site.timezone)+'.':''}</p></section>`;
}
export function floodHTML(site,now=Date.now()){
  const f=site.flood, zone=site.timezone;
  const checked=warningsWatch(site.warnings_status,site.environmental_events,now);
  const status=f?.status==='normal'&&checked.status!=='ok'?'unknown':f?.status;
  const distance=f?.river_distance_miles;
  const river=f?.river_status==='no_mapped_river'
    ? `No mapped river/stream within ${f.river_search_radius_km} km`
    : `${f?.river_name==='Unnamed river/stream'?'A small unnamed stream':f?.river_name||'Unavailable'}${Number.isFinite(distance)?' · approx. '+(distance<.1?'<0.1':distance.toFixed(1))+' mi':''}`;
  const period=f?.rainfall_period_start&&f?.rainfall_period_end
    ? `${dateLabel(f.rainfall_period_start,zone)} – ${dateLabel(f.rainfall_period_end,zone)} · ${zone||'Local time'}`
    : f?.window_label||'Unavailable';
  return `<section class="crew-card crew-flood" data-active="${status==='warning'}">
    <p class="crew-eyebrow">${icon("flood")} FLOOD WATCH</p>
    <h2>${esc(status==='warning'?'Flood-risk warning':status==='normal'?'No flood warning right now':'Can’t check flood warnings right now')}</h2>
    <p>${esc(status==='unknown'&&f?.status==='normal'?'The National Weather Service check is out of date, so we can’t confirm there’s no flood warning.':f?.message||'Waiting for flood and rainfall data.')}</p>
    <div class="crew-metrics"><span>River / stream proximity<strong>${esc(river)}</strong></span>
    <span>${esc(f?.rainfall_label||'Overnight rain')}<strong>${esc(f?.rainfall_reading??(Number.isFinite(f?.overnight_rain_mm)?`${f.overnight_rain_mm} mm`:'Unavailable'))}</strong></span>
    <span>Rainfall period<strong>${esc(period)}</strong></span></div>
    <small>Rainfall: ${sourceLink(f?.rainfall_source||f)} · Reading ${dateLabel(f?.observed_at,zone)}</small>
    <small>Warning feed: ${sourceLink(f?.warning_source)} · Checked ${dateLabel(f?.warning_checked_at,zone)}</small>
    ${f?.warning_valid_from?`<small>Warning period: ${dateLabel(f.warning_valid_from,zone)} – ${dateLabel(f.warning_valid_until,zone)} · ${esc(zone||'Local time')}</small>`:''}
    ${f?.river_source?.source_name?`<small>River mapping: ${sourceLink(f.river_source)} · Retrieved ${dateLabel(f.river_source.retrieved_at,zone)}</small><p class="crew-muted">${esc(f.river_source.limitations)}</p>`:''}
    ${f?.rule_description?`<small>Rule: ${esc(f.rule_description)}</small>`:''}
    </section>`;
}
export function makeMap(id,center,zoom=14){if(!window.L)return null;const map=L.map(id,{scrollWheelZoom:false,preferCanvas:true}).setView(center,zoom);const tiles=L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:19,attribution:'© OpenStreetMap contributors'}).addTo(map);tiles.on('tileerror',()=>{const status=document.getElementById(id+'-status');if(status)status.textContent='Basemap unavailable. Locations and coordinate controls remain available.';});const observer=new ResizeObserver(()=>map.invalidateSize());observer.observe(document.getElementById(id));map.on('unload',()=>observer.disconnect());return map;}
