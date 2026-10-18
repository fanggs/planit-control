"""
Live NWS watches, warnings, and advisories for every monitored site.

Every 5 minutes, ask api.weather.gov for the alerts active at each plant's
coordinates (NWS resolves its own zones and polygons). Then:

    environmental_events   one row per NWS alert per site (event_kind nws_warning,
                           nws_advisory, ...), ended early if NWS drops it
    alerts                 a `warning` alert for flood, red flag/fire, and heat
                           warnings, one per site and event type, ended when NWS
                           ends it. Never stop_work: only lightning stops work.
    nws_status.json        which sites were checked and when, so the API can say
                           "no active warnings" only when it actually checked

    .venv/bin/python -m jobs.nws            # run forever
    .venv/bin/python -m jobs.nws --once     # one pass, then exit
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATUS = ROOT / "data" / "live" / "nws_status.json"
API = "https://api.weather.gov/alerts/active?point={lat:.4f},{lon:.4f}"
# NWS asks every client to identify itself with a contact URL.
USER_AGENT = "ForeSite/1.0 (https://github.com/fanggs/planit-control)"
POLL_SECONDS = 300

log = logging.getLogger("planit.nws")

# NWS events that put a warning alert on the crew screen, by hazard.
WARNING_EVENTS = {
    "flooding": {"Flood Warning", "Flash Flood Warning", "Coastal Flood Warning", "Lakeshore Flood Warning"},
    "wildfire": {"Red Flag Warning", "Fire Warning"},
    "heat": {"Heat Advisory", "Excessive Heat Warning", "Extreme Heat Warning", "Heat Warning"},
}


def hazard_for(event: str) -> str:
    if "Flood" in event:
        return "flooding"
    if "Red Flag" in event or "Fire" in event:
        return "wildfire"
    if "Heat" in event:
        return "heat"
    return "other"


def _time(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value).astimezone(timezone.utc) if value else None


@dataclass
class NwsAlert:
    id: str          # NWS alert URL; a new one for every update NWS issues
    event: str       # e.g. "Flood Warning"
    title: str
    severity: str | None
    starts_at: datetime
    ends_at: datetime | None

    @property
    def hazard_type(self) -> str:
        return hazard_for(self.event)

    @property
    def event_kind(self) -> str:
        return "nws_" + self.event.split()[-1].lower()  # nws_warning, nws_advisory, ...

    @property
    def raises_warning(self) -> bool:
        return self.event in WARNING_EVENTS.get(self.hazard_type, set())


def parse(collection: dict) -> list[NwsAlert]:
    """Actual (not test/exercise) alerts from one /alerts/active response."""
    out = []
    for f in collection.get("features", []):
        p = f["properties"]
        if p.get("status") != "Actual" or p.get("messageType") == "Cancel":
            continue
        out.append(NwsAlert(
            id=f["id"], event=p["event"], title=p.get("headline") or p["event"],
            severity=(p.get("severity") or "").lower() or None,
            starts_at=_time(p.get("onset") or p.get("effective")),
            ends_at=_time(p.get("ends") or p.get("expires")),
        ))
    return out


def fetch(site: dict) -> list[NwsAlert]:
    req = urllib.request.Request(API.format(lat=site["latitude"], lon=site["longitude"]),
                                 headers={"User-Agent": USER_AGENT, "Accept": "application/geo+json"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return parse(json.load(r))


# ---------------------------------------------------------------- one site

def sync_site(site_id: int, active: list[NwsAlert], store, now: datetime) -> list[dict]:
    """Bring one site's stored events and warning alerts in line with NWS. Returns notices."""
    store.save_events(site_id, active, now)
    store.end_missing_events(site_id, [a.id for a in active], now)

    notices = []
    wanted = {}  # event name -> newest alert of that event (NWS may list several updates)
    for a in active:
        if a.raises_warning and a.starts_at <= now and (a.ends_at is None or a.ends_at > now):
            if a.event not in wanted or a.starts_at > wanted[a.event].starts_at:
                wanted[a.event] = a
    open_alerts = store.open_warning_alerts(site_id)  # event name -> {"id", "clear_at"}
    for event, a in wanted.items():
        if event in open_alerts:
            current = open_alerts[event]
            if current["clear_at"] != a.ends_at:
                store.update_alert(current["id"], a, now)
                notices.append({"type": "alert.updated", "site_id": site_id, "alert_id": current["id"],
                                "clear_at": a.ends_at.isoformat().replace("+00:00", "Z") if a.ends_at else None})
        else:
            alert_id = store.start_alert(site_id, a, now)
            notices.append({"type": "alert.started", "site_id": site_id, "alert_id": alert_id})
    for event, current in open_alerts.items():
        if event not in wanted:
            store.end_alert(current["id"], now)
            notices.append({"type": "alert.cleared", "site_id": site_id, "alert_id": current["id"]})
    return notices


class TigerStore:
    """environmental_events and alerts in Tiger Data."""

    def save_events(self, site_id: int, active: list[NwsAlert], now: datetime) -> None:
        from api import db
        for a in active:
            db.execute("""
                INSERT INTO public.environmental_events
                    (id, site_id, hazard_type, event_kind, title, severity, starts_at, ends_at,
                     source_name, source_url, retrieved_at)
                VALUES (:id, :site_id, :hazard_type, :event_kind, :title, :severity, :starts_at, :ends_at,
                        'National Weather Service', :id, :now)
                ON CONFLICT (id, site_id) DO UPDATE SET
                    title = EXCLUDED.title, severity = EXCLUDED.severity,
                    ends_at = EXCLUDED.ends_at, retrieved_at = EXCLUDED.retrieved_at""",
                id=a.id, site_id=site_id, hazard_type=a.hazard_type, event_kind=a.event_kind,
                title=a.title, severity=a.severity, starts_at=a.starts_at,
                ends_at=max(a.ends_at, a.starts_at) if a.ends_at else None, now=now)

    def end_missing_events(self, site_id: int, active_ids: list[str], now: datetime) -> None:
        """NWS no longer lists these (cancelled, replaced by an update, or expired)."""
        from api import db
        db.execute("""
            UPDATE public.environmental_events SET ends_at = GREATEST(:now, starts_at)
            WHERE site_id = :site_id AND event_kind LIKE 'nws_%'
              AND (ends_at IS NULL OR ends_at > :now) AND NOT (id = ANY(:ids))""",
            site_id=site_id, now=now, ids=active_ids)

    def open_warning_alerts(self, site_id: int) -> dict[str, dict]:
        from api import db
        rows = db.query("""
            SELECT id, trigger->>'nws_event' AS event, clear_at FROM public.alerts
            WHERE site_id = :site_id AND ended_at IS NULL AND trigger ? 'nws_event'""", site_id=site_id)
        return {r["event"]: {"id": r["id"], "clear_at": _time(r["clear_at"].replace("Z", "+00:00")) if r["clear_at"] else None}
                for r in rows}

    def start_alert(self, site_id: int, a: NwsAlert, now: datetime) -> int:
        from sqlalchemy import text
        from api import db
        with db.engine().begin() as conn:
            return conn.execute(text("""
                INSERT INTO public.alerts (site_id, hazard_type, level, message, started_at,
                                           last_trigger_at, clear_at, ended_at, trigger)
                VALUES (:site_id, :hazard_type, 'warning', :message, :now, :now, :clear_at, NULL,
                        CAST(:trigger AS jsonb))
                RETURNING id"""), {
                "site_id": site_id, "hazard_type": a.hazard_type, "message": a.title, "now": now,
                "clear_at": a.ends_at, "trigger": json.dumps({"nws_event": a.event, "nws_id": a.id}),
            }).scalar_one()

    def update_alert(self, alert_id: int, a: NwsAlert, now: datetime) -> None:
        from api import db
        db.execute("""
            UPDATE public.alerts SET message = :message, last_trigger_at = :now, clear_at = :clear_at,
                trigger = CAST(:trigger AS jsonb)
            WHERE id = :id AND ended_at IS NULL""",
            id=alert_id, message=a.title, now=now, clear_at=a.ends_at,
            trigger=json.dumps({"nws_event": a.event, "nws_id": a.id}))

    def end_alert(self, alert_id: int, now: datetime) -> None:
        from api import db
        db.execute("UPDATE public.alerts SET ended_at = GREATEST(:now, started_at) WHERE id = :id AND ended_at IS NULL",
                   id=alert_id, now=now)


def write_status(now: datetime, sites_ok: list[int], failed: int) -> None:
    STATUS.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATUS.with_suffix(".tmp")
    tmp.write_text(json.dumps({"checked_at": now.isoformat().replace("+00:00", "Z"),
                               "sites_ok": sorted(sites_ok), "failed": failed}, indent=2))
    os.replace(tmp, STATUS)


# ---------------------------------------------------------------- loop

def run_once(sites: list[dict], store, publish) -> None:
    now = datetime.now(timezone.utc)
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda s: _safe_fetch(s), sites))
    sites_ok, warnings = [], 0
    for site, active in zip(sites, results):
        if active is None:
            continue  # couldn't check: leave its stored state alone, status says unknown
        for notice in sync_site(site["site_id"], active, store, now):
            log.info("notice %s", notice)
            publish(notice["type"], **{k: v for k, v in notice.items() if k != "type"})
        sites_ok.append(site["site_id"])
        warnings += sum(a.raises_warning for a in active)
    write_status(now, sites_ok, len(sites) - len(sites_ok))
    log.info("checked %d/%d sites, %d warning-level alerts active", len(sites_ok), len(sites), warnings)


def _safe_fetch(site: dict) -> list[NwsAlert] | None:
    try:
        return fetch(site)
    except Exception as e:  # network, HTTP 5xx, bad JSON
        log.warning("NWS check failed for %s: %s", site["site_id"], e)
        return None


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true", help="one pass, then exit")
    args = parser.parse_args()
    for line in (ROOT / ".env").read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    from api.realtime import publish
    from api.site_data import load_sites
    sites, store = load_sites(), TigerStore()
    log.info("watching %d sites for NWS alerts every %d s", len(sites), POLL_SECONDS)
    while True:
        try:
            run_once(sites, store, publish)
        except Exception:  # database hiccup: log it, status goes stale, try again next pass
            log.exception("NWS pass failed")
        if args.once:
            break
        time.sleep(POLL_SECONDS)
