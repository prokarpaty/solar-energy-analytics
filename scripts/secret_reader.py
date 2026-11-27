"""Secure runtime credential loading."""

import os
import stat


MAX_SECRET_BYTES = 8192


class SecretError(RuntimeError):
    """Credential validation failure without sensitive details."""


def read_secret(path):
    """Read a private, regular, single-link credential file."""

    fd = None

    try:
        flags = (
            os.O_RDONLY
            | os.O_NOFOLLOW
            | os.O_NONBLOCK
            | os.O_CLOEXEC
        )

        fd = os.open(path, flags)

        info = os.fstat(fd)

        if not stat.S_ISREG(info.st_mode):
            raise SecretError("Credential file is not a regular file")

        if info.st_uid != os.geteuid():
            raise SecretError("Invalid credential file ownership")

        if stat.S_IMODE(info.st_mode) != 0o600:
            raise SecretError("Invalid credential file permissions")

        if info.st_nlink != 1:
            raise SecretError("Invalid credential file link count")

        if not 0 < info.st_size <= MAX_SECRET_BYTES:
            raise SecretError("Invalid credential file size")

        with os.fdopen(fd, "rb") as stream:
            fd = None
            raw = stream.read(MAX_SECRET_BYTES + 1)

        if len(raw) > MAX_SECRET_BYTES:
            raise SecretError("Credential exceeds size limit")

        value = raw.decode("utf-8").rstrip("\r\n")

        if not value or not value.strip():
            raise SecretError("Credential is empty")

        if any(
            ord(character) < 32 or ord(character) == 127
            for character in value
        ):
            raise SecretError("Invalid credential characters")

        return value

    except SecretError:
        raise

    except (OSError, ValueError, TypeError):
        raise SecretError(
            "Unable to read credential securely"
        ) from None

    finally:
        if fd is not None:
            os.close(fd)
