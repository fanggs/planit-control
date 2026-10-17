"""
Labeled lightning replay for the demo.

There may be no storm near any site during the expo, so this plays back a real
recorded storm (data/replay/*.json, real NOAA GOES-19 flashes) as if it were
happening now, through the same LightningRule the live job uses.

Every replayed strike is marked `is_replay`, and alerts carry
`trigger.is_replay = true`, so screens label them "Replay". Nothing here is
presented as live weather.

    # real time: the storm and the 30-minute countdowns take as long as they did
    .venv/bin/python -m jobs.replay

    # demo speed: 10x faster, so a 30-minute countdown takes 3 minutes
    .venv/bin/python -m jobs.replay --speed 10

Speed also shortens the countdown by the same factor, so the replay keeps the
storm's real rhythm (strikes, resets, all-clear) just compressed.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from jobs.lightning import ALL_CLEAR, LightningRule, _iso, _tiger_store, write_live_alerts

log = logging.getLogger("planit.replay")
ROOT = Path(__file__).resolve().parents[1]
DEFAULT_STORM = ROOT / "data" / "replay" / "everglades-2026-08-03.json"
LEAD_IN = timedelta(minutes=5)  # start a bit before the first close strike so the storm approaches


def load_storm(path: Path) -> dict:
    storm = json.loads(path.read_text())
    for f in storm["flashes"]:
        f["_orig"] = datetime.fromisoformat(f["struck_at"].replace("Z", "+00:00"))
    storm["flashes"].sort(key=lambda f: f["_orig"])
    return storm


def storm_start(storm: dict, rule: LightningRule) -> datetime:
    """When the replay clock starts: shortly before the first strike that triggers an alert."""
    probe = LightningRule(rule.sites)
    for f in storm["flashes"]:
        if probe.process([dict(f, strike_id=f["source_id"])], f["_orig"], f["_orig"] - timedelta(hours=1)):
            return f["_orig"] - LEAD_IN
    return storm["flashes"][0]["_orig"]


def replay(storm: dict, sites: list[dict], speed: float = 1.0, publish=None, tick: float = 1.0) -> None:
    if publish is None:
        from api.realtime import publish
    store = _tiger_store(replay=True)
    rule = LightningRule(sites, all_clear=ALL_CLEAR / speed, store=store)
    t0_storm = storm_start(storm, rule)
    t0_wall = datetime.now(timezone.utc)
    if store is not None:
        store.end_all_open(t0_wall)  # a previous replay that was stopped midway
    pending = [f for f in storm["flashes"] if f["_orig"] >= t0_storm]
    log.info("replaying %s at %sx: %d flashes, starting %s", storm["name"], speed, len(pending), _iso(t0_storm))

    def shifted(orig: datetime) -> datetime:
        return t0_wall + (orig - t0_storm) / speed

    while True:
        now = datetime.now(timezone.utc)
        storm_now = t0_storm + (now - t0_wall) * speed
        due = []
        while pending and pending[0]["_orig"] <= storm_now:
            f = pending.pop(0)
            due.append({
                "strike_id": f"replay-{f['source_id']}",
                "struck_at": _iso(shifted(f["_orig"])),
                "latitude": f["latitude"],
                "longitude": f["longitude"],
                "is_replay": True,
                "source_name": storm["source_name"] + " (replay)",
                "source_url": f["source_url"],
                "retrieved_at": _iso(now),
            })
        if store is not None and due:
            store.save_strikes(due, sites)
        # The replay feed is always "up": it's recorded data.
        notices = rule.process(due, now, t0_wall - timedelta(hours=1))
        write_live_alerts(rule.alerts())
        for n in notices:
            log.info("notice %s", n)
            publish(n["type"], **{k: v for k, v in n.items() if k != "type"})
        if not pending and not rule.active:
            log.info("replay finished: storm over and all clear")
            write_live_alerts([])
            if store is not None:
                store.end_all_open(datetime.now(timezone.utc))
            return
        time.sleep(tick)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Play back a recorded storm, labeled as replay.")
    parser.add_argument("--speed", type=float, default=1.0, help="how many times faster than real time (default 1)")
    parser.add_argument("--storm", type=Path, default=DEFAULT_STORM)
    args = parser.parse_args()

    for line in (ROOT / ".env").read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    from api.site_data import load_sites
    sites = load_sites()
    replay(load_storm(args.storm), sites, speed=args.speed)
