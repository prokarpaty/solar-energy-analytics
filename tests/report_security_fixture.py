"""Deterministic synthetic report fixture for security tests."""

from datetime import datetime, timedelta, timezone

from ha_client import (
    summarize_energy,
    summarize_measurement
)


ENERGY_MAPPING = {
    role: f"sensor.test_energy_{role}"
    for role in (
        "production",
        "consumption",
        "grid_import",
        "grid_export",
        "battery_charge",
        "battery_discharge",
        "inverter_losses"
    )
}


def create_reference():

    start = datetime(
        2026, 1, 15, tzinfo=timezone.utc
    )

    end = start + timedelta(days=1)

    raw_energy = {}
    raw_measurements = {}

    for index, sensor in enumerate(
        ENERGY_MAPPING.values()
    ):

        rows = []

        counter = 1000.0 + index * 100

        change = (index + 1) * 0.125

        for hour in range(24):

            timestamp = int(
                (
                    start + timedelta(hours=hour)
                ).timestamp() * 1000
            )

            counter += change

            rows.append({
                "start": timestamp,
                "end": timestamp + 3600000,
                "state": counter,
                "sum": counter,
                "change": change
            })

        raw_energy[sensor] = rows

    for index in range(59):

        sensor = f"sensor.test_measurement_{index:02d}"

        rows = []

        for hour in range(24):

            timestamp = int(
                (
                    start + timedelta(hours=hour)
                ).timestamp() * 1000
            )

            mean = 20.0 + index + hour * 0.125

            rows.append({
                "start": timestamp,
                "end": timestamp + 3600000,
                "min": mean - 1.0,
                "mean": mean,
                "max": mean + 1.0
            })

        raw_measurements[sensor] = rows

    return {
        "report_type": "daily",
        "start": start.isoformat(),
        "end": end.isoformat(),
        "timezone": "UTC",
        "generated_at": (
            end + timedelta(minutes=15)
        ).isoformat(),

        "energy": {
            role: summarize_energy(
                raw_energy[sensor],
                start,
                end
            )
            for role, sensor in ENERGY_MAPPING.items()
        },

        "measurements": {
            sensor: summarize_measurement(
                rows,
                start,
                end
            )
            for sensor, rows in raw_measurements.items()
        },

        "raw": {
            "energy": raw_energy,
            "measurements": raw_measurements
        }
    }
