import {config} from './crew-config.js';
import {initAuth, session, signIn, signOut, authConfigured} from './crew-auth.js';
import {workspaceForUser, siteParameter, workspaceURL} from './crew-routing.js';
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
      const url = workspaceURL(workspace,location.href);
      if(workspace==='supervisor'){
        // The independent dashboard initializes its own Auth0 session and checks
        // the verified role. Never pass an access token between pages in a URL.
        location.replace(url.href);
        return;
      }
      if(siteId)url.searchParams.set('site',siteId);
      document.title='PlanIT Control · Crew';
      document.getElementById('crew-access-root').id='crew-root';
      history.replaceState({},document.title,url);
      // Crew keeps the SDK's memory-only token by loading in this document.
      await import('./crew.js');
      return;
    }
    status.textContent = 'Use your work account to continue securely.';
    button.disabled = false;
    if (query.get('start') === '1') await startLogin();
  } catch (error) { showError(error); }
}
export const ready=boot();
