"""
PlanIT Control API.

Sits between Sid's data and the supervisor/crew pages (Aryan, Isaiah).

Sites come from api/site_data.py: Sid's 60 real EIA-860M plants by default, or
the three placeholder sites with PLANIT_DATA=sample. Real sites get no invented
data: until scores, weather, and briefings exist they come back null / empty,
which the contract treats as "no data". Lightning alerts are live from
jobs/lightning.py or the labeled replay in jobs/replay.py.

Response shapes follow api/CONTRACT.md. Open /docs while the server runs.
"""
from __future__ import annotations

import json
import os
from urllib.parse import urlsplit

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import OperationalError

from api import ask, db, live_status, site_data
from api.auth.hazard_auth import Auth0Config, Principal, create_auth_dependency, require_roles
from api.schemas.alerts import Alert, Briefing
from api.schemas.ask import AskAnswer, AskRequest, CannotAnswer
from api.schemas.sites import SiteDetail, SiteSummary
from db.screening_read import unavailable
from get_data.site_context import for_site
from get_data.rivers import for_site as river_context

LIVE_ALERTS = site_data.ROOT / "data" / "live" / "alerts.json"
LEVEL_RANK = {"stop_work": 2, "warning": 1}
LOCAL_CORS_ORIGINS = (
    "http://127.0.0.1:4174",
    "http://127.0.0.1:4175",
)


def _cors_origins() -> list[str]:
    """Allow only explicit browser origins; never widen CORS on bad input.

    Production sets PLANIT_CORS_ORIGINS to its exact HTTPS frontend origin(s).
    The two documented loopback preview origins are the only HTTP exceptions.
    """
    configured = os.environ.get("PLANIT_CORS_ORIGINS")
    if configured is None:
        return list(LOCAL_CORS_ORIGINS)
    origins = configured.split(",")
    if not origins or any(not origin or origin != origin.strip() for origin in origins):
        raise ValueError("PLANIT_CORS_ORIGINS needs comma-separated exact origins")
    for origin in origins:
        parsed = urlsplit(origin)
        try:
            port = parsed.port
        except ValueError as exc:
            raise ValueError("PLANIT_CORS_ORIGINS contains an invalid port") from exc
        if (
            not parsed.hostname or not parsed.netloc
            or parsed.username is not None or parsed.password is not None
            or parsed.path or parsed.query or parsed.fragment
            or any(ord(character) <= 32 or ord(character) == 127 or character in "*\\" for character in origin)
            or (port is not None and port == 0)
            or (origin not in LOCAL_CORS_ORIGINS and (
                parsed.scheme != "https" or origin != f"https://{parsed.netloc}"
            ))
        ):
            raise ValueError("PLANIT_CORS_ORIGINS allows only exact HTTPS origins or documented 127.0.0.1 previews")
    return list(dict.fromkeys(origins))


try:
    _auth0_config = Auth0Config.from_env()
except ValueError:
    # The health check remains available, but no data route becomes public when
    # tenant settings are missing or malformed. Its auth dependency returns 503.
    _auth0_config = None
_get_principal = create_auth_dependency(_auth0_config)


def _require_data_viewer(principal: Principal = Depends(_get_principal)) -> None:
    require_roles(principal, "crew", "supervisor")


def _live_lightning() -> list[dict] | None:
    """Alerts written by the lightning job or replay; None if neither has run."""
    try:
        return json.loads(LIVE_ALERTS.read_text(encoding="utf-8"))["lightning"]
    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        return None


def _alerts() -> list[dict]:
    live = _live_lightning()
    if site_data.mode() == "database":
        # Every active alert lives in Tiger Data: lightning stop-work alerts
        # (jobs/lightning.py and the labeled replay) and report warnings.
        return db.query("""
            SELECT id, site_id, hazard_type, level, message, started_at,
                   last_trigger_at, clear_at, trigger
            FROM public.alerts WHERE ended_at IS NULL
            ORDER BY started_at DESC, id DESC""")
    if site_data.mode() != "sample":
        return live or []
    # Sample mode: sample alerts, with lightning replaced by live state if any.
    rows = site_data.sample("alerts")
    if live is None:
        return rows
    return [a for a in rows if a["hazard_type"] != "lightning"] + live


def _site_alerts(site_id: int, rows: list[dict]) -> list[dict]:
    mine = [a for a in rows if a["site_id"] == site_id]
    return sorted(mine, key=lambda a: -LEVEL_RANK[a["level"]])


def _reports() -> list[dict]:
    if site_data.mode() == "database":
        return db.query("""
            SELECT id, site_id, reporter_id, hazard_type, severity, description,
                   latitude, longitude, photo_key, status, created_at,
                   resolved_at, resolved_by
            FROM public.hazard_reports ORDER BY created_at DESC, id DESC""")
    return site_data.sample("reports") if site_data.mode() == "sample" else []


def _screening(site: dict) -> dict:
    return site.get("screening") or unavailable("no_data", "No stored screening prediction")


def _summary(site: dict, alerts: list[dict], reports: list[dict], lightning_watch: dict | None = None) -> dict:
    top = _site_alerts(site["site_id"], alerts)
    screening = _screening(site)
    shown = screening["score"] is not None  # a real 0 is still a score
    return {
        "site_id": site["site_id"],
        "name": site["name"],
        "state": site["state"],
        "latitude": site["latitude"],
        "longitude": site["longitude"],
        "timezone": site["timezone"],
        "hazard_region": site["hazard_region"],
        "score": screening["score"],
        "scored_at": screening["scored_at"] if shown else None,
        "score_status": screening["status"],
        # The two features that moved the score most, up or down.
        "top_factors": sorted(screening["factors"], key=lambda f: -abs(f["contribution"]))[:2] if shown else None,
        "active_alert": (
            {"level": top[0]["level"], "hazard_type": top[0]["hazard_type"], "clear_at": top[0]["clear_at"]}
            if top else None
        ),
        "open_report_count": sum(
            r["site_id"] == site["site_id"] and r["status"] == "open" for r in reports
        ),
        "lightning_status": live_status.lightning_status(site["site_id"], alerts, lightning_watch),
    }


app = FastAPI(
    title="PlanIT Control",
    description="Real EIA-860M sites by default (PLANIT_DATA=sample for placeholders). "
                "Scores, weather, and briefings show as no data until they exist.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_methods=["GET", "POST", "PATCH"],
    allow_headers=["Authorization", "Content-Type"],
)


# The contract's error shape: {"error": {"code": ..., "message": ...}}
@app.exception_handler(HTTPException)
async def _error_shape(request: Request, exc: HTTPException):
    code = {404: "not_found", 401: "unauthorized", 403: "forbidden"}.get(exc.status_code, "error")
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": code, "message": exc.detail}},
        headers=exc.headers,
    )


# Database down: say so (503) instead of returning empty or sample data.
@app.exception_handler(OperationalError)
async def _database_down(request: Request, exc: OperationalError):
    return JSONResponse(
        status_code=503,
        content={"error": {"code": "service_unavailable", "message": "Database unavailable"}},
    )


# ---------------------------------------------------------------- endpoints

@app.get("/health")
def health():
    return {"ok": True, "data": site_data.mode(), "sites": len(site_data.load_sites())}


@app.get("/sites", response_model=list[SiteSummary], dependencies=[Depends(_require_data_viewer)])
def sites():
    alerts, reports, watch = _alerts(), _reports(), live_status.read_lightning()
    return [_summary(s, alerts, reports, watch) for s in site_data.load_sites()]


@app.get("/sites/{site_id}", response_model=SiteDetail, dependencies=[Depends(_require_data_viewer)])
def site_detail(site_id: int):
    site = next((s for s in site_data.load_sites() if s["site_id"] == site_id), None)
    if site is None:
        raise HTTPException(404, f"Site {site_id} not found")
    alerts = _alerts()
    return {
        **site,
        "latest_weather": site.get("latest_weather"),
        "screening": _screening(site),
        "wildlife_context": for_site(site_id),
        "river_context": river_context(site),
        "lightning_status": live_status.lightning_status(site_id, alerts, live_status.read_lightning()),
        "warnings_status": live_status.warnings_status(site_id, live_status.read_nws()),
        "active_alerts": _site_alerts(site_id, alerts),
        "environmental_events": site_data.active_events(site_id) or site.get("environmental_events", []),
        "recent_reports": [r for r in _reports() if r["site_id"] == site_id],
    }


@app.post("/ask", response_model=AskAnswer | CannotAnswer, dependencies=[Depends(_require_data_viewer)])
def ask_question(body: AskRequest):
    try:
        return ask.answer(body.question)
    except ask.AskUnavailable as e:
        return JSONResponse(status_code=503,
                            content={"error": {"code": "service_unavailable", "message": str(e)}})


@app.get("/alerts", response_model=list[Alert], dependencies=[Depends(_require_data_viewer)])
def alerts():
    return _alerts()


LIVE_BRIEFINGS = site_data.ROOT / "data" / "live" / "briefings.json"


def _briefings() -> dict:
    """jobs/briefings.py writes these at each site's 6 PM local."""
    if site_data.mode() == "sample":
        return site_data.sample("briefings")
    if site_data.mode() == "database":
        rows = db.query("""
            SELECT DISTINCT ON (site_id) site_id, for_date, generated_at, text, inputs
            FROM public.briefings ORDER BY site_id, for_date DESC, generated_at DESC""")
        return {str(r["site_id"]): r for r in rows}
    try:
        return json.loads(LIVE_BRIEFINGS.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


@app.get("/briefings/{site_id}", response_model=Briefing, dependencies=[Depends(_require_data_viewer)])
def briefing(site_id: int):
    found = _briefings().get(str(site_id))
    if found is None:
        raise HTTPException(404, f"No briefing for site {site_id}")
    # Stored briefings keep their sources inside inputs (the table has no column for them).
    return {**found, "sources": found.get("sources") or (found.get("inputs") or {}).get("sources", [])}


if site_data.mode() == "database" and _auth0_config is not None:
    # The real report/photo endpoints replace the old sample-only GET route.
    # Both routes and site summaries use the same Tiger Data service.
    from api.hazard_reporting import register_hazard_reporting
    from api.realtime import publish
    from api.services.hazard_warning_service import clear_report_warning, start_report_warning

    register_hazard_reporting(
        app,
        get_db=db.get_db,
        start_warning=start_report_warning,
        clear_warning=clear_report_warning,
        publish_event=publish,
        photo_directory=os.environ.get("PLANIT_PRIVATE_PHOTOS_DIR") or site_data.ROOT / "data" / "private_photos",
        auth_config=_auth0_config,
    )
else:
    # Keep the explicit offline/sample preview usable without a database.
    # Missing Auth0 settings still fail closed via _require_data_viewer.
    @app.get("/reports", dependencies=[Depends(_require_data_viewer)])
    def reports(site_id: int | None = None):
        return [r for r in _reports() if site_id is None or r["site_id"] == site_id]
