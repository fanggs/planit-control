/* Why: A URL or demo selection must never grant supervisor access. */
export function userRoles(user, claim) {
  const roles = user?.[claim];
  return Array.isArray(roles)
    ? [...new Set(roles.filter(role => role === 'crew' || role === 'supervisor'))]
    : [];
}
export function workspaceForUser(user, claim) {
  const roles = userRoles(user, claim);
  // This chooser serves crew entry pages. The dashboard checks its own role.
  if (roles.includes('crew')) return 'crew';
  if (roles.includes('supervisor')) return 'supervisor';
  return null;
}
export function siteParameter(value) {
  const text = String(value ?? '');
  return /^\d+$/.test(text) && Number.isSafeInteger(Number(text)) && Number(text) > 0
    ? String(Number(text)) : null;
}

// Only exact, registered Auth0 callbacks can receive a redirect. Never turn
// arbitrary location paths (or query parameters) into a redirect URI.
export function crewCallbackPath(pathname) {
  if (pathname === '/crew/crew.html' || pathname === '/crew.html') return '/crew/crew.html';
  if (pathname === '/crew/crew-atlas.html' || pathname === '/crew-atlas.html') return '/crew/crew-atlas.html';
  return '/crew/login.html';
}

// Fixed destinations work with both /crew/ hosting and the local root aliases.
// No role, arbitrary return URL, token or authorization code goes in this URL.
export function workspaceURL(workspace,baseURL){
  if(workspace==='supervisor')return new URL('crew-supervisor.html',baseURL);
  if(workspace==='crew')return new URL('crew.html',baseURL);
  throw new Error('Unknown workspace.');
}

// Aryan's dashboard is the canonical live supervisor destination. The
// crew-owned supervisor page remains an explicitly labeled sample preview.
export function supervisorDashboardURL(baseURL){
  return new URL('../supervisor/index.html',baseURL);
}

export function supervisorNavigationURL(baseURL,dataMode){
  if(dataMode==='mock'){
    const preview=new URL('crew-supervisor.html',baseURL);
    preview.searchParams.set('demo','1');
    return preview;
  }
  return supervisorDashboardURL(baseURL);
}

// The public deployment can use live API data only on its exact HTTPS origin.
// Local and IP-address previews remain clearly labeled samples.
export function isLiveDeploymentURL(moduleURL){
  return new URL(moduleURL).origin==='https://foresite.work';
}
