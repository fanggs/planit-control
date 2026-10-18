import {assessScore, lightningDisplay, summaryScore, validSiteId, warningsDisplay} from './domain.js';

function lightningFor(row, now) {
  const summaryStop = row?.active_alert?.hazard_type === 'lightning' && row.active_alert.level === 'stop_work';
  const detailStop = Array.isArray(row?.active_alerts) && row.active_alerts.some(alert =>
    alert.hazard_type === 'lightning' && alert.level === 'stop_work');
  return lightningDisplay(row?.lightning_status, now, summaryStop || detailStop);
}

// A successful fetch is not needed for a displayed "clear" to expire. The
// browser clock can only make old evidence less reassuring, never more so.
export function updateWatchChips(root, sites, detail, now = Date.now()) {
  const byId = new Map(sites.map(site => [site.site_id, site]));
  for (const node of root.querySelectorAll('[data-watch-kind]')) {
    const id = Number(node.dataset.watchSiteId);
    if (!validSiteId(id)) continue;
    const row = node.dataset.watchScope === 'detail' && detail?.site_id === id ? detail : byId.get(id);
    if (!row) continue;
    const result = node.dataset.watchKind === 'lightning' ? lightningFor(row, now)
      : node.dataset.watchKind === 'warnings' ? warningsDisplay(row.warnings_status, row.environmental_events, now)
        : null;
    if (!result) continue;
    node.textContent = result.text;
    node.dataset.tone = result.status === 'stop_work' ? 'high'
      : result.status === 'clear' || result.status === 'ok' ? 'low' : 'unknown';
  }
}

export function screeningAvailability(sites, now = Date.now(), allowHistorical = false) {
  return new Map(sites.map(site => [site.site_id, summaryScore(site, now, allowHistorical) !== null]));
}

export function screeningAvailabilityChanged(previous, current) {
  if (previous.size !== current.size) return true;
  for (const [id, available] of current) if (previous.get(id) !== available) return true;
  return false;
}

export function detailScreeningStatus(detail, now = Date.now(), allowHistorical = false) {
  return detail ? assessScore(detail.screening, now, allowHistorical).status : null;
}
