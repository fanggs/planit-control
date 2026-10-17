# PlanIT primary site map

Open **Site map** in the welcome page navigation or crew header. The main map
is `crew-atlas.html`. **Supervisor** opens the restored original crew-owned
`crew-supervisor.html` dashboard. It keeps the earlier summary cards, filters,
risk ranking and selected-site details, with a compact 60-site overview map.
**Open 2D / 3D map** opens this Atlas and preserves the selected site. The old
national catalog remains removed. Aryan’s separate dashboard is unchanged.

## Locations and scores

The map and demo crew picker use exactly Sid’s 60 EIA-860M plants from
`get_data/generated/sites.json`, copied to `crew-data/monitored-sites.json`.
There are ten plants in each of six regions. Coordinates, source information
and site timezones come from those records. Existing saved demo reports remain.

The highest scores appear first. Marker glow, beam and list colors use the crew
score bands: **green 0–3.9**, **amber 4–6.9**, **coral 7–10**, **gray unavailable**.
Zero is valid; missing, invalid and failed readings never become zero. Hollow
unscored beacons have a fixed decorative height. Scored beams follow the index.
The selected plant shows its score, timestamp, risk label and **Open crew site**
button; the crew screen includes the score explanation and waterfall chart.

Default mock mode shares the crew’s explicitly labeled **synthetic sample
scores**. These are not trained-model results or current conditions. Live mode
uses the existing authenticated bulk API list. Only the approved 60 IDs can add
scores; API rows cannot replace verified geography or add plants. Failed live
reads clear scores and remain unavailable without falling back to sample data.

## Interaction and requests

- **2D / 3D** animates over 1.05 seconds; this is an orthographic map without
  terrain elevation data. Forest surfaces, mint controls and system typography
  follow the crew workspace’s PlanIT palette.
- Search by plant, utility, state or EIA ID. Region filters stay within the
  roster; clearing filters restores all 60. Every plant keeps a separate beacon.
- Select a plant to inspect; **Locate** centers it; **Overview** resets the view.
- Drag to pan; Shift + drag tilts/orbits 3D. Wheel and pinch zoom follow the
  pointer. Nearby heads spread with geographic leader lines to remain distinct.
- Arrow keys pan, + / − zoom, N / P select plants, Escape returns to overview.
  The searchable list provides a canvas alternative. Phone controls include a
  collapsible plant list, score counts, and access to the selected crew site.
- **Motion** and system reduced-motion preferences disable transitions and
  pulses. Glow is static; rendering has no permanent animation loop.
- Initial loading and **Refresh scores** each use one bulk site-list read.
  Pan, zoom, selection, filtering and view transitions do not request scores.
- Alerts, countdowns, reports and briefings remain in the crew screen. The
  DeepSpace subscription connection is still separate issue #1.

## Refresh and verify

After Sid changes the roster, run these from `page/crew/`:

```sh
node dev/sync-atlas-roster.mjs
node dev/check.mjs
node --test
```

Validation rejects incomplete or unexpected rosters. Tests compare the exact
snapshot with Sid’s file, cover risk-color boundaries and ranking, check shared
demo scores/timezones, safe API merges, projection coverage, transition math,
anchored zoom and overlapping-pin placement. `crew-data/atlas-source.json`
records provenance. Local D3 and Census-derived geography include licenses.
No map key, tile service, hosted font or new package is required.
