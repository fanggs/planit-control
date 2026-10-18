"""
Is the site being watched right now? (contract section 5, lightning_status and
warnings_status)

No alert is not the same as clear: the lightning job or the NWS job could be
down. These read the status files the two jobs write every poll, and say
"clear" / "ok" only when the watch is fresh and working. Anything else is
"unknown" with a reason, so the crew screen never shows clear from stale data.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LIGHTNING_STATUS = ROOT / "data" / "live" / "lightning_status.json"
NWS_STATUS = ROOT / "data" / "live" / "nws_status.json"

LIGHTNING_FRESH = timedelta(minutes=5)   # job polls every 20 s
WATCHED_BEFORE_CLEAR = timedelta(minutes=30)  # same 30 minutes as the all-clear rule
NWS_FRESH = timedelta(minutes=15)        # job polls every 5 min

LIGHTNING_SOURCE = {"source_name": "NOAA GOES GLM", "source_url": "https://www.goes-r.gov/spacesegment/glm.html"}
NWS_SOURCE = {"source_name": "National Weather Service", "source_url": "https://api.weather.gov/alerts/active"}


def _read(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def _time(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value.replace("Z", "+00:00")) if value else None


def read_lightning() -> dict | None:
    return _read(LIGHTNING_STATUS)


def read_nws() -> dict | None:
    return _read(NWS_STATUS)


def lightning_status(site_id: int, alerts: list[dict], watch: dict | None, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    checked = _time(watch.get("checked_at")) if watch else None
    hold = [a for a in alerts if a["site_id"] == site_id
            and a["hazard_type"] == "lightning" and a["level"] == "stop_work"]

    def result(status: str, reason: str | None) -> dict:
        return {"status": status, "checked_at": checked, "reason": reason, **LIGHTNING_SOURCE}

    if hold:  # an open stop-work alert wins, whatever the feed is doing
        return result("stop_work", None)
    if checked is None:
        return result("unknown", "Lightning watch is not running")
    if now - checked > LIGHTNING_FRESH:
        return result("unknown", "Lightning watch has not checked in recently")
    ok_since = _time(watch.get("feed_ok_since"))
    if ok_since is None:
        return result("unknown", watch.get("error") or "Lightning feed is unavailable")
    if now - ok_since < WATCHED_BEFORE_CLEAR:
        return result("unknown", "Lightning watch restarted; clear after 30 watched minutes")
    return result("clear", None)


def warnings_status(site_id: int, watch: dict | None, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    checked = _time(watch.get("checked_at")) if watch else None
    fresh = checked is not None and now - checked <= NWS_FRESH
    ok = fresh and site_id in set(watch.get("sites_ok", []))
    return {"status": "ok" if ok else "unknown", "checked_at": checked, **NWS_SOURCE}
