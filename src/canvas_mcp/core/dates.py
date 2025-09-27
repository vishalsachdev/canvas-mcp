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
