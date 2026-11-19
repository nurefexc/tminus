import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
from tminus import active_alarms, format_countdown, urgency_for  # noqa: E402


class CountdownTests(unittest.TestCase):
    def test_format(self):
        self.assertEqual(format_countdown(0), "00:00:00")
        self.assertEqual(format_countdown(42), "00:00:42")
        self.assertEqual(format_countdown(95.9), "00:01:35")
        self.assertEqual(format_countdown(3661), "01:01:01")
        self.assertEqual(format_countdown(90061), "1d 01:01:01")

    def test_urgency(self):
        self.assertEqual(urgency_for(3601), "low")
        self.assertEqual(urgency_for(3600), "normal")
        self.assertEqual(urgency_for(600), "critical")


class AlarmWindowTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 11, 19, 7, 30, 0).astimezone()
        self.date = self.now.strftime("%Y-%m-%d")

    def event(self, alarm_delta, **extra):
        event = {
            "uid": "abc",
            "title": "Standup",
            "calendar": "work",
            "start-date-full": self.date,
            "start-time-full": "08:00",
            "alarms-list": [{"delta": alarm_delta}],
        }
        event.update(extra)
        return event

    def test_alarm_fired_but_not_started(self):
        alarms = active_alarms([self.event(-3600)], self.now)
        self.assertEqual(len(alarms), 1)
        self.assertEqual(alarms[0]["uid"], "abc")
        self.assertEqual(alarms[0]["alarm_at"][:16], "2026-11-19T07:00")

    def test_alarm_not_yet_fired(self):
        self.assertEqual(active_alarms([self.event(-60)], self.now), [])

    def test_event_already_started(self):
        past = self.event(-7200, **{"start-time-full": "06:00"})
        self.assertEqual(active_alarms([past], self.now), [])

    def test_event_without_alarm_is_ignored(self):
        self.assertEqual(active_alarms([self.event(-3600, **{"alarms-list": []})],
                                       self.now), [])

    def test_latest_fired_alarm_wins(self):
        event = self.event(-3600)
        event["alarms-list"] = [{"delta": -3600}, {"delta": -600}]
        later = self.now + timedelta(minutes=25)
        alarms = active_alarms([event], later)
        self.assertEqual(alarms[0]["alarm_at"][:16], "2026-11-19T07:50")


if __name__ == "__main__":
    unittest.main()
