/* API fields follow api/CONTRACT.md v1.2, with an explicit legacy API bridge.
   Revisions below order client requests; they are not backend data or timestamps. */
import {screeningDetail,screeningSummary,screeningFactors} from './crew-screening.js';
export const HAZARD_LABELS = Object.freeze({
  heat: 'Extreme heat', lightning: 'Lightning', flooding: 'Flooding',
  wildfire: 'Wildfire', soil_saturation: 'Soil saturation', wildlife: 'Wildlife', other: 'Other'
});
const displayKeys = {heat: 'heat', lightning: 'lightning', flooding: 'flood', wildfire: 'wildfire', soil_saturation: 'soil', wildlife: 'wildlife'};
const finite = value => typeof value === 'number' && Number.isFinite(value);
const scoreValue = value => finite(value) && value >= 0 && value <= 10 ? value : null;
const time = value => typeof value === 'string' && Number.isFinite(Date.parse(value)) ? value : null;
const source = value => ({source_name: value?.source_name, source_url: value?.source_url ?? null, retrieved_at: value?.retrieved_at ?? null});

export function contractSiteId(value) {
  const text = String(value ?? '');
  if (!/^[1-9]\d*$/.test(text) || !Number.isSafeInteger(Number(text))) throw new Error('A positive integer site_id is required.');
  return Number(text);
}
function wireSiteId(value) {
  if (!Number.isSafeInteger(value) || value <= 0) throw new Error('The API must return an integer site_id.');
  return String(value);
}
function factors(rows) {
  return (Array.isArray(rows) ? rows : []).map(factor => {
    if (factor?.feature != null) return screeningFactors([factor])[0];
    if (!Object.hasOwn(HAZARD_LABELS, factor.hazard_type) || !finite(factor.contribution)) throw new Error('Invalid score factor from the API.');
    return {...factor, name: HAZARD_LABELS[factor.hazard_type], unit: 'score_points'};
  });
}
export function mapSiteSummary(raw, {now = Date.now()} = {}) {
  const modern = raw.score_status != null;
  const screening = modern ? screeningSummary(raw,now) : {
    score:scoreValue(raw.score),score_updated_at:time(raw.scored_at),score_status:'legacy',
    score_reason:'The API is still using the earlier score format.',valid_from:null,valid_until:null,captured_at:null
  };
  let topFactors=null;
  try{topFactors=raw.top_factors==null||screening.score===null?null:factors(raw.top_factors);}catch{topFactors=null;}
  return {...raw, id: wireSiteId(raw.site_id), operator: raw.utility,
    ...screening,top_factors:topFactors,provenance:source(raw)};
}
export function mapReport(raw) {
  const site_id = wireSiteId(raw.site_id);
  if (!raw.id || !Object.hasOwn(HAZARD_LABELS, raw.hazard_type) || !['open', 'resolved'].includes(raw.status)) throw new Error('Invalid report returned by the API.');
  return {...raw, id: String(raw.id), site_id, category: HAZARD_LABELS[raw.hazard_type],
    latitude: finite(raw.latitude) ? raw.latitude : null, longitude: finite(raw.longitude) ? raw.longitude : null,
    photo_key: raw.photo_key ?? null, photo_url: undefined, shared: undefined};
}
function format(value, unit) { return finite(value) ? `${value} ${unit}` : 'No data'; }
function eventSeverity(value) {
  return ({minor: 'lower', moderate: 'elevated', severe: 'high', extreme: 'high', low: 'lower', medium: 'elevated', high: 'high'})[value] || 'unknown';
}
function displayHazards(raw, activeAlerts) {
  const weather = raw.latest_weather;
  const observed_at = time(weather?.observed_at);
  const hazards = Object.fromEntries(['weather', 'heat', 'lightning', 'flood', 'wildfire', 'soil', 'wildlife'].map(key => [key, {
    reading: 'No data', severity: 'unknown', observed_at: null, source_name: undefined, source_url: null
  }]));
  if (weather) {
    const common = {...source(weather), observed_at};
    hazards.weather = {...hazards.weather, ...common, reading: `Temperature ${format(weather.temperature_f, '°F')} · wind ${format(weather.wind_mph, 'mph')} · rain ${format(weather.precip_24h_in, 'in / 24 h')}`};
    hazards.heat = {...hazards.heat, ...common, reading: `Heat index ${format(weather.heat_index_f, '°F')}`};
    hazards.soil = {...hazards.soil, ...common, reading: `Soil moisture ${format(weather.soil_moisture, 'm³/m³')}`};
  }
  for (const event of raw.environmental_events || []) {
    const key = displayKeys[event.hazard_type];
    if (key) hazards[key] = {...hazards[key], ...source(event), reading: event.title || 'Environmental warning', severity: eventSeverity(event.severity), observed_at: null};
  }
  for (const alert of activeAlerts) {
    const key = displayKeys[alert.hazard_type];
    if (!key) continue;
    const report = (raw.recent_reports || []).find(r => String(r.id) === String(alert.trigger?.report_id));
    hazards[key] = {...hazards[key], reading: alert.message,
      severity: alert.level === 'stop_work' || report?.severity === 'high' ? 'high' : 'elevated',
      observed_at: time(alert.last_trigger_at || alert.started_at), source_name: report ? 'Crew report' : 'Site alert'};
  }
  return hazards;
}

export function createContractMapper({now = () => Date.now()} = {}) {
  let sequence = 0;
  const snapshots = new Map();
  const nextRevision = () => ++sequence;
  function site(raw, revision = nextRevision(), {clearedAlertId} = {}) {
    const id = wireSiteId(raw.site_id), previous = snapshots.get(id);
    if (previous && revision <= previous.revision) return previous;
    if (!Array.isArray(raw.active_alerts)) throw new Error('Site details must include active_alerts.');
    const active = raw.active_alerts.filter(alert => String(alert.site_id) === id);
    const holds = active.filter(alert => alert.hazard_type === 'lightning' && alert.level === 'stop_work');
    // An invalid deadline must not silently turn an existing stop-work instruction into clear.
    if (holds.some(alert => !time(alert.clear_at))) throw new Error('A lightning stop-work alert has no valid clear_at.');
    const hold = holds.sort((a, b) => Date.parse(b.clear_at) - Date.parse(a.clear_at))[0];
    const confirmedClear = clearedAlertId != null && previous?.alert?.contract_id != null && String(clearedAlertId) === String(previous.alert.contract_id);
    const alert = {site_id: id, version: revision, status: hold ? 'hold' : confirmedClear || previous?.alert?.status === 'cleared' ? 'cleared' : 'unknown',
      contract_id: hold?.id ?? previous?.alert?.contract_id ?? null,
      all_clear_at: hold?.clear_at ?? null, last_strike_at: hold?.last_trigger_at ?? null,
      distance_miles: finite(hold?.trigger?.distance_mi) ? hold.trigger.distance_mi : null};
    // A stale same-alert response must not shorten a hold that already incorporated a newer strike.
    if (hold && previous?.alert?.status === 'hold' && String(hold.id) === String(previous.alert.contract_id)
      && Date.parse(hold.clear_at) < Date.parse(previous.alert.all_clear_at)) Object.assign(alert, previous.alert, {version: revision});
    const modern = Object.hasOwn(raw,'screening');
    const model = modern ? null : raw.score;
    if (model && wireSiteId(model.site_id) !== id) throw new Error('The score belongs to a different site.');
    const mappedFactors = factors(model?.factors);
    const baseline = finite(model?.baseline) ? model.baseline : null;
    const value = scoreValue(model?.score);
    const reconciles = value !== null && baseline !== null && Math.abs(baseline + mappedFactors.reduce((sum, f) => sum + f.contribution, 0) - value) <= .050000001;
    const floodAlert = active.find(a => a.hazard_type === 'flooding');
    const floodEvent = (raw.environmental_events || []).find(e => e.hazard_type === 'flooding');
    const screening = modern ? screeningDetail(raw.screening,now()) : null;
    const mapped = {...mapSiteSummary({...raw, score: value, scored_at: model?.scored_at},{now:now()}),
      revision, server_time: null, timezone: raw.timezone ?? null, sample: model?.model_version === 'sample',
      score_method: model?.model_version === 'sample' ? 'Sample API score. Not a live trained-model result.'
        : model ? `${String(model.model_version || 'Model version unavailable')} · ${model.horizon_hours ?? 'Unknown'}-hour outlook` : 'Score unavailable.',
      baseline, factors: mappedFactors.map(f => ({...f, scored_at: time(model?.scored_at)})),
      score_reconciles: reconciles, horizon_hours: model?.horizon_hours ?? null,
      model: {version: model?.model_version},
      ...(modern?{...screening,sample:false,score_method:'Prototype screening index for NWS warnings or heat advisories in the next 24 hours. Not an injury probability.',
        model:{name:'Forecast screening model',version:raw.screening?.artifact_sha256},
        factors:screening.factors?.map(f=>({...f,scored_at:screening.score_updated_at}))||[],horizon_hours:24}:{}),
      wildlife_context:mapWildlife(raw.wildlife_context,id),alert, active_alerts: active,
      warnings: active.filter(a => a.level === 'warning'), hazards: displayHazards(raw, active),
      flood: {...source(floodEvent), status: floodAlert || floodEvent ? 'warning' : 'unknown',
        message: floodAlert?.message || floodEvent?.title || 'Flood warning status unavailable. No hydrologic assessment was supplied.',
        river_name: null, river_distance_miles: null, overnight_rain_mm: null,
        rainfall_label: 'Rain · rolling 24 hours', rainfall_reading: finite(raw.latest_weather?.precip_24h_in) ? `${raw.latest_weather.precip_24h_in} in` : 'No data',
        window_label: floodEvent ? `${floodEvent.starts_at} — ${floodEvent.ends_at || 'End unavailable'}` : 'Unavailable', observed_at: null},
      recent_reports: (raw.recent_reports || []).map(mapReport)};
    snapshots.set(id, mapped);
    return mapped;
  }
  function briefing(raw, siteId) {
    if (wireSiteId(raw.site_id) !== String(siteId)) throw new Error('The briefing belongs to a different site.');
    if (!/^\d{4}-\d{2}-\d{2}$/.test(raw.for_date) || typeof raw.text !== 'string') throw new Error('Invalid briefing returned by the API.');
    return {...raw, id: `latest:${raw.site_id}:${raw.for_date}:${raw.generated_at}`, site_id: String(raw.site_id),
      title: 'Next-day safety briefing', valid_date: raw.for_date, body: raw.text,
      timezone: snapshots.get(String(siteId))?.timezone ?? null, forecast: [], sources: [], delivery_status: null};
  }
  return {nextRevision, site, briefing};
}

function mapWildlife(raw,id){
  if(!raw)return null;
  if(raw.site_id!=null&&String(raw.site_id)!==id)throw new Error('Wildlife evidence belongs to a different site.');
  return {...raw,site_id:id,sightings:Array.isArray(raw.sightings)?raw.sightings:[],encounter_probability:null,numeric_score_contribution:null};
}

/* Alan supplies the DeepSpace SDK connection through this small frontend boundary.
   Events are invalidation notices: fetch authorized API data before updating screens. */
export function subscribeContractEvents({siteId, getSource, getToken, readSite, listSites,
  onEvent, onConnection, heartbeatMs = 45000, timers = globalThis, retryBaseMs = 1000}) {
  const types = new Set(['alert.started', 'alert.updated', 'alert.cleared', 'report.created', 'report.resolved', 'scores.updated']);
  let stopped = false, generation = 0, cleanup, retry, heartbeat, opening;
  let connected = false, confirming = false, attempt = 0, queue = Promise.resolve(), pendingScores;
  const current = gen => !stopped && gen === generation;
  const clearTimers = () => {timers.clearInterval(heartbeat); timers.clearTimeout(opening);};
  function reconnect(gen) {
    if (!current(gen)) return;
    generation++; connected = false; confirming = false; pendingScores = undefined; clearTimers();
    const close = cleanup; cleanup = undefined;
    try { close?.(); } catch { /* The SDK connection is already lost. */ }
    onConnection(false);
    retry = timers.setTimeout(connect, Math.min(30000, retryBaseMs * 2 ** Math.min(attempt++, 5)));
    retry?.unref?.();
  }
  async function refresh(gen, notice) {
    if (!current(gen)) return;
    if(siteId===null){
      const sites=await listSites();
      if(current(gen))onEvent({type:'site',sites,
        ...(notice?.type==='scores.updated'?{site_ids:notice.site_ids.map(String)}:notice?{site_ids:[String(notice.site_id)]}:{})});
      return;
    }
    const id=String(siteId);
    const site=await readSite(id,{refreshAlerts:true,clearedAlertId:notice?.type==='alert.cleared'?notice.alert_id:undefined});
    if(!current(gen))return;
    onEvent({type:'site',site_id:id,site});
    if(notice?.type.startsWith('report.'))onEvent({type:'report',site_id:id});
  }

  function enqueue(gen, task) {
    queue = queue.then(() => current(gen) ? task() : undefined).catch(() => reconnect(gen));
  }
  async function connect() {
    if (stopped) return;
    const gen = ++generation; queue = Promise.resolve(); confirming = false; pendingScores = undefined;
    onConnection(false);
    opening = timers.setTimeout(() => reconnect(gen), heartbeatMs);
    opening?.unref?.();
    try {
      const source = await getSource();
      if(!current(gen))return;
      if (typeof source?.subscribe !== 'function') { reconnect(gen); return; }
      // Check the session, but keep its bearer token on authorized API reads.
      await getToken();
      if (!current(gen)) return;
      const unsubscribe = await source.subscribe({
        site_id: siteId === null ? null : contractSiteId(siteId),
        onEvent(notice) {
          if(!current(gen)||!types.has(notice?.type))return;
          if(notice.type==='scores.updated'){
            if(!Array.isArray(notice.site_ids)||!notice.site_ids.length||!notice.site_ids.every(id=>Number.isSafeInteger(id)&&id>0))return;
            if(siteId!==null&&!notice.site_ids.includes(Number(siteId)))return;
            if(pendingScores){for(const id of notice.site_ids)pendingScores.add(id);return;}
            const ids=new Set(notice.site_ids);pendingScores=ids;
            enqueue(gen,async()=>{if(pendingScores===ids)pendingScores=undefined;await refresh(gen,{type:'scores.updated',site_ids:[...ids]});});
            return;
          }
          if(!Number.isSafeInteger(notice.site_id)||notice.site_id<=0)return;
          if (siteId !== null && String(notice.site_id) !== String(siteId)) return;
          if (notice.type.startsWith('alert.') && (!Number.isSafeInteger(notice.alert_id) || notice.alert_id <= 0)) return;
          if (notice.type.startsWith('report.') && (typeof notice.report_id !== 'string' || !notice.report_id)) return;
          enqueue(gen, () => refresh(gen, notice));
        },
        onConnection(value) {
          if (!current(gen)) return;
          if(value!==true){reconnect(gen);return;}
          if(connected||confirming)return;confirming=true;
          enqueue(gen, async () => {
            await refresh(gen);
            if (!current(gen)) return;
            connected = true; confirming = false; attempt = 0; clearTimers(); onConnection(true);
            // This heartbeat describes a confirmed SDK transport, not lightning-feed health.
            heartbeat = timers.setInterval(() => {if (current(gen) && connected) onEvent({type: 'heartbeat'});}, Math.max(1000, Math.floor(heartbeatMs / 3)));
            heartbeat?.unref?.();
          });
        },
        onError() { reconnect(gen); }
      });
      if (!current(gen)) { if (typeof unsubscribe === 'function') unsubscribe(); return; }
      if (typeof unsubscribe !== 'function') throw new Error('The real-time source must supply an unsubscribe function.');
      cleanup = unsubscribe;
    } catch { reconnect(gen); }
  }
  connect();
  return () => {
    stopped = true; generation++; connected = false;
    timers.clearTimeout(retry); clearTimers();
    const close = cleanup; cleanup = undefined;
    try { close?.(); } catch { /* Closing an already-disconnected SDK is harmless. */ }
  };
}
