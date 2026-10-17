"""
6 PM next-day safety briefings (Sperry brief, requirement 3).

Every minute, for each monitored site: once the site's LOCAL time is 6 PM or
later and it has no briefing for tomorrow yet, write one with api.briefing and
save it. Sites in different time zones get theirs at their own 6 PM.

Until the briefings table is live in Tiger Data, briefings go to
data/live/briefings.json (gitignored), which the API serves.

    .venv/bin/python -m jobs.briefings          # run the scheduler
    .venv/bin/python -m jobs.briefings --now    # write every site's briefing once, immediately
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from api import db
from api.briefing import briefing_for, latest_forecasts
from api.site_data import ROOT, load_sites

log = logging.getLogger("planit.briefings")
LIVE_BRIEFINGS = ROOT / "data" / "live" / "briefings.json"
SEND_HOUR = 18  # 6 PM local


def load_saved() -> dict:
    try:
        return json.loads(LIVE_BRIEFINGS.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save(briefings: dict) -> None:
    LIVE_BRIEFINGS.parent.mkdir(parents=True, exist_ok=True)
    tmp = LIVE_BRIEFINGS.with_suffix(".tmp")
    tmp.write_text(json.dumps(briefings, indent=2))
    os.replace(tmp, LIVE_BRIEFINGS)


def current_alerts() -> list[dict]:
    try:
        return json.loads((ROOT / "data" / "live" / "alerts.json").read_text())["lightning"]
    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        return []


def due(site: dict, saved: dict, now: datetime) -> bool:
    """Past 6 PM local, and no briefing for tomorrow written since then.

    A briefing written earlier in the day (a manual --now run) doesn't count:
    the scheduled one uses the latest forecast at 6 PM.
    """
    tz = ZoneInfo(site["timezone"])
    local = now.astimezone(tz)
    if local.hour < SEND_HOUR:
        return False
    tomorrow = (local.date() + timedelta(days=1)).isoformat()
    have = saved.get(str(site["site_id"]))
    if not have or have["for_date"] != tomorrow:
        return True
    sent_at = datetime.fromisoformat(have["generated_at"].replace("Z", "+00:00")).astimezone(tz)
    return sent_at.date() != local.date() or sent_at.hour < SEND_HOUR


def run_once(force: bool = False) -> int:
    """Write every briefing that's due (or all, if force). Returns how many."""
    saved, now = load_saved(), datetime.now(timezone.utc)
    rows, as_of = latest_forecasts()
    if not rows:
        log.warning("no forecasts available; no briefings written")
        return 0
    written = 0
    for site in load_sites():
        if not (force or due(site, saved, now)):
            continue
        b = briefing_for(site, rows, current_alerts(), now=now)
        if b is None:
            log.warning("no forecast for %s tomorrow", site["name"])
            continue
        saved[str(site["site_id"])] = b
        save(saved)  # save as we go, so a crash keeps finished briefings
        if db.configured():
            db.execute("""
                INSERT INTO public.briefings (site_id, for_date, generated_at, text, model, inputs)
                VALUES (:site_id, :for_date, :generated_at, :text, :model, CAST(:inputs AS jsonb))""",
                site_id=b["site_id"], for_date=b["for_date"], generated_at=b["generated_at"],
                text=b["text"], model=os.environ.get("GEMINI_MODEL", "") if b["inputs"]["method"] == "gemini" else "template",
                inputs=json.dumps(b["inputs"]))
        written += 1
        log.info("briefing for %s (%s) via %s", site["name"], b["for_date"], b["inputs"]["method"])
    return written


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--now", action="store_true", help="write every site's briefing once and exit")
    args = parser.parse_args()
    for line in (ROOT / ".env").read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    if args.now:
        log.info("wrote %d briefings", run_once(force=True))
    else:
        log.info("briefing scheduler running: each site at %d:00 local", SEND_HOUR)
        while True:
            run_once()
            time.sleep(60)
