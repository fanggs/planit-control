import {validSiteId, validateSummary} from './domain.js';

function sitePath(id) {
  if (!validSiteId(id)) throw new Error('A positive integer site_id is required.');
  return String(id);
}
export function createAPI({base, token, timeoutMs = 20000, fetcher = fetch}) {
  const url = new URL(base);
  if (url.username || url.password || url.search || url.hash
    || !(url.protocol === 'https:' || (url.protocol === 'http:' && url.hostname === '127.0.0.1'))) {
    throw new Error('API URL must use HTTPS, or http://127.0.0.1 for local development.');
  }
  const origin = url.href.replace(/\/$/, '');
  async function request(path, {method = 'GET', body, image = false} = {}) {
    const bearer = await token();
    if (typeof bearer !== 'string' || !bearer) throw new Error('A valid access token is required.');
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), timeoutMs);
    try {
      const response = await fetcher(origin + path, {method, signal: controller.signal, cache: 'no-store',
        credentials: 'omit', redirect: 'error', headers: {Authorization: `Bearer ${bearer}`,
          Accept: image ? 'image/jpeg, image/png' : 'application/json', ...(body ? {'Content-Type': 'application/json'} : {})},
        ...(body ? {body: JSON.stringify(body)} : {})});
      if (!response.ok) {
        let detail;
        try { detail = await response.json(); } catch { /* Non-JSON server error. */ }
        throw new Error(detail?.error?.message || `Request failed (${response.status}).`);
      }
      if (image) {
        const blob = await response.blob();
        if (!['image/jpeg', 'image/png'].includes(blob.type) || blob.size > 5 * 1024 * 1024) {
          throw new Error('The photo response is not an allowed JPEG/PNG image under 5 MB.');
        }
        return blob;
      }
      // Keep the timeout active until the body has finished, not just its headers.
      return await response.json();
    } catch (error) {
      if (error.name === 'AbortError') throw new Error('The API request timed out. Data may be out of date.');
      throw error;
    } finally { clearTimeout(timeout); }
  }
  return {
    async sites() {
      const rows = await request('/sites');
      if (!Array.isArray(rows)) throw new Error('GET /sites must return a list.');
      return rows.map(validateSummary);
    },
    async detail(id) {
      const row = await request(`/sites/${sitePath(id)}`);
      if (row?.site_id !== id || !Array.isArray(row.active_alerts)) throw new Error('Invalid site detail returned by the API.');
      return row;
    },
    async reports(id) {
      const rows = await request(`/reports?site_id=${sitePath(id)}`);
      if (!Array.isArray(rows) || rows.some(row => row.site_id !== id)) throw new Error('Invalid site reports returned by the API.');
      return rows;
    },
    async alerts() {
      const rows = await request('/alerts');
      if (!Array.isArray(rows)) throw new Error('GET /alerts must return a list.');
      return rows;
    },
    resolve(id) {
      if (typeof id !== 'string' || !/^[0-9a-f-]{36}$/i.test(id)) throw new Error('A report UUID is required.');
      return request(`/reports/${encodeURIComponent(id)}`, {method: 'PATCH', body: {status: 'resolved'}});
    },
    photo(key) {
      if (typeof key !== 'string' || !/^[A-Za-z0-9_-]{1,1024}$/.test(key)) throw new Error('Invalid private photo key.');
      return request(`/photos/${encodeURIComponent(key)}`, {image: true});
    }
  };
}

export async function createSampleAPI(fetcher = fetch) {
  const names = ['sites', 'site_details', 'reports', 'alerts'];
  const values = await Promise.all(names.map(async name => {
    const response = await fetcher(new URL(`sample-data/${name}.json`, import.meta.url));
    if (!response.ok) throw new Error('Sample fixtures could not load. Serve the page over HTTP.');
    return response.json();
  }));
  const [sites, details, reports, alerts] = values;
  return {
    sites: async () => structuredClone(sites),
    detail: async id => structuredClone(details[sitePath(id)]),
    reports: async id => structuredClone(reports.filter(report => report.site_id === id)),
    alerts: async () => structuredClone(alerts),
    resolve: async () => { throw new Error('Sample preview is read-only. Configure live mode to resolve reports.'); },
    photo: async () => { throw new Error('Sample fixtures contain no real photographs.'); }
  };
}
