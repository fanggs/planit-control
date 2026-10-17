// Pure display rules: numbers always come from the API, never from UI heuristics.
export const HAZARDS = Object.freeze({heat: 'Heat', lightning: 'Lightning', flooding: 'Flooding',
  wildfire: 'Wildfire', soil_saturation: 'Soil saturation', wildlife: 'Wildlife', other: 'Other'});
export const finite = value => typeof value === 'number' && Number.isFinite(value);
export const validTime = value => typeof value === 'string' && Number.isFinite(Date.parse(value));
export const validSiteId = value => Number.isSafeInteger(value) && value > 0;
export const scoreNumber = value => finite(value) && value >= 0 && value <= 10 ? value : null;
export const validFactors = rows => Array.isArray(rows) && rows.every(row =>
  row && Object.hasOwn(HAZARDS, row.hazard_type) && finite(row.contribution));
export const label = hazard => HAZARDS[hazard] || 'Unknown hazard';
export const points = value => `${value > 0 ? '+' : ''}${value.toFixed(1)}`;

export function summaryScore(site) {
  // The map/list only have top factors, not the full baseline. Never display
  // a numerical score there without at least one signed explanation.
  return validTime(site?.scored_at) && validFactors(site?.top_factors) && site.top_factors.length > 0
    ? scoreNumber(site?.score) : null;
}
export function validateSummary(site) {
  if (!site || !validSiteId(site.site_id) || typeof site.name !== 'string') throw new Error('Invalid site returned by the API.');
  return site;
}
export function coordinates(row) {
  return finite(row?.latitude) && Math.abs(row.latitude) <= 90 && finite(row?.longitude)
    && Math.abs(row.longitude) <= 180 ? [row.latitude, row.longitude] : null;
}
export function riskTone(score) {
  // Visual bands only, not a new model or a work-permission decision.
  return score === null ? 'unknown' : score >= 7 ? 'high' : score >= 4 ? 'medium' : 'low';
}
export function rankSites(rows, {search = '', filter = 'all'} = {}) {
  const query = search.trim().toLowerCase();
  return rows.filter(site => (!query || [site.name, site.state, site.hazard_region, site.site_id]
    .some(value => String(value ?? '').toLowerCase().includes(query)))
    && (filter === 'all' || (filter === 'alerts' && site.active_alert != null)
      || (filter === 'reports' && Number.isInteger(site.open_report_count) && site.open_report_count > 0)
      || (filter === 'no-data' && summaryScore(site) === null)))
    .sort((a, b) => (summaryScore(b) ?? -1) - (summaryScore(a) ?? -1) || a.site_id - b.site_id);
}
export function assessScore(model, siteId) {
  if (model == null) return {status: 'no_data', message: 'No score data. A missing feed is never a zero.'};
  if (model.site_id !== siteId || scoreNumber(model.score) === null || !finite(model.baseline)
    || !validFactors(model.factors) || model.factors.length === 0 || !validTime(model.scored_at)) {
    return {status: 'invalid', message: 'The score explanation is incomplete. Refresh or contact the data team.'};
  }
  const total = model.baseline + model.factors.reduce((sum, factor) => sum + factor.contribution, 0);
  if (Math.abs(total - model.score) > .050000001) return {status: 'mismatch', total,
    message: `Explanation does not reconcile: ${total.toFixed(2)} calculated, ${model.score.toFixed(2)} supplied. Contact the model team.`};
  let running = model.baseline;
  const steps = [{name: 'Baseline', value: model.baseline, start: 0, end: model.baseline, kind: 'baseline'}];
  for (const factor of model.factors) {
    steps.push({name: label(factor.hazard_type), value: factor.contribution, start: running,
      end: running + factor.contribution, kind: factor.contribution < 0 ? 'decrease' : 'increase'});
    running += factor.contribution;
  }
  steps.push({name: 'Final score', value: model.score, start: 0, end: model.score, kind: 'total'});
  return {status: 'ready', total, steps, min: Math.min(0, ...steps.flatMap(step => [step.start, step.end])),
    max: Math.max(10, ...steps.flatMap(step => [step.start, step.end]))};
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
