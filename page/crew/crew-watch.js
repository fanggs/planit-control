// Contract v1.3 watch evidence. Empty alert lists alone never mean "clear".
const validTime = value => typeof value === 'string' && Number.isFinite(Date.parse(value));
const recent = (value, now, minutes) => validTime(value)
  && Date.parse(value) <= now && now - Date.parse(value) <= minutes * 60000;

export function lightningWatch(watch, alerts = [], now = Date.now()) {
  const stop = Array.isArray(alerts) && alerts.some(alert =>
    alert?.hazard_type === 'lightning' && alert.level === 'stop_work');
  if (stop || watch?.status === 'stop_work') return {status: 'stop_work', text: 'Lightning · STOP WORK'};
  if (watch?.status === 'clear' && recent(watch.checked_at, now, 5)) {
    return {status: 'clear', text: 'Lightning watch clear'};
  }
  return {status: 'unknown', text: 'Lightning status unavailable'};
}

export function warningsWatch(watch, events = [], now = Date.now()) {
  if (watch?.status !== 'ok' || !recent(watch.checked_at, now, 15) || !Array.isArray(events)) {
    return {status: 'unknown', text: 'NWS warning status unavailable', count: null};
  }
  const nws = events.filter(event => String(event?.event_kind || '').startsWith('nws_'));
  if (nws.some(event => !validTime(event.starts_at) ||
    (event.ends_at != null && !validTime(event.ends_at)))) {
    return {status: 'unknown', text: 'NWS warning status unavailable', count: null};
  }
  const count = nws.filter(event => Date.parse(event.starts_at) <= now &&
    (event.ends_at == null || Date.parse(event.ends_at) > now)).length;
  return {status: 'ok', text: count ? `${count} active NWS alert${count === 1 ? '' : 's'}` : 'No active NWS alerts', count};
}
