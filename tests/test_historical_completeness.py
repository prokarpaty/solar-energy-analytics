import sys
import unittest
from pathlib import Path
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
with patch.object(Path, 'read_text', return_value='{}'):
    from ha_client import summarize_energy, summarize_measurement, expected_hours

class HistoricalCompleteness(unittest.TestCase):
    def setUp(self):
        self.start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        self.end = self.start + timedelta(hours=4)
        self.rows = [dict(start=t, end=t+3600000, sum=101+i, change=1, min=10, mean=20, max=30) for i,t in enumerate(sorted(expected_hours(self.start,self.end)))]
    def energy(self, rows):
        return summarize_energy(rows,self.start,self.end)
    def test_complete(self):
        r=self.energy(self.rows); self.assertEqual((r['total'],r['status'],r['coverage']),(4,'complete',100))
    def test_unordered_identical_duplicate(self):
        self.assertEqual(self.energy(self.rows[::-1]+[self.rows[0]]),self.energy(self.rows))
    def test_conflicting_duplicate(self):
        rows=self.rows+[dict(self.rows[1],change=9)]
        self.assertEqual(self.energy(rows),self.energy(rows[::-1])); self.assertIsNone(self.energy(rows)['total'])
    def test_missing_boundaries(self):
        for rows in (self.rows[1:],self.rows[:-1]):
            self.assertIsNone(self.energy(rows)['total'])
    def test_recovered(self):
        rows=[self.rows[0],dict(self.rows[2],change=2),self.rows[3]]
        r=self.energy(rows); self.assertEqual((r['total'],r['status'],r['coverage'],r['complete']),(4,'recovered',75,False))
    def test_missing_unrecovered(self):
        self.assertIsNone(self.energy(self.rows[:1]+self.rows[2:])['total'])
    def test_unavailable(self):
        self.assertEqual(self.energy([])['status'],'unavailable')
    def test_invalid_values(self):
        for value in (None,True,'1',float('nan'),float('inf'),-1):
            rows=self.rows.copy(); rows[1]=dict(rows[1],change=value)
            self.assertIsNone(self.energy(rows)['total'])
    def test_canceling_errors(self):
        rows=self.rows.copy(); rows[1]=dict(rows[1],change=2); rows[2]=dict(rows[2],change=0)
        self.assertIsNone(self.energy(rows)['total'])
    def test_invalid_period(self):
        for end in (self.start,self.start-timedelta(hours=1),self.start+timedelta(minutes=30)):
            with self.assertRaises(ValueError): expected_hours(self.start,end)
    def test_measurement_coverage(self):
        rows=[self.rows[0],dict(self.rows[1],mean=None)]
        r=summarize_measurement(rows,self.start,self.end)
        self.assertEqual((r['coverage'],r['mean_coverage'],r['min_coverage']),(50,25,50))
    def test_invalid_row(self):
        self.assertEqual(self.energy(self.rows+[None,{}, {'start':[]}]),self.energy(self.rows))
