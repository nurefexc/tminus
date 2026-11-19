import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
import tminus  # noqa: E402
from tminus import (active_alarms, alarm_key, format_countdown, is_urgent,  # noqa: E402
                    load_dismissed, notification_style, save_dismissed,
                    urgency_for)


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


class ColourTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.patcher = patch.object(tminus, "CALENDAR_DIR", self.base)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)
        self.addCleanup(self.tmp.cleanup)

    def test_calendar_color_from_vdir(self):
        (self.base / "work").mkdir()
        (self.base / "work" / "color").write_text("#A6E3A1\n", encoding="utf-8")
        self.assertEqual(tminus.calendar_color("work"), "#a6e3a1")
        self.assertEqual(tminus.calendar_color("missing"), None)
        self.assertEqual(tminus.calendar_color("../work"), None)

    def test_alpha_channel_is_stripped(self):
        (self.base / "personal").mkdir()
        (self.base / "personal" / "color").write_text(
            "#1c71d8ff\n", encoding="utf-8")
        self.assertEqual(tminus.calendar_color("personal"), "#1c71d8")

    def test_displayname_resolution(self):
        folder = self.base / "personal"
        folder.mkdir()
        (folder / "color").write_text("#1c71d8ff", encoding="utf-8")
        (folder / "displayname").write_text("Personal", encoding="utf-8")
        self.assertEqual(tminus.calendar_color("Personal"), "#1c71d8")
        self.assertEqual(tminus.calendar_color("personal"), "#1c71d8")
        self.assertEqual(tminus.calendar_color("unknown"), None)

    def test_displayname_with_slash(self):
        folder = self.base / "calendar-it"
        folder.mkdir()
        (folder / "color").write_text("#f57c00ff", encoding="utf-8")
        (folder / "displayname").write_text("Events/IT", encoding="utf-8")
        self.assertEqual(tminus.calendar_color("Events/IT"), "#f57c00")

    def test_invalid_color_is_ignored(self):
        (self.base / "bad").mkdir()
        (self.base / "bad" / "color").write_text("not-a-colour", encoding="utf-8")
        self.assertEqual(tminus.calendar_color("bad"), None)

    def test_style_uses_calendar_color_until_final_minute(self):
        (self.base / "work").mkdir()
        (self.base / "work" / "color").write_text("#89b4fa", encoding="utf-8")
        alarm = {"calendar": "work"}
        self.assertEqual(notification_style(alarm, 300), {"frcolor": "#89b4fa"})
        self.assertFalse(is_urgent(61))
        self.assertTrue(is_urgent(59))
        self.assertEqual(notification_style(alarm, 30),
                         {"frcolor": tminus.URGENT_COLOR,
                          "fgcolor": tminus.URGENT_COLOR})

    def test_style_without_color_uses_daemon_default(self):
        self.assertEqual(notification_style({"calendar": "none"}, 300), {})


class DismissalTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)

    def test_key_is_stable_per_alarm_instance(self):
        alarm = {"uid": "abc", "alarm_at": "2026-11-19T07:00:00+01:00"}
        self.assertEqual(alarm_key(alarm), alarm_key(dict(alarm)))
        self.assertNotEqual(alarm_key(alarm),
                            alarm_key({**alarm, "alarm_at": "other"}))

    def test_dismissed_round_trip(self):
        target = self.base / "dismissed.json"
        with patch.object(tminus, "DISMISSED_FILE", target), \
             patch.object(tminus, "RUN_DIR", self.base):
            self.assertEqual(load_dismissed(), set())
            save_dismissed({"a|b", "c|d"})
            self.assertEqual(load_dismissed(), {"a|b", "c|d"})

    def test_event_log_appends_json_lines(self):
        target = self.base / "state" / "events.log"
        alarm = {"uid": "abc", "alarm_at": "2026-11-19T07:00:00+01:00",
                 "title": "Standup", "calendar": "work"}
        with patch.object(tminus, "EVENT_LOG", target):
            tminus.log_event("shown", alarm, notification_id=42)
            tminus.log_event("dismiss", alarm, notification_id=42, reason=2)
        rows = [json.loads(line) for line in target.read_text().splitlines()]
        self.assertEqual([row["event"] for row in rows], ["shown", "dismiss"])
        self.assertEqual(rows[1]["reason"], 2)
        self.assertEqual(rows[0]["key"], alarm_key(alarm))


if __name__ == "__main__":
    unittest.main()
