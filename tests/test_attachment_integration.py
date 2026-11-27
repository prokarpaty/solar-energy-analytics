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

from attachment_security import AttachmentError
from report_manifest_fixture import create_fixture_manifest
from email_security import MAX_RAW_ATTACHMENT_BYTES
from report_security_fixture import (
    create_reference,
    ENERGY_MAPPING
)


class AttachmentIntegrationTests(unittest.TestCase):

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)

        self.root = Path(directory.name)
        self.source = self.root / "report.json"
        self.pdf = self.source.with_suffix(".pdf")
        self.html = self.source.with_suffix(".html")
        self.eml = self.source.with_suffix(".eml")

        self.source.write_text(
            json.dumps(
                create_reference(),
                allow_nan=False
            ),
            encoding="utf-8"
        )

        self.source.chmod(0o600)

        self.pdf.write_bytes(b"%PDF-1.7\nsynthetic")
        self.html.write_bytes(b"<html>synthetic</html>")

        self.pdf.chmod(0o600)
        self.html.chmod(0o600)

        from ha_client import CONFIG

        mapping = patch.dict(
            CONFIG,
            {"energy": dict(ENERGY_MAPPING)}
        )

        mapping.start()
        self.addCleanup(mapping.stop)

        create_fixture_manifest(self.source, "en")

    def resize(self, path, size):
        with path.open("wb") as stream:
            stream.truncate(size)

        path.chmod(0o600)

    def assert_rejected(self):
        with patch.object(
            mail, "build_email"
        ) as body:

            with patch.object(
                mail.smtplib, "SMTP"
            ) as smtp:

                with self.assertRaises(AttachmentError):
                    mail.preview_report(
                        self.source,
                        language="en"
                    )

                body.assert_not_called()
                smtp.assert_not_called()

        self.assertFalse(self.eml.exists())

    def test_valid_attachment_bytes(self):
        message = mail.build_message(
            self.source,
            language="en",
            preview=True
        )

        actual = {
            part.get_filename():
                part.get_payload(decode=True)
            for part in message.iter_attachments()
        }

        expected = {
            self.pdf.name: self.pdf.read_bytes(),
            self.html.name: self.html.read_bytes()
        }

        self.assertEqual(actual, expected)

    def test_decreasing_byte_budget(self):
        from attachment_security import read_attachment

        with patch.object(
            mail,
            "read_attachment",
            wraps=read_attachment
        ) as reader:

            mail.build_message(
                self.source,
                language="en",
                preview=True
            )

        self.assertEqual(reader.call_count, 2)

        self.assertEqual(
            reader.call_args_list[0].kwargs["maximum"],
            MAX_RAW_ATTACHMENT_BYTES
        )

        self.assertEqual(
            reader.call_args_list[1].kwargs["maximum"],
            MAX_RAW_ATTACHMENT_BYTES
            - self.pdf.stat().st_size
        )

    def test_combined_exact_limit(self):
        first = 8_000_000

        self.resize(self.pdf, first)

        self.resize(
            self.html,
            MAX_RAW_ATTACHMENT_BYTES - first
        )

        create_fixture_manifest(self.source, "en")

        message = mail.build_message(
            self.source,
            language="en",
            preview=True
        )

        total = sum(
            len(part.get_payload(decode=True))
            for part in message.iter_attachments()
        )

        self.assertEqual(
            total,
            MAX_RAW_ATTACHMENT_BYTES
        )

        self.assertLessEqual(
            len(message.as_bytes()),
            24_000_000
        )

    def test_combined_limit_exceeded(self):
        self.resize(self.pdf, 9_000_000)
        self.resize(self.html, 9_000_000)

        self.assert_rejected()

    def test_combined_limit_exceeded_by_one(self):
        self.resize(self.pdf, 8_000_000)

        self.resize(
            self.html,
            MAX_RAW_ATTACHMENT_BYTES - 8_000_000 + 1
        )

        self.assert_rejected()

    def test_first_attachment_consumes_budget(self):
        self.resize(
            self.pdf,
            MAX_RAW_ATTACHMENT_BYTES
        )

        self.assert_rejected()

    def test_oversized_first_attachment(self):
        self.resize(
            self.pdf,
            MAX_RAW_ATTACHMENT_BYTES + 1
        )

        self.assert_rejected()

    def test_oversized_second_attachment(self):
        self.resize(
            self.html,
            MAX_RAW_ATTACHMENT_BYTES + 1
        )

        self.assert_rejected()

    def test_missing_pdf(self):
        self.pdf.unlink()
        self.assert_rejected()

    def test_missing_html(self):
        self.html.unlink()
        self.assert_rejected()

    def test_symbolic_link_pdf(self):
        target = self.root / "original.pdf"

        self.pdf.rename(target)
        self.pdf.symlink_to(target)

        self.assert_rejected()

    def test_symbolic_link_html(self):
        target = self.root / "original.html"

        self.html.rename(target)
        self.html.symlink_to(target)

        self.assert_rejected()

    def test_hard_link_attachment(self):
        os.link(
            self.pdf,
            self.root / "duplicate.pdf"
        )

        self.assert_rejected()

    def test_insecure_attachment_permissions(self):
        self.html.chmod(0o644)
        self.assert_rejected()

    def test_empty_attachment(self):
        self.pdf.write_bytes(b"")
        self.assert_rejected()

    def test_fifo_attachment(self):
        self.html.unlink()
        os.mkfifo(self.html, 0o600)

        self.assert_rejected()

    def test_existing_preview_preserved(self):
        original = b"existing private preview"

        self.eml.write_bytes(original)
        self.eml.chmod(0o600)

        self.html.chmod(0o644)

        with self.assertRaises(AttachmentError):
            mail.preview_report(
                self.source,
                language="en"
            )

        self.assertEqual(
            self.eml.read_bytes(),
            original
        )

    def test_verified_bytes_used_after_replacement(self):
        from attachment_security import read_attachment

        original = self.pdf.read_bytes()

        def read_then_replace(path, **kwargs):
            payload = read_attachment(path, **kwargs)

            if Path(path) == self.pdf:
                self.pdf.write_bytes(
                    b"replacement content"
                )

            return payload

        with patch.object(
            mail,
            "read_attachment",
            side_effect=read_then_replace
        ):
            message = mail.build_message(
                self.source,
                language="en",
                preview=True
            )

        attachments = {
            part.get_filename():
                part.get_payload(decode=True)
            for part in message.iter_attachments()
        }

        self.assertEqual(
            attachments[self.pdf.name],
            original
        )


if __name__ == "__main__":
    unittest.main()
