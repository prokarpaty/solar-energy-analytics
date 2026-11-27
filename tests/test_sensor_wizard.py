import sys, unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'installer'))
from sensor_wizard import configure
class WizardSelection(unittest.TestCase):
    def test_auto(self):
        rows={'inverter_total_production':'kWh','inverter_total_load_consumption':'kWh','inverter_pv_power':'W','inverter_load_power':'W','girlianda_power':'W','inverter_grid_l1_voltage':'V','inverter_battery_1':'%','printer_toner':'%'}
        states=[{'entity_id':'sensor.'+i,'state':'1'} for i in rows]
        meta=[{'statistic_id':'sensor.'+i,'statistics_unit_of_measurement':u,'has_sum':u=='kWh','has_mean':u!='kWh'} for i,u in rows.items()]
        result=configure(states,meta,ask=lambda _: '',show=lambda _:None)
        self.assertEqual(result['power'],{'solar':'sensor.inverter_pv_power','house':'sensor.inverter_load_power'})
        self.assertEqual(result['batteries']['battery_1']['soc'],'sensor.inverter_battery_1')
        self.assertNotIn('girlianda',str(result))
        self.assertNotIn('printer',str(result))
    def test_missing_required(self):
        states=[{'entity_id':'sensor.inverter_total_production'}]
        meta=[{'statistic_id':states[0]['entity_id'],'statistics_unit_of_measurement':'kWh','has_sum':True}]
        with self.assertRaises(ValueError): configure(states,meta,ask=lambda _: '',show=lambda _:None)
