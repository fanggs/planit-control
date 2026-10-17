// A new selection must never retain another site's reports or private images.
// Returning false for the same site lets refresh keep its last known data.
export function changeSelectedSite(state, siteId) {
  if (state.selected === siteId) return false;
  state.selected = siteId;
  state.detail = null;
  state.reports = [];
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
