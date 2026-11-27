"""Bounded, descriptor-based report attachment reading."""

import os
import stat

from email_security import MAX_RAW_ATTACHMENT_BYTES


class AttachmentError(RuntimeError):
    """Sanitized attachment validation failure."""


def validate_file(info, maximum):

    if not stat.S_ISREG(info.st_mode):
        raise AttachmentError(
            "Attachment is not a regular file"
        )

    if info.st_uid != os.geteuid():
        raise AttachmentError(
            "Invalid attachment ownership"
        )

    if stat.S_IMODE(info.st_mode) != 0o600:
        raise AttachmentError(
            "Invalid attachment permissions"
        )

    if info.st_nlink != 1:
        raise AttachmentError(
            "Invalid attachment link count"
        )

    if not 0 < info.st_size <= maximum:
        raise AttachmentError(
            "Invalid attachment size"
        )


def fingerprint(info):
    """Metadata used to detect observable file changes."""

    return (
        info.st_dev,
        info.st_ino,
        info.st_mode,
        info.st_uid,
        info.st_gid,
        info.st_nlink,
        info.st_size,
        info.st_mtime_ns,
        info.st_ctime_ns
    )


def read_attachment(
    path,
    *,
    maximum=MAX_RAW_ATTACHMENT_BYTES
):
    """Read an owned private attachment within a fixed budget."""

    if (
        type(maximum) is not int
        or not 0 < maximum <= MAX_RAW_ATTACHMENT_BYTES
    ):
        raise AttachmentError(
            "Invalid attachment byte budget"
        )

    fd = None

    try:
        flags = (
            os.O_RDONLY
            | os.O_NOFOLLOW
            | os.O_NONBLOCK
            | os.O_CLOEXEC
        )

        fd = os.open(path, flags)

        before = os.fstat(fd)

        validate_file(before, maximum)

        with os.fdopen(fd, "rb") as stream:

            fd = None

            # Never read more than the validated size plus
            # one byte, even if the file grows concurrently.
            payload = stream.read(before.st_size + 1)

            after = os.fstat(stream.fileno())

            validate_file(after, maximum)

            if len(payload) != before.st_size:
                raise AttachmentError(
                    "Attachment size changed during reading"
                )

            if fingerprint(before) != fingerprint(after):
                raise AttachmentError(
                    "Attachment changed during reading"
                )

            current = os.stat(
                path,
                follow_symlinks=False
            )

            if fingerprint(after) != fingerprint(current):
                raise AttachmentError(
                    "Attachment replaced during reading"
                )

        return payload

    except AttachmentError:
        raise

    except (OSError, ValueError, TypeError):
        raise AttachmentError(
            "Unable to read attachment securely"
        ) from None

    finally:
        if fd is not None:
            os.close(fd)
