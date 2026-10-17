// Auth0 Post-Login Action. Deploy this in the Auth0 tenant's Login flow;
// importing this file in FastAPI or a browser does not activate the Action.
// Role names and claim name must match api/auth/hazard_auth.py and the pages.
const ROLE_CLAIM = 'https://planit-control/roles';
const ALLOWED_ROLES = new Set(['crew', 'supervisor']);

exports.onExecutePostLogin = async (event, api) => {
  // Assigned Auth0 roles are trusted. User-editable metadata is not.
  const assigned = Array.isArray(event.authorization?.roles) ? event.authorization.roles : [];
  const roles = [...new Set(assigned.filter(role => ALLOWED_ROLES.has(role)))];

  // The ID token selects a workspace; the API independently checks the access
  // token before reading reports/photos or accepting writes.
  api.idToken.setCustomClaim(ROLE_CLAIM, roles);
  api.accessToken.setCustomClaim(ROLE_CLAIM, roles);
};
