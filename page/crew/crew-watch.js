// Contract v1.3 watch evidence. Empty alert lists alone never mean "clear".
const validTime = value => typeof value === 'string' && Number.isFinite(Date.parse(value));
const recent = (value, now, minutes) => validTime(value)
  && Date.parse(value) <= now && now - Date.parse(value) <= minutes * 60000;

export function lightningWatch(watch, alerts = [], now = Date.now()) {
  const stop = Array.isArray(alerts) && alerts.some(alert =>
    alert?.hazard_type === 'lightning' && alert.level === 'stop_work');
  if (stop || watch?.status === 'stop_work') return {status: 'stop_work', text: 'Lightning · STOP WORK'};
  if (watch?.status === 'clear' && recent(watch.checked_at, now, 5)) {
    return {status: 'clear', text: 'No lightning within 10 miles'};
  }
  return {status: 'unknown', text: 'Can’t confirm lightning right now'};
}

export function warningsWatch(watch, events = [], now = Date.now()) {
  if (watch?.status !== 'ok' || !recent(watch.checked_at, now, 15) || !Array.isArray(events)) {
    return {status: 'unknown', text: 'Can’t check weather warnings right now', count: null};
  }
  const nws = events.filter(event => String(event?.event_kind || '').startsWith('nws_'));
  if (nws.some(event => !validTime(event.starts_at) ||
    (event.ends_at != null && !validTime(event.ends_at)))) {
    return {status: 'unknown', text: 'Can’t check weather warnings right now', count: null};
  }
  const active = nws.filter(event => Date.parse(event.starts_at) <= now &&
    (event.ends_at == null || Date.parse(event.ends_at) > now));
  const count = active.length;
  return {status: 'ok', text: count ? `${count} weather alert${count === 1 ? '' : 's'}: ${nwsNames(active)}`
    : 'No weather warnings right now', count};
}

// "Rip Current Statement issued October 17 at ..." -> "Rip Current Statement", each event once.
export function nwsNames(events) {
  const names = events.map(event => String(event?.title || '').split(' issued ')[0].trim()).filter(Boolean);
  return [...new Set(names)].join(', ') || 'details below';
}
