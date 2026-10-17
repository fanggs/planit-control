"""Lightning stop-work rule, tested with fake strikes.

Run: .venv/bin/python -m unittest tests.test_lightning -v
"""
import unittest
from datetime import datetime, timedelta, timezone

from jobs.lightning import LightningRule

T0 = datetime(2026, 10, 17, 18, 0, tzinfo=timezone.utc)
SITE = {"site_id": 9001, "latitude": 25.43, "longitude": -80.33}  # Everglades sample


def strike(minutes_after: float, miles_north: float, n: int = 0) -> dict:
    """A flash `miles_north` of the site (1 degree latitude ~ 69 miles)."""
    t = T0 + timedelta(minutes=minutes_after)
    return {
        "strike_id": f"test-{n}",
        "struck_at": t.isoformat(),
        "latitude": SITE["latitude"] + miles_north / 69.0,
        "longitude": SITE["longitude"],
    }


def at(minutes_after: float) -> datetime:
    return T0 + timedelta(minutes=minutes_after)


FEED_UP = T0 - timedelta(hours=1)  # feed healthy since well before the storm


class LightningRuleTest(unittest.TestCase):
    def setUp(self):
        self.rule = LightningRule([SITE])

    def test_strike_within_10_miles_starts_alert(self):
        notices = self.rule.process([strike(0, 6)], at(0), FEED_UP)
        self.assertEqual(notices, [{"type": "alert.started", "site_id": 9001, "alert_id": 1}])
        row = self.rule.alerts()[0]
        self.assertEqual(row["level"], "stop_work")
        self.assertEqual(row["clear_at"], "2026-10-17T18:30:00Z")
        self.assertEqual(row["trigger"]["distance_mi"], 6.0)

    def test_strike_beyond_10_miles_is_ignored(self):
        self.assertEqual(self.rule.process([strike(0, 12)], at(0), FEED_UP), [])
        self.assertEqual(self.rule.alerts(), [])

    def test_new_strike_resets_countdown(self):
        self.rule.process([strike(0, 6, n=1)], at(0), FEED_UP)
        notices = self.rule.process([strike(15, 8, n=2)], at(15), FEED_UP)
        self.assertEqual(notices, [{"type": "alert.updated", "site_id": 9001, "alert_id": 1,
                                    "clear_at": "2026-10-17T18:45:00Z"}])

    def test_clears_after_30_quiet_minutes_from_last_strike(self):
        self.rule.process([strike(0, 6, n=1)], at(0), FEED_UP)
        self.rule.process([strike(15, 8, n=2)], at(15), FEED_UP)
        self.assertEqual(self.rule.process([], at(30), FEED_UP), [])  # 30 min after FIRST strike: still active
        notices = self.rule.process([], at(45), FEED_UP)
        self.assertEqual(notices, [{"type": "alert.cleared", "site_id": 9001, "alert_id": 1}])
        self.assertEqual(self.rule.alerts(), [])

    def test_feed_down_never_clears(self):
        self.rule.process([strike(0, 6)], at(0), FEED_UP)
        self.assertEqual(self.rule.process([], at(40), None), [])  # feed down: hold
        self.assertEqual(len(self.rule.alerts()), 1)

    def test_feed_gap_during_countdown_never_clears(self):
        self.rule.process([strike(0, 6)], at(0), FEED_UP)
        # Feed came back at minute 20, so minutes 0-20 were unwatched.
        self.assertEqual(self.rule.process([], at(40), at(20)), [])
        self.assertEqual(len(self.rule.alerts()), 1)

    def test_older_strike_does_not_shorten_countdown(self):
        self.rule.process([strike(10, 6, n=1)], at(10), FEED_UP)
        self.assertEqual(self.rule.process([strike(5, 6, n=2)], at(11), FEED_UP), [])
        self.assertEqual(self.rule.alerts()[0]["clear_at"], "2026-10-17T18:40:00Z")

    def test_new_storm_after_clear_gets_new_alert_id(self):
        self.rule.process([strike(0, 6, n=1)], at(0), FEED_UP)
        self.rule.process([], at(31), FEED_UP)
        notices = self.rule.process([strike(40, 6, n=2)], at(40), FEED_UP)
        self.assertEqual(notices, [{"type": "alert.started", "site_id": 9001, "alert_id": 2}])

    def test_flashes_outside_us_are_skipped(self):
        brazil = {"strike_id": "x", "struck_at": T0.isoformat(), "latitude": -8.0, "longitude": -62.7}
        self.assertEqual(self.rule.process([brazil], at(0), FEED_UP), [])

    def test_feed_gap_clears_after_30_watched_minutes(self):
        self.rule.process([strike(0, 6)], at(0), FEED_UP)
        # Feed came back at minute 20: needs 30 watched quiet minutes, so 50.
        self.assertEqual(self.rule.process([], at(49), at(20)), [])
        self.assertEqual(self.rule.process([], at(50), at(20)),
                         [{"type": "alert.cleared", "site_id": 9001, "alert_id": 1}])


class RecordingStore:
    def __init__(self):
        self.calls = []

    def start(self, alert):
        self.calls.append(("start", alert.site_id))
        return 500 + len(self.calls)

    def update(self, alert):
        self.calls.append(("update", alert.alert_id))

    def end(self, alert, at):
        self.calls.append(("end", alert.alert_id))


class StoreTest(unittest.TestCase):
    def test_rule_uses_store_ids_and_calls(self):
        store = RecordingStore()
        rule = LightningRule([SITE], store=store)
        started = rule.process([strike(0, 6, n=1)], at(0), FEED_UP)
        self.assertEqual(started[0]["alert_id"], 501)       # ID comes from the store
        rule.process([strike(10, 7, n=2)], at(10), FEED_UP)
        rule.process([], at(41), FEED_UP)
        self.assertEqual(store.calls, [("start", 9001), ("update", 501), ("end", 501)])

    def test_resumed_alert_keeps_counting_after_restart(self):
        first = LightningRule([SITE])
        first.process([strike(0, 6)], at(0), FEED_UP)
        carried = list(first.active.values())
        restarted = LightningRule([SITE])
        restarted.resume(carried)
        # Job restarted at minute 10: not clear at 31, clear at 40 (30 watched minutes).
        self.assertEqual(restarted.process([], at(31), at(10)), [])
        self.assertEqual(restarted.process([], at(40), at(10))[0]["type"], "alert.cleared")


if __name__ == "__main__":
    unittest.main()
