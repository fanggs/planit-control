// A navigation hint, never an authentication credential. Auth0 and the API
// still verify the user and their role after every full-page navigation.
const key = 'planit.authenticated-in-tab';

export function markAuthenticated() {
  try {
    globalThis.sessionStorage?.setItem(key, '1');
  } catch {
    // Private-browsing policies may disable session storage.
  }
}

export function hasResumeHint() {
  try {
    return globalThis.sessionStorage?.getItem(key) === '1';
  } catch {
    return false;
  }
}

export function clearResumeHint() {
  try {
    globalThis.sessionStorage?.removeItem(key);
  } catch {
    // Signing out must remain possible even when storage is unavailable.
  }
}
