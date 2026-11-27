import sys
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "installer"))
from schedule_times import parse_send_time, delivery_ready_at
from wizard import schedule_yaml
import yaml


class DeliveryTimeTests(unittest.TestCase):
    def test_valid_times(self):
        for value, expected in [("00:00", (0, 0)), ("08:30", (8, 30)),
                                ("23:59", (23, 59))]:
            self.assertEqual(parse_send_time(value), expected)

    def test_invalid_times(self):
        for value in ["8:00", "24:00", "09:60", "-1:00", "09:00\nfoo",
                      "", None, 900, " 09:00", "09:00:00"]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                parse_send_time(value)

    def test_legacy_midnight_and_statistics_delay(self):
        d = datetime(2026, 11, 28, tzinfo=ZoneInfo("Europe/Kyiv"))
        self.assertEqual(delivery_ready_at(d, {}, 10), d.timestamp() + 600)

    def test_delivery_at_requested_time(self):
        d = datetime(2026, 11, 28, tzinfo=ZoneInfo("Europe/Kyiv"))
        target = d.replace(hour=8, minute=15)
        self.assertEqual(
            delivery_ready_at(d, {"send_time": "08:15"}, 10),
            target.timestamp(),
        )

    def test_statistics_delay_is_minimum(self):
        d = datetime(2026, 11, 28, tzinfo=ZoneInfo("Europe/Kyiv"))
        self.assertEqual(delivery_ready_at(
            d, {"send_time": "00:05"}, 10), d.timestamp() + 600
        )

    def test_dst_dates_keep_local_time(self):
        tz = ZoneInfo("Europe/Kyiv")
        for d in [datetime(2026, 3, 29, tzinfo=tz),
                  datetime(2026, 10, 25, tzinfo=tz)]:
            with self.subTest(date=d.date()):
                ts = delivery_ready_at(d, {"send_time": "08:00"})
                result = datetime.fromtimestamp(ts, tz)
                self.assertEqual((result.hour, result.minute), (8, 0))
                self.assertEqual(result.date(), d.date())

    def test_yaml_preserves_custom_per_period_times(self):
        periods = {k: True for k in (
            "daily", "weekly", "monthly", "quarterly", "yearly"
        )}
        times = {k: value for k, value in zip(periods, (
            "08:00", "09:30", "10:00", "11:45", "12:15"
        ))}
        data = yaml.safe_load(schedule_yaml("Europe/Kyiv", periods, times))
        for period, value in times.items():
            self.assertEqual(data["reports"][period]["send_time"], value)
        self.assertEqual(data["reports"]["weekly"]["period"], "previous_week")

    def test_schedule_yaml_legacy_call(self):
        periods = {k: False for k in (
            "daily", "weekly", "monthly", "quarterly", "yearly"
        )}
        data = yaml.safe_load(schedule_yaml("Europe/Kyiv", periods))
        self.assertEqual(data["reports"]["daily"]["send_time"], "00:00")
