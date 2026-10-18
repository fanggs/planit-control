// Pure display rules: numbers always come from the API, never from UI heuristics.
export const HAZARDS = Object.freeze({heat: 'Heat', lightning: 'Lightning', flooding: 'Flooding',
  wildfire: 'Wildfire', soil_saturation: 'Soil saturation', wildlife: 'Wildlife', other: 'Other'});
export const finite = value => typeof value === 'number' && Number.isFinite(value);
export const validTime = value => typeof value === 'string' && Number.isFinite(Date.parse(value));
export const validSiteId = value => Number.isSafeInteger(value) && value > 0;
export const scoreNumber = value => finite(value) && value >= 0 && value <= 10 ? value : null;
export const validFactors = rows => Array.isArray(rows) && rows.every(row =>
  row && typeof row.feature === 'string' && row.feature.trim().length > 0
  && row.feature.length <= 100 && finite(row.contribution));
export const label = hazard => HAZARDS[hazard] || 'Unknown hazard';
export const points = value => `${value > 0 ? '+' : ''}${value.toFixed(1)}`;
const FEATURE_LABELS = Object.freeze({temperature_max_f: 'High temperature',temperature_min_f: 'Low temperature',
  humidity_mean_pct: 'Average humidity',humidity_min_pct: 'Lowest humidity',wind_max_mph: 'Strongest wind',
  rain_max_1h_in: 'Heaviest hourly rain',rain_total_24h_in: 'Rain over 24 hours',heat_index_max_f: 'Highest heat index',
  heat_index_max_f_missing: 'Heat index not available',
  antecedent_forecast_rain_24h_in: 'Rain in the past day',
  antecedent_forecast_rain_72h_in: 'Rain in the past 3 days',
  antecedent_forecast_rain_168h_in: 'Rain in the past week',
  latitude: 'Location (north–south)',longitude: 'Location (east–west)',elevation_m: 'Elevation',
  month_sin: 'Time of year',month_cos: 'Time of year (2)',hour_sin: 'Time of day',hour_cos: 'Time of day (2)',
  soil_moisture: 'Soil moisture'});
export const featureLabel = feature => Object.hasOwn(FEATURE_LABELS, feature)
  ? FEATURE_LABELS[feature] : String(feature).replaceAll('_', ' ');
export const shownScoreStatus = status => status === 'research' || status === 'validated_prototype';
const UNAVAILABLE_SCORE_STATUSES = new Set(['no_data', 'stale', 'invalid', 'research_unapproved']);

export const isReplayAlert = alert => alert?.trigger?.is_replay === true;
export function siteHasReplayAlert(site, alerts) {
  // GET /sites has only an alert summary; match it to the full /alerts rows.
  if (!site?.active_alert || !Array.isArray(alerts)) return false;
  return alerts.some(alert => alert.site_id === site.site_id
    && alert.hazard_type === site.active_alert.hazard_type
    && alert.level === site.active_alert.level && isReplayAlert(alert));
}

export function summaryScreening(site, now = Date.now(), allowHistorical = false) {
  // The summary has top factors but no baseline. Keep a visible explanation
  // alongside every number, and distinguish local expiry from the API status.
  const status = site?.score_status;
  if (!shownScoreStatus(status)) return {score: null, status: UNAVAILABLE_SCORE_STATUSES.has(status) ? status : 'invalid'};
  if (!validTime(site?.scored_at)) return {score: null, status: 'invalid'};
  const scored = Date.parse(site.scored_at);
  if (!allowHistorical && (scored > now || now - scored > 2 * 3600000)) {
    return {score: null, status: 'stale'};
  }
  if (!validFactors(site?.top_factors) || !site.top_factors.length) {
    return {score: null, status: 'invalid'};
  }
  const score = scoreNumber(site?.score);
  return score === null ? {score: null, status: 'invalid'} : {score, status};
}
export function summaryScore(site, now = Date.now(), allowHistorical = false) {
  return summaryScreening(site, now, allowHistorical).score;
}
export function validateSummary(site) {
  if (!site || !validSiteId(site.site_id) || typeof site.name !== 'string') throw new Error('Invalid site returned by the API.');
  return site;
}
export function coordinates(row) {
  return finite(row?.latitude) && Math.abs(row.latitude) <= 90 && finite(row?.longitude)
    && Math.abs(row.longitude) <= 180 ? [row.latitude, row.longitude] : null;
}
export function openReportPins(reports) {
  // Resolved reports remain in the history panel, but are not active map hazards.
  return reports.filter(report => report?.status === 'open' && coordinates(report));
}
export function riskTone(score) {
  // Visual bands only, not a new model or a work-permission decision.
  return score === null ? 'unknown' : score >= 7 ? 'high' : score >= 4 ? 'medium' : 'low';
}
export function rankSites(rows, {search = '', filter = 'all', allowHistorical = false} = {}) {
  const query = search.trim().toLowerCase();
  const scoreOf = site => summaryScore(site, Date.now(), allowHistorical);
  return rows.filter(site => (!query || [site.name, site.state, site.hazard_region, site.site_id]
    .some(value => String(value ?? '').toLowerCase().includes(query)))
    && (filter === 'all' || (filter === 'alerts' && site.active_alert != null)
      || (filter === 'reports' && Number.isInteger(site.open_report_count) && site.open_report_count > 0)
      || (filter === 'no-data' && scoreOf(site) === null)))
    .sort((a, b) => (scoreOf(b) ?? -1) - (scoreOf(a) ?? -1) || a.site_id - b.site_id);
}
export function assessScore(model, now = Date.now(), allowHistorical = false) {
  if (model == null) return {status: 'no_data', message: 'No score data. A missing feed is never a zero.'};
  if (model.score === null && ['no_data', 'stale', 'invalid', 'research_unapproved'].includes(model.status)) {
    return {status: model.status, message: typeof model.reason === 'string' && model.reason.trim()
      ? model.reason : 'Screening index unavailable. Missing data never means safe.'};
  }
  if (!shownScoreStatus(model.status) || scoreNumber(model.score) === null || !finite(model.baseline)
    || !validFactors(model.factors) || model.factors.length === 0 || !validTime(model.scored_at)
    || !validTime(model.captured_at) || !validTime(model.valid_from) || !validTime(model.valid_until)
    || Date.parse(model.valid_from) >= Date.parse(model.valid_until)
    || Date.parse(model.scored_at) < Date.parse(model.captured_at)
    || typeof model.target !== 'string' || !model.target.trim() || model.clears_stop_work !== false
    || typeof model.artifact_sha256 !== 'string' || model.artifact_sha256.length !== 64
    || typeof model.snapshot_id !== 'string' || model.snapshot_id.length !== 64) {
    return {status: 'invalid', message: 'The score explanation is incomplete. Refresh or contact the data team.'};
  }
  if (!allowHistorical) {
    if (Date.parse(model.scored_at) > now || Date.parse(model.captured_at) > now) {
      return {status: 'invalid', message: 'The screening timestamps are in the future.'};
    }
    if (now - Date.parse(model.captured_at) > 2 * 3600000 || now >= Date.parse(model.valid_until)) {
      return {status: 'stale', message: 'Screening inputs or target window are out of date. Refresh for a new prediction.'};
    }
  }
  const total = model.baseline + model.factors.reduce((sum, factor) => sum + factor.contribution, 0);
  if (Math.abs(total - model.score) > 1e-8) return {status: 'mismatch', total,
    message: `Explanation does not reconcile: ${total.toFixed(2)} calculated, ${model.score.toFixed(2)} supplied. Contact the model team.`};
  let running = model.baseline;
  const steps = [{name: 'Baseline', value: model.baseline, start: 0, end: model.baseline, kind: 'baseline'}];
  for (const factor of model.factors) {
    steps.push({name: featureLabel(factor.feature), value: factor.contribution, start: running,
      end: running + factor.contribution, kind: factor.contribution < 0 ? 'decrease' : 'increase'});
    running += factor.contribution;
  }
  steps.push({name: 'Final score', value: model.score, start: 0, end: model.score, kind: 'total'});
  return {status: 'ready', total, steps, min: Math.min(0, ...steps.flatMap(step => [step.start, step.end])),
    max: Math.max(10, ...steps.flatMap(step => [step.start, step.end]))};
}
export function lightningDisplay(watch, now = Date.now(), activeStopWork = false) {
  if (activeStopWork || watch?.status === 'stop_work') return {status: 'stop_work', text: 'Lightning · STOP WORK'};
  const checked = validTime(watch?.checked_at) ? Date.parse(watch.checked_at) : null;
  if (watch?.status === 'clear' && checked !== null && checked <= now && now - checked <= 5 * 60000) {
    return {status: 'clear', text: 'No lightning within 10 miles'};
  }
  return {status: 'unknown', text: 'Can’t confirm lightning right now'};
}
export function warningsDisplay(watch, events, now = Date.now()) {
  const checked = validTime(watch?.checked_at) ? Date.parse(watch.checked_at) : null;
  if (watch?.status !== 'ok' || checked === null || checked > now || now - checked > 15 * 60000) {
    return {status: 'unknown', text: 'Can’t check weather warnings right now'};
  }
  if (!Array.isArray(events)) return {status: 'unknown', text: 'Can’t check weather warnings right now'};
  if (events.some(event => String(event?.event_kind || '').startsWith('nws_') && !validTime(event.starts_at))) {
    return {status: 'unknown', text: 'Can’t check weather warnings right now'};
  }
  const active = events.filter(event => String(event?.event_kind || '').startsWith('nws_')
    && validTime(event.starts_at) && Date.parse(event.starts_at) <= now
    && (!validTime(event.ends_at) || Date.parse(event.ends_at) > now));
  return {status: 'ok', text: active.length
    ? `${active.length} weather alert${active.length === 1 ? '' : 's'}: ${nwsNames(active)}`
    : 'No weather warnings right now'};
}
// "Rip Current Statement issued October 17 at ..." -> "Rip Current Statement", each event once.
export function nwsNames(events) {
  const names = events.map(event => String(event?.title || '').split(' issued ')[0].trim()).filter(Boolean);
  return [...new Set(names)].join(', ') || 'details below';
}
export function wildlifeSummary(context) {
  if (!context || !Array.isArray(context.sightings) || context.status === 'unavailable') {
    return 'Sighting records aren’t available right now. That doesn’t mean there are no animals.';
  }
  if (context.sightings.length === 0) return 'No past sightings recorded nearby. That doesn’t mean there are no animals.';
  return `${context.sightings.length} past sighting${context.sightings.length === 1 ? '' : 's'} nearby (not live)`;
}
export function freshness(value, now = Date.now(), staleMinutes = 60) {
  if (!validTime(value)) return {text: 'No timestamp', stale: true};
  const minutes = Math.floor((now - Date.parse(value)) / 60000);
  if (minutes < -1) return {text: 'Timestamp is in the future', stale: true};
  const age = minutes < 1 ? 'Just now' : minutes < 60 ? `${minutes} min ago`
    : minutes < 1440 ? `${Math.floor(minutes / 60)} h ago` : `${Math.floor(minutes / 1440)} d ago`;
  return {text: minutes >= staleMinutes ? `Stale · ${age}` : age, stale: minutes >= staleMinutes};
}
export function siteTime(value, timezone) {
  if (!validTime(value)) return 'No timestamp';
  try {
    return new Intl.DateTimeFormat('en-US', {timeZone: timezone || 'UTC', month: 'short', day: 'numeric',
      hour: 'numeric', minute: '2-digit', timeZoneName: 'short'}).format(new Date(value));
  } catch { return new Date(value).toISOString(); }
}
export function countdown(clearAt, now = Date.now()) {
  if (!validTime(clearAt)) return 'Clear time unavailable';
  const seconds = Math.ceil((Date.parse(clearAt) - now) / 1000);
  // Only the backend can clear an alert; reaching zero never authorizes work.
  if (seconds <= 0) return 'Awaiting server clearance';
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')} until scheduled clearance`;
}
const EVENT_TYPES = new Set(['alert.started', 'alert.updated', 'alert.cleared', 'report.created', 'report.resolved', 'scores.updated']);
export function validNotice(notice) {
  if (!notice || !EVENT_TYPES.has(notice.type)) return false;
  if (notice.type === 'scores.updated') return Array.isArray(notice.site_ids)
    && notice.site_ids.length > 0 && notice.site_ids.every(validSiteId);
  if (!validSiteId(notice.site_id)) return false;
  return notice.type.startsWith('report.') ? typeof notice.report_id === 'string' && notice.report_id.length > 0
    : validSiteId(notice.alert_id);
}
export function hasSupervisorRole(user, claim) {
  // user must be supplied by Auth0's validated SDK. This is UI gating only.
  return Array.isArray(user?.[claim]) && user[claim].includes('supervisor');
}
export function safeSourceURL(value) {
  try { const url = new URL(value); return url.protocol === 'https:' && !url.username && !url.password ? url.href : null; } catch { return null; }
}
// Common names first; the scientific name stays for anyone looking it up.
const SPECIES = {'Sistrurus miliarius': 'Pygmy rattlesnake', 'Agkistrodon piscivorus': 'Cottonmouth (water moccasin)',
  'Agkistrodon conanti': 'Florida cottonmouth', 'Alligator mississippiensis': 'American alligator',
  'Agkistrodon contortrix': 'Copperhead'};
export function speciesName(species) {
  if (typeof species !== 'string' || !species.trim()) return 'Animal not identified';
  return SPECIES[species] ? `${SPECIES[species]} (${species})` : species;
}
