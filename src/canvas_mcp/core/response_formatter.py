"""Response formatting utilities for token-efficient output.

This module provides centralized formatting with configurable verbosity levels
to optimize token consumption while maintaining clarity.

Verbosity Levels:
- COMPACT: IDs and essential data only (DEFAULT for token efficiency)
- STANDARD: Full labels and human-readable formatting
- VERBOSE: Extra context and debugging information
"""

from enum import Enum
from typing import Any

from .config import get_config


class Verbosity(Enum):
    """Verbosity levels for response formatting."""
    COMPACT = "compact"
    STANDARD = "standard"
    VERBOSE = "verbose"


# Global verbosity setting, initialized from config
_verbosity: Verbosity | None = None


def get_verbosity() -> Verbosity:
    """Get the current verbosity level from config or environment.

    Returns:
        Current Verbosity level
    """
    global _verbosity
    if _verbosity is None:
        config = get_config()
        verbosity_str = getattr(config, 'verbosity', 'compact').lower()
        try:
            _verbosity = Verbosity(verbosity_str)
        except ValueError:
            _verbosity = Verbosity.COMPACT
    return _verbosity


def set_verbosity(level: Verbosity) -> None:
    """Set the global verbosity level.

    Args:
        level: The verbosity level to set
    """
    global _verbosity
    _verbosity = level


def is_compact() -> bool:
    """Check if current verbosity is compact mode."""
    return get_verbosity() == Verbosity.COMPACT


def format_header(
    tool_name: str,
    context: str | None = None,
    verbosity: Verbosity | None = None
) -> str:
    """Format a response header based on verbosity.

    Args:
        tool_name: Short name of the tool (e.g., "asgn", "sub", "users")
        context: Context info (e.g., course code, assignment ID)
        verbosity: Override global verbosity setting

    Returns:
        Formatted header string
    """
    v = verbosity or get_verbosity()

    if v == Verbosity.COMPACT:
        if context:
            return f"{tool_name}|{context}"
        return tool_name
    elif v == Verbosity.STANDARD:
        # Map short names to readable names
        name_map = {
            "asgn": "Assignments",
            "sub": "Submissions",
            "users": "Users",
            "pages": "Pages",
            "modules": "Modules",
            "analytics": "Analytics",
            "courses": "Courses",
        }
        readable_name = name_map.get(tool_name, tool_name.title())
        if context:
            return f"{readable_name} for {context}:"
        return f"{readable_name}:"
    else:  # VERBOSE
        readable_name = tool_name.replace("_", " ").title()
        if context:
            return f"=== {readable_name} for {context} ==="
        return f"=== {readable_name} ==="


def format_item(
    fields: dict[str, Any],
    field_order: list[str] | None = None,
    verbosity: Verbosity | None = None
) -> str:
    """Format a single item (assignment, submission, etc.) based on verbosity.

    Args:
        fields: Dictionary of field names to values
        field_order: Optional list specifying field order
        verbosity: Override global verbosity setting

    Returns:
        Formatted item string
    """
    v = verbosity or get_verbosity()

    if field_order is None:
        field_order = list(fields.keys())

    if v == Verbosity.COMPACT:
        # Pipe-delimited values only
        values = [_format_value_compact(fields.get(f)) for f in field_order if f in fields]
        return "|".join(values)
    elif v == Verbosity.STANDARD:
        # Label: Value format with abbreviated labels
        lines = []
        for field in field_order:
            if field in fields:
                label = _abbreviate_label(field)
                value = _format_value_standard(fields[field])
                lines.append(f"{label}: {value}")
        return "\n".join(lines)
    else:  # VERBOSE
        # Full labels with detailed values
        lines = []
        for field in field_order:
            if field in fields:
                label = field.replace("_", " ").title()
                value = _format_value_verbose(fields[field])
                lines.append(f"{label}: {value}")
        return "\n".join(lines)


def format_list(
    items: list[dict[str, Any]],
    field_order: list[str] | None = None,
    verbosity: Verbosity | None = None,
    separator: str | None = None
) -> str:
    """Format a list of items based on verbosity.

    Args:
        items: List of item dictionaries
        field_order: Optional list specifying field order
        verbosity: Override global verbosity setting
        separator: Custom separator between items

    Returns:
        Formatted list string
    """
    v = verbosity or get_verbosity()

    if not items:
        return "No items found."

    if separator is None:
        separator = "\n" if v == Verbosity.COMPACT else "\n\n"

    formatted_items = [format_item(item, field_order, v) for item in items]
    return separator.join(formatted_items)


def format_footer(verbosity: Verbosity | None = None) -> str:
    """Format a footer with verbosity hint if in compact mode.

    Args:
        verbosity: Override global verbosity setting

    Returns:
        Footer string (empty for non-compact modes)
    """
    v = verbosity or get_verbosity()

    if v == Verbosity.COMPACT:
        return "\n(Use verbosity=standard for full details)"
    return ""


def format_response(
    header: str,
    body: str,
    verbosity: Verbosity | None = None,
    include_footer: bool = True
) -> str:
    """Combine header, body, and optional footer into complete response.

    Args:
        header: Response header
        body: Response body
        verbosity: Override global verbosity setting
        include_footer: Whether to include footer hint in compact mode

    Returns:
        Complete formatted response
    """
    v = verbosity or get_verbosity()

    parts = [header]
    if body:
        parts.append(body)

    if include_footer and v == Verbosity.COMPACT:
        parts.append(format_footer(v))

    separator = "\n" if v == Verbosity.COMPACT else "\n\n"
    return separator.join(parts)


def format_boolean(value: bool, verbosity: Verbosity | None = None) -> str:
    """Format a boolean value based on verbosity.

    Args:
        value: Boolean value to format
        verbosity: Override global verbosity setting

    Returns:
        Formatted boolean string
    """
    v = verbosity or get_verbosity()

    if v == Verbosity.COMPACT:
        return "Y" if value else "N"
    elif v == Verbosity.STANDARD:
        return "Yes" if value else "No"
    else:
        return "True" if value else "False"


def format_count(
    count: int,
    total: int | None = None,
    label: str = "",
    verbosity: Verbosity | None = None
) -> str:
    """Format a count with optional total and percentage.

    Args:
        count: The count value
        total: Optional total for percentage calculation
        label: Optional label for the count
        verbosity: Override global verbosity setting

    Returns:
        Formatted count string
    """
    v = verbosity or get_verbosity()

    if v == Verbosity.COMPACT:
        if total:
            return f"{count}/{total}"
        return str(count)
    else:
        if total:
            pct = (count / total * 100) if total > 0 else 0
            if label:
                return f"{label}: {count}/{total} ({pct:.1f}%)"
            return f"{count}/{total} ({pct:.1f}%)"
        if label:
            return f"{label}: {count}"
        return str(count)


def format_stats(
    stats: dict[str, float | int],
    verbosity: Verbosity | None = None
) -> str:
    """Format statistical data based on verbosity.

    Args:
        stats: Dictionary with stat names and values
        verbosity: Override global verbosity setting

    Returns:
        Formatted stats string
    """
    v = verbosity or get_verbosity()

    if v == Verbosity.COMPACT:
        # Abbreviated stat names
        abbrev = {
            "average": "avg",
            "median": "med",
            "std_dev": "sd",
            "minimum": "min",
            "maximum": "max",
            "count": "n",
            "submitted": "sub",
            "missing": "miss",
            "late": "late",
            "graded": "graded",
        }
        parts = []
        for key, value in stats.items():
            label = abbrev.get(key.lower(), key[:3])
            if isinstance(value, float):
                parts.append(f"{label}:{value:.1f}")
            else:
                parts.append(f"{label}:{value}")
        return "|".join(parts)
    else:
        lines = []
        for key, value in stats.items():
            label = key.replace("_", " ").title()
            if isinstance(value, float):
                lines.append(f"  {label}: {value:.2f}")
            else:
                lines.append(f"  {label}: {value}")
        return "\n".join(lines)


# Private helper functions

def _format_value_compact(value: Any) -> str:
    """Format a value for compact mode."""
    if value is None:
        return "-"
    if isinstance(value, bool):
        return "Y" if value else "N"
    if isinstance(value, float):
        return f"{value:.1f}"
    return str(value)


def _format_value_standard(value: Any) -> str:
    """Format a value for standard mode."""
    if value is None:
        return "N/A"
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, float):
        return f"{value:.2f}"
    return str(value)


def _format_value_verbose(value: Any) -> str:
    """Format a value for verbose mode."""
    if value is None:
        return "Not specified"
    if isinstance(value, bool):
        return "True" if value else "False"
    if isinstance(value, list):
        return ", ".join(str(v) for v in value) if value else "None"
    return str(value)


def _abbreviate_label(label: str) -> str:
    """Abbreviate field labels for standard mode."""
    abbreviations = {
        "id": "ID",
        "name": "Name",
        "due_at": "Due",
        "points_possible": "Points",
        "points": "Pts",
        "submitted_at": "Submitted",
        "submitted": "Sub",
        "score": "Score",
        "grade": "Grade",
        "user_id": "User",
        "published": "Pub",
        "workflow_state": "Status",
        "created_at": "Created",
        "updated_at": "Updated",
        "email": "Email",
        "roles": "Role",
        "url": "URL",
        "title": "Title",
        "description": "Desc",
        "course_code": "Code",
    }
    return abbreviations.get(label.lower(), label.title())


# Convenience functions for common formatting patterns

def format_assignment_item(
    assignment: dict[str, Any],
    verbosity: Verbosity | None = None
) -> str:
    """Format a single assignment for output.

    Args:
        assignment: Assignment data dictionary
        verbosity: Override global verbosity setting

    Returns:
        Formatted assignment string
    """
    fields = {
        "id": assignment.get("id"),
        "name": assignment.get("name", "Unnamed"),
        "due_at": assignment.get("due_at"),
        "points": assignment.get("points_possible", 0),
    }
    return format_item(fields, ["id", "name", "due_at", "points"], verbosity)


def format_submission_item(
    submission: dict[str, Any],
    verbosity: Verbosity | None = None
) -> str:
    """Format a single submission for output.

    Args:
        submission: Submission data dictionary
        verbosity: Override global verbosity setting

    Returns:
        Formatted submission string
    """
    fields = {
        "user_id": submission.get("user_id"),
        "submitted_at": submission.get("submitted_at"),
        "score": submission.get("score"),
        "grade": submission.get("grade"),
    }
    return format_item(fields, ["user_id", "submitted_at", "score", "grade"], verbosity)


def format_user_item(
    user: dict[str, Any],
    verbosity: Verbosity | None = None
) -> str:
    """Format a single user for output.

    Args:
        user: User data dictionary
        verbosity: Override global verbosity setting

    Returns:
        Formatted user string
    """
    enrollments = user.get("enrollments", [])
    roles = [e.get("role", "Student") for e in enrollments]
    role_str = ",".join(set(roles)) if roles else "Student"

    fields = {
        "id": user.get("id"),
        "name": user.get("name", "Unknown"),
        "email": user.get("email"),
        "roles": role_str,
    }
    return format_item(fields, ["id", "name", "email", "roles"], verbosity)
