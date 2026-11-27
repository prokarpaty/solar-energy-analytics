"""Validation of email addresses and MIME header values."""

import re
import unicodedata

from email.headerregistry import Address

MAX_MAILBOX_LENGTH = 254
MAX_RECIPIENTS = 50
MAX_SUBJECT_LENGTH = 512

LOCAL_PART = re.compile(
    r"[A-Za-z0-9!#$%&'*+/=?^_`{|}~-]+"
    r"(?:\.[A-Za-z0-9!#$%&'*+/=?^_`{|}~-]+)*"
)

DOMAIN_LABEL = re.compile(
    r"[A-Za-z0-9]"
    r"(?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
)


def reject_controls(value):
    """Reject control and invisible formatting characters."""

    if not isinstance(value, str):
        raise ValueError("Invalid email text")

    if any(
        unicodedata.category(char) in (
            "Cc", "Cf", "Cs", "Zl", "Zp"
        )
        for char in value
    ):
        raise ValueError("Prohibited email characters")

    return value


def validate_mailbox(value):
    """Accept one conventional ASCII email mailbox."""

    value = reject_controls(value).strip()

    if (
        not value
        or not value.isascii()
        or len(value) > MAX_MAILBOX_LENGTH
        or value.count("@") != 1
    ):
        raise ValueError("Invalid email mailbox")

    local, domain = value.split("@", 1)

    if (
        not local
        or len(local) > 64
        or not LOCAL_PART.fullmatch(local)
    ):
        raise ValueError("Invalid mailbox local part")

    labels = domain.split(".")

    if (
        len(labels) < 2
        or len(domain) > 253
        or not all(
            DOMAIN_LABEL.fullmatch(label)
            for label in labels
        )
    ):
        raise ValueError("Invalid mailbox domain")

    return Address(
        username=local,
        domain=domain.lower()
    )


def validate_recipients(value):
    """Validate a comma-separated recipient list."""

    value = reject_controls(value)

    if len(value) > MAX_RECIPIENTS * (
        MAX_MAILBOX_LENGTH + 2
    ):
        raise ValueError("Recipient list too large")

    parts = value.split(",")

    if not 1 <= len(parts) <= MAX_RECIPIENTS:
        raise ValueError("Invalid recipient count")

    recipients = []
    seen = set()

    for part in parts:

        address = validate_mailbox(part)

        key = address.addr_spec

        if key in seen:
            raise ValueError("Duplicate email recipient")

        seen.add(key)
        recipients.append(address)

    return tuple(recipients)


def validate_subject(value):
    """Validate a single-line Unicode subject."""

    value = reject_controls(value)

    if (
        not value.strip()
        or len(value) > MAX_SUBJECT_LENGTH
    ):
        raise ValueError("Invalid email subject")

    return value


MAX_ATTACHMENT_FILENAME = 200
MAX_RAW_ATTACHMENT_BYTES = 17_000_000


def validate_attachment_filename(value):
    """Validate a report attachment filename."""

    value = reject_controls(value)

    if (
        not value
        or len(value) > MAX_ATTACHMENT_FILENAME
        or value != value.strip()
        or value.startswith(".")
        or "/" in value
        or chr(92) in value
        or ":" in value
        or not re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9._-]*",
            value
        )
        or not value.endswith((".pdf", ".html"))
    ):
        raise ValueError("Invalid attachment filename")

    return value


def validate_attachment_size(sizes):
    """Enforce a preliminary combined attachment size limit."""

    sizes = tuple(sizes)

    if (
        not sizes
        or any(
            type(size) is not int or size <= 0
            for size in sizes
        )
        or sum(sizes) > MAX_RAW_ATTACHMENT_BYTES
    ):
        raise ValueError("Invalid attachment size")

    return sum(sizes)
