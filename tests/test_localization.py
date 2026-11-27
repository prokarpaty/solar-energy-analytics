import sys
import unittest
from pathlib import Path
from string import Formatter
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from localization import Localizer


def flatten(data, prefix=''):
    result = {}
    for key, value in data.items():
        path = prefix + key
        if isinstance(value, dict):
            result.update(flatten(value, path + '.'))
        else:
            result[path] = value
    return result


class LocalizationTests(unittest.TestCase):
    def test_catalog_parity(self):
        en, uk = [flatten(Localizer(lang).catalog) for lang in ('en', 'uk')]
        self.assertEqual(en.keys(), uk.keys())
        for key in en:
            self.assertTrue(en[key].strip() and uk[key].strip())
            fields = lambda s: {field for _, field, _, _ in Formatter().parse(s) if field is not None}
            self.assertEqual(fields(en[key]), fields(uk[key]), key)

    def test_number(self):
        self.assertEqual(Localizer('en').number(1234.5), '1,234.50')
        self.assertEqual(Localizer('uk').number(1234.5), '1 234,50')
        self.assertEqual(Localizer('uk').number(None), '—')

    def test_environment(self):
        with patch.dict('os.environ', {'REPORT_LANGUAGE': 'en'}):
            self.assertEqual(Localizer().language, 'en')

    def test_invalid_language(self):
        with self.assertRaises(ValueError):
            Localizer('../uk')

    def test_missing_key(self):
        with self.assertRaises(KeyError):
            Localizer('en').text('missing.key')

    def test_interpolation(self):
        self.assertEqual(Localizer('en').text('cli.sensors', count=62), 'Measurement sensors: 62')
