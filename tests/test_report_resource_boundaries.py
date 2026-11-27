import sys
import os
import tempfile
import unittest

from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, "/app/scripts")

import report_validation as rv


class ResourceBoundaryTests(unittest.TestCase):

    def test_container_boundary(self):

        with patch.object(rv, "MAX_JSON_CONTAINERS", 5):

            rv.validate_json_depth(
                b"[{},{},{},{}]"
            )

            with self.assertRaises(rv.ReportValidationError):

                rv.validate_json_depth(
                    b"[{},{},{},{},{}]"
                )

    def test_separator_boundary(self):

        with patch.object(rv, "MAX_JSON_SEPARATORS", 10):

            rv.validate_json_depth(
                b"[" + b"0," * 10 + b"0]"
            )

            with self.assertRaises(rv.ReportValidationError):

                rv.validate_json_depth(
                    b"[" + b"0," * 11 + b"0]"
                )

    def test_depth_boundary(self):

        depth = rv.MAX_JSON_DEPTH

        rv.validate_json_depth(
            b"[" * depth + b"0" + b"]" * depth
        )

        with self.assertRaises(rv.ReportValidationError):

            rv.validate_json_depth(
                b"[" * (depth + 1)
                + b"0"
                + b"]" * (depth + 1)
            )

    def test_structural_characters_inside_strings(self):

        with patch.object(rv, "MAX_JSON_CONTAINERS", 2), \
             patch.object(rv, "MAX_JSON_SEPARATORS", 2):

            rv.validate_json_depth(
                b'{"text":"[[[[{{{{,,,,::::"}'
            )

    def test_escaped_quotes(self):

        rv.validate_json_depth(
            b'{"text":"escaped \\" quote [[["}'
        )

    def test_empty_file(self):

        with tempfile.TemporaryDirectory() as directory:

            source = Path(directory) / "empty.json"

            source.touch()

            with self.assertRaises(rv.ReportValidationError):

                rv.load_report(source)

    def test_directory_rejected(self):

        with tempfile.TemporaryDirectory() as directory:

            with self.assertRaises(rv.ReportValidationError):

                rv.load_report(Path(directory))

    def test_symlink_rejected(self):

        with tempfile.TemporaryDirectory() as directory:

            root = Path(directory)

            target = root / "target.json"
            target.write_text("{}")

            link = root / "link.json"
            link.symlink_to(target)

            with patch.object(rv.json, "loads") as parser:

                with self.assertRaises(rv.ReportValidationError):

                    rv.load_report(link)

                parser.assert_not_called()

    def test_fifo_rejected(self):

        with tempfile.TemporaryDirectory() as directory:

            source = Path(directory) / "fifo.json"

            os.mkfifo(source, 0o600)

            with self.assertRaises(rv.ReportValidationError):

                rv.load_report(source)

    def test_invalid_utf8(self):

        with tempfile.TemporaryDirectory() as directory:

            source = Path(directory) / "invalid.json"

            source.write_bytes(b'{"value":"\xff"}')

            with self.assertRaises(rv.ReportValidationError):

                rv.load_report(source)

    def test_file_size_boundary(self):

        with tempfile.TemporaryDirectory() as directory:

            source = Path(directory) / "size.json"

            with patch.object(rv, "MAX_JSON_BYTES", 1024):

                source.write_bytes(
                    b"{}" + b" " * 1022
                )

                with patch.object(
                    rv.json,
                    "loads",
                    return_value={}
                ) as parser:

                    with self.assertRaises(rv.ReportValidationError):

                        rv.load_report(source)

                    parser.assert_called_once()

                source.write_bytes(
                    b"{}" + b" " * 1023
                )

                with patch.object(rv.json, "loads") as parser:

                    with self.assertRaises(rv.ReportValidationError):

                        rv.load_report(source)

                    parser.assert_not_called()

    def test_exponent_overflow(self):

        with self.assertRaises(rv.ReportValidationError):

            rv.parse_json_float("1e999")

    def test_numeric_magnitude_boundary(self):

        rv.parse_json_integer("1000000000000000")

        with self.assertRaises(rv.ReportValidationError):

            rv.parse_json_integer("1000000000000001")


if __name__ == "__main__":

    unittest.main(verbosity=2)
