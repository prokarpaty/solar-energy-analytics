"""Reconcile validated report summaries with raw statistics."""

import math

from datetime import datetime
from collections.abc import Mapping

from report_validation import ReportValidationError

from ha_client import (
    summarize_energy,
    summarize_measurement
)


def fail(message):

    raise ReportValidationError(message)


def compare_summary(stored, calculated):

    if set(stored) != set(calculated):

        fail("Statistical summary fields mismatch")

    for key, expected in calculated.items():

        actual = stored[key]

        if expected is None:

            if actual is not None:
                fail("Statistical summary mismatch")

        elif type(expected) is bool:

            if type(actual) is not bool or actual != expected:
                fail("Statistical summary mismatch")

        elif type(expected) is int:

            if type(actual) is not int or actual != expected:
                fail("Statistical summary mismatch")

        elif type(expected) is float:

            if type(actual) not in (int, float):
                fail("Statistical summary mismatch")

            if not math.isclose(
                actual,
                expected,
                rel_tol=0.0,
                abs_tol=0.000001
            ):
                fail("Statistical summary mismatch")

        else:

            if actual != expected:
                fail("Statistical summary mismatch")


def reconcile_report(data, energy_mapping):

    """
    Verify a structurally validated dataset against its
    raw hourly records and trusted energy sensor mapping.
    """

    if not isinstance(energy_mapping, Mapping):

        fail("Invalid energy sensor mapping")

    start = datetime.fromisoformat(data["start"])
    end = datetime.fromisoformat(data["end"])

    raw_energy = data["raw"]["energy"]
    raw_measurements = data["raw"]["measurements"]

    selected_mapping = {}

    for role in data["energy"]:

        sensor = energy_mapping.get(role)

        if not isinstance(sensor, str):

            fail("Missing energy sensor mapping")

        if not sensor.startswith("sensor."):

            fail("Invalid energy sensor mapping")

        selected_mapping[role] = sensor

    if len(set(selected_mapping.values())) != len(selected_mapping):

        fail("Duplicate energy sensor mapping")

    if not set(raw_energy).issubset(
        set(selected_mapping.values())
    ):

        fail("Unexpected raw energy sensor")

    if not set(raw_measurements).issubset(
        set(data["measurements"])
    ):

        fail("Unexpected raw measurement sensor")

    energy_count = 0
    measurement_count = 0

    for role, stored in data["energy"].items():

        sensor = selected_mapping[role]

        calculated = summarize_energy(
            raw_energy.get(sensor, []),
            start,
            end
        )

        compare_summary(stored, calculated)

        energy_count += 1

    for sensor, stored in data["measurements"].items():

        calculated = summarize_measurement(
            raw_measurements.get(sensor, []),
            start,
            end
        )

        compare_summary(stored, calculated)

        measurement_count += 1

    return {
        "energy": energy_count,
        "measurements": measurement_count,
        "total": energy_count + measurement_count
    }
