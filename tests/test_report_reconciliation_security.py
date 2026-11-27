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

from report_security_fixture import (
    create_reference,
    ENERGY_MAPPING
)

from report_validation import (
    load_report,
    ReportValidationError
)

from report_reconciliation import reconcile_report


class ReconciliationSecurityTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):

        cls.reference = create_reference()

        cls.mapping = dict(ENERGY_MAPPING)

        cls.measurement_sensor = next(
            sensor
            for sensor, summary
            in cls.reference["measurements"].items()
            if summary["mean"] is not None
        )

    def setUp(self):

        self.data = copy.deepcopy(self.reference)

        self.mapping = copy.deepcopy(
            type(self).mapping
        )

        self.production = self.data["energy"]["production"]

        self.production_sensor = self.mapping["production"]

        self.raw_energy = self.data["raw"]["energy"][
            self.production_sensor
        ]

        self.measurement = self.data["measurements"][
            self.measurement_sensor
        ]

        self.raw_measurements = self.data["raw"]["measurements"][
            self.measurement_sensor
        ]

    def validate_structure(self):

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

            return load_report(source)

    def assert_reconciliation_rejected(
        self,
        structural_validation=True
    ):

        if structural_validation:

            data = self.validate_structure()

        else:

            data = self.data

        with self.assertRaises(ReportValidationError):

            reconcile_report(data, self.mapping)

    # Valid reference

    def test_valid_reference(self):

        result = reconcile_report(
            self.data,
            self.mapping
        )

        self.assertEqual(result["energy"], 7)
        self.assertEqual(result["measurements"], 59)
        self.assertEqual(result["total"], 66)

    # Coordinated energy summary manipulation

    def test_coordinated_energy_inflation(self):

        for key in (
            "total",
            "observed_change",
            "counter_delta",
            "counter_end"
        ):

            self.production[key] += 1000

        self.assert_reconciliation_rejected()

    def test_coordinated_counter_offset(self):

        self.production["counter_start"] += 1000
        self.production["counter_end"] += 1000

        self.assert_reconciliation_rejected()

    def test_coordinated_energy_reduction(self):

        adjustment = self.production["total"] / 2

        for key in (
            "total",
            "observed_change",
            "counter_delta",
            "counter_end"
        ):

            self.production[key] -= adjustment

        self.assert_reconciliation_rejected()

    # Measurement summary manipulation

    def test_manipulated_measurement_mean(self):

        self.measurement["mean"] += 1000

        self.assert_reconciliation_rejected()

    def test_manipulated_measurement_minimum(self):

        self.measurement["min"] -= 1000

        self.assert_reconciliation_rejected()

    def test_manipulated_measurement_maximum(self):

        self.measurement["max"] += 1000

        self.assert_reconciliation_rejected()

    def test_coordinated_measurement_shift(self):

        for key in ("min", "mean", "max"):

            if self.measurement[key] is not None:

                self.measurement[key] += 1000

        self.assert_reconciliation_rejected()

    # Raw energy manipulation

    def test_modified_hourly_energy_change(self):

        self.raw_energy[0]["change"] += 1000

        self.assert_reconciliation_rejected()

    def test_modified_hourly_counter(self):

        self.raw_energy[-1]["sum"] += 1000

        self.assert_reconciliation_rejected()

    def test_removed_hourly_energy_record(self):

        self.raw_energy.pop(0)

        self.assert_reconciliation_rejected()

    def test_removed_energy_sensor_history(self):

        del self.data["raw"]["energy"][
            self.production_sensor
        ]

        self.assert_reconciliation_rejected()

    # Raw measurement manipulation

    def test_modified_hourly_measurement(self):

        row = next(
            row
            for row in self.raw_measurements
            if row["mean"] is not None
        )

        row["mean"] += 1000

        self.assert_reconciliation_rejected()

    def test_removed_hourly_measurement(self):

        self.raw_measurements.pop(0)

        self.assert_reconciliation_rejected()

    def test_removed_measurement_history(self):

        del self.data["raw"]["measurements"][
            self.measurement_sensor
        ]

        self.assert_reconciliation_rejected()

    # Trusted mapping manipulation

    def test_missing_energy_mapping(self):

        del self.mapping["production"]

        self.assert_reconciliation_rejected()

    def test_invalid_energy_mapping(self):

        self.mapping["production"] = "invalid"

        self.assert_reconciliation_rejected()

    def test_duplicate_energy_mapping(self):

        self.mapping["production"] = self.mapping["consumption"]

        self.assert_reconciliation_rejected()

    def test_swapped_energy_mapping(self):

        (
            self.mapping["production"],
            self.mapping["consumption"]
        ) = (
            self.mapping["consumption"],
            self.mapping["production"]
        )

        self.assert_reconciliation_rejected()

    def test_unexpected_raw_energy_sensor(self):

        raw = self.data["raw"]["energy"]

        raw["sensor.unexpected"] = raw.pop(
            self.production_sensor
        )

        self.assert_reconciliation_rejected()

    def test_excessive_raw_energy_sensors(self):

        self.data["raw"]["energy"][
            "sensor.unexpected"
        ] = []

        with self.assertRaises(ReportValidationError):
            self.validate_structure()

    # Valid record ordering

    def test_reordered_energy_records(self):

        self.raw_energy.reverse()

        data = self.validate_structure()

        result = reconcile_report(
            data,
            self.mapping
        )

        self.assertEqual(result["total"], 66)

    def test_reordered_measurement_records(self):

        self.raw_measurements.reverse()

        data = self.validate_structure()

        result = reconcile_report(
            data,
            self.mapping
        )

        self.assertEqual(result["total"], 66)

    # Validation must not modify the dataset

    def test_dataset_not_modified(self):

        original = copy.deepcopy(self.data)

        reconcile_report(
            self.data,
            self.mapping
        )

        self.assertEqual(self.data, original)


if __name__ == "__main__":

    unittest.main(verbosity=2)
