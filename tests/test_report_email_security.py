import os
import sys
import json
import tempfile
import unittest

from pathlib import Path
from unittest.mock import patch
from email import policy
from email.parser import BytesParser

sys.path.insert(
    0,
    str(Path(__file__).resolve().parents[1] / "scripts")
)

from ha_client import CONFIG
from report_security_fixture import create_reference, ENERGY_MAPPING
from report_validation import ReportValidationError
from report_manifest_fixture import create_fixture_manifest

import send_report as mail


class ReportEmailSecurityTests(unittest.TestCase):

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)

        self.source = Path(directory.name) / "report.json"
        self.eml = self.source.with_suffix(".eml")
        self.data = create_reference()

        mapping = patch.dict(
            CONFIG,
            {"energy": dict(ENERGY_MAPPING)}
        )

        mapping.start()
        self.addCleanup(mapping.stop)

        self.pdf = b"%PDF-1.7\nSynthetic security fixture"
        self.html = b"<html>Synthetic security fixture</html>"

        self.source.with_suffix(".pdf").write_bytes(self.pdf)
        self.source.with_suffix(".pdf").chmod(0o600)
        self.source.with_suffix(".html").write_bytes(self.html)
        self.source.with_suffix(".html").chmod(0o600)

    def write_dataset(self):
        self.source.write_text(
            json.dumps(self.data, allow_nan=False),
            encoding="utf-8"
        )

    def assert_rejected(self):
        with patch.object(
            mail, "build_email"
        ) as content, patch.object(
            mail, "validate_attachment_filename"
        ) as attachment, patch.object(
            mail.smtplib, "SMTP"
        ) as smtp:

            with self.assertRaises(ReportValidationError):
                mail.build_message(
                    self.source,
                    language="en",
                    preview=True
                )

            content.assert_not_called()
            attachment.assert_not_called()
            smtp.assert_not_called()

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

    def test_missing_source(self):
        self.assert_rejected()

    def test_symlink_source(self):
        target = self.source.with_name("target.json")
        target.write_text(json.dumps(self.data))
        self.source.symlink_to(target)
        self.assert_rejected()

    def test_invalid_mapping(self):
        self.write_dataset()

        with patch.dict(CONFIG, {"energy": {}}):
            self.assert_rejected()

    def test_invalid_preview_creates_no_eml(self):
        self.source.write_text("{}")

        with patch.object(mail, "write_private") as writer:

            with self.assertRaises(ReportValidationError):
                mail.preview_report(self.source, "en")

            writer.assert_not_called()

        self.assertFalse(self.eml.exists())

    def test_invalid_preview_preserves_existing_eml(self):
        self.eml.write_bytes(b"original EML")
        self.source.write_text("{}")

        with self.assertRaises(ReportValidationError):
            mail.preview_report(self.source, "en")

        self.assertEqual(
            self.eml.read_bytes(),
            b"original EML"
        )

    def test_invalid_delivery_is_permanent_failure(self):
        self.source.write_text("{}")

        with patch.dict(
            os.environ,
            {"SMTP_ENABLED": "true"}
        ), patch.object(
            mail.smtplib, "SMTP"
        ) as smtp, patch.object(
            mail, "read_secret"
        ) as secret, patch.object(
            mail, "PrivateFileHandler"
        ) as handler:

            with self.assertRaises(mail.DeliveryError) as ctx:
                mail.send_report(self.source, "en")

            self.assertEqual(
                ctx.exception.outcome,
                "failed"
            )

            self.assertEqual(
                mail.DELIVERY_EXIT[ctx.exception.outcome],
                21
            )

            smtp.assert_not_called()
            secret.assert_not_called()
            handler.assert_not_called()

    def test_validation_error_sanitization(self):
        marker = "SENSITIVE_DATASET_TEST_MARKER"

        self.source.write_text(
            '{"unknown":"' + marker + '"}'
        )

        with patch.dict(
            os.environ,
            {"SMTP_ENABLED": "true"}
        ), patch.object(
            mail.smtplib, "SMTP"
        ) as smtp:

            with self.assertRaises(mail.DeliveryError) as ctx:
                mail.send_report(self.source, "en")

            self.assertNotIn(marker, str(ctx.exception))
            self.assertEqual(ctx.exception.outcome, "failed")
            smtp.assert_not_called()

    def test_valid_bilingual_message(self):
        self.write_dataset()

        for language in ("en", "uk"):
            with self.subTest(language=language):

                create_fixture_manifest(self.source, language)

                message = mail.build_message(
                    self.source,
                    language=language,
                    preview=True
                )

                parsed = BytesParser(
                    policy=policy.default
                ).parsebytes(message.as_bytes())

                body = parsed.get_body(
                    preferencelist=("html",)
                ).get_content()

                self.assertIn(
                    f'lang="{language}"',
                    body
                )

                attachments = {
                    part.get_filename():
                        part.get_payload(decode=True)
                    for part in parsed.iter_attachments()
                }

                self.assertEqual(
                    attachments,
                    {
                        "report.pdf": self.pdf,
                        "report.html": self.html
                    }
                )

                self.assertFalse(parsed.defects)

    def test_valid_preview_is_private(self):
        self.write_dataset()
        create_fixture_manifest(self.source, "en")

        with patch.object(mail.smtplib, "SMTP") as smtp:
            path = mail.preview_report(self.source, "en")
            smtp.assert_not_called()

        self.assertEqual(path, self.eml)
        self.assertTrue(path.is_file())
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(path.stat().st_nlink, 1)

    def test_valid_preview_cannot_overwrite_existing_eml(self):
        self.write_dataset()
        create_fixture_manifest(self.source, "en")
        self.eml.write_bytes(b"original EML")

        with self.assertRaises(FileExistsError):
            mail.preview_report(self.source, "en")

        self.assertEqual(
            self.eml.read_bytes(),
            b"original EML"
        )


if __name__ == "__main__":
    unittest.main()
