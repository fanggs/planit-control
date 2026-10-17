import {config} from './config.js';
import {createAuth} from './auth.js';
import {createAPI, createSampleAPI} from './api.js';
import {alertFeedDisplay, loadDashboardFeeds} from './feeds.js';
import {connectRealtime} from './realtime.js';
import {createDeepSpaceSource} from '../realtime/deepspace-source.js';
import {createRefreshQueue} from './refresh.js';
import {bindPageLifecycle, changeSelectedSite, markDetailStale} from './lifecycle.js';
import {assessScore, coordinates, countdown, finite, freshness, hasSupervisorRole, label, points,
  isReplayAlert, openReportPins, rankSites, riskTone, safeSourceURL, siteHasReplayAlert, siteTime, summaryScore,
  validFactors} from './domain.js';

const $ = id => document.getElementById(id);
const sample = config.mode === 'sample';
const state = {sites: [], alerts: null, selected: null, detail: null, detailStale: false,
  reports: [], search: '', filter: 'all'};
let api, auth, map, siteLayer, reportLayer, detailGeneration = 0;
let stopRealtime, poll, countdownTimer, user, resolving = false;
const photoURLs = new Set();
const siteMarkers = new Map();
const colors = {high: '#ffab94', medium: '#f1cf83', low: '#a1edcc', unknown: '#9cacb2'};

// All API/user text is inserted through textContent, including Leaflet popups.
function el(tag, text, className) {
  const node = document.createElement(tag);
  if (text !== undefined && text !== null) node.textContent = String(text);
  if (className) node.className = className;
  return node;
}
function chip(text, tone = 'unknown') { const node = el('span', text, 'planit-chip'); node.dataset.tone = tone; return node; }
function note(text, warning = false) { return el('p', text, `note${warning ? ' warning-note' : ''}`); }
function showError(error) { $('error').textContent = error.message || String(error); $('error').hidden = false; }
function clearError() { $('error').hidden = true; $('error').textContent = ''; }
function ageText(value) { return freshness(value, Date.now(), config.staleAfterMinutes).text; }
function section(title) { const node = el('section', null, 'detail-section'); node.append(el('h3', title)); return node; }
function revokePhotos() { for (const url of photoURLs) URL.revokeObjectURL(url); photoURLs.clear(); }
function staleDetailNotice() {
  const warning = note('Site detail and crew reports could not be refreshed. Showing last successful data; hazards and report status may have changed.', true);
  warning.dataset.detailStale = 'true';
  warning.setAttribute('role', 'status');
  return warning;
}

function initializeMap() {
  if (!window.L) { $('map-status').hidden = false; $('map-status').textContent = 'Map library unavailable. Use the ranked list to inspect sites.'; return; }
  map = window.L.map('map', {scrollWheelZoom: false}).setView([36.8, -97.6], 4);
  window.L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 18, attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
  }).on('tileerror', () => {
    $('map-status').hidden = false;
    $('map-status').textContent = 'Some basemap tiles could not load. Site markers and the list remain available.';
  }).addTo(map);
  siteLayer = window.L.layerGroup().addTo(map);
  reportLayer = window.L.layerGroup().addTo(map);
}
function fitMap() {
  if (!map) return;
  const coords = rankSites(state.sites, state).map(coordinates).filter(Boolean);
  if (coords.length) map.fitBounds(coords, {padding: [40, 40], maxZoom: 10});
}
function sitePopup(site) {
  const node = el('div');
  node.append(el('strong', site.name));
  const score = summaryScore(site);
  node.append(el('p', score === null ? 'No score data' : `${score.toFixed(1)} / 10 · 24-hour outlook`));
  node.append(el('p', score === null ? 'Missing data never means safe.' : factorSummary(site.top_factors)));
  if (site.active_alert) {
    node.append(el('p', `${site.active_alert.level === 'stop_work' ? 'STOP WORK' : 'Warning'} · ${label(site.active_alert.hazard_type)}`));
    if (siteHasReplayAlert(site, state.alerts)) node.append(chip('REPLAY · recorded lightning', 'medium'));
  }
  const button = el('button', 'View site details', 'planit-button');
  button.addEventListener('click', () => void selectSite(site.site_id));
  node.append(button);
  return node;
}
function renderMap(sites) {
  if (!map) return;
  siteLayer.clearLayers();
  siteMarkers.clear();
  for (const site of sites) {
    const position = coordinates(site);
    if (!position) continue;
    const selected = site.site_id === state.selected;
    const marker = window.L.circleMarker(position, {radius: selected ? 13 : 9, color: selected ? '#f5fff8' : '#152a27',
      weight: selected ? 3 : 2, fillColor: colors[riskTone(summaryScore(site))], fillOpacity: .95});
    marker.bindPopup(sitePopup(site));
    marker.on('click', () => {
      void selectSite(site.site_id, false);
      siteMarkers.get(site.site_id)?.openPopup();
    });
    marker.addTo(siteLayer);
    siteMarkers.set(site.site_id, marker);
  }
}
function renderReportPins() {
  if (!map) return;
  reportLayer.clearLayers();
  for (const report of openReportPins(state.reports)) {
    const position = coordinates(report);
    const content = el('div');
    content.append(el('strong', `${label(report.hazard_type)} · ${report.status}`), el('p', report.description));
    window.L.circleMarker(position, {radius: 6, color: '#add4ff', weight: 2, fillColor: '#1b3454', fillOpacity: 1})
      .bindPopup(content).addTo(reportLayer);
  }
}
function factorSummary(factors) {
  return validFactors(factors) && factors.length ? factors.map(factor => `${label(factor.hazard_type)} ${points(factor.contribution)}`).join(' · ')
    : 'Factor data unavailable';
}
function renderList() {
  const sites = rankSites(state.sites, state);
  const fragment = document.createDocumentFragment();
  sites.forEach((site, index) => {
    const button = el('button', null, 'site-item');
    button.setAttribute('aria-pressed', String(site.site_id === state.selected));
    const heading = el('div', null, 'site-title'), copy = el('div');
    copy.append(el('h3', `${String(index + 1).padStart(2, '0')}  ${site.name}`),
      el('div', `${site.state || 'State unknown'} · EIA ${site.site_id}`, 'site-state'));
    const value = summaryScore(site);
    const score = el('span', value === null ? 'No data' : value.toFixed(1), 'site-score');
    score.dataset.tone = riskTone(value);
    score.setAttribute('aria-label', value === null ? 'No score data' : `Score ${value.toFixed(1)} out of 10`);
    heading.append(copy, score);
    button.append(heading, el('p', value === null ? 'Score or explanation unavailable' : factorSummary(site.top_factors), 'site-factors'));
    const meta = el('div', null, 'site-meta');
    if (site.active_alert) {
      meta.append(chip(site.active_alert.level === 'stop_work' ? 'Stop work' : 'Warning', site.active_alert.level === 'stop_work' ? 'high' : 'medium'));
      if (siteHasReplayAlert(site, state.alerts)) meta.append(chip('REPLAY · recorded lightning', 'medium'));
    }
    if (site.open_report_count > 0) meta.append(chip(`${site.open_report_count} open report${site.open_report_count === 1 ? '' : 's'}`));
    if (!site.active_alert && !(site.open_report_count > 0)) meta.append(chip('No active alerts supplied'));
    button.append(meta, el('span', `${ageText(site.scored_at)} · ${siteTime(site.scored_at, site.timezone)}`, 'site-age'));
    button.addEventListener('click', () => void selectSite(site.site_id));
    fragment.append(button);
  });
  if (!sites.length) fragment.append(el('p', 'No sites match these filters. Try a different search.', 'empty'));
  $('site-list').replaceChildren(fragment);
  $('visible-count').textContent = `${sites.length} shown`;
  renderMap(sites);
}
function renderMetrics() {
  $('site-count').textContent = String(state.sites.length);
  $('site-subtitle').textContent = sample ? `${state.sites.length} sample sites · not production data` : 'Returned by the authenticated API';
  const alertDisplay = alertFeedDisplay(state.alerts);
  $('alert-count').textContent = alertDisplay.count;
  $('alert-status').textContent = alertDisplay.status;
  const complete = state.sites.every(site => Number.isInteger(site.open_report_count) && site.open_report_count >= 0);
  $('report-count').textContent = complete ? String(state.sites.reduce((sum, site) => sum + site.open_report_count, 0)) : 'No data';
  $('missing-count').textContent = String(state.sites.filter(site => summaryScore(site) === null).length);
}
function renderScore(detail) {
  const container = section('Why this site has this score');
  const model = detail.score, analysis = assessScore(model, detail.site_id);
  if (analysis.status !== 'ready') {
    container.append(note(analysis.message, true));
    return container;
  }
  const head = el('div', null, 'score-header'), total = el('div', model.score.toFixed(1), 'score-total');
  total.append(el('small', '/ 10'));
  head.append(total, el('div', `${model.horizon_hours ?? 'Unknown'}-hour forecast risk\nBaseline + signed factors`, 'score-label'));
  container.append(head);
  const graph = el('div', null, 'waterfall'); graph.setAttribute('aria-label', 'Hazard score waterfall');
  for (const step of analysis.steps) {
    const row = el('div', null, 'water-row'), track = el('div', null, 'water-track');
    const bar = el('span', null, 'water-bar'); bar.dataset.kind = step.kind;
    bar.style.left = `${(Math.min(step.start, step.end) - analysis.min) / (analysis.max - analysis.min) * 100}%`;
    bar.style.width = `${Math.abs(step.end - step.start) / (analysis.max - analysis.min) * 100}%`;
    bar.setAttribute('aria-hidden', 'true'); track.append(bar);
    row.title = `${step.name}: ${step.start.toFixed(2)} → ${step.end.toFixed(2)}`;
    row.append(el('span', step.name), track, el('span', ['baseline', 'total'].includes(step.kind) ? step.value.toFixed(1) : points(step.value), 'water-value'));
    graph.append(row);
  }
  const axis = el('div', null, 'water-axis');
  axis.append(el('span', analysis.min.toFixed(0)), el('span', ((analysis.min + analysis.max) / 2).toFixed(0)), el('span', analysis.max.toFixed(0)));
  graph.append(axis);
  container.append(graph, el('p', 'Peach adds risk · Mint lowers risk · Values rounded for display', 'water-legend'),
    note(`Scored ${siteTime(model.scored_at, detail.timezone)} · ${ageText(model.scored_at)}`),
    note(model.model_version === 'sample' ? 'SAMPLE score — not a live trained-model result.' : `Model: ${model.model_version || 'Version unavailable'}`),
    note(`Input observation time: ${model.inputs_observed_at ? siteTime(model.inputs_observed_at, detail.timezone) : 'Not supplied by API'}`),
    note('Crew reports appear separately and do not change this score. Live lightning stop-work rules apply independently.'));
  return container;
}
function renderAlerts(detail) {
  const container = section(`Site alerts · ${detail.active_alerts.length}`);
  for (const alert of detail.active_alerts) {
    const card = el('article', null, `alert-card${alert.level === 'stop_work' ? ' stop' : ''}`);
    card.append(chip(`${alert.level === 'stop_work' ? 'STOP WORK' : 'Warning'} · ${label(alert.hazard_type)}`,
      alert.level === 'stop_work' ? 'high' : 'medium'), el('p', alert.message));
    if (isReplayAlert(alert)) card.append(chip('REPLAY · recorded lightning', 'medium'));
    if (alert.hazard_type === 'lightning' && alert.level === 'stop_work') {
      const clock = el('p', countdown(alert.clear_at), 'countdown');
      clock.dataset.clearAt = alert.clear_at || ''; card.append(clock);
      if (sample) card.append(chip('SAMPLE alert'));
      card.append(note('Continue the stop-work instruction until the server clears the alert.'));
    }
    card.append(note(`Started ${siteTime(alert.started_at, detail.timezone)}`));
    container.append(card);
  }
  if (!detail.active_alerts.length) container.append(note('No active alerts returned. This is not confirmation that conditions are safe.'));
  container.append(note('Lightning feed health is not supplied by contract v1.1. Its availability cannot be confirmed from an empty alert list.', true));
  for (const event of detail.environmental_events || []) {
    container.append(note(`${label(event.hazard_type)}: ${event.title} · ${siteTime(event.starts_at, detail.timezone)}`));
  }
  return container;
}
function renderWeather(detail) {
  const container = section('Latest conditions'), grid = el('div', null, 'weather-grid'), weather = detail.latest_weather;
  const fields = [['Temperature', 'temperature_f', '°F'], ['Heat index', 'heat_index_f', '°F'], ['Wind', 'wind_mph', 'mph'],
    ['Rain · 24 h', 'precip_24h_in', 'in'], ['Rain · 1 h', 'precip_1h_in', 'in'], ['Soil moisture', 'soil_moisture', 'm³/m³']];
  for (const [name, key, unit] of fields) {
    const reading = el('div', null, 'weather-reading');
    reading.append(el('span', name), el('strong', finite(weather?.[key]) ? `${weather[key]} ${unit}` : 'No data')); grid.append(reading);
  }
  container.append(grid, note(`Observed ${siteTime(weather?.observed_at, detail.timezone)} · ${ageText(weather?.observed_at)}`));
  const source = safeSourceURL(weather?.source_url);
  if (source) { const link = el('a', weather.source_name || 'Weather source', 'note'); link.href = source; link.target = '_blank'; link.rel = 'noopener noreferrer'; container.append(link); }
  return container;
}
function renderReports(detail) {
  const container = section(`Crew observations · ${state.reports.length}`);
  container.append(note('Open high-severity reports create warnings. Resolving a report clears its warning, not an independent lightning alert.'));
  for (const report of state.reports) {
    const card = el('article', null, 'report-card');
    const meta = el('div', null, 'site-meta');
    meta.append(chip(label(report.hazard_type)), chip(`${report.severity} severity`, report.severity === 'high' ? 'high' : report.severity === 'medium' ? 'medium' : 'unknown'), chip(report.status));
    card.append(meta, el('p', report.description), note(`Reported ${siteTime(report.created_at, detail.timezone)}`));
    if (report.resolved_at) card.append(note(`Resolved ${siteTime(report.resolved_at, detail.timezone)}`));
    if (!coordinates(report)) card.append(note('No report coordinates supplied; no report pin can be shown.'));
    const actions = el('div', null, 'report-actions');
    if (report.photo_key) {
      const photo = el('button', sample ? 'Sample photo unavailable' : 'View private photo', 'planit-button');
      photo.disabled = sample;
      photo.addEventListener('click', async () => {
        photo.disabled = true; photo.textContent = 'Loading photo…';
        try {
          const blob = await api.photo(report.photo_key);
          if (!card.isConnected) return;
          const objectURL = URL.createObjectURL(blob); photoURLs.add(objectURL);
          const image = el('img', null, 'report-photo'); image.src = objectURL;
          image.alt = `Crew photograph for ${label(report.hazard_type).toLowerCase()} report`;
          card.append(image); photo.hidden = true;
        } catch (error) { showError(error); photo.disabled = false; photo.textContent = 'Retry private photo'; }
      });
      actions.append(photo);
    }
    if (report.status === 'open') {
      const resolve = el('button', sample ? 'Resolve · live mode only' : 'Resolve report', 'planit-button primary');
      resolve.disabled = sample || resolving || !hasSupervisorRole(user, config.auth.rolesClaim);
      resolve.addEventListener('click', () => void resolveReport(report.id, resolve));
      actions.append(resolve);
    }
    card.append(actions); container.append(card);
  }
  if (!state.reports.length) container.append(note('No crew reports returned for this site.'));
  return container;
}
function renderDetail() {
  revokePhotos();
  const detail = state.detail;
  if (!detail) return;
  const header = el('div', null, 'detail-head');
  header.append(el('div', 'Selected site', 'planit-eyebrow'), el('h2', detail.name),
    el('p', `${detail.utility || 'Utility unavailable'} · ${detail.county || ''} ${detail.state || ''} · EIA ${detail.site_id}`));
  if (sample || detail.score?.model_version === 'sample') header.append(chip('SAMPLE DATA', 'medium'));
  $('detail').replaceChildren(...(state.detailStale ? [staleDetailNotice()] : []),
    header, renderScore(detail), renderAlerts(detail), renderWeather(detail), renderReports(detail));
  renderReportPins();
}
async function loadDetail(id) {
  const generation = ++detailGeneration;
  $('detail').setAttribute('aria-busy', 'true');
  try {
    const [detail, reports] = await Promise.all([api.detail(id), api.reports(id)]);
    if (generation !== detailGeneration || state.selected !== id) return;
    state.detail = detail; state.reports = reports; state.detailStale = false; renderDetail();
  } catch (error) {
    if (generation === detailGeneration && state.selected === id) {
      if (markDetailStale(state, id)) {
        const panel = $('detail');
        if (!panel.querySelector('[data-detail-stale]')) panel.prepend(staleDetailNotice());
      } else {
        $('detail').replaceChildren(el('p', 'Site detail unavailable. Use Refresh to retry.', 'empty'));
      }
    }
    throw error;
  } finally { if (generation === detailGeneration) $('detail').setAttribute('aria-busy', 'false'); }
}
function updateSelection(id) {
  if (!changeSelectedSite(state, id)) return;
  detailGeneration++; // Invalidate any response from the previous selection.
  revokePhotos(); reportLayer?.clearLayers();
  $('detail').replaceChildren(el('p', id === null ? 'The API returned no sites.' : 'Loading site details…', 'empty'));
}
async function selectSite(id, pan = true) {
  updateSelection(id);
  renderList();
  if (pan && map) { const position = coordinates(state.sites.find(site => site.site_id === id)); if (position) map.panTo(position); }
  try { await loadDetail(id); }
  catch (error) {
    if (state.selected === id) showError(error);
  }
}
async function fetchData() {
  $('refresh').disabled = true;
  try {
    const {sites, alerts} = await loadDashboardFeeds(api);
    state.sites = sites; state.alerts = alerts;
    if (!sites.some(site => site.site_id === state.selected)) updateSelection(rankSites(sites)[0]?.site_id ?? null);
    renderMetrics(); renderList();
    if (state.selected !== null) await loadDetail(state.selected);
    else { state.detail = null; state.reports = []; revokePhotos(); reportLayer?.clearLayers(); $('detail').replaceChildren(el('p', 'The API returned no sites.', 'empty')); }
    $('updated').textContent = `Fetched ${new Date().toLocaleTimeString([], {hour: 'numeric', minute: '2-digit', second: '2-digit'})}`;
    if (alerts === null) showError(new Error('Alert feed unavailable. The site map is still available, but do not infer safety from missing alerts.'));
    else clearError();
  } finally { $('refresh').disabled = false; }
}
const refresh = createRefreshQueue(fetchData);
async function resolveReport(id, button) {
  if (sample || resolving || !hasSupervisorRole(user, config.auth.rolesClaim)) return;
  resolving = true; button.disabled = true; button.textContent = 'Resolving…';
  try {
    await api.resolve(id);
    // Never claim success before the response. Reload map counts, warnings and report status.
    await refresh();
  } catch (error) { showError(error); }
  finally {
    resolving = false;
    if (state.detail) renderDetail();
    else if (button.isConnected) { button.disabled = false; button.textContent = 'Resolve report'; }
  }
}
async function start() {
  initializeMap();
  $('search').addEventListener('input', event => { state.search = event.target.value; renderList(); });
  document.querySelectorAll('[data-filter]').forEach(button => button.addEventListener('click', () => {
    state.filter = button.dataset.filter;
    document.querySelectorAll('[data-filter]').forEach(item => item.setAttribute('aria-pressed', String(item === button)));
    renderList();
  }));
  $('fit-map').addEventListener('click', fitMap);
  $('refresh').addEventListener('click', () => void refresh().catch(showError));
  if (sample) {
    $('identity').textContent = 'Sample workspace';
    $('mode-banner').textContent = 'SAMPLE PREVIEW · Exact fixtures from the team API. These are demonstration sites, scores and alerts; they must not guide field work. Report actions are read-only.';
    $('connection').textContent = 'Sample data · no live connection';
    api = await createSampleAPI();
  } else if (config.mode === 'live') {
    $('mode-banner').textContent = 'LIVE API MODE · Lightning feed health is not included in v1.1; an empty alert list cannot confirm that lightning data is available.';
    auth = createAuth(config.auth);
    user = await auth.initialize();
    const action = $('auth-action'); action.hidden = false;
    if (!user) {
      $('identity').textContent = 'Sign-in required'; $('connection').textContent = 'Not connected';
      action.textContent = 'Sign in'; action.addEventListener('click', () => void auth.login().catch(showError));
      $('site-list').replaceChildren(el('p', 'Sign in with your supervisor account to load the live workspace.', 'empty'));
      return;
    }
    $('identity').textContent = user.name || 'Signed-in user';
    action.textContent = 'Sign out'; action.addEventListener('click', () => void auth.logout().catch(showError));
    if (!hasSupervisorRole(user, config.auth.rolesClaim)) throw new Error('A supervisor role is required for this workspace. Ask the Auth0 administrator to configure the agreed role claim.');
    api = createAPI({base: config.apiBase, token: auth.token, timeoutMs: config.requestTimeoutMs});
    $('connection').textContent = 'Connecting to API…';
  } else { throw new Error('Unknown mode in config.js. Choose sample or live.'); }
  await refresh().catch(showError); fitMap();
  countdownTimer = setInterval(() => document.querySelectorAll('[data-clear-at]').forEach(node => { node.textContent = countdown(node.dataset.clearAt); }), 1000);
  if (!sample) {
    stopRealtime = connectRealtime({getSource: () => createDeepSpaceSource(config.realtime), getToken: auth.token,
      onInvalidate: refresh, onStatus(connected) {
        $('connection').dataset.connected = String(connected);
        $('connection').textContent = connected ? 'Live events connected' : 'Polling · live events unavailable';
      }});
    // Polling also recovers missed events. A successful fetch is never presented as a live socket.
    poll = setInterval(() => void refresh().catch(showError), config.pollMs);
  }
}
bindPageLifecycle({browser: window, onHide() {
  stopRealtime?.(); clearInterval(poll); clearInterval(countdownTimer); revokePhotos();
  $('connection').dataset.connected = 'false';
  $('connection').textContent = 'Workspace paused · refresh required';
}});
void start().catch(error => { $('connection').textContent = 'Not connected'; showError(error); });
