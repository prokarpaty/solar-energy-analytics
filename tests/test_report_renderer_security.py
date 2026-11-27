import sys
import json
import tempfile
import unittest

from pathlib import Path
from unittest.mock import patch

sys.path.insert(
    0,
    str(Path(__file__).resolve().parents[1] / "scripts")
)

from report_security_fixture import create_reference, ENERGY_MAPPING
from report_validation import ReportValidationError
from report_loader import load_validated_report

import render_report


class RendererSecurityTests(unittest.TestCase):

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)

        self.source = Path(directory.name) / "report.json"
        self.html = self.source.with_suffix(".html")
        self.pdf = self.source.with_suffix(".pdf")
        self.data = create_reference()

        mapping = patch.object(
            render_report,
            "CONFIG",
            {"energy": dict(ENERGY_MAPPING)}
        )

        mapping.start()
        self.addCleanup(mapping.stop)

    def write_dataset(self):
        self.source.write_text(
            json.dumps(self.data, allow_nan=False),
            encoding="utf-8"
        )

    def assert_rejected(self):
        with patch.object(
            render_report, "build_context"
        ) as context, patch.object(
            render_report, "generate_charts"
        ) as charts:

            with self.assertRaises(ReportValidationError):
                render_report.render(self.source, "en")

            context.assert_not_called()
            charts.assert_not_called()

    def test_valid_shared_loader(self):
        self.write_dataset()
        result = load_validated_report(
            self.source,
            energy_mapping=ENERGY_MAPPING
        )
        self.assertEqual(result, self.data)

    def test_invalid_json(self):
        self.source.write_text("{invalid")
        self.assert_rejected()

    def test_duplicate_json_keys(self):
        self.source.write_text(
            '{"report_type":"daily","report_type":"weekly"}'
        )
        self.assert_rejected()

    def test_invalid_schema(self):
        del self.data["energy"]["production"]
        self.write_dataset()
        self.assert_rejected()

    def test_manipulated_energy_summary(self):
        summary = self.data["energy"]["production"]

        for key in (
            "total",
            "observed_change",
            "counter_delta",
            "counter_end"
        ):
            summary[key] += 1000

        self.write_dataset()
        self.assert_rejected()

    def test_manipulated_measurement_summary(self):
        sensor = next(iter(self.data["measurements"]))
        self.data["measurements"][sensor]["mean"] += 1000
        self.write_dataset()
        self.assert_rejected()

    def test_unexpected_energy_sensor(self):
        raw = self.data["raw"]["energy"]
        raw["sensor.unexpected"] = raw.pop(
            ENERGY_MAPPING["production"]
        )
        self.write_dataset()
        self.assert_rejected()

    def test_no_output_created_on_rejection(self):
        self.source.write_text("{}")
        self.assert_rejected()
        self.assertFalse(self.html.exists())
        self.assertFalse(self.pdf.exists())

    def test_existing_outputs_preserved(self):
        self.html.write_bytes(b"original HTML")
        self.pdf.write_bytes(b"original PDF")
        self.source.write_text("{}")
        self.assert_rejected()
        self.assertEqual(self.html.read_bytes(), b"original HTML")
        self.assertEqual(self.pdf.read_bytes(), b"original PDF")

    def test_missing_source(self):
        self.assert_rejected()

    def test_symlink_source(self):
        target = self.source.with_name("target.json")
        target.write_text(json.dumps(self.data))
        self.source.symlink_to(target)
        self.assert_rejected()

    def test_invalid_mapping(self):
        self.write_dataset()
        with patch.object(
            render_report, "CONFIG", {"energy": {}}
        ):
            self.assert_rejected()

    def test_valid_dataset_reaches_renderer(self):
        self.write_dataset()

        class PresentationReached(Exception):
            pass

        with patch.object(
            render_report,
            "build_context",
            side_effect=PresentationReached
        ) as context:

            with self.assertRaises(PresentationReached):
                render_report.render(self.source, "en")

            context.assert_called_once()
            self.assertEqual(context.call_args.args[0], self.data)


if __name__ == "__main__":
    unittest.main()
