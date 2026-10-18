import {config} from './crew-config.js';
import {initAuth, session, signIn, signOut, authConfigured} from './crew-auth.js';
import {workspaceForUser, siteParameter, supervisorDashboardURL} from './crew-routing.js';
import {mountWorkspace} from './crew-workspaces.js';
import {markAuthenticated, clearResumeHint} from '../shared/auth-resume.mjs';
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
    status.textContent = config.authOriginSupported ? 'Secure sign-in is not configured.' : 'This preview address cannot sign in.';
    errorBox.textContent = config.authOriginSupported
      ? 'Ask your administrator to check the Auth0 public application settings.'
      : 'PyCharm’s built-in localhost:63342 preview is not an approved Auth0 callback. Use the link below, or run the project server on http://127.0.0.1:4174 and open /crew/login.html.';
    errorBox.hidden = false;
    button.hidden = true;
    document.getElementById('login-supported-link').hidden = false;
    return;
  }
  try {
    const callback = await initAuth();
    const user = await session();
    if (user) {
      const workspace = workspaceForUser(user, config.authRoleClaim);
      if (!workspace) {
        clearResumeHint();
        status.textContent = 'You’re signed in, but your account has no workspace role yet. Ask your administrator for access.';
        button.hidden = true; logout.hidden = false;
        return;
      }
      markAuthenticated();
      const siteId = siteParameter(callback.siteId ?? query.get('site'));
      if (workspace === 'supervisor') {
        status.textContent = 'Opening the supervisor operations dashboard…';
        // Auth0 tokens stay in memory and never travel in this URL. The
        // destination resumes the tenant session or offers its own sign-in.
        const destination = supervisorDashboardURL(location.href);
        destination.searchParams.set('start', '1');
        location.replace(destination.href);
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
