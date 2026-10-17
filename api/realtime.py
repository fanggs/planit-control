"""
Publish real-time notices to the DeepSpace bridge (planit-realtime).

Every screen subscribes to the bridge's `events` collection. When something
changes here (an alert starts, a report comes in, scores update), the API
posts a small notice to the bridge, and DeepSpace pushes it to every open
screen. Notices carry IDs only; screens fetch the real data from this API.

Call `publish(...)` only after the database write has succeeded, so a screen
never hears about something that didn't save. Publishing never raises: a
failed notice is logged, and the next refresh still shows the right data.

Needs in .env:
    DEEPSPACE_URL=https://<app>.app.space
    PLANIT_NOTIFY_SECRET=<same value as the bridge's secret>
"""
from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request

log = logging.getLogger("planit.realtime")

TYPES = {
    "alert.started", "alert.updated", "alert.cleared",
    "report.created", "report.resolved",
    "scores.updated",
}


def publish(type: str, **ids) -> bool:
    """Send one notice. Returns True if the bridge accepted it.

    publish("alert.started", site_id=9001, alert_id=101)
    publish("alert.updated", site_id=9001, alert_id=101, clear_at="2026-10-17T18:34:00Z")
    publish("report.created", site_id=9001, report_id="3f6c...")
    publish("scores.updated", site_ids=[9001, 9002])
    """
    if type not in TYPES:
        raise ValueError(f"unknown notice type: {type}")

    base = os.environ.get("DEEPSPACE_URL", "").rstrip("/")
    secret = os.environ.get("PLANIT_NOTIFY_SECRET", "")
    if not base or not secret:
        log.warning("realtime not configured; skipped %s", type)
        return False

    body = json.dumps({"type": type, **ids}).encode()
    req = urllib.request.Request(
        f"{base}/api/notify",
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {secret}",
            "User-Agent": "planit-control/0.1",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status == 200
    except urllib.error.HTTPError as e:
        log.warning("notice %s refused: HTTP %s %s", type, e.code, e.read()[:200])
    except (urllib.error.URLError, TimeoutError) as e:
        log.warning("notice %s not delivered: %s", type, e)
    return False
