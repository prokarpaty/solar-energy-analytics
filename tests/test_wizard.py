"""Run: python3 -m unittest discover -s tests -v"""
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'installer'))
import wizard

class WizardTests(unittest.TestCase):
    def test_languages(self):
        self.assertEqual(wizard.select_language('1'),'en')
        self.assertEqual(wizard.select_language('2'),'uk')
    def test_url_rejects_password(self):
        with self.assertRaises(ValueError):wizard.validate_url('http://user:password@example.com:8123')
    def test_url_rejects_wrong_protocol(self):
        with self.assertRaises(ValueError):wizard.validate_url('file:///etc/passwd')
    def test_timezone(self):
        self.assertEqual(wizard.validate_tz('Europe/Kyiv'),'Europe/Kyiv')
    def test_sensor_traversal(self):
        with self.assertRaises(ValueError):wizard.validate_relative_sensor_path('config/../.env')
    def test_private_file(self):
        import tempfile,os
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'token'
            wizard.create_exclusive(p,'private')
            self.assertEqual(p.stat().st_mode & 0o777,0o600)
            with self.assertRaises(FileExistsError):wizard.create_exclusive(p,'secret')

if __name__=='__main__':unittest.main()
