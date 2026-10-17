"""
PlanIT Control API.

Sits between Sid's database and the supervisor/crew pages (Aryan, Isaiah).

For now every endpoint serves the sample JSON in api/samples/, shaped exactly
like api/CONTRACT.md, so the frontend can be built before real data exists.
When Sid's tables are loaded, each endpoint swaps its sample read for a query
and the response shape stays the same.

Open /docs while the server runs to see every endpoint and try it.
"""
from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from api.schemas.alerts import Alert, Briefing
from api.schemas.sites import SiteDetail, SiteSummary

SAMPLES = Path(__file__).resolve().parent / "samples"
LIVE_ALERTS = Path(__file__).resolve().parents[1] / "data" / "live" / "alerts.json"
LEVEL_RANK = {"stop_work": 2, "warning": 1}


def _sample(name: str):
    return json.loads((SAMPLES / f"{name}.json").read_text(encoding="utf-8"))


def _alerts() -> list[dict]:
    """Sample alerts, with lightning replaced by the lightning job's live state.

    jobs/lightning.py (live) and jobs/replay.py (demo) write data/live/alerts.json.
    If neither has run, the sample lightning alert stays so screens have data.
    """
    rows = _sample("alerts")
    try:
        live = json.loads(LIVE_ALERTS.read_text(encoding="utf-8"))["lightning"]
    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        return rows
    return [a for a in rows if a["hazard_type"] != "lightning"] + live


def _site_alerts(site_id: int, rows: list[dict]) -> list[dict]:
    mine = [a for a in rows if a["site_id"] == site_id]
    return sorted(mine, key=lambda a: -LEVEL_RANK[a["level"]])


app = FastAPI(
    title="PlanIT Control",
    description="Serving sample data from api/samples/ until the database is connected.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# The contract's error shape: {"error": {"code": ..., "message": ...}}
@app.exception_handler(HTTPException)
async def _error_shape(request: Request, exc: HTTPException):
    code = {404: "not_found", 401: "unauthorized", 403: "forbidden"}.get(exc.status_code, "error")
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": code, "message": exc.detail}},
    )


# ---------------------------------------------------------------- endpoints

@app.get("/health")
def health():
    return {"ok": True, "data": "sample"}


@app.get("/sites", response_model=list[SiteSummary])
def sites():
    rows = _alerts()
    out = []
    for site in _sample("sites"):
        top = _site_alerts(site["site_id"], rows)
        site["active_alert"] = (
            {"level": top[0]["level"], "hazard_type": top[0]["hazard_type"], "clear_at": top[0]["clear_at"]}
            if top else None
        )
        out.append(site)
    return out


@app.get("/sites/{site_id}", response_model=SiteDetail)
def site_detail(site_id: int):
    detail = _sample("site_details").get(str(site_id))
    if detail is None:
        raise HTTPException(404, f"Site {site_id} not found")
    detail["active_alerts"] = _site_alerts(site_id, _alerts())
    return detail


@app.get("/alerts", response_model=list[Alert])
def alerts():
    return _alerts()


@app.get("/briefings/{site_id}", response_model=Briefing)
def briefing(site_id: int):
    found = _sample("briefings").get(str(site_id))
    if found is None:
        raise HTTPException(404, f"No briefing for site {site_id}")
    return found


# Response model comes from Aryan's hazard report schema once it has one.
@app.get("/reports")
def reports(site_id: int | None = None):
    rows = _sample("reports")
    return [r for r in rows if site_id is None or r["site_id"] == site_id]
