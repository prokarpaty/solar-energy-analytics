import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from sensor_validation import validate_configuration
from sensor_discovery import candidates
class ConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.config={'energy':{'production':'sensor.p','consumption':'sensor.c'}}
        self.registry={x:{'has_sum':True,'unit_of_measurement':'Wh'} for x in ('sensor.p','sensor.c')}
    def test_minimal(self):
        e,u,m,w=validate_configuration(self.config,self.registry)
        self.assertEqual(len(e),2); self.assertEqual(m,{}); self.assertEqual(w,[])
    def test_optional_missing(self):
        self.config['energy']['grid_import']='sensor.missing'
        e,u,m,w=validate_configuration(self.config,self.registry)
        self.assertNotIn('grid_import',e); self.assertEqual(len(w),1)
    def test_required_missing(self):
        del self.config['energy']['production']
        with self.assertRaisesRegex(ValueError,'Missing required'): validate_configuration(self.config,self.registry)
    def test_duplicate(self):
        self.config['energy']['grid_import']='sensor.p'
        with self.assertRaisesRegex(ValueError,'Duplicate'): validate_configuration(self.config,self.registry)
    def test_single_phase(self):
        self.config['grid']={'voltage':{'l1':'sensor.v'}}
        self.registry['sensor.v']={'has_mean':True,'unit_of_measurement':'mV'}
        self.assertEqual(validate_configuration(self.config,self.registry)[2],{'sensor.v':'mV'})
    def test_optional_wrong_unit(self):
        self.config['power']={'solar':'sensor.v'}
        self.registry['sensor.v']={'has_mean':True,'unit_of_measurement':'V'}
        self.assertEqual(len(validate_configuration(self.config,self.registry)[3]),1)
    def test_conflict(self):
        self.config.update(power={'solar':'sensor.x'},grid={'voltage':{'l1':'sensor.x'}})
        with self.assertRaisesRegex(ValueError,'Conflicting'): validate_configuration(self.config,self.registry)
    def test_categories(self):
        ids=['sensor.total_production','sensor.today_production','sensor.other']
        rows=[{'entity_id':i,'state':'1'} for i in ids]
        meta=[{'statistic_id':i,'has_sum':True,'unit_of_measurement':'Wh'} for i in ids]
        self.assertEqual([x['category'] for x in candidates(rows,meta,'production',include_unmatched=True)],['preferred','manual','periodic'])
