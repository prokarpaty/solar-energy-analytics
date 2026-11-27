"""Versioned integrity manifests for rendered report bundles."""

import json
import re

from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path

from attachment_security import (
    AttachmentError,
    read_attachment
)

from email_security import MAX_RAW_ATTACHMENT_BYTES
from report_validation import MAX_JSON_BYTES
from secure_files import write_private


SCHEMA_VERSION = 1
MAX_MANIFEST_BYTES = 16 * 1024

SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")

REPORT_TYPES = frozenset({
    "daily",
    "weekly",
    "monthly",
    "quarterly",
    "yearly"
})

LANGUAGES = frozenset({"en", "uk"})

MANIFEST_FIELDS = frozenset({
    "schema_version",
    "report_type",
    "period_start",
    "period_end",
    "language",
    "generated_at",
    "dataset",
    "attachments"
})


class IntegrityError(RuntimeError):
    """Sanitized report integrity failure."""


def require(condition):
    if not condition:
        raise IntegrityError(
            "Report integrity verification failed"
        )


def manifest_path(source):
    source = Path(source)

    require(source.suffix == ".json")
    require(not source.name.endswith(".manifest.json"))

    return source.with_suffix(".manifest.json")


def byte_identity(payload):
    require(isinstance(payload, bytes))
    require(len(payload) > 0)

    return {
        "sha256": sha256(payload).hexdigest(),
        "size": len(payload)
    }


def validate_identity(identity, maximum):
    require(type(identity) is dict)

    require(
        set(identity) == {"sha256", "size"}
    )

    digest = identity["sha256"]
    size = identity["size"]

    require(type(digest) is str)

    require(
        SHA256_PATTERN.fullmatch(digest) is not None
    )

    require(type(size) is int)
    require(0 < size <= maximum)

    return {
        "sha256": digest,
        "size": size
    }


def validate_timestamp(value):
    require(type(value) is str)
    require(0 < len(value) <= 64)

    try:
        result = datetime.fromisoformat(value)

        require(result.tzinfo is not None)
        require(result.utcoffset() is not None)

        return result

    except (ValueError, OverflowError):
        raise IntegrityError(
            "Invalid manifest timestamp"
        ) from None


def validate_manifest(manifest):
    require(type(manifest) is dict)
    require(set(manifest) == MANIFEST_FIELDS)

    version = manifest["schema_version"]

    require(type(version) is int)
    require(version == SCHEMA_VERSION)

    report_type = manifest["report_type"]
    language = manifest["language"]

    require(type(report_type) is str)
    require(report_type in REPORT_TYPES)

    require(type(language) is str)
    require(language in LANGUAGES)

    start = validate_timestamp(
        manifest["period_start"]
    )

    end = validate_timestamp(
        manifest["period_end"]
    )

    generated = validate_timestamp(
        manifest["generated_at"]
    )

    require(start < end)
    require(generated >= end)

    validate_identity(
        manifest["dataset"],
        MAX_JSON_BYTES
    )

    attachments = manifest["attachments"]

    require(type(attachments) is dict)
    require(set(attachments) == {"pdf", "html"})

    pdf = validate_identity(
        attachments["pdf"],
        MAX_RAW_ATTACHMENT_BYTES
    )

    html = validate_identity(
        attachments["html"],
        MAX_RAW_ATTACHMENT_BYTES
    )

    require(
        pdf["size"] + html["size"]
        <= MAX_RAW_ATTACHMENT_BYTES
    )

    return manifest


def create_manifest(
    data,
    dataset_identity,
    language,
    *,
    pdf_bytes,
    html_bytes
):
    """Create a manifest from validated data and exact output bytes."""

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "report_type": data["report_type"],
        "period_start": data["start"],
        "period_end": data["end"],
        "language": language,
        "generated_at": datetime.now(
            timezone.utc
        ).isoformat(),
        "dataset": validate_identity(
            dataset_identity,
            MAX_JSON_BYTES
        ),
        "attachments": {
            "pdf": byte_identity(pdf_bytes),
            "html": byte_identity(html_bytes)
        }
    }

    return validate_manifest(manifest)


def write_manifest(source, manifest):
    """Atomically publish a private integrity manifest."""

    validate_manifest(manifest)

    payload = (
        json.dumps(
            manifest,
            ensure_ascii=True,
            allow_nan=False,
            sort_keys=True,
            indent=2
        ) + "\n"
    ).encode("utf-8")

    require(
        0 < len(payload) <= MAX_MANIFEST_BYTES
    )

    path = manifest_path(source)

    write_private(path, payload)

    return path


def reject_duplicate_keys(pairs):
    result = {}

    for key, value in pairs:
        require(key not in result)
        result[key] = value

    return result


def reject_constant(value):
    raise IntegrityError(
        "Invalid manifest JSON constant"
    )


def load_manifest(source):
    """Read and strictly validate a bounded private manifest."""

    try:
        payload = read_attachment(
            manifest_path(source),
            maximum=MAX_MANIFEST_BYTES
        )

        manifest = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=reject_duplicate_keys,
            parse_constant=reject_constant
        )

        return validate_manifest(manifest)

    except IntegrityError:
        raise

    except (
        AttachmentError,
        OSError,
        UnicodeError,
        ValueError,
        TypeError,
        OverflowError,
        RecursionError
    ):
        raise IntegrityError(
            "Unable to load report integrity manifest"
        ) from None


def verify_manifest(
    manifest,
    data,
    dataset_identity,
    language,
    *,
    pdf_bytes,
    html_bytes
):
    """Verify exact bytes without reopening the dataset or attachments."""

    validate_manifest(manifest)

    require(
        manifest["report_type"] == data["report_type"]
    )

    require(
        manifest["period_start"] == data["start"]
    )

    require(
        manifest["period_end"] == data["end"]
    )

    require(
        manifest["language"] == language
    )

    require(
        manifest["dataset"] == validate_identity(
            dataset_identity,
            MAX_JSON_BYTES
        )
    )

    require(
        manifest["attachments"]["pdf"]
        == byte_identity(pdf_bytes)
    )

    require(
        manifest["attachments"]["html"]
        == byte_identity(html_bytes)
    )

    return True
