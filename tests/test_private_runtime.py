import sys
import os
import stat
import tempfile
import unittest
import logging
import fcntl
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from secure_files import private_database, private_append, PrivateFileHandler, PrivateRotatingFileHandler

class PrivateRuntime(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        old = os.umask(0o022); self.addCleanup(os.umask, old)
    def mode(self, path):
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
    def test_database(self):
        p = self.root/'db'
        c = private_database(p); c.execute('create table t(x)'); c.execute('insert into t values (1)'); c.commit(); c.close()
        self.mode(p)
        c = private_database(p); self.assertEqual(c.execute('select x from t').fetchone(), (1,)); c.close()
    def test_journal(self):
        p = self.root/'db'; c = private_database(p); self.addCleanup(c.close)
        c.execute('create table t(x)'); c.commit(); c.execute('insert into t values (1)'); self.mode(Path(str(p)+'-journal'))
    def test_lock(self):
        p = self.root/'lock'
        with private_append(p) as a, private_append(p) as b:
            fcntl.flock(a, fcntl.LOCK_EX|fcntl.LOCK_NB)
            with self.assertRaises(BlockingIOError): fcntl.flock(b, fcntl.LOCK_EX|fcntl.LOCK_NB)
            self.mode(p)
    def test_log(self):
        p = self.root/'log'; h = PrivateFileHandler(p); h.close(); self.mode(p)
    def test_rotation(self):
        p = self.root/'log'; h = PrivateRotatingFileHandler(p,maxBytes=20,backupCount=2)
        try:
            for i in range(10): h.emit(logging.LogRecord('x',20,'',0,'abcdefghijk',(),None))
        finally: h.close()
        for name in ('log','log.1','log.2'): self.mode(self.root/name)
    def test_links(self):
        target = self.root/'target'; target.write_text('unchanged')
        for kind in ('symlink','hardlink'):
            p = self.root/kind
            if kind=='symlink': p.symlink_to(target)
            else: os.link(target,p)
            for opener in (private_database,PrivateFileHandler,PrivateRotatingFileHandler):
                with self.assertRaises((OSError,ValueError)): opener(p)
            p.unlink()
        self.assertEqual(target.read_text(),'unchanged')
    def test_rotation_link(self):
        p = self.root/'log'; target = self.root/'target'; target.write_text('unchanged'); (self.root/'log.1').symlink_to(target)
        h = PrivateRotatingFileHandler(p,maxBytes=20,backupCount=2)
        try:
            with self.assertRaises(OSError): h.doRollover()
        finally: h.close()
        self.assertEqual(target.read_text(),'unchanged')
