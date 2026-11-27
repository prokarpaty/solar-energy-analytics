"""Validated local send times; period boundaries stay at local midnight."""
import re


def parse_send_time(value):
    if not isinstance(value, str) or not re.fullmatch(r"(?:[01][0-9]|2[0-3]):[0-5][0-9]", value):
        raise ValueError("Expected a time in 24-hour HH:MM format")
    return tuple(map(int, value.split(":")))


def delivery_ready_at(scheduled, config, statistics_delay_minutes=10):
    """Return earliest epoch time for dispatch without changing report identity."""
    if scheduled.tzinfo is None:
        raise ValueError("Scheduled datetime must be timezone-aware")
    hh, mm = parse_send_time(config.get("send_time", "00:00"))
    requested = scheduled.replace(hour=hh, minute=mm, second=0, microsecond=0)
    return max(
        requested.timestamp(),
        scheduled.timestamp() + statistics_delay_minutes * 60,
    )
