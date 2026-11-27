"""Integrity manifests for synthetic report test bundles."""

from pathlib import Path

from report_loader import load_validated_report
from report_integrity import (
    create_manifest,
    write_manifest
)

from report_security_fixture import ENERGY_MAPPING


def create_fixture_manifest(source, language="en"):
    source = Path(source)

    data, identity = load_validated_report(
        source,
        energy_mapping=ENERGY_MAPPING,
        with_identity=True
    )

    manifest = create_manifest(
        data,
        identity,
        language,
        pdf_bytes=source.with_suffix(".pdf").read_bytes(),
        html_bytes=source.with_suffix(".html").read_bytes()
    )

    return write_manifest(source, manifest)
