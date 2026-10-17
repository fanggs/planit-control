# Field Atlas

Open `crew-atlas.html` from the crew page's **Explore the 60 monitored plants**
link. This is Isaiah's crew-owned map; it does not replace the supervisor app.

## Data

The complete roster is a bundled, exact copy of Sid's
`get_data/generated/sites.json`: **60 real EIA-860M plants, ten in each of six
hazard regions**. The atlas does not load the older national demo catalog.
IDs, names, coordinates, utilities, counties, regions and source metadata come
from that roster. Search, selection and API merging cannot add other plants.

After Sid updates the source file, run from `page/crew/`:

```sh
node dev/sync-atlas-roster.mjs
node --test
```

The script validates the roster and writes only the crew-owned snapshot. Tests
compare it with Sid's current file, so a changed upstream roster cannot silently
leave a stale map. `crew-data/atlas-source.json` records provenance.

## Map behavior

- **2D / 3D** animates the map plane and raises or lowers the beacons over 1.05
  seconds. It is an orthographic visualization, without terrain elevation data.
- Colors identify the six hazard regions. Every plant keeps its own beacon;
  there is no cluster layer or national background plant population.
- A hollow cap means no hazard score. Those location beacons use a fixed,
  decorative height. They are not estimates of danger. If a valid API score is
  available, the cap fills and beam height follows its 0–10 value.
- Select a beacon or list row to inspect verified plant metadata. **Locate**
  centers it; **Overview** fits the current map view. Search and region filters
  narrow the approved roster. Clearing filters restores all 60.
- Drag to pan; Shift + drag tilts/orbits the 3D view. Wheel zoom follows the
  pointer. Touch supports panning and two-finger pinch zoom. Nearby pin heads
  spread with thin geographic leaders, retaining their true ground locations.
- Arrow keys pan, + / − zoom, N / P select plants, Escape returns to overview.
  The searchable list provides an alternative to the canvas. Plant names and
  score availability are announced on selection.
- **Motion** disables transitions and selection pulses; system reduced-motion
  preferences disable both automatically. The glow is static, with no permanent
  render loop. The animation pauses when the tab is hidden.
- **Crew workspace** returns to the original crew selection. Choosing an atlas
  plant does not navigate to an unsupported site in the older demo catalog.

## Backend connection

Default mock configuration displays **real locations only**, with unavailable
scores. It generates no sample risk values and makes no API calls.

When `crew-config.js` is set to live mode, the atlas uses existing Auth0 session
and role checks, then the crew HTTP/custom service's bulk `listSites` method.
Only scores for the approved 60 IDs are accepted. The API cannot override their
verified locations or add another plant. **Refresh scores** repeats that one bulk
read. Camera movement, selection, filtering and mode changes never call the API.

Missing scores and failed reads stay unavailable; failures do not substitute
synthetic conditions. Score timestamps appear in the selected-plant panel.
Alerts, countdowns, reports and briefings remain in the crew workspace. Connecting
DeepSpace notifications and `scores.updated` is still the separate issue #1 task.

## Files and checks

- `crew-atlas.html` / `crew-atlas.css`: full-screen map and floating panels.
- `crew-atlas.js`: canvas rendering, interaction, finite transitions and optional
  authenticated bulk score loading.
- `crew-atlas-data.js`: roster validation, filtering, safe score merging,
  projection transforms, interpolation and overlapping-pin placement.
- `crew-data/monitored-sites.json`: the exact roster snapshot.
- `crew-data/atlas-us-states.json`: simplified Census-derived state geometry.
- Local D3 and geography licenses ship beside their assets. No map keys, hosted
  fonts, tile services, or new package installation are required.

```sh
node dev/check.mjs
node --test
```

The atlas tests cover exact roster membership, invalid roster rejection, score
allowlisting, unknown scores, filtering, transition math, pointer-anchored zoom,
shared-location pins and actual geographic coverage.
