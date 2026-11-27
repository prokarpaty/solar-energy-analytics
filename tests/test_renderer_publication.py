import sys
import json
import stat
import tempfile
import unittest

from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(
    0,
    str(Path(__file__).resolve().parents[1] / "scripts")
)

import render_report as renderer

from report_integrity import (
    IntegrityError,
    create_manifest,
    write_manifest,
    load_manifest,
    manifest_path,
    verify_manifest,
    byte_identity
)

from report_security_fixture import (
    create_reference,
    ENERGY_MAPPING
)

from secure_files import write_private


class RendererPublicationTests(unittest.TestCase):

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)

        self.root = Path(directory.name)
        self.source = self.root / "report.json"
        self.pdf = self.source.with_suffix(".pdf")
        self.html = self.source.with_suffix(".html")
        self.manifest = manifest_path(self.source)

        self.data = create_reference()

        self.payload = json.dumps(
            self.data,
            allow_nan=False
        ).encode("utf-8")

        write_private(self.source, self.payload)

        self.identity = byte_identity(self.payload)

        self.old_pdf = b"%PDF-1.7\nold report"
        self.old_html = b"<html>old report</html>"

        self.new_pdf = b"%PDF-1.7\nnew report"
        self.new_html = "<html>new report</html>"

        write_private(self.pdf, self.old_pdf)
        write_private(self.html, self.old_html)

        write_manifest(
            self.source,
            create_manifest(
                self.data,
                self.identity,
                "en",
                pdf_bytes=self.old_pdf,
                html_bytes=self.old_html
            )
        )

        self.original = self.snapshot()

        self.start_patch(
            patch.dict(
                renderer.CONFIG,
                {"energy": dict(ENERGY_MAPPING)}
            )
        )

        self.start_patch(
            patch.object(
                renderer,
                "generate_charts",
                return_value=[]
            )
        )

        self.environment = self.start_patch(
            patch.object(renderer, "Environment")
        )

        self.template = MagicMock()

        self.environment.return_value.get_template.return_value = (
            self.template
        )

        self.template.render.side_effect = (
            lambda **kwargs:
                "<html>PDF source</html>"
                if kwargs["pdf"]
                else self.new_html
        )

        self.pdf_engine = self.start_patch(
            patch.object(renderer, "HTML")
        )

        self.pdf_engine.return_value.write_pdf.return_value = (
            self.new_pdf
        )

    def start_patch(self, patcher):
        result = patcher.start()
        self.addCleanup(patcher.stop)
        return result

    def snapshot(self):
        return {
            path.name: path.read_bytes()
            for path in (
                self.source,
                self.pdf,
                self.html,
                self.manifest
            )
            if path.exists()
        }

    def assert_preserved(self):
        self.assertEqual(
            self.snapshot(),
            self.original
        )

    def assert_no_manifest(self):
        self.assertFalse(self.manifest.exists())

        with self.assertRaises(IntegrityError):
            load_manifest(self.source)

    def assert_valid_bundle(self, language):
        manifest = load_manifest(self.source)

        self.assertTrue(
            verify_manifest(
                manifest,
                self.data,
                self.identity,
                language,
                pdf_bytes=self.pdf.read_bytes(),
                html_bytes=self.html.read_bytes()
            )
        )

    def test_successful_english_publication(self):
        result = renderer.render(self.source, "en")

        self.assertEqual(
            result,
            (self.html, self.pdf)
        )

        self.assertEqual(
            self.pdf.read_bytes(),
            self.new_pdf
        )

        self.assertEqual(
            self.html.read_bytes(),
            self.new_html.encode("utf-8")
        )

        self.assert_valid_bundle("en")

    def test_successful_ukrainian_publication(self):
        renderer.render(self.source, "uk")

        self.assert_valid_bundle("uk")

    def test_private_output_permissions(self):
        renderer.render(self.source, "en")

        for path in (
            self.html,
            self.pdf,
            self.manifest
        ):
            with self.subTest(path=path.name):
                info = path.stat()

                self.assertEqual(
                    stat.S_IMODE(info.st_mode),
                    0o600
                )

                self.assertEqual(info.st_nlink, 1)

    def test_source_not_modified(self):
        renderer.render(self.source, "en")

        self.assertEqual(
            self.source.read_bytes(),
            self.payload
        )

    def test_html_rendering_failure(self):
        self.template.render.side_effect = (
            RuntimeError("Synthetic HTML failure")
        )

        with self.assertRaises(RuntimeError):
            renderer.render(self.source, "en")

        self.assert_preserved()

    def test_pdf_template_failure(self):
        self.template.render.side_effect = [
            self.new_html,
            RuntimeError("Synthetic PDF template failure")
        ]

        with self.assertRaises(RuntimeError):
            renderer.render(self.source, "en")

        self.assert_preserved()

    def test_pdf_generation_failure(self):
        self.pdf_engine.return_value.write_pdf.side_effect = (
            RuntimeError("Synthetic PDF failure")
        )

        with self.assertRaises(RuntimeError):
            renderer.render(self.source, "en")

        self.assert_preserved()

    def test_manifest_creation_failure(self):
        with patch.object(
            renderer,
            "create_manifest",
            side_effect=IntegrityError(
                "Synthetic manifest failure"
            )
        ):
            with self.assertRaises(IntegrityError):
                renderer.render(self.source, "en")

        self.assert_preserved()

    def test_empty_pdf_rejected_before_publication(self):
        self.pdf_engine.return_value.write_pdf.return_value = b""

        with self.assertRaises(IntegrityError):
            renderer.render(self.source, "en")

        self.assert_preserved()

    def test_html_publication_failure(self):
        with patch.object(
            renderer,
            "write_private",
            side_effect=OSError("Synthetic write failure")
        ):
            with self.assertRaises(OSError):
                renderer.render(self.source, "en")

        self.assert_no_manifest()

        self.assertEqual(
            self.html.read_bytes(),
            self.old_html
        )

        self.assertEqual(
            self.pdf.read_bytes(),
            self.old_pdf
        )

    def test_pdf_publication_failure(self):
        def publish(path, payload):
            if Path(path) == self.pdf:
                raise OSError("Synthetic PDF write failure")

            write_private(path, payload)

        with patch.object(
            renderer,
            "write_private",
            side_effect=publish
        ):
            with self.assertRaises(OSError):
                renderer.render(self.source, "en")

        self.assert_no_manifest()

        self.assertEqual(
            self.html.read_bytes(),
            self.new_html.encode("utf-8")
        )

        self.assertEqual(
            self.pdf.read_bytes(),
            self.old_pdf
        )

    def test_manifest_publication_failure(self):
        with patch.object(
            renderer,
            "write_manifest",
            side_effect=OSError(
                "Synthetic manifest write failure"
            )
        ):
            with self.assertRaises(OSError):
                renderer.render(self.source, "en")

        self.assert_no_manifest()

        self.assertEqual(
            self.pdf.read_bytes(),
            self.new_pdf
        )

        self.assertEqual(
            self.html.read_bytes(),
            self.new_html.encode("utf-8")
        )

    def test_manifest_published_last(self):
        events = []

        def publish(path, payload):
            self.assertFalse(self.manifest.exists())

            events.append(Path(path).suffix)

            write_private(path, payload)

        def publish_manifest(source, manifest):
            self.assertFalse(self.manifest.exists())

            self.assertEqual(
                self.pdf.read_bytes(),
                self.new_pdf
            )

            self.assertEqual(
                self.html.read_bytes(),
                self.new_html.encode("utf-8")
            )

            events.append("manifest")

            return write_manifest(source, manifest)

        with patch.object(
            renderer,
            "write_private",
            side_effect=publish
        ):
            with patch.object(
                renderer,
                "write_manifest",
                side_effect=publish_manifest
            ):
                renderer.render(self.source, "en")

        self.assertEqual(
            events,
            [".html", ".pdf", "manifest"]
        )

        self.assert_valid_bundle("en")

    def test_successful_regeneration(self):
        renderer.render(self.source, "en")
        self.assert_valid_bundle("en")

        renderer.render(self.source, "uk")
        self.assert_valid_bundle("uk")

    def test_no_residual_temporary_files(self):
        renderer.render(self.source, "en")

        self.assertEqual(
            {path.name for path in self.root.iterdir()},
            {
                self.source.name,
                self.pdf.name,
                self.html.name,
                self.manifest.name
            }
        )

    def test_invalid_dataset_preserves_outputs(self):
        from report_validation import ReportValidationError

        write_private(self.source, b"{invalid")

        before = self.snapshot()

        with self.assertRaises(ReportValidationError):
            renderer.render(self.source, "en")

        self.assertEqual(
            self.snapshot(),
            before
        )

        self.template.render.assert_not_called()


if __name__ == "__main__":
    unittest.main()
