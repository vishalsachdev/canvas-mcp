"""Date parsing and formatting utilities for Canvas API.

Date/Time Formatting Standard
---------------------------
This module standardizes all date/time values to ISO 8601 format (YYYY-MM-DDTHH:MM:SSZ)
with the following conventions:
- All dates include time components (even if they're 00:00:00)
- All dates include timezone information (Z for UTC or +/-HH:MM offset)
- UTC timezone is used for all internal date handling
- Dates without timezone information are assumed to be in UTC
- The format_date() function handles conversion of various formats to this standard

Smart Date Formatting
--------------------
For token efficiency, this module also provides smart date formatting modes:
- "standard": Full ISO 8601 format (2026-01-21T23:59:00Z)
- "compact": Short month-day format (Jan 21)
- "relative": Relative to current time (in 3 days, yesterday)
"""

import datetime
import sys
from typing import Literal

from dateutil import parser as date_parser


# Type alias for date format modes
DateFormatMode = Literal["standard", "compact", "relative"]


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
    """Format a date string to ISO 8601 format (YYYY-MM-DDTHH:MM:SSZ) or return 'N/A' if None.

    All dates are converted to ISO 8601 format for consistency across the API.
    Timezone information is preserved if present, otherwise UTC is assumed.

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

    # Format to ISO 8601 with Z for UTC or offset for other timezones
    if dt.tzinfo == datetime.timezone.utc:
        return dt.strftime('%Y-%m-%dT%H:%M:%SZ')
    else:
        return dt.strftime('%Y-%m-%dT%H:%M:%S%z')


def truncate_text(text: str, max_length: int = 100) -> str:
    """Truncate text to a maximum length and add ellipsis if needed."""
    if not text or len(text) <= max_length:
        return text

    return text[:max_length - 3] + "..."


def format_date_smart(
    date_str: str | None,
    mode: DateFormatMode = "standard"
) -> str:
    """Format a date string with configurable verbosity for token efficiency.

    Args:
        date_str: The date string to format
        mode: Formatting mode:
            - "standard": Full ISO 8601 (2026-01-21T23:59:00Z)
            - "compact": Short format (Jan 21) - ~60% token savings
            - "relative": Relative time (in 3 days, yesterday)

    Returns:
        Formatted date string based on mode, or '-' for compact/N/A for standard if None
    """
    if not date_str:
        return "-" if mode == "compact" else "N/A"

    dt = parse_date(date_str)
    if not dt:
        return date_str  # Return original if parsing fails

    if mode == "standard":
        # Full ISO 8601 format
        if dt.tzinfo == datetime.timezone.utc:
            return dt.strftime('%Y-%m-%dT%H:%M:%SZ')
        else:
            return dt.strftime('%Y-%m-%dT%H:%M:%S%z')

    elif mode == "compact":
        # Short month-day format (most token efficient)
        # Include year only if not current year
        now = datetime.datetime.now(datetime.timezone.utc)
        if dt.year != now.year:
            return dt.strftime('%b %d %Y')
        return dt.strftime('%b %d')

    elif mode == "relative":
        # Relative time format
        now = datetime.datetime.now(datetime.timezone.utc)
        delta = dt - now
        total_seconds = int(delta.total_seconds())
        abs_seconds = abs(total_seconds)

        # Within 24 hours (86400 seconds) - handles same-day correctly
        # Note: We use total_seconds instead of delta.days because Python
        # represents negative deltas < 24h as -1 day + positive seconds,
        # which would incorrectly trigger "yesterday" for times like "2h ago"
        if abs_seconds < 86400:
            if abs_seconds < 60:
                return "now"
            hours = abs_seconds // 3600
            if hours == 0:
                minutes = abs_seconds // 60
                return f"in {minutes}m" if total_seconds > 0 else f"{minutes}m ago"
            return f"in {hours}h" if total_seconds > 0 else f"{hours}h ago"

        # Beyond 24 hours - calculate days from total seconds
        days = abs_seconds // 86400
        if total_seconds > 0:
            # Future dates
            if days == 1:
                return "tomorrow"
            elif days <= 7:
                return f"in {days} days"
        else:
            # Past dates
            if days == 1:
                return "yesterday"
            elif days <= 7:
                return f"{days} days ago"

        # Fall back to compact for dates more than a week away
        if dt.year != now.year:
            return dt.strftime('%b %d %Y')
        return dt.strftime('%b %d')

    return date_str  # Fallback


def format_datetime_compact(date_str: str | None) -> str:
    """Format a datetime with time in compact mode.

    Includes time for submissions/events where time matters.

    Args:
        date_str: The date string to format

    Returns:
        Compact datetime string (e.g., "Jan 21 14:30") or '-' if None
    """
    if not date_str:
        return "-"

    dt = parse_date(date_str)
    if not dt:
        return date_str

    now = datetime.datetime.now(datetime.timezone.utc)
    if dt.year != now.year:
        return dt.strftime('%b %d %Y %H:%M')
    return dt.strftime('%b %d %H:%M')


def parse_to_iso8601(date_string: str, end_of_day: bool = True) -> str:
    """Convert human-friendly date to Canvas-compatible ISO 8601 format.

    Uses dateutil.parser for flexible parsing of various date formats.

    Supported formats include:
    - "12/10/2025" (US format: MM/DD/YYYY)
    - "Dec 10, 2025"
    - "December 10, 2025"
    - "2025-12-10" (ISO format)
    - "2025-12-10T14:30:00" (with time)
    - "2025-12-10T10:00:00-05:00" (with timezone offset)
    - And many more via dateutil

    Note on date format: Ambiguous dates like "12/10/2025" are parsed using US format
    (MM/DD/YYYY), where 12/10 is December 10th, not October 12th. This follows the
    dateutil default behavior.

    Note on midnight handling: When end_of_day=True, dates parsed as midnight (00:00:00)
    are converted to 23:59:00. This means if you explicitly specify midnight
    (e.g., "2025-12-10T00:00:00"), it will be converted to 23:59:00. To preserve
    an explicit midnight time, set end_of_day=False.

    Note on timezone handling: Timezone-aware datetimes are converted to UTC. For example,
    "2025-12-10T10:00:00-05:00" (10 AM EST) becomes "2025-12-10T15:00:00Z" (3 PM UTC).
    Naive datetimes (without timezone info) are assumed to already be in UTC.

    Args:
        date_string: The date string to parse
        end_of_day: If True and no time specified, defaults to 23:59:00 (11:59 PM).
            Note: This also converts explicit midnight times to 23:59:00.

    Returns:
        ISO 8601 formatted string in UTC (e.g., "2025-12-10T23:59:00Z")

    Raises:
        ValueError: If the date string cannot be parsed
    """
    try:
        parsed = date_parser.parse(date_string)
    except (ValueError, TypeError) as e:
        raise ValueError(f"Could not parse date: {date_string}") from e

    # If no time was specified (defaults to midnight), use end of day
    if end_of_day and parsed.hour == 0 and parsed.minute == 0 and parsed.second == 0:
        parsed = parsed.replace(hour=23, minute=59, second=0)

    # Ensure UTC timezone
    if parsed.tzinfo is None:
        # Naive datetime: assume it's already in UTC
        parsed = parsed.replace(tzinfo=datetime.timezone.utc)
    else:
        # Timezone-aware datetime: convert to UTC
        parsed = parsed.astimezone(datetime.timezone.utc)

    return parsed.strftime("%Y-%m-%dT%H:%M:%SZ")
