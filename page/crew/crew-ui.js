/* Why: Use scoped styles and reusable evidence-aware components so crew screens remain consistent without replacing the shared design system. */
import {hazards,validScore,riskLabel} from './crew-domain.js';
import {contributionLabel} from './crew-state.js';
import {icon} from './crew-visuals.js';
import {expireScreening,scoreBadgeText} from './crew-screening.js';
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
    const severity=['lower','elevated','high'].includes(h?.severity)?h.severity:'unknown';
    // Category tints/icons identify the factor; the text badge communicates risk.
    return `<article class="crew-hazard" data-hazard="${key}" data-severity="${severity}"><div class="crew-hazard-top"><span class="crew-hazard-icon">${icon(key)}</span><span class="crew-pill">${esc(h?.severity||'Unavailable')}</span></div><h3>${name}</h3><strong>${esc(h?.reading??'Reading unavailable')}</strong><p>${esc(h?.advice||help)}</p><small>${sourceLink(h)}<br>Observed: ${dateLabel(h?.observed_at)}</small></article>`;
  }).join('')}</div>`;
}
export function scoreBadgeHTML(site){return `<span class="crew-score-badge" data-score-status="${esc(site?.score_status||'no_data')}">${esc(scoreBadgeText(site))}</span>`;}
export function scoreWindowHTML(site){return `<p class="crew-score-window">Forecast window: ${site.valid_from&&site.valid_until?`${dateLabel(site.valid_from,site.timezone)} – ${dateLabel(site.valid_until,site.timezone)}`:'not supplied'}${site.timezone?' · '+esc(site.timezone):''}</p>`;}
export function scorePanel(input){
  const site=expireScreening(input),modern=['research','validated_prototype'].includes(site.score_status),available=validScore(site.score);
  return `<section class="crew-card crew-index-card"><div class="crew-row"><div><p class="crew-eyebrow">HAZARD SCREENING INDEX · ${riskLabel(site.score)}</p><h2>Understand your site’s score</h2>${scoreBadgeHTML(site)}</div>${scoreHTML(site.score)}</div>
    ${!available?`<p class="crew-muted"><strong>No data</strong> · ${esc(site.score_reason||'No screening prediction was supplied.')} (${esc(site.score_status||'no_data')})</p>`:''}
    ${scoreWindowHTML(site)}<p class="crew-muted">Score calculated: ${dateLabel(site.score_updated_at,site.timezone)}</p>
    <p class="crew-muted">${esc(site.score_target||site.score_method||'Model details unavailable.')}</p>
    ${modern?'<p class="crew-muted">Prototype screening estimate only. It is not an established probability, an injury prediction, or an all-clear. Red-flag warnings describe fire weather; severe-storm warnings do not confirm measured lightning.</p>':''}
    <details><summary>What pushed the score?</summary>${available&&site.factors?.length&&site.score_reconciles!==false?site.factors.map(f=>`<article class="crew-factor"><div class="crew-row"><strong>${esc(f.name)}</strong><b>${esc(contributionLabel(f))}</b></div>${f.reading?`<p>${esc(f.reading)}</p>`:''}<small>${f.feature?'Model explanation':sourceLink(f)} · ${dateLabel(f.scored_at||f.retrieved_at,site.timezone)}</small></article>`).join(''):'<p>Factor contributions are unavailable. Missing values are not zero.</p>'}
    <p class="crew-muted">${available&&Number.isFinite(site.baseline)?`Baseline: ${esc(site.baseline)}. `:''}Baseline plus signed contributions equals the index. Negative contributions lower the estimate; they never clear safety alerts.</p>
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
export function floodHTML(site){const f=site.flood;return `<section class="crew-card crew-flood" data-active="${f?.status==='warning'}"><p class="crew-eyebrow">${icon("flood")} FLOOD WATCH</p><h2>${esc(f?.status==='warning'?'Flood-risk warning':f?.status==='normal'?'No flood warning reported':'Flood status unavailable')}</h2><p>${esc(f?.message||'Waiting for river and overnight rainfall data.')}</p><div class="crew-metrics"><span>River proximity<strong>${esc(f?.river_name||'Unavailable')}${Number.isFinite(f?.river_distance_miles)?` · ${f.river_distance_miles} mi`:''}</strong></span><span>${esc(f?.rainfall_label||'Overnight rain')}<strong>${esc(f?.rainfall_reading??(Number.isFinite(f?.overnight_rain_mm)?`${f.overnight_rain_mm} mm`:'Unavailable'))}</strong></span><span>Observation window<strong>${esc(f?.window_label||'Unavailable')}</strong></span></div><small>${sourceLink(f)} · Updated ${dateLabel(f?.observed_at)}</small>${f?.rule_description?`<small>Rule: ${esc(f.rule_description)}</small>`:''}</section>`;}
export function makeMap(id,center,zoom=14){if(!window.L)return null;const map=L.map(id,{scrollWheelZoom:false,preferCanvas:true}).setView(center,zoom);const tiles=L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:19,attribution:'© OpenStreetMap contributors'}).addTo(map);tiles.on('tileerror',()=>{const status=document.getElementById(id+'-status');if(status)status.textContent='Basemap unavailable. Locations and coordinate controls remain available.';});const observer=new ResizeObserver(()=>map.invalidateSize());observer.observe(document.getElementById(id));map.on('unload',()=>observer.disconnect());return map;}
