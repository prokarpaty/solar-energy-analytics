"""Report directory ownership and path protection."""

import os
import stat
from pathlib import Path


def secure_report_directory(directory):
    directory = Path(directory)

    if not directory.is_absolute() or ".." in directory.parts:
        raise ValueError("Invalid report directory")

    current = Path(directory.anchor)

    for part in directory.parts[1:]:
        current = current / part

        try:
            info = current.lstat()
        except FileNotFoundError:
            current.mkdir(mode=0o700)
            info = current.lstat()

        if not stat.S_ISDIR(info.st_mode):
            raise ValueError("Unsafe report directory")

    info = directory.lstat()

    if (
        info.st_uid != os.geteuid()
        or stat.S_IMODE(info.st_mode) & 0o077
    ):
        raise ValueError("Report directory must be private")

    return directory
