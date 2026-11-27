import sys
import json
import hashlib
import tempfile
import unittest

from pathlib import Path
from unittest.mock import patch

sys.path.insert(
    0,
    str(Path(__file__).resolve().parents[1] / "scripts")
)

from report_validation import (
    load_report,
    ReportValidationError
)

from report_loader import load_validated_report

from report_security_fixture import (
    create_reference,
    ENERGY_MAPPING
)


class ReportIdentityTests(unittest.TestCase):

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)

        self.source = Path(directory.name) / "report.json"

        self.data = create_reference()

        self.payload = json.dumps(
            self.data,
            ensure_ascii=False,
            allow_nan=False,
            indent=2
        ).encode("utf-8")

        self.source.write_bytes(self.payload)
        self.source.chmod(0o600)

    def load(self):
        return load_validated_report(
            self.source,
            energy_mapping=ENERGY_MAPPING,
            with_identity=True
        )

    def test_validator_backward_compatibility(self):
        self.assertEqual(
            load_report(self.source),
            self.data
        )

    def test_loader_backward_compatibility(self):
        self.assertEqual(
            load_validated_report(
                self.source,
                energy_mapping=ENERGY_MAPPING
            ),
            self.data
        )

    def test_validator_identity(self):
        data, identity = load_report(
            self.source,
            with_identity=True
        )

        self.assertEqual(data, self.data)

        self.assertEqual(
            identity,
            {
                "sha256": hashlib.sha256(
                    self.payload
                ).hexdigest(),
                "size": len(self.payload)
            }
        )

    def test_reconciled_identity(self):
        data, identity = self.load()

        self.assertEqual(data, self.data)

        self.assertEqual(
            identity["sha256"],
            hashlib.sha256(self.payload).hexdigest()
        )

        self.assertEqual(
            identity["size"],
            len(self.payload)
        )

    def test_identity_is_deterministic(self):
        self.assertEqual(
            self.load(),
            self.load()
        )

    def test_whitespace_changes_identity(self):
        original_data, original_identity = self.load()

        self.source.write_bytes(
            self.payload + b"\n"
        )

        data, identity = self.load()

        self.assertEqual(data, original_data)

        self.assertNotEqual(
            identity["sha256"],
            original_identity["sha256"]
        )

        self.assertEqual(
            identity["size"],
            original_identity["size"] + 1
        )

    def test_equivalent_serialization_changes_identity(self):
        original_data, original_identity = self.load()

        self.source.write_text(
            json.dumps(
                self.data,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False
            ),
            encoding="utf-8"
        )

        data, identity = self.load()

        self.assertEqual(data, original_data)

        self.assertNotEqual(
            identity["sha256"],
            original_identity["sha256"]
        )

    def test_invalid_json_rejected(self):
        self.source.write_bytes(b"{invalid")

        with self.assertRaises(ReportValidationError):
            self.load()

    def test_invalid_schema_rejected(self):
        self.data["energy"].pop("production")

        self.source.write_text(
            json.dumps(self.data),
            encoding="utf-8"
        )

        with self.assertRaises(ReportValidationError):
            self.load()

    def test_manipulated_summary_rejected(self):
        item = self.data["energy"]["production"]

        for field in (
            "total",
            "observed_change",
            "counter_delta",
            "counter_end"
        ):
            item[field] += 1000

        self.source.write_text(
            json.dumps(self.data),
            encoding="utf-8"
        )

        with self.assertRaises(ReportValidationError):
            self.load()

    def test_invalid_mapping_rejected(self):
        with self.assertRaises(ReportValidationError):
            load_validated_report(
                self.source,
                energy_mapping={},
                with_identity=True
            )

    def test_missing_source_rejected(self):
        self.source.unlink()

        with self.assertRaises(ReportValidationError):
            self.load()

    def test_symlink_source_rejected(self):
        target = self.source.with_name("original.json")

        self.source.rename(target)
        self.source.symlink_to(target)

        with self.assertRaises(ReportValidationError):
            self.load()

    def test_source_not_modified(self):
        self.load()

        self.assertEqual(
            self.source.read_bytes(),
            self.payload
        )

    def test_identity_uses_original_validated_bytes(self):
        import report_validation as validator

        original = validator.validate_structure

        def replace_after_read(data):
            self.source.write_bytes(
                self.payload + b"\n"
            )

            return original(data)

        with patch.object(
            validator,
            "validate_structure",
            side_effect=replace_after_read
        ):
            data, identity = self.load()

        self.assertEqual(data, self.data)

        self.assertEqual(
            identity["sha256"],
            hashlib.sha256(self.payload).hexdigest()
        )

        self.assertNotEqual(
            identity["sha256"],
            hashlib.sha256(
                self.source.read_bytes()
            ).hexdigest()
        )


if __name__ == "__main__":
    unittest.main()
