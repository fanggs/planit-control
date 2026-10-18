"""Lightning status, NWS status, and the NWS warnings job, with fake data.

Run: .venv/bin/python -m unittest tests.test_live_status -v
"""
import unittest
from datetime import datetime, timedelta, timezone

from api.live_status import lightning_status, warnings_status
from jobs.nws import NwsAlert, parse, sync_site

NOW = datetime(2026, 10, 18, 2, 0, tzinfo=timezone.utc)


def iso(dt):
    return dt.isoformat().replace("+00:00", "Z")


def watch(checked_ago=timedelta(seconds=20), ok_for=timedelta(hours=2), error=None):
    return {"checked_at": iso(NOW - checked_ago),
            "feed_ok_since": iso(NOW - ok_for) if ok_for is not None else None, "error": error}


HOLD = {"site_id": 621, "hazard_type": "lightning", "level": "stop_work"}


class LightningStatusTest(unittest.TestCase):
    def test_clear_when_watch_is_fresh_and_working(self):
        s = lightning_status(621, [], watch(), NOW)
        self.assertEqual((s["status"], s["reason"]), ("clear", None))

    def test_stop_work_alert_wins(self):
        self.assertEqual(lightning_status(621, [HOLD], watch(), NOW)["status"], "stop_work")
        self.assertEqual(lightning_status(621, [HOLD], None, NOW)["status"], "stop_work")

    def test_other_sites_alert_does_not_count(self):
        self.assertEqual(lightning_status(622, [HOLD], watch(), NOW)["status"], "clear")

    def test_unknown_when_job_never_ran(self):
        self.assertEqual(lightning_status(621, [], None, NOW)["status"], "unknown")

    def test_unknown_when_watch_is_stale(self):
        s = lightning_status(621, [], watch(checked_ago=timedelta(minutes=6)), NOW)
        self.assertEqual(s["status"], "unknown")

    def test_unknown_when_feed_is_down(self):
        s = lightning_status(621, [], watch(ok_for=None, error="Lightning feed is unavailable"), NOW)
        self.assertEqual((s["status"], s["reason"]), ("unknown", "Lightning feed is unavailable"))

    def test_unknown_until_30_watched_minutes_after_restart(self):
        self.assertEqual(lightning_status(621, [], watch(ok_for=timedelta(minutes=29)), NOW)["status"], "unknown")
        self.assertEqual(lightning_status(621, [], watch(ok_for=timedelta(minutes=30)), NOW)["status"], "clear")


class WarningsStatusTest(unittest.TestCase):
    def test_ok_only_for_checked_sites_recently(self):
        w = {"checked_at": iso(NOW - timedelta(minutes=4)), "sites_ok": [621]}
        self.assertEqual(warnings_status(621, w, NOW)["status"], "ok")
        self.assertEqual(warnings_status(622, w, NOW)["status"], "unknown")
        stale = {"checked_at": iso(NOW - timedelta(minutes=20)), "sites_ok": [621]}
        self.assertEqual(warnings_status(621, stale, NOW)["status"], "unknown")
        self.assertEqual(warnings_status(621, None, NOW)["status"], "unknown")


def nws(event, n=1, starts=NOW - timedelta(hours=1), ends=NOW + timedelta(hours=6)):
    return NwsAlert(id=f"https://api.weather.gov/alerts/urn:test.{n}", event=event,
                    title=f"{event} issued by NWS", severity="severe", starts_at=starts, ends_at=ends)


class FakeStore:
    def __init__(self):
        self.events, self.alerts, self.next_id = {}, {}, 100

    def save_events(self, site_id, active, now):
        for a in active:
            self.events[a.id] = {"kind": a.event_kind, "ended": False}

    def end_missing_events(self, site_id, active_ids, now):
        for k, e in self.events.items():
            if k not in active_ids:
                e["ended"] = True

    def open_warning_alerts(self, site_id):
        return {a["event"]: {"id": i, "clear_at": a["clear_at"]} for i, a in self.alerts.items() if not a["ended"]}

    def start_alert(self, site_id, a, now):
        self.next_id += 1
        self.alerts[self.next_id] = {"event": a.event, "clear_at": a.ends_at, "ended": False}
        return self.next_id

    def update_alert(self, alert_id, a, now):
        self.alerts[alert_id]["clear_at"] = a.ends_at

    def end_alert(self, alert_id, now):
        self.alerts[alert_id]["ended"] = True


class NwsJobTest(unittest.TestCase):
    def test_parse_skips_tests_and_cancels(self):
        def feature(n, status="Actual", kind="Alert"):
            return {"id": f"u{n}", "properties": {"event": "Flood Warning", "headline": "h", "severity": "Severe",
                    "status": status, "messageType": kind, "onset": "2026-10-17T21:40:00-04:00",
                    "effective": "2026-10-17T21:40:00-04:00", "ends": None, "expires": "2026-10-18T11:00:00-04:00"}}
        alerts = parse({"features": [feature(1), feature(2, status="Test"), feature(3, kind="Cancel")]})
        self.assertEqual([a.id for a in alerts], ["u1"])
        self.assertEqual(alerts[0].starts_at, datetime(2026, 10, 18, 1, 40, tzinfo=timezone.utc))
        self.assertEqual(alerts[0].ends_at, datetime(2026, 10, 18, 15, 0, tzinfo=timezone.utc))  # falls back to expires
        self.assertEqual((alerts[0].hazard_type, alerts[0].event_kind), ("flooding", "nws_warning"))

    def test_flood_warning_starts_one_warning_alert(self):
        store = FakeStore()
        notices = sync_site(621, [nws("Flood Warning")], store, NOW)
        self.assertEqual(notices, [{"type": "alert.started", "site_id": 621, "alert_id": 101}])

    def test_advisories_and_watches_are_events_only(self):
        store = FakeStore()
        self.assertEqual(sync_site(621, [nws("High Surf Advisory"), nws("Flood Watch", n=2)], store, NOW), [])
        self.assertEqual(len(store.events), 2)

    def test_heat_advisory_and_red_flag_raise_warnings(self):
        store = FakeStore()
        notices = sync_site(621, [nws("Heat Advisory"), nws("Red Flag Warning", n=2)], store, NOW)
        self.assertEqual([n["type"] for n in notices], ["alert.started", "alert.started"])

    def test_nws_update_keeps_the_same_alert(self):
        store = FakeStore()
        sync_site(621, [nws("Flood Warning", n=1)], store, NOW)
        later = nws("Flood Warning", n=2, ends=NOW + timedelta(hours=9))  # NWS update: new ID
        notices = sync_site(621, [later], store, NOW + timedelta(minutes=5))
        self.assertEqual([n["type"] for n in notices], ["alert.updated"])
        self.assertTrue(store.events[nws("Flood Warning", n=1).id]["ended"])  # old message superseded

    def test_alert_ends_when_nws_drops_it(self):
        store = FakeStore()
        sync_site(621, [nws("Flood Warning")], store, NOW)
        self.assertEqual(sync_site(621, [], store, NOW + timedelta(minutes=5)),
                         [{"type": "alert.cleared", "site_id": 621, "alert_id": 101}])

    def test_future_warning_waits_for_onset(self):
        store = FakeStore()
        upcoming = nws("Heat Advisory", starts=NOW + timedelta(hours=10), ends=NOW + timedelta(hours=20))
        self.assertEqual(sync_site(621, [upcoming], store, NOW), [])
        self.assertEqual(len(store.events), 1)  # still listed as an upcoming event


if __name__ == "__main__":
    unittest.main()
