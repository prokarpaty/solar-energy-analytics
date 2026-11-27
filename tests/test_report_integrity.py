import os
import sys
import json
import stat
import copy
import tempfile
import unittest

from pathlib import Path

sys.path.insert(
    0,
    str(Path(__file__).resolve().parents[1] / "scripts")
)

from report_integrity import (
    IntegrityError,
    MAX_MANIFEST_BYTES,
    byte_identity,
    manifest_path,
    create_manifest,
    validate_manifest,
    write_manifest,
    load_manifest,
    verify_manifest
)

from report_security_fixture import create_reference


class ReportIntegrityTests(unittest.TestCase):

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)

        self.source = Path(directory.name) / "report.json"

        self.data = create_reference()

        self.payload = json.dumps(
            self.data,
            allow_nan=False
        ).encode("utf-8")

        self.identity = byte_identity(self.payload)

        self.pdf = b"%PDF-1.7\nsynthetic report"
        self.html = b"<html>synthetic report</html>"

        self.manifest = create_manifest(
            self.data,
            self.identity,
            "en",
            pdf_bytes=self.pdf,
            html_bytes=self.html
        )

    def verify(self, **overrides):
        arguments = {
            "manifest": self.manifest,
            "data": self.data,
            "dataset_identity": self.identity,
            "language": "en",
            "pdf_bytes": self.pdf,
            "html_bytes": self.html
        }

        arguments.update(overrides)

        return verify_manifest(**arguments)

    def write_raw(self, payload):
        path = manifest_path(self.source)

        path.write_bytes(payload)
        path.chmod(0o600)

        return path

    def reject_field(self, field, value):
        manifest = copy.deepcopy(self.manifest)

        manifest[field] = value

        with self.assertRaises(IntegrityError):
            validate_manifest(manifest)

    def test_valid_manifest(self):
        self.assertTrue(self.verify())

    def test_manifest_filename(self):
        self.assertEqual(
            manifest_path(self.source).name,
            "report.manifest.json"
        )

    def test_invalid_source_extension(self):
        with self.assertRaises(IntegrityError):
            manifest_path("report.pdf")

    def test_recursive_manifest_name(self):
        with self.assertRaises(IntegrityError):
            manifest_path("report.manifest.json")

    def test_private_manifest_roundtrip(self):
        path = write_manifest(
            self.source,
            self.manifest
        )

        self.assertEqual(
            load_manifest(self.source),
            self.manifest
        )

        self.assertEqual(
            stat.S_IMODE(path.stat().st_mode),
            0o600
        )

        self.assertEqual(path.stat().st_nlink, 1)

    def test_atomic_manifest_replacement(self):
        path = write_manifest(
            self.source,
            self.manifest
        )

        updated = copy.deepcopy(self.manifest)
        updated["language"] = "uk"

        write_manifest(self.source, updated)

        self.assertEqual(
            load_manifest(self.source),
            updated
        )

        self.assertEqual(
            list(path.parent.iterdir()),
            [path]
        )

    def test_unknown_schema_version(self):
        self.reject_field("schema_version", 2)

    def test_boolean_schema_version(self):
        self.reject_field("schema_version", True)

    def test_invalid_report_type(self):
        self.reject_field("report_type", "invalid")

    def test_invalid_language(self):
        self.reject_field("language", "fr")

    def test_invalid_timestamp(self):
        self.reject_field("period_start", "invalid")

    def test_naive_timestamp(self):
        self.reject_field(
            "period_start",
            "2026-01-15T00:00:00"
        )

    def test_reversed_period(self):
        self.reject_field(
            "period_start",
            self.manifest["period_end"]
        )

    def test_generation_before_period_end(self):
        self.reject_field(
            "generated_at",
            self.manifest["period_start"]
        )

    def test_unknown_field(self):
        self.manifest["unexpected"] = True

        with self.assertRaises(IntegrityError):
            self.verify()

    def test_missing_field(self):
        self.manifest.pop("dataset")

        with self.assertRaises(IntegrityError):
            self.verify()

    def test_invalid_hash(self):
        self.manifest["dataset"]["sha256"] = "invalid"

        with self.assertRaises(IntegrityError):
            self.verify()

    def test_invalid_size(self):
        self.manifest["dataset"]["size"] = -1

        with self.assertRaises(IntegrityError):
            self.verify()

    def test_boolean_size(self):
        self.manifest["dataset"]["size"] = True

        with self.assertRaises(IntegrityError):
            self.verify()

    def test_dataset_mismatch(self):
        with self.assertRaises(IntegrityError):
            self.verify(
                dataset_identity=byte_identity(
                    self.payload + b"\n"
                )
            )

    def test_pdf_mismatch(self):
        with self.assertRaises(IntegrityError):
            self.verify(
                pdf_bytes=self.pdf + b"modified"
            )

    def test_html_mismatch(self):
        with self.assertRaises(IntegrityError):
            self.verify(
                html_bytes=self.html + b"modified"
            )

    def test_same_size_pdf_modification(self):
        modified = b"X" + self.pdf[1:]

        self.assertEqual(
            len(modified),
            len(self.pdf)
        )

        with self.assertRaises(IntegrityError):
            self.verify(pdf_bytes=modified)

    def test_swapped_attachments(self):
        with self.assertRaises(IntegrityError):
            self.verify(
                pdf_bytes=self.html,
                html_bytes=self.pdf
            )

    def test_language_mismatch(self):
        with self.assertRaises(IntegrityError):
            self.verify(language="uk")

    def test_report_type_mismatch(self):
        data = copy.deepcopy(self.data)
        data["report_type"] = "weekly"

        with self.assertRaises(IntegrityError):
            self.verify(data=data)

    def test_period_mismatch(self):
        data = copy.deepcopy(self.data)
        data["start"] = data["end"]

        with self.assertRaises(IntegrityError):
            self.verify(data=data)

    def test_missing_manifest(self):
        with self.assertRaises(IntegrityError):
            load_manifest(self.source)

    def test_invalid_json(self):
        self.write_raw(b"{invalid")

        with self.assertRaises(IntegrityError):
            load_manifest(self.source)

    def test_duplicate_json_keys(self):
        self.write_raw(
            b'{"schema_version":1,"schema_version":1}'
        )

        with self.assertRaises(IntegrityError):
            load_manifest(self.source)

    def test_invalid_utf8(self):
        self.write_raw(b"\xff\xfe")

        with self.assertRaises(IntegrityError):
            load_manifest(self.source)

    def test_nan_constant(self):
        self.write_raw(b'{"value":NaN}')

        with self.assertRaises(IntegrityError):
            load_manifest(self.source)

    def test_oversized_manifest(self):
        self.write_raw(
            b" " * (MAX_MANIFEST_BYTES + 1)
        )

        with self.assertRaises(IntegrityError):
            load_manifest(self.source)

    def test_symbolic_link(self):
        path = write_manifest(
            self.source,
            self.manifest
        )

        target = path.with_name("original.json")

        path.rename(target)
        path.symlink_to(target)

        with self.assertRaises(IntegrityError):
            load_manifest(self.source)

    def test_hard_link(self):
        path = write_manifest(
            self.source,
            self.manifest
        )

        os.link(
            path,
            path.with_name("duplicate.json")
        )

        with self.assertRaises(IntegrityError):
            load_manifest(self.source)

    def test_insecure_permissions(self):
        path = write_manifest(
            self.source,
            self.manifest
        )

        path.chmod(0o644)

        with self.assertRaises(IntegrityError):
            load_manifest(self.source)

    def test_fifo_manifest(self):
        os.mkfifo(
            manifest_path(self.source),
            0o600
        )

        with self.assertRaises(IntegrityError):
            load_manifest(self.source)

    def test_empty_manifest(self):
        self.write_raw(b"")

        with self.assertRaises(IntegrityError):
            load_manifest(self.source)

    def test_verification_does_not_modify_manifest(self):
        original = copy.deepcopy(self.manifest)

        self.verify()

        self.assertEqual(
            self.manifest,
            original
        )

    def test_combined_attachment_budget(self):
        self.manifest["attachments"]["pdf"]["size"] = 9_000_000
        self.manifest["attachments"]["html"]["size"] = 9_000_000

        with self.assertRaises(IntegrityError):
            self.verify()

    def test_ukrainian_manifest(self):
        manifest = create_manifest(
            self.data,
            self.identity,
            "uk",
            pdf_bytes=self.pdf,
            html_bytes=self.html
        )

        self.assertTrue(
            self.verify(
                manifest=manifest,
                language="uk"
            )
        )


if __name__ == "__main__":
    unittest.main()
