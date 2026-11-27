import sys
import copy
import json
import tempfile
import unittest

from pathlib import Path

sys.path.insert(
    0,
    str(Path(__file__).resolve().parents[1] / "scripts")
)

from report_security_fixture import create_reference

import report_validation as rv





class SchemaSecurityTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):

        cls.reference = create_reference()

        cls.energy_key = "production"

        cls.measurement_key = next(
            iter(cls.reference["measurements"])
        )

        cls.raw_energy_key = next(
            key
            for key, rows
            in cls.reference["raw"]["energy"].items()
            if rows
        )

        cls.raw_measurement_key = next(
            key
            for key, rows
            in cls.reference["raw"]["measurements"].items()
            if rows
        )

    def setUp(self):

        self.data = copy.deepcopy(self.reference)

        self.energy = self.data["energy"][self.energy_key]

        self.measurement = self.data["measurements"][
            self.measurement_key
        ]

        self.raw_energy = self.data["raw"]["energy"][
            self.raw_energy_key
        ]

        self.raw_measurements = self.data["raw"]["measurements"][
            self.raw_measurement_key
        ]

    def assert_rejected(self):

        with tempfile.TemporaryDirectory() as directory:

            source = Path(directory) / "modified.json"

            source.write_text(
                json.dumps(
                    self.data,
                    ensure_ascii=False,
                    allow_nan=False
                ),
                encoding="utf-8"
            )

            with self.assertRaises(rv.ReportValidationError):

                rv.load_report(source)

    # Valid reference

    def test_valid_reference(self):

        with tempfile.TemporaryDirectory() as directory:

            source = Path(directory) / "reference.json"

            source.write_text(
                json.dumps(
                    self.reference,
                    ensure_ascii=False,
                    allow_nan=False
                ),
                encoding="utf-8"
            )

            self.assertEqual(
                rv.load_report(source),
                self.reference
            )

    # Root schema

    def test_unknown_root_field(self):

        self.data["unexpected"] = True

        self.assert_rejected()

    def test_missing_required_field(self):

        del self.data["generated_at"]

        self.assert_rejected()

    def test_invalid_report_type(self):

        self.data["report_type"] = "arbitrary"

        self.assert_rejected()

    def test_invalid_energy_collection(self):

        self.data["energy"] = []

        self.assert_rejected()

    def test_missing_production(self):

        del self.data["energy"]["production"]

        self.assert_rejected()

    def test_missing_consumption(self):

        del self.data["energy"]["consumption"]

        self.assert_rejected()

    def test_unknown_energy_category(self):

        self.data["energy"]["unexpected"] = self.energy.copy()

        self.assert_rejected()

    def test_unknown_raw_collection(self):

        self.data["raw"]["unexpected"] = {}

        self.assert_rejected()

    # Calendar and timezone

    def test_invalid_timezone(self):

        self.data["timezone"] = "Invalid/Timezone"

        self.assert_rejected()

    def test_naive_start_timestamp(self):

        self.data["start"] = "2026-11-24T00:00:00"

        self.assert_rejected()

    def test_invalid_start_timestamp(self):

        self.data["start"] = "invalid"

        self.assert_rejected()

    def test_reversed_period(self):

        self.data["start"], self.data["end"] = (
            self.data["end"],
            self.data["start"]
        )

        self.assert_rejected()

    def test_zero_length_period(self):

        self.data["end"] = self.data["start"]

        self.assert_rejected()

    def test_incorrect_calendar_period(self):

        self.data["report_type"] = "yearly"

        self.assert_rejected()

    def test_generation_before_period_end(self):

        self.data["generated_at"] = self.data["start"]

        self.assert_rejected()

    # Energy summary

    def test_invalid_energy_status(self):

        self.energy["status"] = "unknown"

        self.assert_rejected()

    def test_negative_record_count(self):

        self.energy["records"] = -1

        self.assert_rejected()

    def test_excessive_record_count(self):

        self.energy["records"] = self.energy["expected"] + 1

        self.assert_rejected()

    def test_boolean_record_count(self):

        self.energy["records"] = True

        self.assert_rejected()

    def test_incorrect_expected_hours(self):

        self.energy["expected"] += 1

        self.assert_rejected()

    def test_invalid_energy_coverage(self):

        self.energy["coverage"] = 101

        self.assert_rejected()

    def test_inconsistent_energy_coverage(self):

        self.energy["coverage"] = 50

        self.assert_rejected()

    def test_invalid_complete_flag(self):

        self.energy["complete"] = "true"

        self.assert_rejected()

    def test_inconsistent_complete_flag(self):

        self.energy["complete"] = not self.energy["complete"]

        self.assert_rejected()

    def test_incorrect_missing_hours(self):

        self.energy["missing_hours"] += 1

        self.assert_rejected()

    def test_invalid_energy_total(self):

        self.energy["total"] = "999"

        self.assert_rejected()

    def test_negative_complete_total(self):

        self.energy["total"] = -100

        self.assert_rejected()

    def test_manipulated_energy_total(self):

        self.energy["total"] += 1000

        self.assert_rejected()

    def test_unknown_energy_summary_field(self):

        self.energy["unexpected"] = 123

        self.assert_rejected()

    # Measurement summary

    def test_invalid_measurement_coverage(self):

        self.measurement["coverage"] = 101

        self.assert_rejected()

    def test_invalid_measurement_records(self):

        self.measurement["records"] = -1

        self.assert_rejected()

    def test_invalid_measurement_mean(self):

        self.measurement["mean"] = "invalid"

        self.assert_rejected()

    def test_invalid_measurement_metric_coverage(self):

        self.measurement["mean_coverage"] = 101

        self.assert_rejected()

    def test_unknown_measurement_summary_field(self):

        self.measurement["unexpected"] = True

        self.assert_rejected()

    # Raw hourly statistics

    def test_duplicate_energy_timestamp(self):

        self.raw_energy[1] = copy.deepcopy(
            self.raw_energy[0]
        )

        self.assert_rejected()

    def test_duplicate_measurement_timestamp(self):

        self.raw_measurements[1] = copy.deepcopy(
            self.raw_measurements[0]
        )

        self.assert_rejected()

    def test_misaligned_hourly_timestamp(self):

        self.raw_energy[0]["start"] += 1000

        self.assert_rejected()

    def test_invalid_hour_duration(self):

        self.raw_energy[0]["end"] += 1000

        self.assert_rejected()

    def test_out_of_period_timestamp(self):

        self.raw_energy[0]["start"] -= 86400000

        self.raw_energy[0]["end"] -= 86400000

        self.assert_rejected()

    def test_boolean_hourly_timestamp(self):

        self.raw_energy[0]["start"] = True

        self.assert_rejected()

    def test_invalid_raw_energy_value(self):

        self.raw_energy[0]["change"] = "invalid"

        self.assert_rejected()

    def test_invalid_raw_measurement_value(self):

        self.raw_measurements[0]["mean"] = True

        self.assert_rejected()

    def test_unknown_raw_record_field(self):

        self.raw_energy[0]["unexpected"] = 123

        self.assert_rejected()

    def test_missing_raw_record_field(self):

        del self.raw_energy[0]["end"]

        self.assert_rejected()

    def test_invalid_sensor_identifier(self):

        self.data["raw"]["energy"]["invalid"] = []

        self.assert_rejected()

    # Configuration warnings

    def test_invalid_warning_collection(self):

        self.data["configuration_warnings"] = "invalid"

        self.assert_rejected()

    def test_invalid_warning_type(self):

        self.data["configuration_warnings"] = [123]

        self.assert_rejected()

    def test_excessive_warning_length(self):

        self.data["configuration_warnings"] = [
            "x" * (rv.MAX_WARNING_LENGTH + 1)
        ]

        self.assert_rejected()

    def test_excessive_warning_count(self):

        self.data["configuration_warnings"] = [
            "warning"
        ] * (rv.MAX_WARNINGS + 1)

        self.assert_rejected()


if __name__ == "__main__":

    unittest.main(verbosity=2)
