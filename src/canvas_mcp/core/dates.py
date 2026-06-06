"""Date parsing and formatting utilities for Canvas API.

Date/Time Formatting Standard
---------------------------
This module standardizes all date/time values to ISO 8601 format with the
following conventions:
- All dates include time components (even if they're 00:00:00)
- All dates include timezone information (Z for UTC or +/-HH:MM offset)
- Canvas returns UTC; internal datetime comparisons stay in UTC
- User-facing output is converted to the configured TIMEZONE (default UTC)
  so models surface a wall-clock time the user recognizes. Output remains
  ISO 8601 (e.g. ``2026-05-28T18:59:59-05:00``) so downstream parsers that
  use ``fromisoformat`` continue to work.
- Dates without timezone information are assumed to be in UTC
"""

import datetime
import sys
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

_tz_cache: dict[str, datetime.tzinfo] = {}
_tz_warned: set[str] = set()


def _output_tz() -> datetime.tzinfo:
    """Resolve the configured output timezone, falling back to UTC."""
    from .config import get_config

    name = (get_config().timezone or "UTC").strip()
    if name in _tz_cache:
        return _tz_cache[name]

    if name.upper() == "UTC":
        tz: datetime.tzinfo = datetime.timezone.utc
    else:
        try:
            tz = ZoneInfo(name)
        except ZoneInfoNotFoundError:
            if name not in _tz_warned:
                print(
                    f"Warning: TIMEZONE='{name}' not found; falling back to UTC. "
                    "On Windows, install the 'tzdata' package.",
                    file=sys.stderr,
                )
                _tz_warned.add(name)
            tz = datetime.timezone.utc

    _tz_cache[name] = tz
    return tz


def parse_date(date_str: str | None) -> datetime.datetime | None:
    """Parse a date string into a datetime object.

    Attempts to parse various date formats into a standard datetime object.
    If timezone information is present, it's preserved; otherwise, UTC is assumed.

    Args:
        date_str: The date string to parse

    Returns:
        datetime object or None if parsing fails
    """
    if not date_str:
        return None

    # Remove any surrounding whitespace
    date_str = date_str.strip()

    # Try different date formats
    formats = [
        # ISO 8601 formats
        '%Y-%m-%dT%H:%M:%SZ',  # 2023-01-15T14:30:00Z
        '%Y-%m-%dT%H:%M:%S.%fZ',  # 2023-01-15T14:30:00.000Z
        '%Y-%m-%dT%H:%M:%S%z',  # 2023-01-15T14:30:00+0000
        '%Y-%m-%dT%H:%M:%S.%f%z',  # 2023-01-15T14:30:00.000+0000

        # Common date formats
        '%Y-%m-%d %H:%M:%S',  # 2023-01-15 14:30:00
        '%Y-%m-%d',  # 2023-01-15
        '%m/%d/%Y %H:%M:%S',  # 01/15/2023 14:30:00
        '%m/%d/%Y',  # 01/15/2023
    ]

    for fmt in formats:
        try:
            dt = datetime.datetime.strptime(date_str, fmt)

            # If no timezone info, assume UTC
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=datetime.timezone.utc)

            return dt
        except ValueError:
            continue

    # If all parsing attempts fail, return None
    print(f"Warning: Could not parse date string: {date_str}", file=sys.stderr)
    return None


def format_date(date_str: str | None) -> str:
    """Format a date string to ISO 8601 in the configured output timezone.

    Converts the parsed datetime to the timezone specified by the ``TIMEZONE``
    environment variable (default ``UTC``) and emits ISO 8601. UTC is rendered
    with the ``Z`` suffix for backward compatibility; other zones use a
    numeric offset (e.g. ``2026-05-28T18:59:59-05:00``).

    Args:
        date_str: The date string to format

    Returns:
        Formatted date string in ISO 8601 format or 'N/A' if None
    """
    if not date_str:
        return "N/A"

    dt = parse_date(date_str)
    if not dt:
        return date_str  # Return original if parsing fails

    tz = _output_tz()
    local_dt = dt.astimezone(tz)

    iso = local_dt.isoformat(timespec="seconds")
    if local_dt.utcoffset() == datetime.timedelta(0):
        return iso.replace("+00:00", "Z")
    return iso


def truncate_text(text: str, max_length: int = 100) -> str:
    """Truncate text to a maximum length and add ellipsis if needed."""
    if not text or len(text) <= max_length:
        return text

    return text[:max_length - 3] + "..."
