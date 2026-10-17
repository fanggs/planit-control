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

Safety: missing data is never "safe". If the lightning feed has been down
since before a countdown would end, the alert is NOT cleared; it stays until
fresh data shows 30 quiet minutes.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

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
    clear_at: datetime = field(init=False)

    def __post_init__(self):
        self.clear_at = self.last_trigger_at + ALL_CLEAR

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


class LightningRule:
    def __init__(self, sites: list[dict], first_alert_id: int = 1):
        self.sites = sites
        self.active: dict[int, ActiveAlert] = {}  # site_id -> alert
        self._next_id = first_alert_id

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

            alert = self.active.get(sid)
            if alert is None:
                alert = ActiveAlert(self._next_id, sid, started_at=struck_at, last_trigger_at=struck_at, trigger=trigger)
                self._next_id += 1
                self.active[sid] = alert
                notices.append({"type": "alert.started", "site_id": sid, "alert_id": alert.alert_id})
            elif struck_at > alert.last_trigger_at:
                alert.last_trigger_at = struck_at
                alert.clear_at = struck_at + ALL_CLEAR
                alert.trigger = trigger
                notices.append({"type": "alert.updated", "site_id": sid, "alert_id": alert.alert_id,
                                "clear_at": _iso(alert.clear_at)})

        for sid, alert in list(self.active.items()):
            if now < alert.clear_at:
                continue
            # Only clear if we were watching the whole countdown window.
            if feed_ok_since is None or feed_ok_since > alert.last_trigger_at:
                continue
            del self.active[sid]
            notices.append({"type": "alert.cleared", "site_id": sid, "alert_id": alert.alert_id})

        return notices

    def alerts(self) -> list[dict]:
        return [a.to_row() for a in self.active.values()]


# ---------------------------------------------------------------- live loop

def run(sites: list[dict], poll_seconds: float = 20.0, publish=None) -> None:
    """Poll both GOES satellites forever, apply the rule, publish notices."""
    if publish is None:
        from api.realtime import publish
    rule = LightningRule(sites)
    seen: dict[str, str] = {}  # satellite -> newest file key processed
    feed_ok_since: datetime | None = None

    while True:
        now = datetime.now(timezone.utc)
        flashes: list[dict] = []
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

        for notice in rule.process(flashes, now, feed_ok_since):
            log.info("notice %s", notice)
            ids = {k: v for k, v in notice.items() if k != "type"}
            publish(notice["type"], **ids)

        time.sleep(poll_seconds)


if __name__ == "__main__":
    import json
    import os
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    for line in (root / ".env").read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    sites = json.loads((root / "api" / "samples" / "sites.json").read_text())
    log.info("watching %d sites for lightning within %.0f mi", len(sites), STOP_WORK_MILES)
    run(sites)
