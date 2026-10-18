import {isSessionExpired} from '../shared/auth-session.mjs';

let expired = false;
export const sessionExpired = () => expired;

// A persistent, same-origin sign-in path covers every crew page, including the
// map and supervisor preview. No token or private report data enters this UI.
export function reportSessionExpired(error) {
  if (!isSessionExpired(error)) return false;
  if (expired) return true;
  expired = true;
  const doc = globalThis.document;
  if (doc?.body && typeof doc.createElement === 'function') {
    const banner = doc.createElement('section');
    banner.id = 'crew-session-expired';
    banner.className = 'crew-session-expired';
    banner.setAttribute('role', 'alert');
    const message = doc.createElement('p');
    message.textContent = 'Your sign-in expired. Sign in again to see live alerts and current site data. Information below may be out of date.';
    const link = doc.createElement('a');
    link.textContent = 'Sign in again';
    const target = new URL('login.html', globalThis.location.href);
    target.searchParams.set('start', '1');
    const site = new URLSearchParams(globalThis.location.search).get('site');
    if (/^[1-9]\d*$/.test(site || '')) target.searchParams.set('site', site);
    link.href = target.href;
    banner.append(message, link);
    doc.body.prepend(banner);
  }
  globalThis.window?.dispatchEvent?.(new Event('planit:session-expired'));
  return true;
}
