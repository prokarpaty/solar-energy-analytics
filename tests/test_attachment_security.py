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

import attachment_security as security

from attachment_security import (
    AttachmentError,
    read_attachment
)

from email_security import MAX_RAW_ATTACHMENT_BYTES


class AttachmentSecurityTests(unittest.TestCase):

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)

        self.root = Path(directory.name)
        self.path = self.root / "report.pdf"
        self.payload = b"synthetic report attachment"

        self.path.write_bytes(self.payload)
        self.path.chmod(0o600)

    def test_valid_private_file(self):
        self.assertEqual(
            read_attachment(self.path),
            self.payload
        )

    def test_exact_byte_budget(self):
        self.assertEqual(
            read_attachment(
                self.path,
                maximum=len(self.payload)
            ),
            self.payload
        )

    def test_exceeded_byte_budget(self):
        with self.assertRaises(AttachmentError):
            read_attachment(
                self.path,
                maximum=len(self.payload) - 1
            )

    def test_invalid_byte_budgets(self):
        for maximum in (
            0,
            -1,
            True,
            1.5,
            None,
            MAX_RAW_ATTACHMENT_BYTES + 1
        ):
            with self.subTest(maximum=maximum):
                with self.assertRaises(AttachmentError):
                    read_attachment(
                        self.path,
                        maximum=maximum
                    )

    def test_missing_file(self):
        self.path.unlink()

        with self.assertRaises(AttachmentError):
            read_attachment(self.path)

    def test_empty_file(self):
        self.path.write_bytes(b"")

        with self.assertRaises(AttachmentError):
            read_attachment(self.path)

    def test_invalid_permissions(self):
        for mode in (
            0o400,
            0o640,
            0o644,
            0o666,
            0o700,
            0o777
        ):
            with self.subTest(mode=oct(mode)):
                self.path.chmod(mode)

                with self.assertRaises(AttachmentError):
                    read_attachment(self.path)

    def test_invalid_owner(self):
        with patch.object(
            security.os,
            "geteuid",
            return_value=os.geteuid() + 1
        ):
            with self.assertRaises(AttachmentError):
                read_attachment(self.path)

    def test_symbolic_link(self):
        link = self.root / "link.pdf"
        link.symlink_to(self.path)

        with self.assertRaises(AttachmentError):
            read_attachment(link)

        self.assertEqual(
            self.path.read_bytes(),
            self.payload
        )

    def test_dangling_symbolic_link(self):
        link = self.root / "dangling.pdf"
        link.symlink_to(self.root / "missing.pdf")

        with self.assertRaises(AttachmentError):
            read_attachment(link)

    def test_hard_link(self):
        link = self.root / "hardlink.pdf"
        os.link(self.path, link)

        for path in (self.path, link):
            with self.subTest(path=path.name):
                with self.assertRaises(AttachmentError):
                    read_attachment(path)

    def test_directory(self):
        directory = self.root / "directory.pdf"
        directory.mkdir(mode=0o700)

        with self.assertRaises(AttachmentError):
            read_attachment(directory)

    def test_fifo_without_writer(self):
        fifo = self.root / "pipe.pdf"
        os.mkfifo(fifo, 0o600)

        with self.assertRaises(AttachmentError):
            read_attachment(fifo)

    def test_character_device(self):
        with self.assertRaises(AttachmentError):
            read_attachment("/dev/null")

    def test_oversized_sparse_file(self):
        with self.path.open("wb") as stream:
            stream.truncate(
                MAX_RAW_ATTACHMENT_BYTES + 1
            )

        with patch.object(
            security.os, "fdopen"
        ) as reader:

            with self.assertRaises(AttachmentError):
                read_attachment(self.path)

            reader.assert_not_called()

    def test_maximum_allowed_size(self):
        with self.path.open("wb") as stream:
            stream.truncate(
                MAX_RAW_ATTACHMENT_BYTES
            )

        payload = read_attachment(self.path)

        self.assertEqual(
            len(payload),
            MAX_RAW_ATTACHMENT_BYTES
        )

    def test_sanitized_error(self):
        marker = "SENSITIVE_ATTACHMENT_PATH_MARKER"

        with self.assertRaises(AttachmentError) as ctx:
            read_attachment(
                self.root / f"{marker}.pdf"
            )

        self.assertNotIn(marker, str(ctx.exception))

    def simulate_change(self, action):
        real_fstat = os.fstat
        calls = 0

        def changed_fstat(fd):
            nonlocal calls
            calls += 1

            info = real_fstat(fd)

            if calls == 1:
                action()

            return info

        with patch.object(
            security.os,
            "fstat",
            side_effect=changed_fstat
        ):
            with self.assertRaises(AttachmentError):
                read_attachment(self.path)

        self.assertGreaterEqual(calls, 2)

    def test_concurrent_growth(self):
        def grow():
            with self.path.open("ab") as stream:
                stream.write(b"additional data")

        self.simulate_change(grow)

    def test_concurrent_truncation(self):
        def truncate():
            with self.path.open("wb") as stream:
                stream.write(b"x")

        self.simulate_change(truncate)

    def test_concurrent_same_size_modification(self):
        def modify():
            self.path.write_bytes(
                b"x" * len(self.payload)
            )

            info = self.path.stat()

            os.utime(
                self.path,
                ns=(
                    info.st_atime_ns,
                    info.st_mtime_ns + 1_000_000_000
                )
            )

        self.simulate_change(modify)

    def test_concurrent_permission_change(self):
        self.simulate_change(
            lambda: self.path.chmod(0o644)
        )

    def test_concurrent_hardlink_creation(self):
        self.simulate_change(
            lambda: os.link(
                self.path,
                self.root / "new-link.pdf"
            )
        )

    def test_concurrent_path_replacement(self):
        replacement = self.root / "replacement.pdf"
        replacement.write_bytes(b"replacement content")
        replacement.chmod(0o600)

        def replace():
            self.path.rename(
                self.root / "original.pdf"
            )

            replacement.rename(self.path)

        self.simulate_change(replace)

    def test_concurrent_symlink_replacement(self):
        def replace():
            original = self.root / "original.pdf"

            self.path.rename(original)
            self.path.symlink_to(original)

        self.simulate_change(replace)

    def test_descriptor_cleanup_after_rejection(self):
        self.path.chmod(0o644)

        before = len(
            os.listdir("/proc/self/fd")
        )

        for _ in range(100):
            with self.assertRaises(AttachmentError):
                read_attachment(self.path)

        after = len(
            os.listdir("/proc/self/fd")
        )

        self.assertEqual(before, after)

    def test_descriptor_cleanup_after_success(self):
        before = len(
            os.listdir("/proc/self/fd")
        )

        for _ in range(100):
            self.assertEqual(
                read_attachment(self.path),
                self.payload
            )

        after = len(
            os.listdir("/proc/self/fd")
        )

        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
