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
DeepSpace (real-time alerts, photo storage) · Vultr (hosting) · GoDaddy (domain)

## Setup

Copy `.env.example` to `.env` and fill in keys. Never commit `.env`.

## Run the API

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn api.main:app --reload --port 8010
```

Then open http://localhost:8010/docs to see every endpoint and try it.
Until the database is connected, endpoints serve the sample data in
`api/samples/` (shaped exactly like `api/CONTRACT.md`).
