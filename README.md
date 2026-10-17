# PlanIT Control

SwampHacks XII, Sperry Tech challenge. A real-time platform that pulls scattered
environmental hazard data (heat, lightning, flooding, wildfire, soil saturation,
wildlife) into one risk picture per utility job site, with alerts, a 6 PM
next-day safety briefing, crew photo hazard reporting, a supervisor dashboard,
and an explainable ML hazard index (0-10).

## Layout

| Folder | What |
| --- | --- |
| `api/` | FastAPI backend and the Gemini layer |
| `get_data/` | Ingest pipeline with provenance on every row |
| `model/` | Trained hazard index model |
| `jobs/` | Polling, alerts, 6 PM briefing |
| `page/` | Supervisor dashboard and map |
| `db/` | Tiger Data schema |
| `data/` | Local data (`raw/` is gitignored) |

## Stack

Gemini (LLM) · Tiger Data (Postgres time-series) · Auth0 (logins) ·
DeepSpace (real-time alerts) · Vultr (hosting) · GoDaddy (domain)

## Setup

Copy `.env.example` to `.env` and fill in keys. Never commit `.env`.

## Run the API

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn api.main:app --reload --env-file .env --host 127.0.0.1 --port 8010
```

Then open http://127.0.0.1:8010/docs to see the endpoints. `/health` is public;
data routes require a valid Auth0 API access token with the `crew` or
`supervisor` role. Set `AUTH0_DOMAIN` and `AUTH0_AUDIENCE` in `.env` before
testing them. If either setting is missing or invalid, data routes return 503
instead of becoming public. With `DATABASE_URL` and `PGPASSWORD` set, leave
`PLANIT_DATA` unset or set it to `database` to read Tiger Data and register the
authenticated report/photo routes. Set `PLANIT_DATA=sample` only for the
labeled offline fixtures. Photos are kept under the private, Git-ignored
`data/private_photos/` directory locally; set `PLANIT_PRIVATE_PHOTOS_DIR` to a
dedicated persistent 0700 directory outside any public static root on a server.
