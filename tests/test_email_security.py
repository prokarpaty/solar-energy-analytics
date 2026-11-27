import sys
import json
import unittest
import tempfile

from pathlib import Path
from unittest.mock import patch
from html.parser import HTMLParser
from email import policy
from email.parser import BytesParser

sys.path.insert(
    0,
    str(Path(__file__).resolve().parents[1] / "scripts")
)

from email_security import (
    validate_mailbox,
    validate_recipients,
    validate_subject,
    validate_attachment_filename,
    validate_attachment_size,
    MAX_RAW_ATTACHMENT_BYTES,
)

from send_report import build_email, build_message
from report_security_fixture import create_reference, ENERGY_MAPPING
from ha_client import CONFIG
from report_manifest_fixture import create_fixture_manifest


PAYLOADS = [
    '<script id="security-test">TEST</script>',
    '<img src="https://example.invalid/test" onerror="TEST">',
    '<svg onload="TEST"></svg>',
    '<a href="javascript:TEST">TEST</a>',
    '"><iframe src="https://example.invalid"></iframe>',
]


def sample_data():
    return {
        "report_type": "daily",
        "start": "2026-11-24T00:00:00+02:00",
        "end": "2026-11-25T00:00:00+02:00",
        "timezone": "Europe/Kyiv",
        "energy": {
            "production": {
                "total": 1.5,
                "coverage": 100.0,
                "status": "complete",
            }
        },
        "configuration_warnings": list(PAYLOADS),
    }


def validated_sample_data():
    data = create_reference()
    data["configuration_warnings"] = list(PAYLOADS)
    return data


class HTMLInspector(HTMLParser):

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tags = []
        self.attributes = []
        self.text_nodes = []

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)
        self.attributes.extend(attrs)

    def handle_data(self, data):
        self.text_nodes.append(data)


class EmailSecurity(unittest.TestCase):

    def setUp(self):
        mapping = patch.dict(CONFIG, {"energy": dict(ENERGY_MAPPING)})
        mapping.start()
        self.addCleanup(mapping.stop)

    def test_valid_mailboxes(self):
        for value in (
            "solar@example.com",
            "solar.reports@example.com",
            "solar+reports@example.com",
            "solar@example.co.uk",
        ):
            with self.subTest(value=value):
                self.assertEqual(
                    validate_mailbox(value).addr_spec,
                    value
                )

    def test_domain_normalization(self):
        self.assertEqual(
            validate_mailbox("Solar@EXAMPLE.COM").addr_spec,
            "Solar@example.com"
        )

    def test_mailbox_header_injection(self):
        for separator in ("\r", "\n", "\r\n"):
            with self.subTest(separator=repr(separator)):
                with self.assertRaises(ValueError):
                    validate_mailbox(
                        "solar@example.com"
                        + separator
                        + "Bcc: other@example.com"
                    )

    def test_mailbox_invalid_syntax(self):
        for value in (
            "",
            "solar@",
            "@example.com",
            "solar@@example.com",
            "solar..reports@example.com",
            ".solar@example.com",
            "solar.@example.com",
            "solar@-example.com",
            "solar@example-.com",
            "solar@example..com",
            "solar reports@example.com",
            "solar@example",
        ):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    validate_mailbox(value)

    def test_mailbox_display_names(self):
        with self.assertRaises(ValueError):
            validate_mailbox(
                "Solar Reports <solar@example.com>"
            )

    def test_mailbox_comments(self):
        with self.assertRaises(ValueError):
            validate_mailbox(
                "solar@example.com (Reports)"
            )

    def test_multiple_senders(self):
        with self.assertRaises(ValueError):
            validate_mailbox(
                "one@example.com,two@example.com"
            )

    def test_mailbox_controls(self):
        for char in (
            "\x00", "\t", "\x7f",
            "\u202e", "\u200b", "\u2028"
        ):
            with self.subTest(char=repr(char)):
                with self.assertRaises(ValueError):
                    validate_mailbox(
                        "solar" + char + "@example.com"
                    )

    def test_mailbox_length(self):
        with self.assertRaises(ValueError):
            validate_mailbox("a" * 65 + "@example.com")

    def test_non_ascii_mailbox(self):
        with self.assertRaises(ValueError):
            validate_mailbox("звіт@example.com")

    def test_multiple_recipients(self):
        result = validate_recipients(
            "one@example.com, two@example.com"
        )

        self.assertEqual(
            [address.addr_spec for address in result],
            ["one@example.com", "two@example.com"]
        )

    def test_duplicate_recipients(self):
        with self.assertRaises(ValueError):
            validate_recipients(
                "one@example.com,one@EXAMPLE.COM"
            )

    def test_invalid_recipient_lists(self):
        for value in (
            "",
            ",",
            "one@example.com,",
            ",one@example.com",
            "one@example.com,,two@example.com",
            "one@example.com;two@example.com",
        ):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    validate_recipients(value)

    def test_recipient_count_limit(self):
        valid = ",".join(
            f"user{i}@example.com" for i in range(50)
        )

        self.assertEqual(
            len(validate_recipients(valid)),
            50
        )

        with self.assertRaises(ValueError):
            validate_recipients(
                valid + ",extra@example.com"
            )

    def test_recipient_header_injection(self):
        with self.assertRaises(ValueError):
            validate_recipients(
                "one@example.com\r\nBcc: two@example.com"
            )

    def test_bilingual_subjects(self):
        for value in (
            "Solar Energy Report",
            "☀ Звіт сонячної електростанції"
        ):
            self.assertEqual(
                validate_subject(value),
                value
            )

    def test_subject_controls(self):
        for char in (
            "\r", "\n", "\x00", "\x7f",
            "\u202e", "\u2028", "\u2029"
        ):
            with self.subTest(char=repr(char)):
                with self.assertRaises(ValueError):
                    validate_subject("Report" + char)

    def test_subject_length(self):
        self.assertEqual(
            validate_subject("A" * 512),
            "A" * 512
        )

        with self.assertRaises(ValueError):
            validate_subject("A" * 513)

    def test_empty_subject(self):
        for value in ("", "   "):
            with self.assertRaises(ValueError):
                validate_subject(value)

    def test_valid_attachment_filenames(self):
        for value in (
            "report-en.pdf",
            "report-uk.html",
            "solar-daily-2026-11-24_2026-11-24.pdf",
        ):
            self.assertEqual(
                validate_attachment_filename(value),
                value
            )

    def test_attachment_path_traversal(self):
        for value in (
            "../report.pdf",
            "/tmp/report.pdf",
            r"..\report.pdf",
            r"C:\temp\report.pdf",
        ):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    validate_attachment_filename(value)

    def test_attachment_header_injection(self):
        for value in (
            "report\r\nBcc:test.pdf",
            "report\n.pdf",
            "report\x00.pdf",
            "report\u202e.pdf",
        ):
            with self.subTest(value=repr(value)):
                with self.assertRaises(ValueError):
                    validate_attachment_filename(value)

    def test_attachment_invalid_names(self):
        for value in (
            "",
            ".report.pdf",
            "report.exe",
            "report.svg",
            "<script>.html",
            " report.pdf",
            "report.pdf ",
            "a" * 201 + ".pdf",
        ):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    validate_attachment_filename(value)

    def test_attachment_size_boundaries(self):
        self.assertEqual(
            validate_attachment_size([500_000, 5_000_000]),
            5_500_000
        )

        self.assertEqual(
            validate_attachment_size(
                [MAX_RAW_ATTACHMENT_BYTES]
            ),
            MAX_RAW_ATTACHMENT_BYTES
        )

    def test_attachment_invalid_sizes(self):
        for sizes in (
            [],
            [0],
            [-1],
            [True],
            ["100"],
            [MAX_RAW_ATTACHMENT_BYTES + 1],
            [10_000_000, 8_000_000],
        ):
            with self.subTest(sizes=sizes):
                with self.assertRaises(ValueError):
                    validate_attachment_size(sizes)

    def test_html_injection_bilingual(self):
        for language in ("en", "uk"):
            with self.subTest(language=language):

                subject, plain, html = build_email(
                    sample_data(),
                    language
                )

                inspector = HTMLInspector()
                inspector.feed(html)

                for tag in (
                    "script", "img", "svg",
                    "iframe", "object", "embed", "a"
                ):
                    self.assertNotIn(tag, inspector.tags)

                for name, value in inspector.attributes:
                    self.assertFalse(name.startswith("on"))
                    self.assertNotIn(
                        name, ("src", "href", "srcdoc")
                    )

                text = "".join(inspector.text_nodes)

                for payload in PAYLOADS:
                    self.assertIn(payload, text)
                    self.assertIn(payload, plain)
                    self.assertNotIn(payload, html)

                validate_subject(subject)

    def test_mime_integration_bilingual(self):
        with tempfile.TemporaryDirectory() as directory:

            source = Path(directory) / "report.json"

            source.write_text(
                json.dumps(validated_sample_data(), allow_nan=False),
                encoding="utf-8"
            )

            pdf = b"%PDF-1.7\nSynthetic test"
            html = b"<html>Synthetic test</html>"

            source.with_suffix(".pdf").write_bytes(pdf)
            source.with_suffix(".pdf").chmod(0o600)
            source.with_suffix(".html").write_bytes(html)
            source.with_suffix(".html").chmod(0o600)

            for language in ("en", "uk"):
                with self.subTest(language=language):

                    create_fixture_manifest(source, language)

                    with patch.dict(
                        "os.environ",
                        {
                            "SMTP_FROM": "solar@example.com",
                            "SMTP_TO": (
                                "one@example.com,"
                                "two@example.com"
                            ),
                        }
                    ):
                        message = build_message(
                            source,
                            language=language
                        )

                    parsed = BytesParser(
                        policy=policy.default
                    ).parsebytes(message.as_bytes())

                    self.assertEqual(
                        len(parsed["From"].addresses), 1
                    )

                    self.assertEqual(
                        len(parsed["To"].addresses), 2
                    )

                    self.assertIsNone(parsed["Bcc"])
                    self.assertIsNone(parsed["Cc"])
                    self.assertFalse(parsed.defects)

                    attachments = {
                        item.get_filename():
                            item.get_payload(decode=True)
                        for item in parsed.iter_attachments()
                    }

                    self.assertEqual(
                        attachments,
                        {
                            "report.pdf": pdf,
                            "report.html": html,
                        }
                    )

                    self.assertIsNotNone(
                        parsed.get_body(
                            preferencelist=("plain",)
                        )
                    )

                    self.assertIsNotNone(
                        parsed.get_body(
                            preferencelist=("html",)
                        )
                    )

    def test_preview_ignores_unsafe_addresses(self):
        with tempfile.TemporaryDirectory() as directory:

            source = Path(directory) / "report.json"

            source.write_text(
                json.dumps(validated_sample_data(), allow_nan=False),
                encoding="utf-8"
            )

            source.with_suffix(".pdf").write_bytes(b"PDF")
            source.with_suffix(".pdf").chmod(0o600)
            source.with_suffix(".html").write_bytes(b"HTML")
            source.with_suffix(".html").chmod(0o600)

            create_fixture_manifest(source, "en")

            with patch.dict(
                "os.environ",
                {
                    "SMTP_FROM": "invalid\r\nBcc: injected",
                    "SMTP_TO": "invalid\r\nBcc: injected",
                }
            ):
                message = build_message(
                    source,
                    language="en",
                    preview=True
                )

                self.assertEqual(
                    str(message["From"]),
                    "preview@example.invalid"
                )

                self.assertEqual(
                    str(message["To"]),
                    "preview@example.invalid"
                )

                with self.assertRaises(ValueError):
                    build_message(
                        source,
                        language="en",
                        preview=False
                    )


if __name__ == "__main__":
    unittest.main()
