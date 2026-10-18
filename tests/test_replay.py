"""Stopping a replay early never leaves a stop-work alert behind.

Run: .venv/bin/python -m unittest tests.test_replay -v
"""
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from jobs import replay
from jobs.lightning import LightningRule

SITE = {"site_id": 621, "latitude": 25.43, "longitude": -80.33}
NOW = datetime(2026, 10, 18, 7, 0, tzinfo=timezone.utc)


def strike_near_site():
    return {"strike_id": "replay-1", "struck_at": NOW.isoformat(), "latitude": 25.43 + 6 / 69.0,
            "longitude": -80.33, "is_replay": True}


class StopEarlyTest(unittest.TestCase):
    def setUp(self):
        self.sent = []
        self.publish = lambda type, **ids: self.sent.append((type, ids))
        self.rule = LightningRule([SITE])
        self.rule.process([strike_near_site()], NOW, NOW)  # an open replay stop-work alert

    def test_stop_early_clears_alert_and_tells_screens(self):
        with patch.object(replay, "write_live_alerts") as write:
            replay.stop_early(self.rule, None, self.publish)
        self.assertEqual(self.sent, [("alert.cleared", {"site_id": 621, "alert_id": 1})])
        self.assertEqual(self.rule.active, {})
        write.assert_called_once_with([])

    def test_ctrl_c_during_replay_runs_cleanup(self):
        storm = {"name": "test", "flashes": []}
        with patch.object(replay, "_play", side_effect=KeyboardInterrupt), \
             patch.object(replay, "stop_early") as stop, \
             patch.object(replay, "_tiger_store", return_value=None), \
             patch.object(replay, "storm_start", return_value=NOW):
            replay.replay(storm, [SITE], speed=10, publish=self.publish)
        stop.assert_called_once()


if __name__ == "__main__":
    unittest.main()
