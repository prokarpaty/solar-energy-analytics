import os
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from secure_files import atomic_private, write_private, private_append

class SecureFiles(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.path = self.root / 'report'

    def test_mode_and_replacement(self):
        self.path.write_bytes(b'old')
        self.path.chmod(0o644)
        write_private(self.path, b'new')
        self.assertEqual(self.path.read_bytes(), b'new')
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)

    def test_failed_write(self):
        self.path.write_bytes(b'old')
        with self.assertRaises(RuntimeError):
            with atomic_private(self.path) as stream:
                stream.write(b'partial')
                raise RuntimeError()
        self.assertEqual(self.path.read_bytes(), b'old')
        self.assertEqual(list(self.root.iterdir()), [self.path])

    def test_exclusive(self):
        write_private(self.path, b'first', exclusive=True)
        with self.assertRaises(FileExistsError):
            write_private(self.path, b'second', exclusive=True)
        self.assertEqual(self.path.read_bytes(), b'first')
        self.assertEqual(list(self.root.iterdir()), [self.path])

    def test_symlink_replacement(self):
        victim = self.root / 'victim'
        victim.write_bytes(b'untouched')
        self.path.symlink_to(victim)
        write_private(self.path, b'new')
        self.assertFalse(self.path.is_symlink())
        self.assertEqual(victim.read_bytes(), b'untouched')

    def test_exclusive_symlink(self):
        self.path.symlink_to(self.root / 'missing')
        with self.assertRaises(FileExistsError):
            write_private(self.path, b'new', exclusive=True)
        self.assertTrue(self.path.is_symlink())
        self.assertFalse((self.root / 'missing').exists())

    def test_append(self):
        self.path.write_text('old')
        self.path.chmod(0o644)
        with private_append(self.path) as stream:
            stream.write('new')
        self.assertEqual(self.path.read_text(), 'oldnew')
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)

    def test_append_symlink(self):
        self.path.symlink_to(self.root / 'missing')
        with self.assertRaises(OSError):
            private_append(self.path)

    def test_append_hardlink(self):
        victim = self.root / 'victim'
        victim.write_text('old')
        os.link(victim, self.path)
        with self.assertRaises(ValueError):
            private_append(self.path)
