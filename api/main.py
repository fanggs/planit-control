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


def _sample(name: str):
    return json.loads((SAMPLES / f"{name}.json").read_text(encoding="utf-8"))


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
    return _sample("sites")


@app.get("/sites/{site_id}", response_model=SiteDetail)
def site_detail(site_id: int):
    detail = _sample("site_details").get(str(site_id))
    if detail is None:
        raise HTTPException(404, f"Site {site_id} not found")
    return detail


@app.get("/alerts", response_model=list[Alert])
def alerts():
    return _sample("alerts")


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
