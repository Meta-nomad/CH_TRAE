from __future__ import annotations

from datetime import date, datetime, timezone


USDT_LAUNCH_DATE = date(2014, 10, 6)


def parse_iso_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def utc_day_start(timestamp: int) -> int:
    dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)
    normalized = datetime(dt.year, dt.month, dt.day, tzinfo=timezone.utc)
    return int(normalized.timestamp())


def timestamp_to_date_string(timestamp: int | None) -> str | None:
    if timestamp is None:
        return None
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).strftime("%Y-%m-%d")


def timestamp_to_iso8601(timestamp: int) -> str:
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
