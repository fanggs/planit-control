/* Why: A URL or demo selection must never grant supervisor access. */
export function userRoles(user, claim) {
  const roles = user?.[claim];
  return Array.isArray(roles)
    ? [...new Set(roles.filter(role => role === 'crew' || role === 'supervisor'))]
    : [];
}
export function workspaceForUser(user, claim) {
  const roles = userRoles(user, claim);
  if (roles.includes('supervisor')) return 'supervisor';
  if (roles.includes('crew')) return 'crew';
  return null;
}
export function siteParameter(value) {
  const text = String(value ?? '');
  return /^\d+$/.test(text) && Number.isSafeInteger(Number(text)) && Number(text) > 0
    ? String(Number(text)) : null;
}

// Fixed destinations work with both /crew/ hosting and the local root aliases.
// No role, arbitrary return URL, token or authorization code goes in this URL.
export function workspaceURL(workspace,baseURL){
  if(workspace==='supervisor')return new URL('crew-supervisor.html',baseURL);
  if(workspace==='crew')return new URL('crew.html',baseURL);
  throw new Error('Unknown workspace.');
}
