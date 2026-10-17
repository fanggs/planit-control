# get_data/

Ingest pipeline. Mirrors CivicLens `get_data/`.

Planned:
- Sites: 50+ real power plants from EIA-860M
- Live conditions: weather, heat, lightning, flooding, wildfire, soil saturation
- Historical training data: NOAA Storm Events, OSHA Severe Injury Reports
- `validate` step with invariant checks (no empty columns, every reading has a site)

Every row records provenance: source name, source URL, retrieved_at.
