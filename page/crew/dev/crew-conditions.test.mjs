import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import {createContractMapper} from '../crew-integration.js';
import {hazardHTML} from '../crew-ui.js';
import {heatIndexDisplay} from '../../shared/environment-readings.mjs';

const fixture = JSON.parse(await fs.readFile(new URL('./fixtures/contract-v1.1.json', import.meta.url)));
const rawSite = () => structuredClone(fixture.details['9002']);

test('heat-index reasons distinguish cool, missing inputs, high out-of-range and real zero', () => {
  assert.match(heatIndexDisplay({temperature_f: 63, heat_index_f: null}), /Not calculated below 80/);
  assert.match(heatIndexDisplay({temperature_f: 90, heat_index_f: null}), /Unavailable/);
  assert.match(heatIndexDisplay({temperature_f: 115, heat_index_f: null}), /Outside supported range/);
  assert.match(heatIndexDisplay({temperature_f: null, heat_index_f: null}), /Unavailable/);
  assert.match(heatIndexDisplay({temperature_f: 80, heat_index_f: 0}), /Heat index 0/);
});

test('unassessed readings have no severity chip, but active alerts do', () => {
  const raw = rawSite();
  raw.active_alerts = [];
  raw.environmental_events = [];
  raw.latest_weather.temperature_f = 63;
  raw.latest_weather.heat_index_f = null;
  raw.latest_weather.precip_24h_in = 0;
  raw.wildlife_context = {status: 'no_records_in_sample', sightings: []};
  const now = Date.parse('2026-10-17T18:05:00Z');
  raw.lightning_status = {status: 'clear', checked_at: '2026-10-17T18:04:00Z'};
  raw.warnings_status = {status: 'ok', checked_at: '2026-10-17T18:04:00Z'};
  const site = createContractMapper({now: () => now}).site(raw);
  assert.match(site.hazards.heat.reading, /Not calculated below 80/);
  assert.match(site.hazards.weather.reading, /0 in \/ 24 h/);
  assert.match(site.hazards.lightning.reading, /No current lightning stop-work hold/);
  assert.match(site.hazards.flood.reading, /No active NWS flood warning/);
  assert.match(site.hazards.wildfire.reading, /No active NWS fire-weather warning/);
  assert.match(site.hazards.wildlife.reading, /limited sample/);
  const html = hazardHTML(site);
  assert.doesNotMatch(html, /<span class="crew-pill">Unknown<\/span>/i);
  assert.doesNotMatch(html, /<span class="crew-pill">unavailable<\/span>/i);
  assert.match(html, /data-severity="unassessed"/);
  raw.active_alerts = [{id: 7, site_id: raw.site_id, hazard_type: 'lightning', level: 'stop_work',
    message: 'Stop work', started_at: '2026-10-17T18:04:00Z', clear_at: '2026-10-17T18:34:00Z'}];
  const withHold = createContractMapper({now: () => now}).site(raw);
  assert.equal(withHold.hazards.lightning.severity, 'high');
  assert.match(hazardHTML(withHold), /data-severity="high"/);
});

test('a stale warning check cannot produce no-warning text', () => {
  const raw = rawSite(), now = Date.parse('2026-10-17T19:00:00Z');
  raw.active_alerts = []; raw.environmental_events = [];
  raw.warnings_status = {status: 'ok', checked_at: '2026-10-17T18:00:00Z'};
  const site = createContractMapper({now: () => now}).site(raw);
  assert.match(site.hazards.flood.reading, /unavailable/);
  assert.match(site.hazards.wildfire.reading, /unavailable/);
});

test('a replay hold is labeled in the main alert, watch, and hazard card', () => {
  const raw = rawSite(), now = Date.parse('2026-10-17T18:05:00Z');
  raw.active_alerts = [{id: 7, site_id: raw.site_id, hazard_type: 'lightning', level: 'stop_work',
    message: 'Recorded storm lightning hold', started_at: '2026-10-17T18:04:00Z',
    clear_at: '2026-10-17T18:34:00Z', trigger: {is_replay: true}}];
  const site = createContractMapper({now: () => now}).site(raw);
  assert.equal(site.alert.is_replay, true);
  assert.match(site.hazards.lightning.advice, /Recorded storm replay/);
  assert.match(hazardHTML(site), /<span class="crew-pill">REPLAY<\/span>/);
});
