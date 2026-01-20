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
"""

import datetime
import sys

from dateutil import parser as date_parser


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


def parse_to_iso8601(date_string: str, end_of_day: bool = True) -> str:
    """Convert human-friendly date to Canvas-compatible ISO 8601 format.

    Uses dateutil.parser for flexible parsing of various date formats.

    Supported formats include:
    - "12/10/2025" (US format)
    - "Dec 10, 2025"
    - "December 10, 2025"
    - "2025-12-10" (ISO format)
    - "2025-12-10T14:30:00" (with time)
    - And many more via dateutil

    Args:
        date_string: The date string to parse
        end_of_day: If True and no time specified, defaults to 23:59:00 (11:59 PM)

    Returns:
        ISO 8601 formatted string (e.g., "2025-12-10T23:59:00Z")

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
        parsed = parsed.replace(tzinfo=datetime.timezone.utc)

    return parsed.strftime("%Y-%m-%dT%H:%M:%SZ")
