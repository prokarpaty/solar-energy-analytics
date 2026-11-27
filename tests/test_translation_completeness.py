import json
import unittest
from pathlib import Path
from string import Formatter

ROOT = Path(__file__).resolve().parents[1]


def flatten(data, prefix=""):
    result = {}

    for key, value in data.items():
        name = f"{prefix}.{key}" if prefix else key

        if isinstance(value, dict):
            result.update(flatten(value, name))
        else:
            result[name] = value

    return result


class TranslationCompletenessTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.en = flatten(json.loads(
            (ROOT / "locales/en.json").read_text(
                encoding="utf-8"
            )
        ))

        cls.uk = flatten(json.loads(
            (ROOT / "locales/uk.json").read_text(
                encoding="utf-8"
            )
        ))

    def test_catalog_key_parity(self):
        self.assertEqual(set(self.en), set(self.uk))

    def test_nonempty_translations(self):
        for language, catalog in (
            ("en", self.en),
            ("uk", self.uk)
        ):
            for key, value in catalog.items():
                with self.subTest(language=language, key=key):
                    self.assertIsInstance(value, str)
                    self.assertTrue(value.strip())

    def test_placeholder_parity(self):
        for key in self.en.keys() & self.uk.keys():
            with self.subTest(key=key):
                en_fields = {
                    field for _, field, _, _
                    in Formatter().parse(self.en[key])
                    if field is not None
                }

                uk_fields = {
                    field for _, field, _, _
                    in Formatter().parse(self.uk[key])
                    if field is not None
                }

                self.assertEqual(en_fields, uk_fields)

    def test_all_report_periods(self):
        for period in (
            "daily",
            "weekly",
            "monthly",
            "quarterly",
            "yearly"
        ):
            for catalog in (self.en, self.uk):
                self.assertIn(f"report.{period}", catalog)


if __name__ == "__main__":
    unittest.main()
