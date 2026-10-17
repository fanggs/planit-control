"""
Tiger Data storage for lightning alerts and strikes.

    start / update / end   one row per stop-work alert in public.alerts
    save_strikes           flashes within 30 miles of a monitored site go into
                           the public.lightning_strikes hypertable (evidence for
                           each alert, without storing the whole hemisphere)
    load_active            alerts still open, so a restarted job keeps counting

Live and replay alerts are kept apart by trigger.is_replay: the live job never
resumes or ends a replay alert, and vice versa.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta

from sqlalchemy import text

from api import db
from jobs import glm
from jobs.lightning import ActiveAlert, in_us

EVIDENCE_MILES = 30.0


def _message(alert: ActiveAlert) -> str:
    return f"Lightning {alert.trigger['distance_mi']} mi away. Stop work."


class TigerStore:
    def __init__(self, replay: bool = False):
        self.replay = replay

    # -------------------------------------------------------------- alerts

    def start(self, alert: ActiveAlert) -> int:
        with db.engine().begin() as conn:
            return conn.execute(text("""
                INSERT INTO public.alerts
                    (site_id, hazard_type, level, message, started_at, last_trigger_at, clear_at, ended_at, trigger)
                VALUES (:site_id, 'lightning', 'stop_work', :message, :started_at, :last_trigger_at,
                        :clear_at, NULL, CAST(:trigger AS jsonb))
                RETURNING id"""), {
                "site_id": alert.site_id, "message": _message(alert),
                "started_at": alert.started_at, "last_trigger_at": alert.last_trigger_at,
                "clear_at": alert.clear_at, "trigger": json.dumps(alert.trigger),
            }).scalar_one()

    def update(self, alert: ActiveAlert) -> None:
        db.execute("""
            UPDATE public.alerts
            SET last_trigger_at = :last_trigger_at, clear_at = :clear_at,
                message = :message, trigger = CAST(:trigger AS jsonb)
            WHERE id = :id AND ended_at IS NULL""",
            id=alert.alert_id, last_trigger_at=alert.last_trigger_at, clear_at=alert.clear_at,
            message=_message(alert), trigger=json.dumps(alert.trigger))

    def end(self, alert: ActiveAlert, at: datetime) -> None:
        db.execute("UPDATE public.alerts SET ended_at = :at WHERE id = :id AND ended_at IS NULL",
                   id=alert.alert_id, at=max(at, alert.started_at))

    def load_active(self, sites: list[dict], all_clear: timedelta) -> list[ActiveAlert]:
        monitored = {s["site_id"] for s in sites}
        rows = db.query("""
            SELECT id, site_id, started_at, last_trigger_at, clear_at, trigger
            FROM public.alerts
            WHERE hazard_type = 'lightning' AND ended_at IS NULL
              AND COALESCE((trigger->>'is_replay')::boolean, false) = :replay
            ORDER BY started_at""", replay=self.replay)
        alerts = []
        for r in rows:
            if r["site_id"] not in monitored:
                continue
            parse = lambda ts: datetime.fromisoformat(ts.replace("Z", "+00:00"))
            last = parse(r["last_trigger_at"])
            alerts.append(ActiveAlert(r["id"], r["site_id"], started_at=parse(r["started_at"]),
                                      last_trigger_at=last, trigger=r["trigger"],
                                      clear_at=parse(r["clear_at"]) if r["clear_at"] else last + all_clear))
        return alerts

    def end_all_open(self, at: datetime) -> int:
        """Close this mode's open alerts (replay uses it at start and finish)."""
        with db.engine().begin() as conn:
            return conn.execute(text("""
                UPDATE public.alerts SET ended_at = GREATEST(:at, started_at)
                WHERE hazard_type = 'lightning' AND ended_at IS NULL
                  AND COALESCE((trigger->>'is_replay')::boolean, false) = :replay"""),
                {"at": at, "replay": self.replay}).rowcount

    # -------------------------------------------------------------- strikes

    def save_strikes(self, flashes: list[dict], sites: list[dict]) -> int:
        near = [
            f for f in flashes
            if in_us(f) and any(
                glm.distance_mi(s["latitude"], s["longitude"], f["latitude"], f["longitude"]) <= EVIDENCE_MILES
                for s in sites)
        ]
        if not near:
            return 0
        with db.engine().begin() as conn:
            conn.execute(text("""
                INSERT INTO public.lightning_strikes
                    (strike_id, struck_at, latitude, longitude, is_replay, source_name, source_url, retrieved_at)
                VALUES (:strike_id, :struck_at, :latitude, :longitude, :is_replay,
                        :source_name, :source_url, :retrieved_at)
                ON CONFLICT DO NOTHING"""),
                [{k: f.get(k) for k in ("strike_id", "struck_at", "latitude", "longitude",
                                        "source_name", "source_url", "retrieved_at")}
                 | {"is_replay": bool(f.get("is_replay"))} for f in near])
        return len(near)
