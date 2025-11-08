"""Standardized API response format and utilities."""

from enum import Enum
from typing import Any, Generic, TypeVar

from pydantic import BaseModel


class ErrorCode(str, Enum):
    """Standard error codes for API responses."""

    # Client errors (4xx)
    VALIDATION_ERROR = "VALIDATION_ERROR"
    NOT_FOUND = "NOT_FOUND"
    UNAUTHORIZED = "UNAUTHORIZED"
    FORBIDDEN = "FORBIDDEN"
    RATE_LIMITED = "RATE_LIMITED"
    INVALID_PARAMETER = "INVALID_PARAMETER"

    # Server errors (5xx)
    INTERNAL_ERROR = "INTERNAL_ERROR"
    CANVAS_API_ERROR = "CANVAS_API_ERROR"
    NETWORK_ERROR = "NETWORK_ERROR"
    TIMEOUT_ERROR = "TIMEOUT_ERROR"

    # Business logic errors
    COURSE_NOT_FOUND = "COURSE_NOT_FOUND"
    ASSIGNMENT_NOT_FOUND = "ASSIGNMENT_NOT_FOUND"
    USER_NOT_FOUND = "USER_NOT_FOUND"
    INSUFFICIENT_PERMISSIONS = "INSUFFICIENT_PERMISSIONS"
    DUPLICATE_ENTRY = "DUPLICATE_ENTRY"

    # Data errors
    ANONYMIZATION_ERROR = "ANONYMIZATION_ERROR"
    CACHE_ERROR = "CACHE_ERROR"


class ApiError(BaseModel):
    """Standardized error response."""

    code: ErrorCode
    message: str
    details: dict[str, Any] | None = None
    suggestion: str | None = None

    def to_string(self) -> str:
        """Convert error to a formatted string."""
        result = f"Error [{self.code}]: {self.message}"

        if self.suggestion:
            result += f"\n\nSuggestion: {self.suggestion}"

        if self.details:
            result += f"\n\nDetails: {self.details}"

        return result


T = TypeVar('T')


class ApiResponse(BaseModel, Generic[T]):
    """Standardized API response wrapper."""

    success: bool
    data: T | None = None
    error: ApiError | None = None
    metadata: dict[str, Any] | None = None

    @classmethod
    def success_response(cls, data: T, metadata: dict[str, Any] | None = None) -> 'ApiResponse[T]':
        """Create a successful response."""
        return cls(success=True, data=data, metadata=metadata)

    @classmethod
    def error_response(
        cls,
        code: ErrorCode,
        message: str,
        details: dict[str, Any] | None = None,
        suggestion: str | None = None
    ) -> 'ApiResponse[T]':
        """Create an error response."""
        error = ApiError(code=code, message=message, details=details, suggestion=suggestion)
        return cls(success=False, error=error)

    def to_string(self) -> str:
        """Convert response to a formatted string for MCP tools."""
        if self.success and self.data is not None:
            # For successful responses, return the data as a formatted string
            if isinstance(self.data, str):
                return self.data
            elif isinstance(self.data, dict):
                import json
                return json.dumps(self.data, indent=2)
            elif isinstance(self.data, list):
                import json
                return json.dumps(self.data, indent=2)
            else:
                return str(self.data)
        elif self.error:
            return self.error.to_string()
        else:
            return "Unknown response state"


class PaginatedData(BaseModel, Generic[T]):
    """Paginated data response."""

    items: list[T]
    page: int
    per_page: int
    total_count: int | None = None
    has_more: bool = False

    @property
    def total_pages(self) -> int | None:
        """Calculate total pages if total_count is available."""
        if self.total_count is not None and self.per_page > 0:
            return (self.total_count + self.per_page - 1) // self.per_page
        return None


def create_error(
    code: ErrorCode,
    message: str,
    details: dict[str, Any] | None = None,
    suggestion: str | None = None
) -> str:
    """Create a standardized error message string for MCP tools.

    Args:
        code: The error code
        message: Human-readable error message
        details: Optional additional details
        suggestion: Optional suggestion to fix the error

    Returns:
        Formatted error string
    """
    error = ApiError(code=code, message=message, details=details, suggestion=suggestion)
    return error.to_string()


def create_validation_error(param_name: str, param_value: Any, reason: str) -> str:
    """Create a validation error message.

    Args:
        param_name: Name of the invalid parameter
        param_value: Value that failed validation
        reason: Reason for validation failure

    Returns:
        Formatted error string
    """
    return create_error(
        code=ErrorCode.VALIDATION_ERROR,
        message=f"Invalid parameter '{param_name}': {reason}",
        details={"parameter": param_name, "value": str(param_value)},
        suggestion="Please check the parameter value and try again"
    )


def create_not_found_error(resource_type: str, identifier: str | int) -> str:
    """Create a not found error message.

    Args:
        resource_type: Type of resource (e.g., "course", "assignment")
        identifier: The identifier that was not found

    Returns:
        Formatted error string
    """
    return create_error(
        code=ErrorCode.NOT_FOUND,
        message=f"{resource_type.capitalize()} not found: {identifier}",
        details={"resource_type": resource_type, "identifier": str(identifier)},
        suggestion=f"Please verify the {resource_type} identifier and try again"
    )


def create_canvas_api_error(status_code: int, response_body: str | dict[str, Any]) -> str:
    """Create a Canvas API error message.

    Args:
        status_code: HTTP status code
        response_body: Response body from Canvas API

    Returns:
        Formatted error string
    """
    if isinstance(response_body, dict):
        message = response_body.get("message", "Canvas API request failed")
    else:
        message = "Canvas API request failed"

    return create_error(
        code=ErrorCode.CANVAS_API_ERROR,
        message=f"Canvas API error (HTTP {status_code}): {message}",
        details={"status_code": status_code, "response": response_body},
        suggestion="Please check your API token and permissions, or try again later"
    )


def format_list_response(
    items: list[dict[str, Any]],
    item_formatter: callable,
    title: str | None = None,
    empty_message: str = "No items found.",
    metadata: dict[str, Any] | None = None
) -> str:
    """Format a list of items into a consistent string response.

    Args:
        items: List of items to format
        item_formatter: Function that formats a single item to string
        title: Optional title for the response
        empty_message: Message to show when list is empty
        metadata: Optional metadata to include (page info, totals, etc.)

    Returns:
        Formatted string response
    """
    if not items:
        return empty_message

    formatted_items = [item_formatter(item) for item in items]
    result = "\n\n".join(formatted_items)

    if title:
        result = f"{title}:\n\n{result}"

    if metadata:
        meta_str = format_metadata(metadata)
        result = f"{result}\n\n{meta_str}"

    return result


def format_metadata(metadata: dict[str, Any]) -> str:
    """Format metadata dictionary into a readable string.

    Args:
        metadata: Metadata dictionary

    Returns:
        Formatted metadata string
    """
    if not metadata:
        return ""

    lines = ["--- Metadata ---"]
    for key, value in metadata.items():
        # Convert snake_case to Title Case for display
        display_key = key.replace("_", " ").title()
        lines.append(f"{display_key}: {value}")

    return "\n".join(lines)


def format_paginated_response(
    items: list[dict[str, Any]],
    item_formatter: callable,
    title: str | None = None,
    page: int = 1,
    per_page: int = 100,
    total_count: int | None = None,
    has_more: bool = False,
    empty_message: str = "No items found."
) -> str:
    """Format a paginated list response with metadata.

    Args:
        items: List of items to format
        item_formatter: Function that formats a single item to string
        title: Optional title for the response
        page: Current page number
        per_page: Items per page
        total_count: Total number of items (if known)
        has_more: Whether there are more pages
        empty_message: Message to show when list is empty

    Returns:
        Formatted string response with pagination info
    """
    metadata = {
        "page": page,
        "per_page": per_page,
        "items_on_page": len(items),
    }

    if total_count is not None:
        metadata["total_count"] = total_count
        metadata["total_pages"] = (total_count + per_page - 1) // per_page

    if has_more:
        metadata["has_more_pages"] = "Yes"
        metadata["next_page"] = page + 1

    return format_list_response(
        items=items,
        item_formatter=item_formatter,
        title=title,
        empty_message=empty_message,
        metadata=metadata
    )


def create_success_message(message: str, details: dict[str, Any] | None = None) -> str:
    """Create a success message with optional details.

    Args:
        message: Success message
        details: Optional details to include

    Returns:
        Formatted success message
    """
    result = f"✓ {message}"

    if details:
        result += f"\n\n{format_metadata(details)}"

    return result
