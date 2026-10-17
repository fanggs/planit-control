import {config} from './crew-config.js';
import {initAuth, session, signIn, signOut, authConfigured} from './crew-auth.js';
import {workspaceForUser, siteParameter} from './crew-routing.js';
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
      const filename = workspace === 'supervisor' ? 'crew-supervisor' : 'crew';
      const url = new URL(filename + '.html', location.href);
      if (siteId) url.searchParams.set('site', siteId);
      document.title = 'PlanIT Control · ' + (workspace === 'supervisor' ? 'Supervisor' : 'Crew');
      document.getElementById('crew-access-root').id = workspace === 'supervisor' ? 'crew-supervisor-root' : 'crew-root';
      history.replaceState({}, document.title, url);
      // Preserve the SDK's memory-only token by importing into this document.
      await import('./' + filename + '.js');
      return;
    }
    status.textContent = 'Use your work account to continue securely.';
    button.disabled = false;
    if (query.get('start') === '1') await startLogin();
  } catch (error) { showError(error); }
}
boot();
