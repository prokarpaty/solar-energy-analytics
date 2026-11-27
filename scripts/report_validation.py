"""Centralized security validation for report datasets."""

import json
import os
import stat
from pathlib import Path
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo


MAX_JSON_BYTES = 160 * 1024 * 1024
MAX_HOURS = 8784
MAX_MEASUREMENT_SENSORS = 256
MAX_TOTAL_ROWS = 1_000_000
MAX_WARNINGS = 100
MAX_WARNING_LENGTH = 1024
MAX_SENSOR_LENGTH = 255

HOUR_MS = 3_600_000

REPORT_TYPES = frozenset({
    "daily",
    "weekly",
    "monthly",
    "quarterly",
    "yearly"
})

ENERGY_KEYS = frozenset({
    "production",
    "consumption",
    "grid_import",
    "grid_export",
    "battery_charge",
    "battery_discharge",
    "inverter_losses"
})

ROOT_REQUIRED = frozenset({
    "report_type",
    "start",
    "end",
    "timezone",
    "generated_at",
    "energy",
    "measurements",
    "raw"
})

ROOT_OPTIONAL = frozenset({
    "configuration_warnings"
})


class ReportValidationError(ValueError):
    """Invalid or unsafe report dataset."""


def require(condition, message):
    if not condition:
        raise ReportValidationError(message)


def reject_duplicate_keys(pairs):
    require(
        len(pairs) <= MAX_OBJECT_MEMBERS,
        "Too many JSON object members"
    )
    result = {}

    for key, value in pairs:
        require(
            key not in result,
            "Duplicate JSON object key"
        )
        result[key] = value

    return result


def reject_constant(value):
    raise ReportValidationError(
        "Non-finite JSON constant"
    )


def parse_datetime(value):
    require(
        isinstance(value, str)
        and 1 <= len(value) <= 64,
        "Invalid datetime field"
    )

    try:
        result = datetime.fromisoformat(value)
        require(
            result.utcoffset() is not None,
            "Datetime must be timezone-aware"
        )
        return result
    except (ValueError, OverflowError):
        raise ReportValidationError(
            "Invalid timezone-aware datetime"
        ) from None


def validate_metadata(data):
    report_type = data["report_type"]

    require(
        isinstance(report_type, str)
        and report_type in REPORT_TYPES,
        "Invalid report type"
    )

    timezone_name = data["timezone"]

    require(
        isinstance(timezone_name, str)
        and 1 <= len(timezone_name) <= 128,
        "Invalid report timezone"
    )

    try:
        tz = ZoneInfo(timezone_name)
    except (KeyError, ValueError, OSError):
        raise ReportValidationError(
            "Invalid report timezone"
        ) from None

    start = parse_datetime(data["start"])
    end = parse_datetime(data["end"])
    generated = parse_datetime(data["generated_at"])

    for value in (start, end):
        local = value.astimezone(tz)

        require(
            value.utcoffset() == local.utcoffset(),
            "Timezone offset mismatch"
        )

        require(
            not any((
                local.hour,
                local.minute,
                local.second,
                local.microsecond
            )),
            "Report boundaries must be local midnight"
        )

    first = int(start.timestamp() * 1000)
    last = int(end.timestamp() * 1000)

    require(
        first % HOUR_MS == 0
        and last % HOUR_MS == 0,
        "Report boundaries must be UTC-hour aligned"
    )

    hours = (last - first) // HOUR_MS

    require(
        1 <= hours <= MAX_HOURS,
        "Invalid report duration"
    )

    start_date = start.astimezone(tz).date()
    end_date = end.astimezone(tz).date()

    days = (end_date - start_date).days

    if report_type == "daily":
        valid = days == 1

    elif report_type == "weekly":
        valid = (
            days == 7
            and start_date.weekday() == 0
            and end_date.weekday() == 0
        )

    elif report_type == "monthly":
        valid = (
            start_date.day == 1
            and end_date.day == 1
            and (
                end_date.year * 12 + end_date.month
                - start_date.year * 12 - start_date.month
            ) == 1
        )

    elif report_type == "quarterly":
        valid = (
            start_date.day == 1
            and end_date.day == 1
            and start_date.month in (1, 4, 7, 10)
            and end_date.month in (1, 4, 7, 10)
            and (
                end_date.year * 12 + end_date.month
                - start_date.year * 12 - start_date.month
            ) == 3
        )

    else:
        valid = (
            start_date.month == 1
            and start_date.day == 1
            and end_date.month == 1
            and end_date.day == 1
            and end_date.year == start_date.year + 1
        )

    require(valid, "Invalid calendar report period")

    require(
        generated.timestamp() >= end.timestamp(),
        "Report generated before period completion"
    )

    return first, last, hours


def validate_structure(data):
    require(
        isinstance(data, dict),
        "Report root must be an object"
    )

    keys = set(data)

    require(
        ROOT_REQUIRED <= keys,
        "Missing required report fields"
    )

    require(
        keys <= ROOT_REQUIRED | ROOT_OPTIONAL,
        "Unknown report fields"
    )

    first, last, hours = validate_metadata(data)

    energy = data["energy"]
    measurements = data["measurements"]
    raw = data["raw"]

    require(
        isinstance(energy, dict),
        "Invalid energy collection"
    )

    require(
        set(energy) <= ENERGY_KEYS,
        "Unknown energy category"
    )

    require(
        {"production", "consumption"} <= set(energy),
        "Missing mandatory energy categories"
    )

    require(
        isinstance(measurements, dict)
        and len(measurements) <= MAX_MEASUREMENT_SENSORS,
        "Invalid measurement collection"
    )

    require(
        isinstance(raw, dict)
        and set(raw) == {"energy", "measurements"},
        "Invalid raw statistics structure"
    )

    for collection in (energy, measurements):
        require(
            all(
                isinstance(item, dict)
                for item in collection.values()
            ),
            "Invalid statistics summary"
        )

    warnings = data.get("configuration_warnings", [])

    require(
        isinstance(warnings, list)
        and len(warnings) <= MAX_WARNINGS,
        "Invalid configuration warnings"
    )

    for warning in warnings:
        require(
            isinstance(warning, str)
            and len(warning) <= MAX_WARNING_LENGTH,
            "Invalid configuration warning"
        )

    total_rows = 0

    for category in ("energy", "measurements"):
        collection = raw[category]

        limit = (
            len(ENERGY_KEYS)
            if category == "energy"
            else MAX_MEASUREMENT_SENSORS
        )

        require(
            isinstance(collection, dict)
            and len(collection) <= limit,
            "Invalid raw sensor collection"
        )

        for sensor, rows in collection.items():
            require(
                isinstance(sensor, str)
                and sensor.startswith("sensor.")
                and len(sensor) <= MAX_SENSOR_LENGTH,
                "Invalid sensor identifier"
            )

            require(
                isinstance(rows, list)
                and len(rows) <= hours,
                "Invalid hourly record collection"
            )

            total_rows += len(rows)

            require(
                total_rows <= MAX_TOTAL_ROWS,
                "Too many historical records"
            )

    return data


from hashlib import sha256


def load_report(source, *, with_identity=False):
    """Load a bounded, strictly decoded report dataset."""

    source = Path(source)

    try:
        flags = (
            os.O_RDONLY
            | os.O_NOFOLLOW
            | os.O_NONBLOCK
            | os.O_CLOEXEC
        )

        fd = os.open(source, flags)

        with os.fdopen(fd, "rb") as stream:
            info = os.fstat(stream.fileno())

            require(
                stat.S_ISREG(info.st_mode),
                "Report source must be a regular file"
            )

            require(
                0 < info.st_size <= MAX_JSON_BYTES,
                "Invalid report file size"
            )

            payload = stream.read(MAX_JSON_BYTES + 1)

        require(
            0 < len(payload) <= MAX_JSON_BYTES,
            "Report file exceeds size limit"
        )

        validate_json_depth(payload)

        data = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=reject_duplicate_keys,
            parse_constant=reject_constant,
            parse_int=parse_json_integer,
            parse_float=parse_json_float
        )

        validate_structure(data)

        validated = validate_statistics(data)

        if with_identity:
            identity = {
                "sha256": sha256(payload).hexdigest(),
                "size": len(payload)
            }

            return validated, identity

        return validated

    except ReportValidationError:
        raise

    except (
        OSError,
        UnicodeError,
        ValueError,
        OverflowError,
        RecursionError
    ):
        raise ReportValidationError(
            "Unable to load report dataset"
        ) from None


# Detailed statistical validation.

import math
import re


MAX_NUMERIC_MAGNITUDE = 1_000_000_000_000_000

SENSOR_PATTERN = re.compile(
    r"sensor\.[a-z0-9_]+"
)

ENERGY_REQUIRED = frozenset({
    "total",
    "observed_change",
    "records",
    "expected",
    "coverage",
    "complete",
    "status",
    "method",
    "missing_hours",
    "missing_timestamps",
    "counter_decreases"
})

ENERGY_OPTIONAL = frozenset({
    "counter_start",
    "counter_end",
    "counter_delta"
})

MEASUREMENT_FIELDS = frozenset({
    "records",
    "expected",
    "coverage",
    "min",
    "mean",
    "max",
    "min_coverage",
    "mean_coverage",
    "max_coverage"
})

RAW_FIELDS = {
    "energy": frozenset({
        "start", "end", "state", "sum", "change"
    }),
    "measurements": frozenset({
        "start", "end", "min", "mean", "max"
    })
}


def validate_number(value, nullable=False):

    if value is None and nullable:
        return

    require(
        type(value) in (int, float),
        "Invalid numeric value type"
    )

    require(
        abs(value) <= MAX_NUMERIC_MAGNITUDE
        and math.isfinite(value),
        "Invalid numeric magnitude"
    )


def validate_integer(value, minimum, maximum):

    require(
        type(value) is int
        and minimum <= value <= maximum,
        "Invalid integer value"
    )


def validate_coverage(value):

    validate_number(value)

    require(
        0 <= value <= 100,
        "Invalid coverage percentage"
    )


def validate_sensor(sensor):

    require(
        isinstance(sensor, str)
        and len(sensor) <= MAX_SENSOR_LENGTH
        and SENSOR_PATTERN.fullmatch(sensor) is not None,
        "Invalid sensor identifier"
    )


def validate_hour(timestamp, first, last):

    require(
        type(timestamp) is int
        and first <= timestamp < last
        and timestamp % HOUR_MS == 0,
        "Invalid hourly timestamp"
    )


def validate_summary_counts(item, hours):

    validate_integer(item["expected"], hours, hours)
    validate_integer(item["records"], 0, hours)
    validate_coverage(item["coverage"])

    expected_coverage = round(
        item["records"] / hours * 100,
        2
    )

    require(
        math.isclose(
            item["coverage"],
            expected_coverage,
            rel_tol=0,
            abs_tol=0.000001
        ),
        "Inconsistent statistics coverage"
    )


def validate_energy_summary(item, first, last, hours):

    keys = set(item)

    require(
        ENERGY_REQUIRED <= keys
        and keys <= ENERGY_REQUIRED | ENERGY_OPTIONAL,
        "Invalid energy summary fields"
    )

    validate_summary_counts(item, hours)

    for field in ("total", "observed_change"):
        validate_number(item[field], nullable=True)

    for field in ENERGY_OPTIONAL:
        if field in item:
            validate_number(item[field])

    present = keys & ENERGY_OPTIONAL

    require(
        not present or present == ENERGY_OPTIONAL,
        "Incomplete counter boundary fields"
    )

    require(
        type(item["complete"]) is bool,
        "Invalid completeness flag"
    )

    validate_integer(item["missing_hours"], 0, hours)

    require(
        item["missing_hours"] == hours - item["records"],
        "Inconsistent missing hour count"
    )

    missing = item["missing_timestamps"]

    require(
        isinstance(missing, list)
        and len(missing) == item["missing_hours"],
        "Invalid missing timestamp collection"
    )

    seen = set()

    for timestamp in missing:

        validate_hour(timestamp, first, last)

        require(
            timestamp not in seen,
            "Duplicate missing timestamp"
        )

        seen.add(timestamp)

    decreases = item["counter_decreases"]

    if decreases is not None:
        validate_integer(decreases, 0, hours)

    status = item["status"]
    method = item["method"]

    require(
        isinstance(status, str)
        and status in (
            "complete",
            "recovered",
            "partial",
            "unavailable"
        ),
        "Invalid energy status"
    )

    require(
        item["complete"] == (status == "complete"),
        "Inconsistent completeness status"
    )

    if status in ("complete", "recovered"):

        require(
            item["total"] is not None
            and item["total"] >= -0.000001
            and item["observed_change"] is not None
            and present == ENERGY_OPTIONAL
            and decreases == 0,
            "Invalid completed energy summary"
        )

        require(
            math.isclose(
                item["total"],
                item["counter_delta"],
                rel_tol=0.000001,
                abs_tol=0.01
            ),
            "Inconsistent energy counter total"
        )

        require(
            math.isclose(
                item["total"],
                item["observed_change"],
                rel_tol=0.000001,
                abs_tol=0.01
            ),
            "Inconsistent observed energy total"
        )

        require(
            math.isclose(
                item["counter_end"] - item["counter_start"],
                item["counter_delta"],
                rel_tol=0.000001,
                abs_tol=0.01
            ),
            "Inconsistent counter boundaries"
        )

        if status == "complete":

            require(
                method == "hourly_changes"
                and item["records"] == hours,
                "Invalid complete energy status"
            )

        else:

            require(
                method == "cumulative_counter"
                and 0 < item["records"] < hours,
                "Invalid recovered energy status"
            )

    else:

        require(
            item["total"] is None
            and method is None,
            "Unexpected total for incomplete energy"
        )

        if status == "unavailable":

            require(
                item["records"] == 0
                and item["observed_change"] is None
                and decreases is None
                and not present,
                "Invalid unavailable energy status"
            )

        else:

            require(
                item["records"] > 0
                and item["observed_change"] is not None
                and decreases is not None,
                "Invalid partial energy status"
            )


def validate_measurement_summary(item, hours):

    require(
        set(item) == MEASUREMENT_FIELDS,
        "Invalid measurement summary fields"
    )

    validate_summary_counts(item, hours)

    for metric in ("min", "mean", "max"):

        value = item[metric]
        coverage = item[f"{metric}_coverage"]

        validate_number(value, nullable=True)
        validate_coverage(coverage)

        require(
            coverage <= item["coverage"],
            "Invalid measurement metric coverage"
        )

        require(
            (value is None) == (coverage == 0),
            "Inconsistent measurement availability"
        )


def validate_raw_records(rows, category, first, last):

    fields = RAW_FIELDS[category]
    seen = set()

    for row in rows:

        require(
            isinstance(row, dict)
            and set(row) == fields,
            "Invalid hourly record fields"
        )

        timestamp = row["start"]

        validate_hour(timestamp, first, last)

        require(
            type(row["end"]) is int
            and row["end"] == timestamp + HOUR_MS,
            "Invalid hourly record end"
        )

        require(
            timestamp not in seen,
            "Duplicate hourly record timestamp"
        )

        seen.add(timestamp)

        for field in fields - {"start", "end"}:
            validate_number(row[field], nullable=True)


def validate_statistics(data):

    first, last, hours = validate_metadata(data)

    for item in data["energy"].values():

        validate_energy_summary(
            item, first, last, hours
        )

    for sensor, item in data["measurements"].items():

        validate_sensor(sensor)
        validate_measurement_summary(item, hours)

    for category in ("energy", "measurements"):

        for sensor, rows in data["raw"][category].items():

            validate_sensor(sensor)

            validate_raw_records(
                rows, category, first, last
            )

    require(
        set(data["raw"]["measurements"])
        <= set(data["measurements"]),
        "Unexpected raw measurement sensor"
    )

    return data


MAX_JSON_DEPTH = 16
MAX_JSON_CONTAINERS = 1_010_000
MAX_JSON_SEPARATORS = 12_000_000
MAX_OBJECT_MEMBERS = 512
MAX_INTEGER_TOKEN_LENGTH = 32
MAX_FLOAT_TOKEN_LENGTH = 64


def validate_json_depth(payload):
    """Check nesting before JSON deserialization."""

    depth = 0
    containers = 0
    separators = 0
    in_string = False
    escaped = False

    for byte in payload:

        if in_string:

            if escaped:
                escaped = False

            elif byte == 92:
                escaped = True

            elif byte == 34:
                in_string = False

            continue

        if byte == 34:
            in_string = True

        elif byte in (123, 91):
            containers += 1
            require(
                containers <= MAX_JSON_CONTAINERS,
                "JSON container limit exceeded"
            )
            depth += 1

            require(
                depth <= MAX_JSON_DEPTH,
                "JSON nesting limit exceeded"
            )

        elif byte in (44, 58):
            separators += 1
            require(
                separators <= MAX_JSON_SEPARATORS,
                "JSON separator limit exceeded"
            )

        elif byte in (125, 93):
            depth -= 1

            require(
                depth >= 0,
                "Invalid JSON structure"
            )

    require(
        depth == 0 and not in_string,
        "Incomplete JSON structure"
    )


def parse_json_integer(value):

    require(
        len(value) <= MAX_INTEGER_TOKEN_LENGTH,
        "JSON integer token too long"
    )

    result = int(value)

    validate_number(result)

    return result


def parse_json_float(value):

    require(
        len(value) <= MAX_FLOAT_TOKEN_LENGTH,
        "JSON float token too long"
    )

    result = float(value)

    validate_number(result)

    return result
