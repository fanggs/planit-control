# River / stream proximity

`python -m get_data.rivers` builds `get_data/generated/river-site-context.json`
for the 60 monitored plants. It uses the existing data dependencies, without a
database connection or new service. The API serves this checked-in cache, so
normal page loads make no USGS requests. Alan deploys the cache with the API.

Source: [USGS 3DHP Flowline service](https://3dhp.nationalmap.gov/arcgis/rest/services/usgs_3dhp_all/FeatureServer/50).
The service combines newer elevation-derived hydrography and legacy NHD data.
Only `featuretype = 1` (the service's River class) is retained. Canals,
coastlines, drainageways and connector classes are not substituted for rivers.
Some River-class features have no name; those remain unnamed rather than being
skipped for a farther named feature. The service also supplies its own varying
feature labels; classification uses the documented numeric class.

Each plant uses a spherical bounding envelope covering a 25 km search circle.
The query is paginated in OBJECTID order; incomplete/error responses abort the
build rather than producing a false no-match. Full returned line geometries
are compared with the plant coordinate using spherical point-to-segment
distances, including segment interiors. Candidates beyond 25 km are excluded.
Distance is approximate and measured to a mapped centerline, not a river bank,
site boundary, water level, or hydraulic connection.

The output records plant coordinates, match status, name, distance, feature
identifier, exact source query, source checksums and actual retrieval times.
Raw pages and download receipts stay under ignored `data/raw/rivers/`. Cached
pages must pass checksum/URL checks. `--refresh` explicitly retrieves new data.
The output is replaced only after all 60 lookups succeed. Changed plant
coordinates invalidate its cached context. Missing/invalid caches produce
`unavailable`; a completed search with no match produces `no_mapped_river`
within the stated radius. Neither means safe or that no river exists anywhere.

This is geographic context only. It does not modify flood alerts, ML scores,
work authorization, or the NWS watch lifecycle. A nearby river and local rain
alone do not establish flood risk; upstream rainfall, terrain and water levels
are separate evidence.

## Flood panel timing and sources

The rainfall period is the 24 hours ending at `latest_weather.observed_at`,
shown in the site's IANA timezone. It appears only with a finite rolling
24-hour precipitation value and a valid end timestamp. A true zero is kept;
missing/incomplete rainfall does not become zero or a complete period. These
Open-Meteo/IFS values are modeled estimates, not rain-gauge observations.

Rainfall source/time, NWS check source/time, warning effective period (when
present), and river-map source/retrieval time are displayed separately. NWS
warning dates never stand in for the rainfall accumulation period. Missing
warnings do not erase otherwise available rainfall evidence, and stale checks
still cannot produce an all-clear.
