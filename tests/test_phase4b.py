import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from unit_normalization import normalize_rows
from sensor_validation import validate, measurement_target
from sensor_discovery import candidates

class Phase4B(unittest.TestCase):
    def test_energy(self):
        self.assertEqual(normalize_rows([{'start':123,'sum':1000,'change':500}], 'Wh'), [{'start':123,'sum':1,'change':.5}])
    def test_temperature(self):
        self.assertAlmostEqual(normalize_rows([{'mean':32}], '°F')[0]['mean'],0)
    def test_identity(self):
        rows=[{'mean':12}]; self.assertIs(normalize_rows(rows,'W'),rows)
    def test_metadata(self):
        self.assertEqual(validate({'statistics_unit_of_measurement':'Wh','display_unit_of_measurement':'kWh','has_sum':True},'kWh',True),'Wh')
    def test_invalid(self):
        for meta in (None, {'has_mean':True,'unit_of_measurement':'Ah'}):
            with self.assertRaises(ValueError): validate(meta,'kWh')
    def test_ranking(self):
        ids=['sensor.total_production','sensor.today_production','sensor.no_history']
        states=[{'entity_id':i,'state':'1'} for i in ids]
        meta=[{'statistic_id':i,'has_sum':True,'unit_of_measurement':'kWh'} for i in ids[:2]]
        self.assertEqual([x['entity_id'] for x in candidates(states,meta,'production')],ids[:2])
    def test_roles(self):
        self.assertEqual(measurement_target(['grid','voltage','l1']),'V')
        self.assertEqual(measurement_target(['battery_bank','capacity']),'kWh')

    def test_unrelated_candidates(self):
        ids = ['sensor.total_production', 'sensor.girlianda_total_energy', 'sensor.total_battery_charge']
        states = [{'entity_id': i, 'state': '1'} for i in ids]
        meta = [{'statistic_id': i, 'has_sum': True, 'unit_of_measurement': 'kWh'} for i in ids]
        self.assertEqual([x['entity_id'] for x in candidates(states, meta, 'production')], ids[:1])
        self.assertEqual(len(candidates(states, meta, 'production', include_unmatched=True)), 3)
