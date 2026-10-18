/* Why: Keep absolute deadlines, version ordering and missing-data handling independent of rendering so safety behavior can be tested. */
// Pure functions: no browser, network or timers. This makes the critical alert behavior testable.
import {lightningWatch} from './crew-watch.js';
export function remainingSeconds(deadline, now = Date.now()) {
  const timestamp = Date.parse(deadline);
  return Number.isFinite(timestamp) ? Math.max(0, Math.ceil((timestamp - now) / 1000)) : null;
}

// A later version wins even when messages arrive in the wrong order.
// The contract adapter supplies a local request-order counter, not a backend revision.
export function acceptAlert(previous, incoming, siteId) {
  if (!incoming || String(incoming.site_id) !== String(siteId)) return previous;
  if (!Number.isSafeInteger(incoming.version) || incoming.version < 0) return previous;
  if (previous && incoming.version <= previous.version) return previous;
  if (!['hold', 'cleared', 'unknown'].includes(incoming.status)) return previous;
  if (incoming.status === 'hold' && !Number.isFinite(Date.parse(incoming.all_clear_at))) return previous;
  return {...incoming};
}

export function alertView(alert, connected, now = Date.now(), watch = null) {
  const watched = watch ? lightningWatch(watch, [], now) : null;
  if (watched?.status === 'stop_work' && alert?.status !== 'hold') {
    return {title:'Stop work · Lightning', detail:'The API reports a stop-work condition. The countdown is unavailable; confirm with your supervisor.', tone:'hold', seconds:null};
  }
  if (!alert) return {title:'Status unavailable', detail:'Waiting for the alert service. Confirm conditions with your supervisor.', tone:'unknown', seconds:null};
  if (alert.status === 'hold') {
    const seconds = remainingSeconds(alert.all_clear_at, now);
    const replay = alert.is_replay === true;
    return {title:replay?'REPLAY · Stop work · Lightning':'Stop work · Lightning',
      detail:replay ? 'Recorded storm replay for the demo, not a current lightning observation. Wait for the server to clear this simulated hold.'
        : seconds === 0 ? 'Timer elapsed. Waiting for server confirmation; do not resume from the timer alone.'
        : 'Follow your site lightning procedure. Every new nearby strike resets this hold.', tone:'hold', seconds};
  }
  if (!connected || alert.status !== 'cleared' || (watched && watched.status !== 'clear')) return {title:'Status unavailable', detail:connected?'The lightning watch has not confirmed a fresh clear status. Check with your supervisor.':'Live updates are unavailable. The screen cannot confirm that work may resume.', tone:'unknown', seconds:null};
  return {title:'No active lightning hold reported', detail:'This describes the lightning alert only. Check all hazards and follow site procedures.', tone:'clear', seconds:null};
}

export function contributionLabel(factor) {
  if (!Number.isFinite(factor?.contribution)) return 'Unavailable';
  // Round only the display, never the factor used for score reconciliation.
  const rounded = factor.contribution.toFixed(2);
  const signed = `${factor.contribution >= 0 ? '+' : ''}${rounded}`;
  return `${signed} ${factor.unit === 'score_points' ? 'points' : (factor.unit || 'contribution units')}`;
}
