"""End-to-end email report integrity enforcement."""

import os
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

import send_report as mail

from ha_client import CONFIG
from report_integrity import IntegrityError, manifest_path
from report_security_fixture import (
    create_reference,
    ENERGY_MAPPING
)
from report_manifest_fixture import create_fixture_manifest


class EmailManifestSecurityTests(unittest.TestCase):

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)

        self.root = Path(directory.name)
        self.source = self.root / "report.json"
        self.pdf = self.source.with_suffix(".pdf")
        self.html = self.source.with_suffix(".html")
        self.eml = self.source.with_suffix(".eml")
        self.manifest = manifest_path(self.source)

        self.source.write_text(
            json.dumps(create_reference(), allow_nan=False),
            encoding="utf-8"
        )

        self.pdf.write_bytes(b"%PDF-1.7\nSynthetic PDF")
        self.html.write_bytes(b"<html>Synthetic HTML</html>")

        for path in (self.source, self.pdf, self.html):
            path.chmod(0o600)

        mapping = patch.dict(
            CONFIG,
            {"energy": dict(ENERGY_MAPPING)}
        )

        mapping.start()
        self.addCleanup(mapping.stop)

        create_fixture_manifest(self.source, "en")

    def modify_manifest(self, callback):
        data = json.loads(self.manifest.read_text())
        callback(data)
        self.manifest.write_text(
            json.dumps(data),
            encoding="utf-8"
        )

    def assert_rejected(self, language="en"):
        with patch.object(
            mail, "build_email"
        ) as body, patch.object(
            mail, "EmailMessage"
        ) as mime, patch.object(
            mail, "read_secret"
        ) as secret, patch.object(
            mail.smtplib, "SMTP"
        ) as smtp:

            with self.assertRaises(IntegrityError):
                mail.preview_report(
                    self.source,
                    language
                )

            body.assert_not_called()
            mime.assert_not_called()
            secret.assert_not_called()
            smtp.assert_not_called()

        self.assertFalse(self.eml.exists())

    def test_missing_manifest(self):
        self.manifest.unlink()
        self.assert_rejected()

    def test_empty_manifest(self):
        self.manifest.write_bytes(b"")
        self.assert_rejected()

    def test_invalid_manifest_json(self):
        self.manifest.write_text("{invalid")
        self.assert_rejected()

    def test_duplicate_manifest_keys(self):
        self.manifest.write_text(
            '{"schema_version":1,"schema_version":1}'
        )
        self.assert_rejected()

    def test_manifest_symbolic_link(self):
        target = self.root / "original-manifest.json"
        self.manifest.rename(target)
        self.manifest.symlink_to(target)
        self.assert_rejected()

    def test_manifest_hard_link(self):
        os.link(
            self.manifest,
            self.root / "duplicate-manifest.json"
        )
        self.assert_rejected()

    def test_manifest_insecure_permissions(self):
        self.manifest.chmod(0o644)
        self.assert_rejected()

    def test_manifest_fifo(self):
        self.manifest.unlink()
        os.mkfifo(self.manifest, 0o600)
        self.assert_rejected()

    def test_dataset_serialization_changed(self):
        with self.source.open("ab") as stream:
            stream.write(b"\n")

        self.assert_rejected()

    def test_pdf_modified(self):
        self.pdf.write_bytes(b"Modified PDF")
        self.assert_rejected()

    def test_html_modified(self):
        self.html.write_bytes(b"Modified HTML")
        self.assert_rejected()

    def test_same_size_pdf_modified(self):
        payload = self.pdf.read_bytes()
        self.pdf.write_bytes(
            bytes([payload[0] ^ 1]) + payload[1:]
        )
        self.assert_rejected()

    def test_same_size_html_modified(self):
        payload = self.html.read_bytes()
        self.html.write_bytes(
            bytes([payload[0] ^ 1]) + payload[1:]
        )
        self.assert_rejected()

    def test_swapped_attachments(self):
        pdf = self.pdf.read_bytes()
        html = self.html.read_bytes()

        self.pdf.write_bytes(html)
        self.html.write_bytes(pdf)

        self.assert_rejected()

    def test_language_mismatch(self):
        self.assert_rejected(language="uk")

    def test_dataset_hash_mismatch(self):
        self.modify_manifest(
            lambda data: data["dataset"].update(
                sha256="0" * 64
            )
        )
        self.assert_rejected()

    def test_pdf_hash_mismatch(self):
        self.modify_manifest(
            lambda data: data["attachments"]["pdf"].update(
                sha256="0" * 64
            )
        )
        self.assert_rejected()

    def test_html_hash_mismatch(self):
        self.modify_manifest(
            lambda data: data["attachments"]["html"].update(
                sha256="0" * 64
            )
        )
        self.assert_rejected()

    def test_dataset_size_mismatch(self):
        self.modify_manifest(
            lambda data: data["dataset"].update(
                size=data["dataset"]["size"] + 1
            )
        )
        self.assert_rejected()

    def test_report_type_mismatch(self):
        self.modify_manifest(
            lambda data: data.update(report_type="weekly")
        )
        self.assert_rejected()

    def test_period_mismatch(self):
        self.modify_manifest(
            lambda data: data.update(
                period_start="2026-01-14T00:00:00+00:00"
            )
        )
        self.assert_rejected()

    def test_unsupported_manifest_version(self):
        self.modify_manifest(
            lambda data: data.update(schema_version=999)
        )
        self.assert_rejected()

    def test_existing_preview_preserved(self):
        original = b"Existing private EML"

        self.eml.write_bytes(original)
        self.eml.chmod(0o600)

        self.pdf.write_bytes(b"Modified PDF")

        with self.assertRaises(IntegrityError):
            mail.preview_report(self.source, "en")

        self.assertEqual(
            self.eml.read_bytes(),
            original
        )

    def test_delivery_integrity_failure_is_permanent(self):
        self.html.write_bytes(b"Modified HTML")

        with patch.dict(
            os.environ,
            {"SMTP_ENABLED": "true"}
        ), patch.object(
            mail, "read_secret"
        ) as secret, patch.object(
            mail, "PrivateFileHandler"
        ) as handler, patch.object(
            mail.smtplib, "SMTP"
        ) as smtp:

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

            secret.assert_not_called()
            handler.assert_not_called()
            smtp.assert_not_called()

    def test_integrity_error_sanitization(self):
        marker = "SENSITIVE_MANIFEST_TEST_MARKER"

        self.manifest.write_text(
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

    def test_valid_bilingual_bundle(self):
        for language in ("en", "uk"):
            with self.subTest(language=language):

                create_fixture_manifest(
                    self.source,
                    language
                )

                inputs = {
                    path: path.read_bytes()
                    for path in (
                        self.source,
                        self.pdf,
                        self.html,
                        self.manifest
                    )
                }

                message = mail.build_message(
                    self.source,
                    language=language,
                    preview=True
                )

                attachments = {
                    part.get_filename():
                        part.get_payload(decode=True)
                    for part in message.iter_attachments()
                }

                self.assertEqual(
                    attachments,
                    {
                        self.pdf.name: inputs[self.pdf],
                        self.html.name: inputs[self.html]
                    }
                )

                for path, payload in inputs.items():
                    self.assertEqual(
                        path.read_bytes(),
                        payload
                    )


if __name__ == "__main__":
    unittest.main()
