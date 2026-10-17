import {config} from './crew-config.js';
import {initAuth, session, signIn, signOut, authConfigured} from './crew-auth.js';
import {workspaceForUser, siteParameter, supervisorDashboardURL} from './crew-routing.js';
import {mountWorkspace} from './crew-workspaces.js';
const query = new URLSearchParams(location.search);
const status = document.getElementById('login-status');
const errorBox = document.getElementById('login-error');
const button = document.getElementById('login-continue');
const logout = document.getElementById('login-signout');
function showError(error) {
  status.textContent = 'We couldn’t complete sign-in.';
  errorBox.textContent = error.message || 'Please try again.';
  errorBox.hidden = false;
  button.disabled = !authConfigured();
}
async function startLogin() {
  button.disabled = true; errorBox.hidden = true;
  status.textContent = 'Opening secure sign-in…';
  try { await initAuth(); await signIn(); } catch (error) { showError(error); }
}
async function boot() {
  document.getElementById('login-demo').hidden = config.dataMode !== 'mock';
  button.addEventListener('click', startLogin);
  logout.addEventListener('click', () => signOut().catch(showError));
  if (!authConfigured()) {
    status.textContent = 'Secure sign-in is not connected yet. Please come back soon.';
    button.textContent = 'Sign-in coming soon';
    return;
  }
  try {
    const callback = await initAuth();
    const user = await session();
    if (user) {
      const workspace = workspaceForUser(user, config.authRoleClaim);
      if (!workspace) {
        status.textContent = 'You’re signed in, but your account has no workspace role yet. Ask your administrator for access.';
        button.hidden = true; logout.hidden = false;
        return;
      }
      const siteId = siteParameter(callback.siteId ?? query.get('site'));
      if (workspace === 'supervisor') {
        status.textContent = 'Opening the supervisor operations dashboard…';
        // Auth0 tokens stay in memory and never travel in this URL. The
        // destination resumes the tenant session or offers its own sign-in.
        location.replace(supervisorDashboardURL(location.href).href);
        return;
      }
      await mountWorkspace(workspace,{baseURL:location.href,siteId,document,history});
      return;
    }
    status.textContent = 'Use your work account to continue securely.';
    button.disabled = false;
    if (query.get('start') === '1') await startLogin();
  } catch (error) { showError(error); }
}
export const ready=boot();
