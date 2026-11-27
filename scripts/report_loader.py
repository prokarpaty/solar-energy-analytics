"""Shared secure report loading entry point."""

from collections.abc import Mapping

from report_validation import (
    load_report,
    ReportValidationError
)

from report_reconciliation import reconcile_report


def load_validated_report(
    source,
    *,
    energy_mapping=None,
    with_identity=False
):
    """
    Load and reconcile a report before application processing.

    An explicit mapping can be supplied for isolated tests.
    Production callers use the trusted local configuration.
    """

    if energy_mapping is None:

        from ha_client import CONFIG

        if not isinstance(CONFIG, Mapping):

            raise ReportValidationError(
                "Invalid report configuration"
            )

        energy_mapping = CONFIG.get("energy")

    if not isinstance(energy_mapping, Mapping):

        raise ReportValidationError(
            "Invalid energy sensor configuration"
        )

    if with_identity:
        data, identity = load_report(
            source,
            with_identity=True
        )
    else:
        data = load_report(source)

    reconcile_report(
        data,
        energy_mapping
    )

    if with_identity:
        return data, identity

    return data
