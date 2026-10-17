import {validNotice} from './domain.js';
import {createRefreshQueue} from './refresh.js';

// DeepSpace broadcasts public IDs only; fetch all details from the authorized API.
export function connectRealtime({getSource, getToken, onInvalidate, onStatus, timers = globalThis}) {
  let stopped = false, cleanup, retry, opening, generation = 0, connected = false;
  const active = gen => !stopped && gen === generation;
  const invalidate = createRefreshQueue(async () => {
    const gen = generation;
    if (!active(gen)) return;
    await onInvalidate();
    if (active(gen) && connected) onStatus(true);
  });
  function requestRefresh(gen) { void invalidate().catch(() => schedule(gen)); }
  function disconnect() {
    timers.clearTimeout(opening);
    try { cleanup?.(); } catch { /* An already-closed provider is harmless. */ }
    cleanup = undefined;
  }
  function schedule(gen) {
    if (!active(gen)) return;
    generation++; connected = false; disconnect(); onStatus(false);
    timers.clearTimeout(retry);
    retry = timers.setTimeout(connect, 10000);
  }
  async function connect() {
    if (stopped) return;
    const gen = ++generation;
    connected = false;
    onStatus(false);
    try {
      const source = getSource();
      if (typeof source?.subscribe !== 'function') { schedule(gen); return; }
      // Check the Auth0 session before listening, but never send its token to
      // the anonymous DeepSpace bridge. API refetches use their own bearer token.
      await getToken();
      if (!active(gen)) return;
      opening = timers.setTimeout(() => schedule(gen), 20000);
      const close = await source.subscribe({
        onEvent(notice) {
          if (!active(gen) || !validNotice(notice)) return;
          requestRefresh(gen);
        },
        onConnection(providerConnected) {
          if (!active(gen)) return;
          if (providerConnected !== true) { schedule(gen); return; }
          timers.clearTimeout(opening);
          // Refresh after every reconnect to recover events missed while disconnected.
          connected = true;
          requestRefresh(gen);
        },
        onError() { schedule(gen); }
      });
      if (!active(gen)) { if (typeof close === 'function') close(); return; }
      if (typeof close !== 'function') throw new Error('Realtime provider must return an unsubscribe function.');
      cleanup = close;
    } catch { schedule(gen); }
  }
  void connect();
  return () => { stopped = true; generation++; timers.clearTimeout(retry); disconnect(); };
}
