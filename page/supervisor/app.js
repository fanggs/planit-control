import {config} from './config.js';
import {createAuth, shouldResumeSignIn} from './auth.js';
import {createAPI, createSampleAPI} from './api.js';
import {alertFeedDisplay, loadDashboardFeeds} from './feeds.js';
import {connectRealtime} from './realtime.js';
import {createDeepSpaceSource} from '../realtime/deepspace-source.js';
import {createRefreshQueue} from './refresh.js';
import {createPhotoCache} from './photo-cache.js';
import {bindPageLifecycle, changeSelectedSite, markDetailStale} from './lifecycle.js';
import {detailScreeningStatus, screeningAvailability, screeningAvailabilityChanged, updateWatchChips} from './status-clock.js';
import {isSessionExpired} from '../shared/auth-session.mjs';
import {clearResumeHint, hasResumeHint, markAuthenticated} from '../shared/auth-resume.mjs';
import {heatIndexDisplay} from '../shared/environment-readings.mjs';
import {assessScore, coordinates, countdown, featureLabel, finite, freshness, hasSupervisorRole, label,
  lightningDisplay, points, isReplayAlert, openReportPins, rankSites, riskTone, safeSourceURL,
  siteHasReplayAlert, siteTime, speciesName, summaryScreening, validFactors, warningsDisplay, wildlifeSummary} from './domain.js';

const $ = id => document.getElementById(id);
const sample = config.mode === 'sample';
const state = {sites: [], alerts: null, selected: null, detail: null, detailStale: false,
  reports: [], search: '', filter: 'all'};
let api, auth, map, siteLayer, reportLayer, detailGeneration = 0, photoGeneration = 0;
let stopRealtime, poll, countdownTimer, user, resolving = false;
let sessionExpired = false;
let renderedScreening = new Map();
const photos = createPhotoCache();
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
function watchChip(text, tone, kind, siteId, scope = 'summary') {
  const node = chip(text, tone);
  node.dataset.watchKind = kind;
  node.dataset.watchSiteId = String(siteId);
  node.dataset.watchScope = scope;
  return node;
}
function note(text, warning = false) { return el('p', text, `note${warning ? ' warning-note' : ''}`); }
function expireSession() {
  if (sessionExpired) return;
  sessionExpired = true;
  stopRealtime?.(); stopRealtime = null;
  clearInterval(poll); poll = null;
  clearResumeHint();
  detailGeneration++; // An in-flight detail response must not restore private report data.
  state.reports = [];
  revokePhotos(); reportLayer?.clearLayers();
  setAskControls(false);
  $('refresh').disabled = true;
  $('connection').dataset.connected = 'false';
  $('connection').textContent = 'Sign-in expired · live updates paused';
  $('auth-action').textContent = 'Sign in again';
  $('error').textContent = 'Your sign-in expired. Sign in again to see live alerts and current site data. The last displayed data may be out of date.';
  $('error').hidden = false;
  if (state.detail) { state.detailStale = true; renderDetail(); }
}
function showError(error) {
  if (isSessionExpired(error)) { expireSession(); return; }
  if (sessionExpired) return;
  $('error').textContent = error.message || String(error); $('error').hidden = false;
}
function clearError() { if (sessionExpired) return; $('error').hidden = true; $('error').textContent = ''; }
function setAskControls(enabled) {
  $('ask-question').disabled = !enabled;
  $('ask-submit').disabled = !enabled;
  document.querySelectorAll('[data-ask-example]').forEach(button => { button.disabled = !enabled; });
  $('ask-panel').setAttribute('aria-busy', String(!enabled && Boolean(api) && !sample));
}
function askFailureText(error) {
  if (error.status === 503 || error.code === 'service_unavailable') return 'The question service is temporarily unavailable. Site data and safety alerts remain separate; please try again later.';
  if (error.code === 'timeout') return 'The question took longer than 30 seconds. Please try a simpler question.';
  if (error.status === 401 || error.status === 403) return 'Your session cannot use the question service. Sign out and sign in again with a supervisor account.';
  if (error.status === 422) return 'The question was rejected. Please use between 3 and 500 characters.';
  return error.message || 'The question could not be answered right now.';
}
function renderAskResult(result) {
  const panel = $('ask-result');
  panel.replaceChildren();
  if (result.answer === null) {
    panel.append(el('p', 'The available data cannot answer that question. Try asking about our plants, weather, forecasts, alerts or hazard scores.', 'ask-unanswered'));
    $('ask-status').textContent = 'No answer from the available data.';
  } else {
    panel.append(el('h3', 'Answer'), el('p', result.answer, 'ask-answer'));
    const sources = el('div', null, 'ask-sources');
    sources.append(el('h4', 'Sources'));
    if (result.sources.length) {
      const list = el('ul');
      for (const source of result.sources) {
        const item = el('li'), url = safeSourceURL(source.url);
        if (url) {
          const link = el('a', source.label || 'Source');
          link.href = url; link.target = '_blank'; link.rel = 'noopener noreferrer';
          item.append(link);
        } else item.textContent = `${source.label || 'Source'} · link unavailable`;
        list.append(item);
      }
      sources.append(list);
    } else sources.append(el('p', 'No source links were returned. Review the query before relying on this answer.'));
    panel.append(sources);
    const query = el('details', null, 'ask-query');
    query.append(el('summary', 'View read-only SQL used for this answer'), el('pre', result.sql));
    panel.append(query);
    $('ask-status').textContent = 'Answer loaded. Review its sources and query.';
  }
  panel.hidden = false;
}
async function submitAsk() {
  if (sample || !api || !hasSupervisorRole(user, config.auth.rolesClaim) || $('ask-submit').disabled) return;
  const question = $('ask-question').value.trim();
  $('ask-error').hidden = true; $('ask-error').textContent = '';
  if (question.length < 3 || question.length > 500) {
    $('ask-error').textContent = 'Enter a question between 3 and 500 characters.';
    $('ask-error').hidden = false; $('ask-question').focus();
    return;
  }
  $('ask-result').hidden = true;
  $('ask-result').replaceChildren();
  $('ask-status').textContent = 'Checking the available records…';
  setAskControls(false);
  try {
    renderAskResult(await api.ask(question));
  } catch (error) {
    if (isSessionExpired(error)) { showError(error); return; }
    $('ask-error').textContent = askFailureText(error);
    $('ask-error').hidden = false;
    $('ask-status').textContent = 'No answer was returned.';
  } finally { setAskControls(!sessionExpired); }
}
function bindAsk() {
  $('ask-form').addEventListener('submit', event => { event.preventDefault(); void submitAsk(); });
  document.querySelectorAll('[data-ask-example]').forEach(button => button.addEventListener('click', () => {
    $('ask-question').value = button.dataset.askExample;
    $('ask-question').focus();
  }));
}
function ageText(value) { return freshness(value, Date.now(), config.staleAfterMinutes).text; }
function section(title) { const node = el('section', null, 'detail-section'); node.append(el('h3', title)); return node; }
function shownSummary(site) { return summaryScreening(site, Date.now(), sample); }
function shownSummaryScore(site) { return shownSummary(site).score; }
function summaryLightning(site) {
  const stopWork = site.active_alert?.hazard_type === 'lightning' && site.active_alert.level === 'stop_work';
  return lightningDisplay(site.lightning_status, Date.now(), stopWork);
}
const SCREENING_TARGET = 'How likely a National Weather Service warning or heat advisory is here in the next 24 hours';
function sourceLink(record, fallback) {
  const source = safeSourceURL(record?.source_url);
  if (!source) return null;
  const link = el('a', record.source_name || fallback, 'note');
  link.href = source; link.target = '_blank'; link.rel = 'noopener noreferrer';
  return link;
}
function revokePhotos() { photoGeneration++; photos.clear(); }
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
  const coords = rankSites(state.sites, {...state, allowHistorical: sample}).map(coordinates).filter(Boolean);
  if (coords.length) map.fitBounds(coords, {padding: [40, 40], maxZoom: 10});
}
function sitePopup(site) {
  const node = el('div');
  node.append(el('strong', site.name));
  const score = shownSummaryScore(site);
  node.append(el('p', score === null ? 'Screening index unavailable' : `Prototype · ${score.toFixed(1)} / 10`));
  node.append(el('p', score === null ? 'No score right now. That doesn’t mean it’s safe.' : `${SCREENING_TARGET}. Open the site for details.`));
  if (score !== null) node.append(el('p', factorSummary(site.top_factors)));
  const lightning = summaryLightning(site);
  node.append(watchChip(lightning.text, lightning.status === 'stop_work' ? 'high' : lightning.status === 'clear' ? 'low' : 'unknown',
    'lightning', site.site_id));
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
      weight: selected ? 3 : 2, fillColor: colors[riskTone(shownSummaryScore(site))], fillOpacity: .95});
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
  return validFactors(factors) && factors.length ? factors.map(factor => `${featureLabel(factor.feature)} ${points(factor.contribution)}`).join(' · ')
    : 'Factor data unavailable';
}
function renderList() {
  const sites = rankSites(state.sites, {...state, allowHistorical: sample});
  const fragment = document.createDocumentFragment();
  sites.forEach((site, index) => {
    const button = el('button', null, 'site-item');
    button.setAttribute('aria-pressed', String(site.site_id === state.selected));
    const heading = el('div', null, 'site-title'), copy = el('div');
    copy.append(el('h3', `${String(index + 1).padStart(2, '0')}  ${site.name}`),
      el('div', `${site.state || 'State unknown'} · EIA ${site.site_id}`, 'site-state'));
    const screening = shownSummary(site), value = screening.score;
    const score = el('span', value === null ? 'No data' : value.toFixed(1), 'site-score');
    score.dataset.tone = riskTone(value);
    score.setAttribute('aria-label', value === null ? 'No screening index data' : `Prototype screening index ${value.toFixed(1)} out of 10`);
    heading.append(copy, score);
    button.append(heading, el('p', value === null ? 'Screening unavailable · missing data never means safe'
      : `${SCREENING_TARGET}. Open the site for details.`, 'site-factors'));
    if (value !== null) button.append(el('p', factorSummary(site.top_factors), 'site-factors'));
    const meta = el('div', null, 'site-meta');
    if (value !== null) meta.append(chip('Prototype', 'medium'));
    if (site.active_alert) {
      meta.append(chip(site.active_alert.level === 'stop_work' ? 'Stop work' : 'Warning', site.active_alert.level === 'stop_work' ? 'high' : 'medium'));
      if (siteHasReplayAlert(site, state.alerts)) meta.append(chip('REPLAY · recorded lightning', 'medium'));
    }
    if (site.open_report_count > 0) meta.append(chip(`${site.open_report_count} open report${site.open_report_count === 1 ? '' : 's'}`));
    const lightning = summaryLightning(site);
    meta.append(watchChip(lightning.text, lightning.status === 'stop_work' ? 'high' : lightning.status === 'clear' ? 'low' : 'unknown',
      'lightning', site.site_id));
    button.append(meta, el('span', value === null ? `Screening status: ${screening.status.replaceAll('_', ' ')}`
      : `${ageText(site.scored_at)} · ${siteTime(site.scored_at, site.timezone)}`, 'site-age'));
    button.addEventListener('click', () => void selectSite(site.site_id));
    fragment.append(button);
  });
  if (!sites.length) fragment.append(el('p', 'No sites match these filters. Try a different search.', 'empty'));
  $('site-list').replaceChildren(fragment);
  $('visible-count').textContent = `${sites.length} shown`;
  renderedScreening = screeningAvailability(state.sites, Date.now(), sample);
  renderMap(sites);
}
function renderMetrics() {
  $('site-count').textContent = String(state.sites.length);
  $('site-subtitle').textContent = sample ? `${state.sites.length} sample sites · not production data` : 'Plants we monitor';
  const alertDisplay = alertFeedDisplay(state.alerts);
  $('alert-count').textContent = alertDisplay.count;
  $('alert-status').textContent = alertDisplay.status;
  const complete = state.sites.every(site => Number.isInteger(site.open_report_count) && site.open_report_count >= 0);
  $('report-count').textContent = complete ? String(state.sites.reduce((sum, site) => sum + site.open_report_count, 0)) : 'No data';
  $('missing-count').textContent = String(state.sites.filter(site => shownSummaryScore(site) === null).length);
}
function renderScore(detail) {
  const container = section('Hazard score (early-stage estimate)');
  const model = detail.screening, analysis = assessScore(model, Date.now(), sample);
  container.dataset.screeningStatus = analysis.status;
  if (analysis.status !== 'ready') {
    container.append(note(`No screening score · ${analysis.message} Missing data is not a zero or an all-clear.`, true));
    return container;
  }
  const head = el('div', null, 'score-header'), total = el('div', model.score.toFixed(1), 'score-total');
  total.append(el('small', '/ 10'));
  head.append(total, el('div', 'Chance of a weather warning or heat advisory in the next 24 hours', 'score-label'));
  container.append(head, chip('Prototype', 'medium'),
    note(model.status === 'research' ? 'Early-stage model that hasn’t passed all its accuracy checks yet. A low score doesn’t mean it’s safe. Always follow active alerts.'
      : 'Early-stage model that passed its accuracy checks. It doesn’t predict injuries, and a low score doesn’t mean it’s safe.', true),
    note('What this score means: how likely the National Weather Service is to issue a warning or heat advisory for this plant, from 0 (very unlikely) to 10 (very likely).'),
    note(`Covers ${siteTime(model.valid_from, detail.timezone)} to ${siteTime(model.valid_until, detail.timezone)}`));
  const graph = el('div', null, 'waterfall'); graph.setAttribute('aria-label', 'Prototype screening feature-contribution waterfall');
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
  container.append(graph, el('p', 'Orange pushed the score up, green pulled it down.', 'water-legend'),
    note(`Scored ${siteTime(model.scored_at, detail.timezone)} · ${ageText(model.scored_at)}`),
    note(`Weather data from ${siteTime(model.captured_at, detail.timezone)}`),
    note(sample ? 'SAMPLE screening result — demonstration data only.'
      : `Model version: ${typeof model.artifact_sha256 === 'string' ? `${model.artifact_sha256.slice(0, 12)}…` : 'Not supplied'}`),
    note('Crew reports don’t change this score, and a low score never cancels a lightning stop-work.'));
  return container;
}
function renderWildlife(detail) {
  const container = section('Dangerous animals seen nearby');
  const context = detail.wildlife_context;
  container.append(note(wildlifeSummary(context)));
  if (!context || !Array.isArray(context.sightings) || context.status === 'unavailable') return container;
  if (finite(context.radius_km)) container.append(note(`Past sightings within ${context.radius_km} km (${Math.round(context.radius_km * 0.621)} mi). They show what lives in the area, not what’s here today.`));
  if (context.limitations) container.append(note('Not seeing an animal listed doesn’t mean there are none; records depend on where people report.', true));
  for (const sighting of context.sightings.slice(0, 5)) {
    const card = el('article', null, 'wildlife-card');
    card.append(el('strong', speciesName(sighting.species)),
      note(`Seen ${siteTime(sighting.observed_at, detail.timezone)}${finite(sighting.distance_km) ? ` · ${sighting.distance_km.toFixed(1)} km (${(sighting.distance_km * 0.621).toFixed(1)} mi) away` : ''}`));
    const source = sourceLink({...sighting, source_name: 'GBIF sighting record'}, 'GBIF sighting record');
    if (source) card.append(source);
    container.append(card);
  }
  if (context.sightings.length > 5) container.append(note(`Showing 5 of ${context.sightings.length} sightings.`));
  container.append(note('Sightings don’t change the hazard score. Crew reports of animals seen today appear below.'));
  return container;
}
function renderAlerts(detail) {
  const container = section(`Site alerts · ${detail.active_alerts.length}`);
  const stopWork = detail.active_alerts.some(alert => alert.hazard_type === 'lightning' && alert.level === 'stop_work');
  const lightning = lightningDisplay(detail.lightning_status, Date.now(), stopWork);
  container.append(watchChip(lightning.text, lightning.status === 'stop_work' ? 'high' : lightning.status === 'clear' ? 'low' : 'unknown',
    'lightning', detail.site_id, 'detail'));
  if (lightning.status === 'unknown') container.append(note(detail.lightning_status?.reason || 'The lightning watch could not confirm current conditions.', true));
  if (lightning.status === 'clear') container.append(note('No strikes within 10 miles in the last 30 minutes. Check the other conditions too.'));
  container.append(note(`Lightning checked ${siteTime(detail.lightning_status?.checked_at, detail.timezone)}`));
  const lightningSource = sourceLink(detail.lightning_status, 'Lightning source');
  if (lightningSource) container.append(lightningSource);
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
  if (!detail.active_alerts.length) container.append(note('No alerts at this site right now. Still check conditions before work.'));
  const warnings = warningsDisplay(detail.warnings_status, detail.environmental_events);
  container.append(watchChip(warnings.text, warnings.status === 'ok' ? 'low' : 'unknown',
    'warnings', detail.site_id, 'detail'));
  if (warnings.status === 'unknown') container.append(note('NWS coverage has not been confirmed recently; the event list may be incomplete.', true));
  container.append(note(`NWS checked ${siteTime(detail.warnings_status?.checked_at, detail.timezone)}`));
  const nwsSource = sourceLink(detail.warnings_status, 'National Weather Service');
  if (nwsSource) container.append(nwsSource);
  for (const event of detail.environmental_events || []) {
    const upcoming = Date.parse(event.starts_at) > Date.now();
    const row = el('div', null, 'event-row');
    row.append(note(`${upcoming ? 'Starting ' + siteTime(event.starts_at, detail.timezone) : 'In effect'}: ${String(event.title || 'Weather alert').split(' issued ')[0]}${event.ends_at ? ` · until ${siteTime(event.ends_at, detail.timezone)}` : ''}`));
    const link = sourceLink(event, 'Event source');
    if (link) row.append(link);
    container.append(row);
  }
  return container;
}
function renderWeather(detail) {
  const container = section('Latest conditions'), grid = el('div', null, 'weather-grid'), weather = detail.latest_weather;
  const fields = [['Temperature', 'temperature_f', '°F'], ['Heat index', 'heat_index_f', '°F'], ['Wind', 'wind_mph', 'mph'],
    ['Rain · 24 h', 'precip_24h_in', 'in'], ['Rain · 1 h', 'precip_1h_in', 'in'], ['Soil moisture', 'soil_moisture', 'm³/m³']];
  for (const [name, key, unit] of fields) {
    const reading = el('div', null, 'weather-reading');
    const value = key === 'heat_index_f' ? heatIndexDisplay(weather)
      : finite(weather?.[key]) ? `${weather[key]} ${unit}` : 'No data';
    reading.append(el('span', name), el('strong', value)); grid.append(reading);
  }
  container.append(grid, note(`Observed ${siteTime(weather?.observed_at, detail.timezone)} · ${ageText(weather?.observed_at)}`));
  const source = safeSourceURL(weather?.source_url);
  if (source) { const link = el('a', weather.source_name || 'Weather source', 'note'); link.href = source; link.target = '_blank'; link.rel = 'noopener noreferrer'; container.append(link); }
  return container;
}
function renderReports(detail) {
  const container = section(`Crew observations · ${state.reports.length}`);
  if (sessionExpired) {
    container.append(note('Sign in again to view crew reports and private photos.', true));
    return container;
  }
  container.append(note('A high-severity report creates a warning for the crew. Resolving the report clears that warning (not a lightning stop-work).'));
  for (const report of state.reports) {
    const card = el('article', null, 'report-card');
    const meta = el('div', null, 'site-meta');
    meta.append(chip(label(report.hazard_type)), chip(`${report.severity} severity`, report.severity === 'high' ? 'high' : report.severity === 'medium' ? 'medium' : 'unknown'), chip(report.status));
    card.append(meta, el('p', report.description), note(`Reported ${siteTime(report.created_at, detail.timezone)}`));
    if (report.resolved_at) card.append(note(`Resolved ${siteTime(report.resolved_at, detail.timezone)}`));
    if (!coordinates(report)) card.append(note('No report coordinates supplied; no report pin can be shown.'));
    const actions = el('div', null, 'report-actions');
    if (report.photo_key) {
      const showPhoto = objectURL => {
        const image = el('img', null, 'report-photo'); image.src = objectURL;
        image.alt = `Crew photograph for ${label(report.hazard_type).toLowerCase()} report`;
        card.append(image);
      };
      const cached = photos.get(report.photo_key);
      if (cached) showPhoto(cached);
      else {
        const photo = el('button', sample ? 'Sample photo unavailable' : 'View private photo', 'planit-button');
        photo.disabled = sample;
        photo.addEventListener('click', async () => {
          photo.disabled = true; photo.textContent = 'Loading photo…';
          const selected = state.selected;
          const generation = photoGeneration;
          try {
            const blob = await api.photo(report.photo_key);
            if (photoGeneration !== generation || state.selected !== selected
              || !state.reports.some(item => item.photo_key === report.photo_key)) return;
            const objectURL = photos.remember(report.photo_key, blob);
            if (card.isConnected) { showPhoto(objectURL); photo.hidden = true; }
            else renderDetail(); // A routine refresh replaced the card while the photo loaded.
          } catch (error) {
            if (card.isConnected) { showError(error); photo.disabled = false; photo.textContent = 'Retry private photo'; }
          }
        });
        actions.append(photo);
      }
    }
    if (report.status === 'open') {
      const resolve = el('button', sample ? 'Resolve · live mode only' : 'Resolve report', 'planit-button primary');
      resolve.disabled = sample || sessionExpired || resolving || !hasSupervisorRole(user, config.auth.rolesClaim);
      resolve.addEventListener('click', () => void resolveReport(report.id, resolve));
      actions.append(resolve);
    }
    card.append(actions); container.append(card);
  }
  if (!state.reports.length) container.append(note('No crew reports returned for this site.'));
  return container;
}
function renderDetail() {
  const detail = state.detail;
  if (!detail) return;
  photos.retain(state.reports.map(report => report.photo_key).filter(Boolean));
  const header = el('div', null, 'detail-head');
  header.append(el('div', 'Selected site', 'planit-eyebrow'), el('h2', detail.name),
    el('p', `${detail.utility || 'Utility unavailable'} · ${detail.county || ''} ${detail.state || ''} · EIA ${detail.site_id}`));
  if (sample) header.append(chip('SAMPLE DATA', 'medium'));
  const scorePanel = renderScore(detail);
  $('detail').dataset.screeningStatus = scorePanel.dataset.screeningStatus;
  const next = document.createElement('div');
  next.append(...(state.detailStale ? [staleDetailNotice()] : []),
    header, scorePanel, renderAlerts(detail), renderWeather(detail), renderWildlife(detail), renderReports(detail));
  // Refreshes arrive every 30 s and on every live notice. Swapping in identical
  // markup would replace the buttons under the supervisor's pointer, so only
  // replace the panel when what it shows actually changed.
  if (next.innerHTML !== $('detail').innerHTML) $('detail').replaceChildren(...next.childNodes);
  renderReportPins();
}
async function loadDetail(id) {
  const generation = ++detailGeneration;
  $('detail').setAttribute('aria-busy', 'true');
  try {
    const [detail, reports] = await Promise.all([api.detail(id), api.reports(id)]);
    if (sessionExpired || generation !== detailGeneration || state.selected !== id) return;
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
    const {sites, alerts, alertError} = await loadDashboardFeeds(api);
    if (sessionExpired) return;
    if (isSessionExpired(alertError)) throw alertError;
    state.sites = sites; state.alerts = alerts;
    if (!sites.some(site => site.site_id === state.selected)) updateSelection(rankSites(sites, {allowHistorical: sample})[0]?.site_id ?? null);
    renderMetrics(); renderList();
    if (state.selected !== null) await loadDetail(state.selected);
    else { state.detail = null; state.reports = []; revokePhotos(); reportLayer?.clearLayers(); $('detail').replaceChildren(el('p', 'The API returned no sites.', 'empty')); }
    $('updated').textContent = `Fetched ${new Date().toLocaleTimeString([], {hour: 'numeric', minute: '2-digit', second: '2-digit'})}`;
    if (alerts === null) showError(new Error('Alert feed unavailable. The site map is still available, but do not infer safety from missing alerts.'));
    else clearError();
  } finally { $('refresh').disabled = sessionExpired; }
}
const refresh = createRefreshQueue(fetchData);
async function resolveReport(id, button) {
  if (sample || sessionExpired || resolving || !hasSupervisorRole(user, config.auth.rolesClaim)) return;
  resolving = true; button.disabled = true; button.textContent = 'Resolving…';
  const selected = state.selected;
  let saved = false;
  try {
    const receipt = await api.resolve(id);
    saved = true;
    if (state.selected === selected) {
      // The committed receipt prevents a stale card from offering a second PATCH
      // if the following read fails. Counts and alerts still need a fresh read.
      state.reports = state.reports.map(report => report.id === id ? receipt : report);
      if (state.detail) renderDetail();
    }
    await refresh();
  } catch (error) {
    showError(saved && !isSessionExpired(error) ? new Error('Report resolved, but the dashboard could not refresh. Verify current alerts and use Refresh before relying on counts.') : error);
  }
  finally {
    resolving = false;
    if (state.detail) renderDetail();
    else if (button.isConnected) { button.disabled = false; button.textContent = 'Resolve report'; }
  }
}
function refreshClock() {
  const now = Date.now();
  document.querySelectorAll('[data-clear-at]').forEach(node => { node.textContent = countdown(node.dataset.clearAt, now); });
  // These labels must expire even if the API or real-time bridge is offline.
  updateWatchChips(document, state.sites, state.detail, now);
  const available = screeningAvailability(state.sites, now, sample);
  if (screeningAvailabilityChanged(renderedScreening, available)) { renderMetrics(); renderList(); }
  if (state.detail && $('detail').dataset.screeningStatus !== detailScreeningStatus(state.detail, now, sample)) {
    renderDetail();
  }
}
async function start() {
  bindAsk();
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
    $('ask-status').textContent = 'Questions require the live database. Sample mode does not call Gemini.';
    $('mode-banner').textContent = 'SAMPLE PREVIEW · Demonstration sites, screening predictions and alerts. Historical timestamps are for the demo only; do not use this screen for field work. Report actions are read-only.';
    $('connection').textContent = 'Sample data · no live connection';
    api = await createSampleAPI();
  } else if (config.mode === 'live') {
    $('mode-banner').textContent = 'Live data. Hazard scores are early-stage estimates, not permission to work. Lightning and weather warnings show only after a recent check.';
    auth = createAuth(config.auth);
    const action = $('auth-action'); action.hidden = false;
    action.disabled = true; action.textContent = 'Checking sign-in…';
    action.addEventListener('click', () => {
      if (action.disabled) return;
      if (user && !sessionExpired) {
        clearResumeHint();
        void auth.logout().catch(showError);
      } else void auth.login().catch(showError);
    });
    if (!auth.configured) {
      action.textContent = 'Sign in unavailable'; action.disabled = true;
      $('identity').textContent = 'Open a supported address';
      $('connection').textContent = 'Not connected';
      $('supported-auth-link').hidden = false;
      $('site-list').replaceChildren(el('p', 'This preview cannot sign in. Open the supported ForeSite address above.', 'empty'));
      throw new Error('This preview is not an approved Auth0 callback origin. Use the ForeSite link above, or run the preview on http://127.0.0.1:4174.');
    }
    try { user = await auth.initialize(); }
    catch (error) {
      clearResumeHint();
      action.disabled = false;
      action.textContent = 'Try sign-in again';
      throw error;
    }
    action.disabled = false;
    const resumeRequested = shouldResumeSignIn(window.location.search, hasResumeHint());
    if (new URLSearchParams(window.location.search).has('start')) {
      window.history.replaceState({}, '', config.auth.redirectUri);
    }
    if (!user) {
      $('identity').textContent = 'Sign-in required'; $('connection').textContent = 'Not connected';
      $('ask-status').textContent = 'Sign in as a supervisor to ask about live data.';
      action.textContent = 'Sign in';
      $('site-list').replaceChildren(el('p', 'Sign in with your supervisor account to load the live workspace.', 'empty'));
      if (resumeRequested) {
        // Consume the non-secret hint before leaving. A denied/expired Auth0
        // handoff returns here with no hint, so the page cannot loop.
        clearResumeHint();
        $('identity').textContent = 'Continuing sign-in…';
        await auth.login();
      }
      return;
    }
    $('identity').textContent = user.name || 'Signed-in user';
    action.textContent = 'Sign out';
    if (!hasSupervisorRole(user, config.auth.rolesClaim)) {
      clearResumeHint();
      throw new Error('A supervisor role is required for this workspace. Ask the Auth0 administrator to configure the agreed role claim.');
    }
    markAuthenticated();
    api = createAPI({base: config.apiBase, token: auth.token, timeoutMs: config.requestTimeoutMs});
    setAskControls(true);
    $('ask-status').textContent = 'Ready for a question about live site data.';
    $('connection').textContent = 'Connecting to API…';
  } else { throw new Error('Unknown mode in config.js. Choose sample or live.'); }
  await refresh().catch(showError); fitMap();
  countdownTimer = setInterval(refreshClock, 1000);
  if (!sample) {
    stopRealtime = connectRealtime({getSource: () => createDeepSpaceSource(config.realtime), getToken: auth.token,
      onInvalidate: refresh, onSessionExpired: showError, onStatus(connected) {
        if (sessionExpired) return;
        $('connection').dataset.connected = String(connected);
        $('connection').textContent = connected ? 'Live updates on' : 'Live updates paused · refreshing every 30 seconds';
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
