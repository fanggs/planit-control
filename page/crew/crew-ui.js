/* Why: Use scoped styles and reusable evidence-aware components so crew screens remain consistent without replacing the shared design system. */
import {hazards,validScore,riskLabel} from './crew-domain.js';
import {contributionLabel} from './crew-state.js';
import {icon} from './crew-visuals.js';
import {expireScreening,scoreBadgeText} from './crew-screening.js';
import {lightningWatch,warningsWatch} from './crew-watch.js';
export const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
export function safeURL(value){try{const u=new URL(value);return ['https:','http:'].includes(u.protocol)?u.href:null;}catch{return null;}}
export function sourceLink(s){const url=safeURL(s?.source_url);return url?`<a href="${esc(url)}" target="_blank" rel="noopener noreferrer">${esc(s.source_name||'Source')} ↗</a>`:esc(s?.source_name||'Source unavailable');}
export function dateLabel(value,zone){if(!Number.isFinite(Date.parse(value)))return 'Unavailable';try{return new Date(value).toLocaleString(undefined,{timeZone:zone||undefined,dateStyle:'medium',timeStyle:'short'});}catch{return 'Timezone unavailable';}}
export function scoreHTML(score){
  const valid=validScore(score);
  // The ring depicts the supplied score; it never estimates missing data.
  const color=!valid?'#a0aaa2':score>=7?'#efab87':score>=4?'#e8bf72':'#9bdbac';
  return `<div class="crew-score-ring" style="--score-sweep:${valid?score*36:0}deg;--score-color:${color}"><strong class="crew-score">${valid?score.toFixed(1):'—'}<small>/ 10</small></strong></div>`;
}
export function hazardHTML(site){
  return `<div class="crew-hazard-grid">${hazards.map(([key,name,help])=>{
    const h=site.hazards?.[key];
    const severity=['lower','elevated','high'].includes(h?.severity)?h.severity:null;
    // A measurement or missing feed is not itself a severity assessment.
    return `<article class="crew-hazard" data-hazard="${key}" data-severity="${severity||'unassessed'}"><div class="crew-hazard-top"><span class="crew-hazard-icon">${icon(key)}</span>${h?.is_replay?'<span class="crew-pill">REPLAY</span>':''}${severity?`<span class="crew-pill">${esc(severity)}</span>`:''}</div><h3>${name}</h3><strong>${esc(h?.reading??'Reading unavailable')}</strong><p>${esc(h?.advice||help)}</p><small>${sourceLink(h)}<br>${esc(h?.time_label||'Observed')}: ${dateLabel(h?.observed_at)}</small></article>`;
  }).join('')}</div>`;
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
  return `<section class="crew-card crew-watch" aria-label="Live safety watch status"><p class="crew-eyebrow">INDEPENDENT SAFETY WATCHES</p><h2>Checked conditions</h2>
    <div class="crew-watch-grid"><div data-watch-tone="${lightning.status}"><strong>${replay?'REPLAY · ':''}${esc(lightning.text)}</strong><p>${replay?'Recorded storm replay for the demo, not a current lightning observation.':esc(site.lightning_status?.reason||'A score never clears a lightning hold.')}</p><small>Checked ${dateLabel(site.lightning_status?.checked_at,site.timezone)} · ${sourceLink(site.lightning_status)}</small></div>
    <div data-watch-tone="${warnings.status}"><strong>${esc(warnings.text)}</strong><p>${warnings.status==='ok'?'The NWS feed was checked recently. Other hazards may still exist.':'An empty warning list cannot confirm safety while the NWS check is unavailable.'}</p><small>Checked ${dateLabel(site.warnings_status?.checked_at,site.timezone)} · ${sourceLink(site.warnings_status)}</small></div></div></section>`;
}
export function scoreWaterfall(site){
  if(!validScore(site?.score)||!Number.isFinite(site.baseline)||site.score_reconciles!==true||!site.factors?.length)return '';
  let running=site.baseline;
  const steps=[{name:'Baseline',start:0,end:running,value:running}];
  for(const factor of site.factors){const next=running+factor.contribution;
    steps.push({name:factor.name,start:running,end:next,value:factor.contribution});running=next;}
  steps.push({name:'Final index',start:0,end:site.score,value:site.score});
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
  return `<section class="crew-card crew-index-card"><div class="crew-row"><div><p class="crew-eyebrow">HAZARD SCREENING INDEX · ${riskLabel(site.score)}</p><h2>Understand your site’s score</h2>${scoreBadgeHTML(site)}</div>${scoreHTML(site.score)}</div>
    ${!available?`<p class="crew-muted"><strong>No data</strong> · ${esc(site.score_reason||'No screening prediction was supplied.')} (${esc(site.score_status||'no_data')})</p>`:''}
    ${scoreWindowHTML(site)}<p class="crew-muted">Score calculated: ${dateLabel(site.score_updated_at,site.timezone)}</p>
    <p class="crew-muted">${esc(site.score_target||site.score_method||'Model details unavailable.')}</p>
    ${modern?'<p class="crew-muted">Prototype screening estimate only. It is not an established probability, an injury prediction, or an all-clear. Red-flag warnings describe fire weather; severe-storm warnings do not confirm measured lightning.</p>':''}
    <details open><summary>What pushed the score?</summary>${scoreWaterfall(site)}${available&&site.factors?.length&&site.score_reconciles!==false?site.factors.map(f=>`<article class="crew-factor"><div class="crew-row"><strong>${esc(f.name)}</strong><b>${esc(contributionLabel(f))}</b></div>${f.reading?`<p>${esc(f.reading)}</p>`:''}<small>${f.feature?'Model explanation':sourceLink(f)} · ${dateLabel(f.scored_at||f.retrieved_at,site.timezone)}</small></article>`).join(''):'<p>Factor contributions are unavailable. Missing values are not zero.</p>'}
    <p class="crew-muted">${available&&Number.isFinite(site.baseline)?`Baseline: ${esc(site.baseline.toFixed(2))}. `:''}Baseline plus signed contributions equals the index. Negative contributions lower the estimate; they never clear safety alerts.</p>
    <h3>Model information</h3><p class="crew-muted">${esc(site.model?.name||'Model details unavailable')} · ${site.score_status==='research'?'Research prototype':site.score_status==='validated_prototype'?'Validated prototype':esc(scoreBadgeText(site))}${site.captured_at?'<br>Inputs captured: '+dateLabel(site.captured_at,site.timezone):''}</p></details></section>`;
}
export function wildlifeHTML(site){
  const context=site.wildlife_context,rows=Array.isArray(context?.sightings)?context.sightings:[];
  return `<section class="crew-card crew-wildlife-evidence"><p class="crew-eyebrow">WILDLIFE EVIDENCE · SEPARATE FROM THE SCORE</p><h2>Recorded wildlife sightings</h2>
    <p class="crew-muted">Historical sightings provide context. They do not measure current presence, encounter probability, or contribute points to the index. Crew wildlife reports stay alongside this evidence.</p>
    ${context?`<p class="crew-muted">${Number.isFinite(context.radius_km)?'Search radius: '+esc(context.radius_km)+' km. ':''}${esc(context.radius_meaning||'Radius is not a safety boundary.')} · ${esc(({recorded_sightings:'Recorded sightings',no_records_in_sample:'No records in the sample',sample_no_evidence:'Sample · no historical feed'})[context.status]||'Evidence unavailable')}</p>`:''}
    ${rows.length?rows.slice(0,20).map(row=>`<article class="crew-factor"><strong>${esc(row.species||'Species unavailable')}</strong><p>Observed: ${esc(row.observed_calendar_date||row.event_date_raw||dateLabel(row.observed_at,'UTC'))}${Number.isFinite(row.distance_km)?' · '+esc(row.distance_km.toFixed(1))+' km from the site':''}</p><small>${sourceLink(row)}${Number.isFinite(row.coordinate_uncertainty_m)?' · Coordinate uncertainty: '+esc(row.coordinate_uncertainty_m)+' m':' · Coordinate uncertainty unavailable'}</small></article>`).join(''):`<p>${context?.status==='no_records_in_sample'?'No sightings in the supplied sample. This does not mean wildlife is absent.':'Wildlife evidence is unavailable. This does not mean wildlife is absent.'}</p>`}
    <p class="crew-muted">${esc(context?.limitations||'Sighting coverage is incomplete and depends on where people report observations.')}${context?.context_built_at?' Context prepared: '+dateLabel(context.context_built_at,site.timezone):''}</p></section>`;
}
export function floodHTML(site,now=Date.now()){const f=site.flood,checked=warningsWatch(site.warnings_status,site.environmental_events,now),status=f?.status==='normal'&&checked.status!=='ok'?'unknown':f?.status;return `<section class="crew-card crew-flood" data-active="${status==='warning'}"><p class="crew-eyebrow">${icon("flood")} FLOOD WATCH</p><h2>${esc(status==='warning'?'Flood-risk warning':status==='normal'?'No active NWS flood warning':'Flood status unavailable')}</h2><p>${esc(status==='unknown'&&f?.status==='normal'?'The NWS check is no longer fresh. Warning status is unavailable.':f?.message||'Waiting for river and overnight rainfall data.')}</p><div class="crew-metrics"><span>River proximity<strong>${esc(f?.river_name||'Unavailable')}${Number.isFinite(f?.river_distance_miles)?` · ${f.river_distance_miles} mi`:''}</strong></span><span>${esc(f?.rainfall_label||'Overnight rain')}<strong>${esc(f?.rainfall_reading??(Number.isFinite(f?.overnight_rain_mm)?`${f.overnight_rain_mm} mm`:'Unavailable'))}</strong></span><span>Observation window<strong>${esc(f?.window_label||'Unavailable')}</strong></span></div><small>${sourceLink(f)} · Updated ${dateLabel(f?.observed_at)}</small>${f?.rule_description?`<small>Rule: ${esc(f.rule_description)}</small>`:''}</section>`;}
export function makeMap(id,center,zoom=14){if(!window.L)return null;const map=L.map(id,{scrollWheelZoom:false,preferCanvas:true}).setView(center,zoom);const tiles=L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:19,attribution:'© OpenStreetMap contributors'}).addTo(map);tiles.on('tileerror',()=>{const status=document.getElementById(id+'-status');if(status)status.textContent='Basemap unavailable. Locations and coordinate controls remain available.';});const observer=new ResizeObserver(()=>map.invalidateSize());observer.observe(document.getElementById(id));map.on('unload',()=>observer.disconnect());return map;}
