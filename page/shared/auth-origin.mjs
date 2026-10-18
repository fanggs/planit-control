// Only these deployed/loopback origins have exact callbacks in the PlanIT
// development Auth0 application. An IDE preview must never start OAuth.
const crewOrigins = new Set(['https://foresite.work', 'http://127.0.0.1:4174']);
const supervisorOrigins = new Set([...crewOrigins, 'http://127.0.0.1:4175']);

function originAllowed(value, allowed) {
  try {
    const url = new URL(value);
    return !url.username && !url.password && allowed.has(url.origin);
  } catch {
    return false;
  }
}

export function supportedAuthOrigin(value) {
  return originAllowed(value, crewOrigins);
}

export function supportedSupervisorAuthOrigin(value) {
  return originAllowed(value, supervisorOrigins);
}
