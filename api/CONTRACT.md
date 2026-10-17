# PlanIT Control: Contract v1

**Status:** v1.1, decided 2026-10-17 from Sid's and Aryan's AI reviews and the
team's answers. Any change gets announced in the team chat first.

**Build order:** everything here is in scope, but the core comes first:
60 sites → live weather → score → lightning alert → map. Everything else is
added once the core works.

---

## 1. Shared rules

- **Hazard types (exact strings, used everywhere):** `heat`, `lightning`, `flooding`, `wildfire`, `soil_saturation`, `wildlife`, `other`
- **Field name for a hazard, everywhere:** `hazard_type`
- **Field names:** `snake_case`
- **Times:** UTC ISO 8601, like `2026-10-17T18:00:00Z`. The frontend converts to the site's `timezone`.
- **Units:** °F, inches, miles, mph. Soil moisture in m³/m³ (0 to 7 cm depth).
- **Site ID:** the EIA plant code (integer). One row per plant, grouped from EIA-860M generator rows.
- **Provenance:** every row loaded from an outside source stores `source_name`, `source_url`, `retrieved_at`. Crew reports are the exception: the crew member is the source.
- **Missing data is never zero or "safe."** If a feed is down or a value is unknown, store `null` and the UI shows "no data." A dead lightning feed must never look like "no strikes."
- **Freshness:** every reading and score carries its own time, and the UI shows how old it is.

## 2. Roles and permissions (Auth0)

Two roles: `crew` and `supervisor`. The API checks a validated Auth0 access token.
`reporter_id` and `resolved_by` always come from the token's `sub`, never from
the request body.

| Action | crew | supervisor |
| --- | --- | --- |
| View sites, scores, alerts, briefings | ✅ (all sites) | ✅ |
| View reports and their photos | ✅ | ✅ |
| Create a report, upload a photo | ✅ | ✅ |
| Resolve a report | ❌ | ✅ |
| Use `/ask` | ✅ | ✅ |

## 3. Database tables (Tiger Data / PostgreSQL)

**sites**
`site_id` (EIA plant code, PK), `name`, `utility`, `state`, `county`, `county_fips`,
`latitude`, `longitude`, `timezone`, `plant_type` (documented summary across the
plant's generators), `hazard_region`, `operating_status`, `is_monitored`,
`source_name`, `source_url`, `source_vintage` (EIA month), `retrieved_at`

**weather_readings** (time-series, one row per check-in per provider)
`site_id`, `observed_at`, `provider`, `temperature_f`, `heat_index_f`, `wind_mph`,
`precip_1h_in`, `precip_24h_in` (rolling 24 h), `soil_moisture`,
`source_name`, `source_url`, `retrieved_at`
Unique on (`site_id`, `observed_at`, `provider`) so reloads don't duplicate.

**weather_forecasts** (time-series)
`site_id`, `issued_at`, `valid_at`, `provider`, same weather columns as above,
`source_name`, `source_url`, `retrieved_at`

**environmental_events** (NWS warnings, wildfire, flood warnings)
`id`, `site_id`, `hazard_type`, `event_kind` (e.g. `nws_warning`), `title`,
`severity`, `starts_at`, `ends_at`, `source_name`, `source_url`, `retrieved_at`

**wildlife_observations** (training data for the wildlife model)
`occurrence_id` (GBIF ID), `species`, `observed_at`, `latitude`, `longitude`,
`source_name`, `source_url`, `retrieved_at`

**lightning_strikes** (time-series, stored once, not per site)
`strike_id` (provider-qualified), `struck_at`, `latitude`, `longitude`,
`is_replay` (true if replayed historical data), `source_name`, `source_url`, `retrieved_at`

**hazard_scores** (time-series)
`site_id`, `scored_at`, `horizon_hours` (24), `score`, `baseline`, `factors` (jsonb),
`model_version`, `inputs_observed_at`

**alerts**
`id`, `site_id`, `hazard_type`, `level` (`warning` / `stop_work`), `message`,
`started_at`, `last_trigger_at`, `clear_at`, `ended_at`,
`trigger` (jsonb, e.g. `{"strike_id": "...", "distance_mi": 6.2}`)

**hazard_reports**
`id` (uuid), `site_id`, `reporter_id`, `hazard_type`, `severity` (`low` / `medium` / `high`),
`description`, `latitude`, `longitude`, `photo_key` (nullable), `status` (`open` / `resolved`),
`created_at`, `resolved_at`, `resolved_by`

**briefings**
`id`, `site_id`, `for_date` (site-local calendar date), `generated_at`, `text`,
`model`, `inputs` (jsonb: which forecast and score it was written from)

Gemini's `/ask` queries run as a **read-only database user** (Sid creates it when
setting up the database).

**Load order for Sid:** sites → weather readings → weather forecasts →
wildlife observations → environmental events. Forecasts come before
environmental events because the 6 PM briefing depends on them.

**Site selection:** pick the 60 by a written rule (latest EIA-860M month,
operating plants only, about 10 per hazard region), **plus these must-include
demo sites**, even if the rule misses them:
- a real Florida plant near the Everglades (demo opener: heat, lightning, wildlife)
- at least 2 plants along the Mississippi River (flood warning example from the brief)
- at least 2 plants in a California / Western wildfire area

## 4. Hazard score (model output)

The 0 to 10 score has **two trained parts**, added together:

| Part | Range | What it predicts | Trained on |
| --- | --- | --- | --- |
| **Weather** | 0 to 8 | How likely hazardous outdoor-work conditions are at the site in the next 24 hours (8 × predicted probability) | NOAA Storm Events: whether a relevant event (thunderstorm, lightning, heat, flood, flash flood, wildfire, high wind) occurred in the site's county that day, with that day's weather as inputs. Not an injury prediction. |
| **Wildlife** | 0 to 2 | How likely dangerous wildlife is near the site this month (2 × predicted probability) | GBIF sighting records (includes iNaturalist) of American alligator, cottonmouth, rattlesnakes, and copperhead, by location and month |

- **Models:** a small decision tree for each part (about 4 levels). Trained on
  older years, tested on the most recent year.
- **Explanation:** `score = baseline + sum of contributions`, where `wildlife` is
  one of the contributions. Contributions can be negative. Must match within
  0.05. Round only for display.
- **Known limitation (say it if asked):** wildlife sightings cluster where people
  are, so remote areas can look safer than they are.
- **Fallback:** if a trained part isn't ready in time, ship a rules-based version
  and label it **rules-based**, never "ML," until the trained one replaces it.
- **Crew reports** do not change the score in v1 (see section 7).

```json
{
  "site_id": 6045,
  "score": 8.2,
  "baseline": 2.4,
  "scored_at": "2026-10-17T18:00:00Z",
  "horizon_hours": 24,
  "model_version": "weather-tree-v1+wildlife-tree-v1",
  "factors": [
    {"hazard_type": "heat", "contribution": 3.1},
    {"hazard_type": "lightning", "contribution": 2.6},
    {"hazard_type": "soil_saturation", "contribution": 0.9},
    {"hazard_type": "flooding", "contribution": -1.5},
    {"hazard_type": "wildlife", "contribution": 1.7}
  ]
}
```

(Site IDs in examples are placeholders.)

**Breakdown panel (UI):** show it as a waterfall: start at the baseline, then
each factor as a bar going up (adds risk) or down (lowers risk), ending at the
score. Label each bar with its hazard and value.

## 5. API endpoints

Errors always look like: `{"error": {"code": "not_found", "message": "Site 123 not found"}}`

### `GET /sites`: supervisor map list
```json
[
  {
    "site_id": 6045,
    "name": "Example Plant",
    "state": "FL",
    "latitude": 25.43,
    "longitude": -80.33,
    "timezone": "America/New_York",
    "hazard_region": "florida_gulf",
    "score": 8.2,
    "scored_at": "2026-10-17T18:00:00Z",
    "top_factors": [
      {"hazard_type": "heat", "contribution": 3.1},
      {"hazard_type": "lightning", "contribution": 2.8}
    ],
    "active_alert": {"level": "stop_work", "hazard_type": "lightning", "clear_at": "2026-10-17T18:30:00Z"},
    "open_report_count": 1
  }
]
```
`score`, `scored_at`, `top_factors` are `null` if no score yet. `active_alert` is `null` if none.

### `GET /sites/{site_id}`: site detail + breakdown panel
Returns the site fields, plus:
`latest_weather` (with `observed_at`), `score` (full model output from section 4),
`active_alerts` (list), `environmental_events` (active ones), `recent_reports` (list).

### `GET /alerts`: active alerts
```json
[
  {
    "id": 101,
    "site_id": 6045,
    "hazard_type": "lightning",
    "level": "stop_work",
    "message": "Lightning 6.2 mi away. Stop work.",
    "started_at": "2026-10-17T18:00:00Z",
    "last_trigger_at": "2026-10-17T18:04:00Z",
    "clear_at": "2026-10-17T18:34:00Z",
    "trigger": {"strike_id": "replay-88213", "distance_mi": 6.2}
  }
]
```

### `GET /briefings/{site_id}`: latest briefing
```json
{
  "site_id": 6045,
  "for_date": "2026-10-18",
  "generated_at": "2026-10-17T22:00:00Z",
  "text": "Tomorrow: heat index reaches 112°F by 1 PM. Storms likely after 3 PM...",
  "inputs": {"forecast_valid_from": "2026-10-18T04:00:00Z", "score_scored_at": "2026-10-17T22:00:00Z"}
}
```

### `GET /reports?site_id=6045`: reports for map pins
List of reports (fields from the `hazard_reports` table).

### `POST /photos`: upload a photo (crew, supervisor)
Multipart image upload, max 5 MB, jpeg/png. Stored privately on our server.
Returns `{"photo_key": "a1b2c3"}`.

### `GET /photos/{photo_key}`: view a photo (crew, supervisor)
Returns the image. Requires login.

### `POST /reports`: create a report (crew, supervisor)
Request body:
```json
{
  "site_id": 6045,
  "hazard_type": "wildlife",
  "severity": "high",
  "description": "Gator in the ditch by the east gate",
  "latitude": 25.431,
  "longitude": -80.334,
  "photo_key": "a1b2c3"
}
```
`latitude`/`longitude` are optional but must come as a pair (both or neither); `photo_key` is optional.
The server sets `id`, `reporter_id`, `status` (`open`), `created_at`.
Returns the full report.

### `PATCH /reports/{id}`: resolve a report (supervisor only)
Request body: `{"status": "resolved"}`. The server sets `resolved_at`, `resolved_by`.

### `POST /ask`: question in plain English
Request: `{"question": "Which Florida sites have the highest heat risk tomorrow?"}`
Response:
```json
{
  "answer": "Three Florida sites...",
  "sql": "SELECT ...",
  "sources": [{"label": "Open-Meteo forecast", "url": "https://..."}]
}
```
If the data can't answer it: `{"answer": null, "reason": "cannot_answer"}`.

## 6. Real-time events (DeepSpace)

Sent **only after the database save succeeds**. Payloads are **IDs only**; screens
fetch details from the API (so private info isn't broadcast).

| Event | Payload | When |
| --- | --- | --- |
| `alert.started` | `{alert_id, site_id}` | Lightning within 10 mi, or a flood/other warning |
| `alert.updated` | `{alert_id, site_id, clear_at}` | New strike, countdown resets to 30:00 |
| `alert.cleared` | `{alert_id, site_id}` | Countdown reaches zero |
| `report.created` | `{report_id, site_id, created_at}` | Crew submits a report |
| `report.resolved` | `{report_id, site_id}` | Supervisor resolves a report |

DeepSpace is used for real-time only. Photos do **not** go through DeepSpace.

## 7. Crew reports and the score

Reports are shown **next to** the score and can trigger their own warning. They
do **not** change the trained score in v1, so the score stays an honest model
output.

## 8. Lightning data (live)

**Source: NOAA GOES Geostationary Lightning Mapper (GLM)**, free, no API key,
published on AWS Open Data in near real time (new files about every 20 seconds).
GOES-East covers the eastern/central U.S., GOES-West the western U.S. Verify
bucket names and latency when building.

- A job (Alan, `jobs/`) polls the newest GLM files about every minute, extracts
  each flash's time, latitude, longitude, and stores it in `lightning_strikes`
  with `is_replay = false`.
- The lightning rule checks distance from every monitored site (10 miles →
  stop-work alert, 30-minute countdown, reset on each new strike).
- **Accuracy note:** GLM locates flashes to roughly 8 to 14 km, so a strike near
  the 10-mile edge is approximate. Say this if asked.
- **If the feed is down, show "lightning data unavailable,"** never "no strikes."
- **Demo backup:** there may be no storms near any site during the expo. Keep a
  replay mode that plays back real recorded GLM flashes with `is_replay = true`,
  clearly labeled "replay" in the UI. Live stays the default.

## 9. Postponed (README "what we'd do next")

Input snapshots per score, data-quality status fields, model calibration checks,
explanation method versioning, assigned sites per crew member, reports feeding
the model.
