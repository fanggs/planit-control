// A failed alerts request must not hide a healthy site map. Keep the failed
// feed unknown rather than turning it into an empty (apparently safe) list.
export async function loadDashboardFeeds(api) {
  const alertsRequest = Promise.resolve().then(() => api.alerts()).then(
    alerts => ({alerts, alertError: null}),
    alertError => ({alerts: null, alertError}));
  const sites = await api.sites();
  return {sites, ...await alertsRequest};
}

export function alertFeedDisplay(alerts) {
  if (alerts === null) return {count: 'No data', status: 'Alert feed unavailable · do not infer safety'};
  if (alerts.length === 0) return {count: '0', status: 'No active alerts returned · feed health unconfirmed'};
  return {count: String(alerts.length), status: 'Warnings and stop-work alerts'};
}
