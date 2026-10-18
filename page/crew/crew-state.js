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
  if (!alert) return {title:'Checking lightning…', detail:'Waiting for the alert service. Check with your supervisor before working outside.', tone:'unknown', seconds:null};
  if (alert.status === 'hold') {
    const seconds = remainingSeconds(alert.all_clear_at, now);
    const replay = alert.is_replay === true;
    return {title:replay?'REPLAY · Stop work · Lightning':'Stop work · Lightning',
      detail:replay ? 'This is a recorded storm played back for the demo, not real lightning. It clears on its own.'
        : seconds === 0 ? 'Timer is done. Wait for the all-clear before going back to work.'
        : 'Get to shelter and follow your lightning procedure. Each new strike nearby restarts the timer.', tone:'hold', seconds};
  }
  if (!connected || alert.status !== 'cleared' || (watched && watched.status !== 'clear')) return {title:'Can’t confirm lightning status', detail:connected?'The lightning check is out of date. Check with your supervisor before working outside.':'Live updates are off, so this screen can’t confirm it’s safe. Check with your supervisor.', tone:'unknown', seconds:null};
  return {title:'No lightning nearby', detail:'No strikes within 10 miles in the last 30 minutes. Check the other conditions below.', tone:'clear', seconds:null};
}

export function contributionLabel(factor) {
  if (!Number.isFinite(factor?.contribution)) return 'Unavailable';
  // Round only the display, never the factor used for score reconciliation.
  const rounded = factor.contribution.toFixed(2);
  const signed = `${factor.contribution >= 0 ? '+' : ''}${rounded}`;
  return `${signed} ${factor.unit === 'score_points' ? 'points' : (factor.unit || 'contribution units')}`;
}
