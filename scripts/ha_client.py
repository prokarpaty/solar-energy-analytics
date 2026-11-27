import os
import json
import math
import yaml
import websocket
from sensor_validation import validate_configuration
from unit_normalization import normalize_rows

from pathlib import Path
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo


TZ = ZoneInfo(
    os.getenv("REPORT_TIMEZONE", "Europe/Kyiv")
)

CONFIG = yaml.safe_load(
    Path("/app/config/sensors.yaml").read_text(
        encoding="utf-8"
    )
)


def get_period(report_type, now=None):
    now = now or datetime.now(TZ)

    today = now.replace(
        hour=0, minute=0, second=0, microsecond=0
    )

    if report_type == "daily":
        end = today
        start = end - timedelta(days=1)

    elif report_type == "weekly":
        end = today - timedelta(days=today.weekday())
        start = end - timedelta(days=7)

    elif report_type == "monthly":
        end = today.replace(day=1)
        start = (end - timedelta(days=1)).replace(day=1)

    elif report_type == "quarterly":
        month = ((today.month - 1) // 3) * 3 + 1
        end = today.replace(month=month, day=1)

        if month == 1:
            start = end.replace(
                year=end.year - 1, month=10
            )
        else:
            start = end.replace(month=month - 3)

    elif report_type == "yearly":
        end = today.replace(month=1, day=1)
        start = end.replace(year=end.year - 1)

    else:
        raise ValueError(f"Unknown report: {report_type}")

    return start, end


class HAClient:

    def __init__(self):
        self.url = os.environ["HA_URL"].rstrip("/")

        self.token = Path(
            os.environ["HA_TOKEN_FILE"]
        ).read_text().strip()

        self.ws = None
        self.request_id = 0

    def __enter__(self):
        url = (
            self.url.replace("https://", "wss://", 1)
                    .replace("http://", "ws://", 1)
            + "/api/websocket"
        )

        self.ws = websocket.create_connection(
            url, timeout=120
        )

        try:
            json.loads(self.ws.recv())

            self.ws.send(json.dumps({
                "type": "auth",
                "access_token": self.token
            }))

            result = json.loads(self.ws.recv())

            if result.get("type") != "auth_ok":
                raise RuntimeError("HA authentication failed")

            return self

        except Exception:
            self.ws.close()
            raise

    def __exit__(self, *args):
        if self.ws:
            self.ws.close()

    def request(self, command, **kwargs):
        self.request_id += 1

        message = {
            "id": self.request_id,
            "type": command,
            **kwargs
        }

        self.ws.send(json.dumps(message))

        while True:
            result = json.loads(self.ws.recv())

            if result.get("id") != self.request_id:
                continue

            if not result.get("success"):
                raise RuntimeError(
                    json.dumps(result.get("error"))
                )

            return result["result"]

    def statistics(self, sensors, start, end, types):
        return self.request(
            "recorder/statistics_during_period",
            start_time=start.isoformat(),
            end_time=end.isoformat(),
            statistic_ids=list(sensors),
            period="hour",
            types=types
        )


def numeric(value):
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
    )


def expected_hours(start, end):
    return set(range(
        int(start.timestamp() * 1000),
        int(end.timestamp() * 1000),
        3600000
    ))


def valid_rows(rows, start, end):
    expected = expected_hours(start, end)

    return {
        row["start"]: row
        for row in rows
        if row.get("start") in expected
        and row.get("end") == row["start"] + 3600000
    }


def summarize_energy(rows, start, end):
    expected_set = expected_hours(start, end)
    expected = len(expected_set)

    records = valid_rows(rows, start, end)

    ordered = [
        records[key] for key in sorted(records)
    ]

    changes = [
        row["change"]
        for row in ordered
        if numeric(row.get("change"))
    ]

    observed = sum(changes) if changes else None

    missing = sorted(
        expected_set - {
            row["start"]
            for row in ordered
            if numeric(row.get("change"))
        }
    )

    coverage = round(
        len(changes) / expected * 100, 2
    )

    result = {
        "total": None,
        "observed_change": round(observed, 3)
            if observed is not None else None,
        "records": len(changes),
        "expected": expected,
        "coverage": coverage,
        "complete": False,
        "status": "unavailable",
        "method": None,
        "missing_hours": len(missing),
        "missing_timestamps": missing,
        "counter_decreases": None
    }

    if not ordered or not changes:
        return result

    result["status"] = "partial"

    first = ordered[0]
    last = ordered[-1]

    boundaries_valid = (
        first["start"] == min(expected_set)
        and last["start"] == max(expected_set)
        and numeric(first.get("sum"))
        and numeric(first.get("change"))
        and numeric(last.get("sum"))
    )

    sums = [
        row["sum"]
        for row in ordered
        if numeric(row.get("sum"))
    ]

    decreases = sum(
        1 for a, b in zip(sums, sums[1:])
        if b < a - 0.000001
    )

    result["counter_decreases"] = decreases

    if not boundaries_valid:
        return result

    baseline = first["sum"] - first["change"]
    cumulative_total = last["sum"] - baseline

    result["counter_start"] = round(baseline, 3)
    result["counter_end"] = round(last["sum"], 3)
    result["counter_delta"] = round(
        cumulative_total, 3
    )

    consistent = (
        decreases == 0
        and len(sums) == len(ordered)
        and cumulative_total >= -0.000001
        and all(change >= -0.000001 for change in changes)
        and math.isclose(
            cumulative_total,
            observed,
            rel_tol=0.000001,
            abs_tol=0.01
        )
    )

    if not consistent:
        return result

    result["total"] = round(cumulative_total, 3)

    if not missing:
        result["complete"] = True
        result["status"] = "complete"
        result["method"] = "hourly_changes"
    else:
        result["status"] = "recovered"
        result["method"] = "cumulative_counter"

    return result


def summarize_measurement(rows, start, end):
    records = valid_rows(rows, start, end)

    expected = len(expected_hours(start, end))

    result = {
        "records": len(records),
        "expected": expected,
        "coverage": round(len(records) / expected * 100, 2)
    }

    for metric in ("min", "mean", "max"):
        values = [
            row[metric]
            for row in records.values()
            if numeric(row.get(metric))
        ]

        if not values:
            result[metric] = None
        elif metric == "min":
            result[metric] = round(min(values), 3)
        elif metric == "max":
            result[metric] = round(max(values), 3)
        else:
            result[metric] = round(
                sum(values) / len(values), 3
            )

        result[f"{metric}_coverage"] = round(
            len(values) / expected * 100, 2
        )

    return result


def extract_sensors(value):
    if isinstance(value, dict):
        for item in value.values():
            yield from extract_sensors(item)

    elif isinstance(value, str) and value.startswith("sensor."):
        yield value


def collect_report(report_type, now=None):
    start, end = get_period(report_type, now=now)

    energy_raw = {}
    measurement_raw = {}

    # Query in seven-day batches to limit API response sizes.
    with HAClient() as ha:

        registry = {m["statistic_id"]: m for m in ha.request("recorder/list_statistic_ids")}
        energy, energy_units, measurement_units, warnings = validate_configuration(CONFIG, registry)
        measurements = sorted(measurement_units)
        for warning in warnings:
            print(f"[WARNING] {warning}")
        cursor = start.astimezone(timezone.utc)
        finish = end.astimezone(timezone.utc)

        while cursor < finish:
            batch_end = min(
                cursor + timedelta(days=7),
                finish
            )

            print(
                f"Collecting {cursor.isoformat()} "
                f"-> {batch_end.isoformat()}"
            )

            result = ha.statistics(
                energy.values(),
                cursor,
                batch_end,
                ["sum", "state", "change"]
            )

            for sensor, rows in result.items():
                energy_raw.setdefault(sensor, []).extend(normalize_rows(rows, energy_units[sensor]))

            result = ha.statistics(
                measurements,
                cursor,
                batch_end,
                ["min", "mean", "max"]
            ) if measurements else {}

            for sensor, rows in result.items():
                measurement_raw.setdefault(
                    sensor, []
                ).extend(normalize_rows(rows, measurement_units[sensor]))

            cursor = batch_end

    return {
        "report_type": report_type,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "timezone": str(TZ),
        "generated_at": datetime.now(TZ).isoformat(),

        "energy": {
            name: summarize_energy(
                energy_raw.get(sensor, []),
                start,
                end
            )
            for name, sensor in energy.items()
        },

        "measurements": {
            sensor: summarize_measurement(
                measurement_raw.get(sensor, []),
                start,
                end
            )
            for sensor in measurements
        },

        **({"configuration_warnings": warnings} if warnings else {}),
        "raw": {
            "energy": energy_raw,
            "measurements": measurement_raw
        }
    }
