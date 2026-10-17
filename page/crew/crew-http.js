/* Contract HTTP transport. Screens consume mapped UI objects, never raw API DTOs. */
import {createCrewRealtimeProvider} from './crew-realtime-source.js';
import {contractSiteId, createContractMapper, mapSiteSummary, mapReport, subscribeContractEvents} from './crew-integration.js';
import {createHazardReportPayload, validateReportPhoto, MAX_PHOTO_BYTES} from './crew-report-mapping.js';

export const CONTRACT_ROUTES = Object.freeze({
  sites: '/sites', site: '/sites/{id}', alerts: '/alerts',
  reports: '/reports', photos: '/photos', photo: '/photos/{photo_key}',
  photoSuggestion: '/photos/{photo_key}/suggestion',
  briefing: '/briefings/{id}'
});
export class CrewAPIError extends Error {
  constructor(message, {status = 0, code = 'request_failed', ambiguousWrite = false} = {}) {
    super(message); this.name = 'CrewAPIError'; this.status = status;
    this.code = code; this.ambiguousWrite = ambiguousWrite;
  }
}

export function createHTTPAPI(settings, getToken, fetcher = fetch) {
  const mapper = createContractMapper();
  const getRealtimeSource = createCrewRealtimeProvider(settings);
  const briefingCache = new Map();
  const uploads = new Map(), inFlightUploads = new Map();
  const receipts = new Map(), uncertainReports = new Set(), submissions = new Map();
  function url(route, params = {}, query = {}) {
    if (!settings.baseURL) throw new Error('Set config.api.baseURL before using live HTTP mode.');
    const template = settings.routes?.[route] || CONTRACT_ROUTES[route];
    if (!template) throw new Error(`Unsupported contract route: ${route}`);
    const path = template.replace(/\{(\w+)\}/g, (_, key) => {
      if (params[key] == null) throw new Error(`Missing route parameter: ${key}`);
      return encodeURIComponent(params[key]);
    });
    const base = new URL(settings.baseURL.endsWith('/') ? settings.baseURL : settings.baseURL + '/');
    // Never send an access token to plain HTTP outside this machine, or to a
    // URL carrying credentials, a query string, or a fragment.
    if (base.username || base.password || base.search || base.hash
      || !(base.protocol === 'https:' || (base.protocol === 'http:' && base.hostname === '127.0.0.1'))) {
      throw new Error('API URL must use HTTPS, or http://127.0.0.1 for local development.');
    }
    const result = new URL(path.replace(/^\//, ''), base);
    if (result.origin !== base.origin) throw new Error('API routes must stay on the configured API origin.');
    for (const [key, value] of Object.entries(query)) if (value != null) result.searchParams.set(key, value);
    return result;
  }
  async function request(route, {params, query, method = 'GET', body, binary = false} = {}) {
    const target = url(route, params, query), token = await getToken();
    if (typeof token !== 'string' || !token) throw new Error('A valid access token is required.');
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), settings.timeoutMs || 20000);
    try {
      const headers = {Accept: binary ? 'image/jpeg,image/png' : 'application/json', Authorization: `Bearer ${token}`};
      if (body && !(body instanceof FormData)) headers['Content-Type'] = 'application/json';
      const response = await fetcher(target, {method, headers,
        body: body instanceof FormData ? body : body ? JSON.stringify(body) : undefined,
        signal: controller.signal, cache: 'no-store', credentials: 'omit', redirect: 'error'});
      if (!response.ok) {
        const problem = await response.json().catch(() => null);
        const fallback = response.status === 401 ? 'Your session expired. Sign in again.'
          : response.status === 403 ? 'Your account does not have permission for this action.'
          : `Service request failed (${response.status}).`;
        throw new CrewAPIError(problem?.error?.message || fallback, {
          status: response.status, code: problem?.error?.code || 'request_failed', ambiguousWrite: method !== 'GET' && response.status >= 500
        });
      }
      if (binary) {
        const photo = await response.blob();
        if (!['image/jpeg', 'image/png'].includes(photo.type)) throw new Error('The photo service did not return a JPEG or PNG image.');
        if (photo.size > MAX_PHOTO_BYTES) throw new Error('The photo exceeds the 5 MB contract limit.');
        return photo;
      }
      return response.status === 204 ? null : await response.json();
    } catch (error) {
      if (error instanceof CrewAPIError) throw error;
      if (method !== 'GET') throw new CrewAPIError('The request could not be confirmed. Check whether the report was saved before submitting again.', {ambiguousWrite: true});
      if (error.name === 'AbortError') throw new CrewAPIError('The request timed out. Try again.', {code: 'timeout'});
      throw error;
    } finally { clearTimeout(timer); }
  }
  function array(value, label) {
    if (!Array.isArray(value)) throw new Error(`Expected the contract array for ${label}.`);
    return value;
  }
  async function listSites() {
    return array(await request('sites'), 'sites').map(mapSiteSummary);
  }
  async function readSite(id, {refreshAlerts = false, clearedAlertId} = {}) {
    const site_id = contractSiteId(id), revision = mapper.nextRevision();
    const [raw, alerts] = await Promise.all([
      request('site', {params: {id: site_id}}),
      refreshAlerts ? request('alerts') : null
    ]);
    if (raw?.site_id !== site_id) throw new Error('The API returned a different site_id.');
    if (refreshAlerts) raw.active_alerts = array(alerts, 'alerts').filter(a => a.site_id === site_id);
    return mapper.site(raw, revision, {clearedAlertId});
  }
  async function listReports(id) {
    const site_id = contractSiteId(id);
    const reports = array(await request('reports', {query: {site_id}}), 'reports').map(mapReport);
    if (reports.some(report => report.site_id !== String(site_id))) throw new Error('The API returned a report for a different site.');
    return Promise.all(reports.map(async report => {
      if (!report.photo_key) return report;
      try { return {...report, photo: await request('photo', {params: {photo_key: report.photo_key}, binary: true})}; }
      catch (error) {
        if (error.status === 401 || error.status === 403) throw error;
        return {...report, photo_error: error.message};
      }
    }));
  }
  async function listBriefings(id) {
    const site_id = contractSiteId(id);
    try {
      const briefing = mapper.briefing(await request('briefing', {params: {id: site_id}}), site_id);
      briefingCache.set(String(site_id), briefing);
      return [briefing];
    } catch (error) {
      if (error.status === 404) { briefingCache.delete(String(site_id)); return []; }
      throw error;
    }
  }
  async function readBriefing(id, briefingId) {
    const key = String(contractSiteId(id));
    if (!briefingCache.has(key)) await listBriefings(id);
    const briefing = briefingCache.get(key);
    if (!briefing || briefing.id !== briefingId) throw new Error('Only the latest briefing is available for this site.');
    return briefing;
  }
  function unsupported() { throw new Error('Briefing preferences are not part of API contract v1.1.'); }
  async function uploadReportPhoto(photo, requestId) {
    validateReportPhoto(photo);
    if (!photo) throw new Error('Choose a photo before requesting a suggestion.');
    const previous = requestId && uploads.get(requestId);
    if (previous?.photo === photo) return previous.photoKey;
    const active = requestId && inFlightUploads.get(requestId);
    if (active?.photo === photo) return active.promise;
    const promise = (async () => {
      const form = new FormData();
      form.append(settings.photoField || 'file', photo, photo.name || 'hazard-photo');
      const uploaded = await request('photos', {method: 'POST', body: form});
      if (typeof uploaded?.photo_key !== 'string' || !uploaded.photo_key) {
        throw new Error('The photo service did not return photo_key.');
      }
      return uploaded.photo_key;
    })();
    const entry = {photo, promise};
    if (requestId) inFlightUploads.set(requestId, entry);
    try {
      const photoKey = await promise;
      // A previous file's slower upload must not replace the selected file.
      if (requestId && inFlightUploads.get(requestId) === entry) {
        uploads.set(requestId, {photo, photoKey});
      }
      return photoKey;
    } finally {
      if (requestId && inFlightUploads.get(requestId) === entry) inFlightUploads.delete(requestId);
    }
  }
  async function prepareReportPhoto(photo, requestId) {
    const photoKey = await uploadReportPhoto(photo, requestId);
    try {
      const result = await request('photoSuggestion', {
        params: {photo_key: photoKey}, method: 'POST'
      });
      return {photo_key: photoKey, suggestion: result?.suggestion ?? null};
    } catch (error) {
      // Gemini is optional. Authentication failures still need a fresh sign-in.
      if (error.status === 401 || error.status === 403) throw error;
      return {photo_key: photoKey, suggestion: null};
    }
  }
  async function submitReport(report) {
    validateReportPhoto(report.photo);
    // Validate all metadata before uploading. A photo is optional; identity is server-owned.
    createHazardReportPayload(report);
    const key = report.request_id;
    if (key && receipts.has(key)) return receipts.get(key);
    if (key && uncertainReports.has(key)) throw new Error('The previous submission was not confirmed. Refresh the reports before submitting again; automatic retry could create a duplicate.');
    if (key && submissions.has(key)) return submissions.get(key);
    const pending = (async () => {
      let photoKey = null;
      if (report.photo) {
        photoKey = await uploadReportPhoto(report.photo, key);
        createHazardReportPayload(report, photoKey);
      }
      let raw;
      try { raw = await request('reports', {method: 'POST', body: createHazardReportPayload(report, photoKey)}); }
      catch (error) { if (key && error.ambiguousWrite) uncertainReports.add(key); throw error; }
      let receipt;
      try {
        receipt = mapReport(raw);
        if (receipt.site_id !== String(contractSiteId(report.site_id))) throw new Error('The saved report belongs to a different site.');
      } catch {
        if (key) uncertainReports.add(key);
        throw new Error('The server returned an invalid report receipt. Check the report list before submitting again.');
      }
      if (key) { receipts.set(key, receipt); uploads.delete(key); }
      return receipt;
    })();
    if (key) submissions.set(key, pending);
    try { return await pending; }
    finally { if (key) submissions.delete(key); }
  }
  function subscribeEvents(siteId, onEvent, onConnection) {
    return subscribeContractEvents({siteId: siteId === null ? null : String(contractSiteId(siteId)),
      getSource: getRealtimeSource,
      getToken, readSite, listSites, onEvent, onConnection,
      heartbeatMs: settings.heartbeatMs, timers: settings.timers || globalThis, retryBaseMs: settings.retryBaseMs});
  }
  return {listSites, readSite, listReports, prepareReportPhoto, submitReport, listBriefings, readBriefing,
    readPreferences: unsupported, savePreferences: unsupported, subscribeEvents};
}
