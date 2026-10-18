// Keep authentication failures distinct from a temporary API or socket outage.
const interactiveCodes = new Set([
  'login_required', 'missing_refresh_token', 'invalid_grant',
  'consent_required', 'interaction_required', 'session_expired'
]);

export function isSessionExpired(error) {
  if (!error || typeof error !== 'object') return false;
  if (error.status === 401) return true;
  return interactiveCodes.has(String(error.error || error.code || '').toLowerCase());
}

export function expiredSessionError(error) {
  const result = new Error('Your sign-in expired. Sign in again to see live alerts and current site data.');
  result.name = 'SessionExpiredError';
  result.code = 'session_expired';
  result.status = 401;
  if (error) result.cause = error;
  return result;
}
