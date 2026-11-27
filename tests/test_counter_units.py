import sys
import unittest
from pathlib import Path
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from unit_normalization import normalize_rows, response_unit
from sensor_validation import validate
with patch.object(Path, 'read_text', return_value='{}'):
    from ha_client import summarize_energy, expected_hours

class CounterUnits(unittest.TestCase):
    def setUp(self):
        self.start = datetime(2026,1,1,tzinfo=timezone.utc)
        self.end = self.start + timedelta(hours=4)
        self.rows = [dict(start=t,end=t+3600000,sum=101+i,change=1,state=1000+i) for i,t in enumerate(sorted(expected_hours(self.start,self.end)))]
    def summarize(self, rows):
        return summarize_energy(rows,self.start,self.end)
    def test_physical_reset(self):
        self.rows[2]['state']=0
        self.rows[3]['state']=1
        self.assertEqual(self.summarize(self.rows)['total'],4)
    def test_multiple_physical_resets(self):
        for row,state in zip(self.rows,[1000,0,1,0]): row['state']=state
        self.assertEqual(self.summarize(self.rows)['status'],'complete')
    def test_statistical_reset(self):
        self.rows[2]['sum']=0
        self.rows[3]['sum']=1
        r=self.summarize(self.rows)
        self.assertIsNone(r['total']); self.assertEqual(r['counter_decreases'],1)
    def test_negative_change(self):
        self.rows[2]['change']=-1
        self.assertIsNone(self.summarize(self.rows)['total'])
    def test_energy_scales(self):
        for unit,factor in [('Wh',1000),('kWh',1),('MWh',.001)]:
            rows=[dict(r,sum=r['sum']*factor,change=r['change']*factor,state=r['state']*factor) for r in self.rows]
            self.assertEqual(self.summarize(normalize_rows(rows,unit))['total'],4)
    def test_measurement_scales(self):
        for unit,value,expected in [('kW',1.5,1500),('MW',.002,2000),('mV',230000,230),('mA',500,0.5),('mAh',1000,1)]:
            self.assertAlmostEqual(normalize_rows([{'mean':value}],unit)[0]['mean'],expected)
    def test_temperature_offset(self):
        r=normalize_rows([{'min':32,'mean':68,'max':104,'change':18}], '°F')[0]
        for key,value in [('min',0),('mean',20),('max',40),('change',10)]: self.assertAlmostEqual(r[key],value)
    def test_preserve_input(self):
        rows=[{'start':123,'end':456,'mean':1.5,'other':7},None]
        result=normalize_rows(rows,'kW')
        self.assertEqual(result,[{'start':123,'end':456,'mean':1500,'other':7},None]); self.assertEqual(rows[0]['mean'],1.5)
    def test_canonical_identity(self):
        rows=[{'sum':10,'change':2}]
        self.assertEqual(normalize_rows(rows,'kWh'),rows)
    def test_missing_incompatible_unit(self):
        for meta in ({'has_sum':True},{'has_sum':True,'statistics_unit_of_measurement':'W'}):
            with self.assertRaises(ValueError): validate(meta,'kWh',True)
        with self.assertRaises(ValueError): normalize_rows([], 'unknown')
    def test_response_unit_guard(self):
        self.assertEqual(response_unit({'display_unit_of_measurement':'kWh'},'kWh'),'kWh')
        self.assertEqual(response_unit({},'Wh'),'Wh')
        with self.assertRaisesRegex(ValueError,'Ambiguous'): response_unit({'display_unit_of_measurement':'kWh'},'Wh')
