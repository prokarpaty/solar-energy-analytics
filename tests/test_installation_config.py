import sys
import tempfile
import unittest
from pathlib import Path
import yaml
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from installation_config import load_installation


class InstallationConfigTests(unittest.TestCase):
    def load(self, overrides):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'installation.yaml'
            path.write_text(yaml.safe_dump(overrides), encoding='utf-8')
            return load_installation(path)

    def test_defaults(self):
        with tempfile.TemporaryDirectory() as directory:
            config = load_installation(Path(directory) / 'missing.yaml')
        self.assertEqual(config['thresholds']['grid_voltage']['minimum'], 207)
        self.assertEqual(len(config['report']['kpis']), 6)

    def test_merge(self):
        config = self.load({'installation': {'name': 'Test'}, 'report': {'sections': {'charts': False}}})
        self.assertEqual(config['installation']['name'], 'Test')
        self.assertFalse(config['report']['sections']['charts'])
        self.assertTrue(config['report']['sections']['energy_summary'])

    def test_invalid_settings(self):
        cases = [None, [], {'unknown': True}, {'installation': None},
                 {'installation': {'name': 123}},
                 {'equipment': {'solar': {'panel_count': True}}},
                 {'equipment': {'battery': {'nominal_capacity_kwh': -1}}},
                 {'equipment': {'inverter': {'rated_power_kw': float('inf')}}},
                 {'branding': {'primary_color': 'red'}},
                 {'branding': {'logo': 'https://example.invalid/logo.png'}},
                 {'report': {'sections': {'charts': 'false'}}},
                 {'report': {'kpis': ['unknown']}},
                 {'report': {'kpis': ['production', 'production']}},
                 {'thresholds': {'grid_voltage': {'minimum': 240}}}]
        for case in cases:
            with self.subTest(case=case), self.assertRaises(ValueError):
                self.load(case)

    def test_custom_thresholds(self):
        config = self.load({'thresholds': {'grid_voltage': {'nominal': 120, 'minimum': 108, 'maximum': 132}}})
        self.assertEqual(config['thresholds']['grid_voltage']['nominal'], 120)

    def test_independent_loads(self):
        config = self.load({'report': {'kpis': []}})
        self.assertEqual(config['report']['kpis'], [])
        self.assertEqual(len(self.load({})['report']['kpis']), 6)
