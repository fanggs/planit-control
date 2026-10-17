// A new selection must never retain another site's reports or private images.
// Returning false for the same site lets refresh keep its last known data.
export function changeSelectedSite(state, siteId) {
  if (state.selected === siteId) return false;
  state.selected = siteId;
  state.detail = null;
  state.reports = [];
  state.detailStale = false;
  return true;
}

// Keep last-known data visible after a failed same-site refresh, but never
// allow it to look current or leak into a different site's panel.
export function markDetailStale(state, siteId) {
  if (state.selected !== siteId || state.detail?.site_id !== siteId) return false;
  state.detailStale = true;
  return true;
}

export function bindPageLifecycle({browser, onHide}) {
  const hide = () => onHide();
  const show = event => {
    // Back/Forward Cache restores the old JS heap without running app startup.
    // Reload to re-check Auth0 and fetch fresh data before reconnecting timers.
    if (event.persisted) browser.location.reload();
  };
  browser.addEventListener('pagehide', hide);
  browser.addEventListener('pageshow', show);
  return () => {
    browser.removeEventListener('pagehide', hide);
    browser.removeEventListener('pageshow', show);
  };
}
