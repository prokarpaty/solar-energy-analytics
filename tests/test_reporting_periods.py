import sys
import unittest
from pathlib import Path
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
with patch.object(Path, 'read_text', return_value='{}'):
    import ha_client as ha

class ReportingPeriods(unittest.TestCase):
    def period(self, kind, date, zone='Europe/Kyiv'):
        tz = ZoneInfo(zone)
        with patch.object(ha, 'TZ', tz):
            start, end = ha.get_period(kind, datetime.fromisoformat(date).replace(tzinfo=tz))
        return str(start.date()), str(end.date()), len(ha.expected_hours(start,end))
    def test_daily(self):
        self.assertEqual(self.period('daily','2026-11-25'), ('2026-11-24','2026-11-25',24))
    def test_spring(self):
        self.assertEqual(self.period('daily','2026-03-30')[2],23)
    def test_autumn(self):
        self.assertEqual(self.period('daily','2026-10-26')[2],25)
    def test_weeks(self):
        for date,hours in [('2026-03-30',167),('2026-10-26',169),('2026-11-23',168)]:
            self.assertEqual(self.period('weekly',date)[2],hours)
    def test_months(self):
        for date,hours in [('2026-03-01',672),('2024-03-01',696),('2026-11-01',745)]:
            self.assertEqual(self.period('monthly',date)[2],hours)
    def test_quarters(self):
        self.assertEqual(self.period('quarterly','2026-01-01')[:2],('2025-10-01','2026-01-01'))
        self.assertEqual(self.period('quarterly','2026-07-01')[:2],('2026-04-01','2026-07-01'))
    def test_years(self):
        self.assertEqual(self.period('yearly','2025-01-01')[2],8784)
        self.assertEqual(self.period('yearly','2026-01-01')[2],8760)
    def test_reference_conversion(self):
        with patch.object(ha,'TZ',ZoneInfo('Europe/Kyiv')):
            start,end=ha.get_period('daily',datetime(2026,11,24,23,tzinfo=timezone.utc))
        self.assertEqual(str(start.date()),'2026-11-24')
        self.assertEqual(start.astimezone(timezone.utc).isoformat(),'2026-11-23T22:00:00+00:00')
    def test_naive(self):
        with self.assertRaises(ValueError): ha.get_period('daily',datetime(2026,1,1))
    def test_fractional_offset(self):
        for zone in ('Asia/Kolkata','Asia/Kathmandu'):
            with self.assertRaisesRegex(ValueError,'UTC-hour-aligned'): self.period('daily','2026-11-25',zone)
    def test_other_zones(self):
        self.assertEqual(self.period('daily','2026-03-09','America/New_York')[2],23)
        self.assertEqual(self.period('daily','2026-11-25','UTC')[2],24)
    def test_invalid_zone(self):
        with self.assertRaises(ZoneInfoNotFoundError): ZoneInfo('Invalid/Zone')
    def test_repeated_hour(self):
        tz=ZoneInfo('Europe/Kyiv')
        start=datetime(2026,10,25,tzinfo=tz); end=start+timedelta(days=1)
        stamps=sorted(ha.expected_hours(start,end))
        rows=[dict(start=t,end=t+3600000,sum=i+1,change=1) for i,t in enumerate(stamps)]
        result=ha.summarize_energy(rows,start,end)
        self.assertEqual((result['total'],result['coverage'],result['status']),(25,100,'complete'))
