import os
import sys
import tempfile
import unittest

from pathlib import Path
from unittest.mock import patch

sys.path.insert(
    0,
    str(Path(__file__).resolve().parents[1] / "scripts")
)

from secret_reader import (
    read_secret,
    SecretError,
    MAX_SECRET_BYTES
)


class SecretReaderTests(unittest.TestCase):

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root / "credential"

    def write_secret(self, content, mode=0o600):
        self.path.write_bytes(content)
        self.path.chmod(mode)
        return self.path

    def test_valid(self):
        self.write_secret(b"synthetic-test-token\n")
        self.assertEqual(
            read_secret(self.path),
            "synthetic-test-token"
        )

    def test_crlf(self):
        self.write_secret(b"synthetic-password\r\n")
        self.assertEqual(
            read_secret(self.path),
            "synthetic-password"
        )

    def test_preserve_spaces(self):
        self.write_secret(b" password \n")
        self.assertEqual(
            read_secret(self.path),
            " password "
        )

    def test_insecure_permissions(self):
        for mode in (0o644, 0o640, 0o666, 0o777, 0o400):
            with self.subTest(mode=oct(mode)):
                self.write_secret(b"dummy", mode)
                with self.assertRaises(SecretError):
                    read_secret(self.path)

    def test_wrong_owner(self):
        self.write_secret(b"dummy")
        with patch(
            "secret_reader.os.geteuid",
            return_value=os.geteuid() + 1
        ):
            with self.assertRaises(SecretError):
                read_secret(self.path)

    def test_symbolic_link(self):
        self.write_secret(b"dummy")
        link = self.root / "symlink"
        link.symlink_to(self.path)

        with self.assertRaises(SecretError):
            read_secret(link)

    def test_hard_link(self):
        self.write_secret(b"dummy")
        link = self.root / "hardlink"
        os.link(self.path, link)

        for path in (self.path, link):
            with self.assertRaises(SecretError):
                read_secret(path)

    def test_directory(self):
        with self.assertRaises(SecretError):
            read_secret(self.root)

    def test_fifo(self):
        os.mkfifo(self.path, 0o600)

        with self.assertRaises(SecretError):
            read_secret(self.path)

    def test_missing(self):
        with self.assertRaises(SecretError):
            read_secret(self.path)

    def test_empty(self):
        self.write_secret(b"")

        with self.assertRaises(SecretError):
            read_secret(self.path)

    def test_whitespace(self):
        self.write_secret(b"   \n")

        with self.assertRaises(SecretError):
            read_secret(self.path)

    def test_maximum_size(self):
        self.write_secret(b"x" * MAX_SECRET_BYTES)

        self.assertEqual(
            len(read_secret(self.path)),
            MAX_SECRET_BYTES
        )

    def test_oversized(self):
        self.write_secret(b"x" * (MAX_SECRET_BYTES + 1))

        with self.assertRaises(SecretError):
            read_secret(self.path)

    def test_invalid_utf8(self):
        self.write_secret(b"\xff\xfe")

        with self.assertRaises(SecretError):
            read_secret(self.path)

    def test_control_characters(self):
        for value in (
            b"dummy\x00value",
            b"dummy\nvalue",
            b"dummy\rvalue",
            b"dummy\tvalue",
            b"dummy\x1bvalue",
            b"dummy\x7fvalue"
        ):
            with self.subTest(value=value):
                self.write_secret(value)

                with self.assertRaises(SecretError):
                    read_secret(self.path)

    def test_error_sanitization(self):
        marker = "SYNTHETIC_SECRET_DO_NOT_DISCLOSE"
        self.write_secret(
            (marker + "\x00").encode()
        )

        with self.assertRaises(SecretError) as result:
            read_secret(self.path)

        self.assertNotIn(
            marker,
            str(result.exception)
        )

    def test_path_sanitization(self):
        marker = "SENSITIVE_PATH_MARKER"

        with self.assertRaises(SecretError) as result:
            read_secret(self.root / marker)

        self.assertNotIn(
            marker,
            str(result.exception)
        )


if __name__ == "__main__":
    unittest.main()
