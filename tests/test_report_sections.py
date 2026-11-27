import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from report_sections import apply_sections
from installation_config import load_installation

class SectionTests(unittest.TestCase):
    def context(self):
        return dict(profile=load_installation(), energy=[{'key': 'production'}, {'key': 'consumption'}], charts=[], phases=[], battery_bank=[], batteries=[{'rows': []}], temperatures=[])
    def test_minimal(self):
        c = apply_sections(self.context())
        self.assertEqual(c['section_numbers'], {'kpi_summary':'01','energy_summary':'02','data_quality':'03','conclusions':'04'})
        self.assertEqual(c['batteries'], [])
    def test_order_and_visibility(self):
        c = self.context()
        c['profile']['report']['kpis'] = ['consumption','grid_export','production']
        c['profile']['report']['sections']['energy_summary'] = False
        apply_sections(c)
        self.assertEqual([r['key'] for r in c['kpis']], ['consumption','production'])
        self.assertNotIn('energy_summary', c['section_numbers'])
        self.assertEqual(c['section_numbers']['data_quality'], '02')
