"""
Lightning stop-work rule (Sperry brief, contract section 8).

    Any strike within 10 miles of a site -> stop-work alert.
    The all-clear countdown is 30 minutes from the LATEST qualifying strike,
    so every new strike within 10 miles resets it.
    The alert clears when 30 minutes pass with no new strike.

`LightningRule` is pure logic: feed it flashes and the current time, and it
returns the notices to publish. No network, no clock of its own, so it can be
tested with fake strikes. `run()` at the bottom is the live loop that feeds it
real GOES flashes and publishes each notice to the DeepSpace bridge.

Safety: missing data is never "safe". An alert only clears after 30 quiet
minutes that the job actually watched: if the feed was down (or the job
restarted) during the countdown, the alert stays until the feed has been up
for a full 30 minutes with no new strike.

Where alerts live: an AlertStore. MemoryStore for tests and file-only runs;
jobs/lightning_store.TigerStore saves alerts and nearby strikes to Tiger Data,
so they survive restarts and the API reads them from the database.
"""
from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from jobs import glm

log = logging.getLogger("planit.lightning")

STOP_WORK_MILES = 10.0
ALL_CLEAR = timedelta(minutes=30)
# Continental U.S. (generous). GLM sees the whole hemisphere; skip the rest.
US_BOX = {"lat": (24.0, 50.0), "lon": (-125.0, -66.0)}


def in_us(flash: dict) -> bool:
    return US_BOX["lat"][0] <= flash["latitude"] <= US_BOX["lat"][1] and \
        US_BOX["lon"][0] <= flash["longitude"] <= US_BOX["lon"][1]


def _iso(t: datetime) -> str:
    return t.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _parse(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


@dataclass
class ActiveAlert:
    alert_id: int
    site_id: int
    started_at: datetime
    last_trigger_at: datetime
    trigger: dict
    clear_at: datetime

    def to_row(self) -> dict:
        """Shaped like the contract's alerts table."""
        return {
            "id": self.alert_id,
            "site_id": self.site_id,
            "hazard_type": "lightning",
            "level": "stop_work",
            "message": f"Lightning {self.trigger['distance_mi']} mi away. Stop work.",
            "started_at": _iso(self.started_at),
            "last_trigger_at": _iso(self.last_trigger_at),
            "clear_at": _iso(self.clear_at),
            "trigger": self.trigger,
        }


class MemoryStore:
    """Alert IDs from a counter; nothing persisted. Tests and file-only runs."""

    def __init__(self, first_alert_id: int = 1):
        self._next_id = first_alert_id

    def start(self, alert: ActiveAlert) -> int:
        alert_id, self._next_id = self._next_id, self._next_id + 1
        return alert_id

    def update(self, alert: ActiveAlert) -> None:
        pass

    def end(self, alert: ActiveAlert, at: datetime) -> None:
        pass


class LightningRule:
    def __init__(self, sites: list[dict], first_alert_id: int = 1, all_clear: timedelta = ALL_CLEAR,
                 store=None):
        self.sites = sites
        self.active: dict[int, ActiveAlert] = {}  # site_id -> alert
        self.store = store or MemoryStore(first_alert_id)
        self.all_clear = all_clear  # shortened only by replay's demo speed

    def resume(self, alerts: list[ActiveAlert]) -> None:
        """Pick up alerts still active from before a restart."""
        for alert in alerts:
            self.active[alert.site_id] = alert

    def process(self, flashes: list[dict], now: datetime, feed_ok_since: datetime | None) -> list[dict]:
        """Apply new flashes, then expire countdowns.

        feed_ok_since: start of the current unbroken stretch of good feed data
        (None if the feed is down right now). Clears only happen when the feed
        has been up for the whole countdown.
        Returns notices: {"type": ..., "site_id": ..., "alert_id": ..., "clear_at": ...}
        """
        notices: list[dict] = []
        us_flashes = [f for f in flashes if in_us(f)]

        for site in self.sites:
            sid = site["site_id"]
            near = []
            for f in us_flashes:
                miles = glm.distance_mi(site["latitude"], site["longitude"], f["latitude"], f["longitude"])
                if miles <= STOP_WORK_MILES:
                    near.append((miles, f))
            if not near:
                continue
            # Latest strike drives the countdown; report its distance.
            miles, latest = max(near, key=lambda pair: pair[1]["struck_at"])
            struck_at = _parse(latest["struck_at"])
            trigger = {"strike_id": latest["strike_id"], "distance_mi": round(miles, 1)}
            if latest.get("is_replay"):
                trigger["is_replay"] = True

            alert = self.active.get(sid)
            if alert is None:
                alert = ActiveAlert(0, sid, started_at=struck_at, last_trigger_at=struck_at,
                                    trigger=trigger, clear_at=struck_at + self.all_clear)
                alert.alert_id = self.store.start(alert)
                self.active[sid] = alert
                notices.append({"type": "alert.started", "site_id": sid, "alert_id": alert.alert_id})
            elif struck_at > alert.last_trigger_at:
                alert.last_trigger_at = struck_at
                alert.clear_at = struck_at + self.all_clear
                alert.trigger = trigger
                self.store.update(alert)
                notices.append({"type": "alert.updated", "site_id": sid, "alert_id": alert.alert_id,
                                "clear_at": _iso(alert.clear_at)})

        for sid, alert in list(self.active.items()):
            # Clear only after 30 quiet minutes we actually watched: the feed must
            # be up now and have been up for a full countdown since the later of
            # the last strike and when the feed (or job) came back.
            if feed_ok_since is None:
                continue
            if now < max(alert.clear_at, feed_ok_since + self.all_clear):
                continue
            del self.active[sid]
            self.store.end(alert, now)
            notices.append({"type": "alert.cleared", "site_id": sid, "alert_id": alert.alert_id})

        return notices

    def alerts(self) -> list[dict]:
        return [a.to_row() for a in self.active.values()]


# ---------------------------------------------------------------- shared state

# Until the alerts table exists in Tiger Data, the job hands its active alerts
# to the API through this file (gitignored). Written atomically so the API
# never reads half a file.
LIVE_ALERTS = Path(__file__).resolve().parents[1] / "data" / "live" / "alerts.json"


def write_live_alerts(rows: list[dict]) -> None:
    LIVE_ALERTS.parent.mkdir(parents=True, exist_ok=True)
    tmp = LIVE_ALERTS.with_suffix(".tmp")
    tmp.write_text(json.dumps({"updated_at": _iso(datetime.now(timezone.utc)), "lightning": rows}, indent=2))
    os.replace(tmp, LIVE_ALERTS)


# How the live watch is doing, so the API can say "clear" only when it knows.
# Written every poll by the live job (never by the replay).
LIVE_STATUS = LIVE_ALERTS.with_name("lightning_status.json")


def write_status(now: datetime, feed_ok_since: datetime | None, error: str | None) -> None:
    tmp = LIVE_STATUS.with_suffix(".tmp")
    tmp.write_text(json.dumps({
        "checked_at": _iso(now),
        "feed_ok_since": _iso(feed_ok_since) if feed_ok_since else None,
        "error": error,
    }, indent=2))
    os.replace(tmp, LIVE_STATUS)


def _tiger_store(replay: bool):
    """TigerStore when DATABASE_URL is set, else None (file-only)."""
    from api import db
    if not db.configured():
        return None
    from jobs.lightning_store import TigerStore
    return TigerStore(replay=replay)


# ---------------------------------------------------------------- live loop

def run(sites: list[dict], poll_seconds: float = 20.0, publish=None) -> None:
    """Poll both GOES satellites forever, apply the rule, publish notices."""
    if publish is None:
        from api.realtime import publish
    store = _tiger_store(replay=False)
    rule = LightningRule(sites, store=store)
    if store is not None:
        rule.resume(store.load_active(sites, all_clear=ALL_CLEAR))
        log.info("resumed %d active lightning alerts from Tiger Data", len(rule.active))
    seen: dict[str, str] = {}  # satellite -> newest file key processed
    feed_ok_since: datetime | None = None

    while True:
        now = datetime.now(timezone.utc)
        flashes: list[dict] = []
        error = None
        try:
            for sat in glm.SATELLITES:
                keys = glm.latest_keys(sat, count=6, now=now)
                new = [k for k in keys if k > seen.get(sat, "")]
                if sat not in seen:
                    new = new[-1:]  # on startup, just the newest file
                for key in new:
                    flashes += glm.parse_flashes(glm._get(glm.file_url(sat, key)), sat, key)
                if keys:
                    seen[sat] = keys[-1]
            feed_ok_since = feed_ok_since or now
        except Exception as e:  # network or parse failure: feed is down
            log.warning("lightning feed unavailable: %s", e)
            feed_ok_since = None
            error = "Lightning feed is unavailable"

        if store is not None and flashes:
            store.save_strikes(flashes, sites)
        notices = rule.process(flashes, now, feed_ok_since)
        write_live_alerts(rule.alerts())  # before publishing, so screens fetch fresh data
        write_status(now, feed_ok_since, error)
        for notice in notices:
            log.info("notice %s", notice)
            ids = {k: v for k, v in notice.items() if k != "type"}
            publish(notice["type"], **ids)

        time.sleep(poll_seconds)


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    for line in (root / ".env").read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    from api.site_data import load_sites
    sites = load_sites()
    log.info("watching %d sites for lightning within %.0f mi", len(sites), STOP_WORK_MILES)
    run(sites)
