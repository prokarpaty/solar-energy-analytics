"""Private file creation in application-owned directories."""
import os
import stat
import tempfile
from pathlib import Path
from contextlib import contextmanager


@contextmanager
def atomic_private(path, *, exclusive=False):
    """Publish a complete 0600 file; exclusive mode never replaces a target."""
    path = Path(path)
    fd, name = tempfile.mkstemp(prefix='.' + path.name + '.', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            os.fchmod(stream.fileno(), 0o600)
            yield stream
            stream.flush()
            os.fsync(stream.fileno())
        if exclusive:
            os.link(name, path)
        else:
            os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def write_private(path, data, *, exclusive=False):
    with atomic_private(path, exclusive=exclusive) as stream:
        stream.write(data)


def private_append(path):
    """Open an owned regular file without following a final symlink."""
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or info.st_nlink != 1:
            raise ValueError('Expected an owned regular file')
        os.fchmod(fd, 0o600)
        return os.fdopen(fd, 'a', encoding='utf-8')
    except BaseException:
        os.close(fd)
        raise


import logging
from logging.handlers import RotatingFileHandler
import sqlite3


class PrivateFileHandler(logging.FileHandler):
    def _open(self):
        return private_append(self.baseFilename)


class PrivateRotatingFileHandler(RotatingFileHandler):
    def _open(self):
        return private_append(self.baseFilename)

    def doRollover(self):
        # Validate existing rotation targets before renaming any files.
        for i in range(1, self.backupCount + 1):
            path = Path(self.rotation_filename(f'{self.baseFilename}.{i}'))
            if os.path.lexists(path):
                with private_append(path):
                    pass
        super().doRollover()


def private_database(path, **kwargs):
    # SQLite reopens by pathname; requires an application-owned private directory.
    with private_append(path):
        pass
    for suffix in ('-journal', '-wal', '-shm'):
        sidecar = str(path) + suffix
        if os.path.lexists(sidecar):
            with private_append(sidecar):
                pass
    return sqlite3.connect(path, **kwargs)
