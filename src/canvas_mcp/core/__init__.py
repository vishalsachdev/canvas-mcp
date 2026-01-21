"""Core utilities for Canvas MCP server."""

from .client import make_canvas_request, fetch_all_paginated_results, cleanup_http_client
from .cache import get_course_id, get_course_code, refresh_course_cache
from .validation import validate_params, validate_parameter, format_error, is_error_response
from .dates import format_date, parse_date, truncate_text, format_date_smart, format_datetime_compact
from .types import CourseInfo, AssignmentInfo, PageInfo, AnnouncementInfo
from .config import get_config, validate_config, API_BASE_URL, API_TOKEN
from .response_formatter import (
    Verbosity,
    get_verbosity,
    set_verbosity,
    is_compact,
    format_header,
    format_item,
    format_list,
    format_footer,
    format_response,
    format_boolean,
    format_count,
    format_stats,
    format_assignment_item,
    format_submission_item,
    format_user_item,
)

__all__ = [
    'make_canvas_request',
    'fetch_all_paginated_results',
    'cleanup_http_client',
    'get_course_id',
    'get_course_code',
    'refresh_course_cache',
    'validate_params',
    'validate_parameter',
    'format_error',
    'is_error_response',
    'format_date',
    'parse_date',
    'truncate_text',
    'format_date_smart',
    'format_datetime_compact',
    'CourseInfo',
    'AssignmentInfo',
    'PageInfo',
    'AnnouncementInfo',
    'get_config',
    'validate_config',
    'API_BASE_URL',
    'API_TOKEN',
    # Response formatter exports
    'Verbosity',
    'get_verbosity',
    'set_verbosity',
    'is_compact',
    'format_header',
    'format_item',
    'format_list',
    'format_footer',
    'format_response',
    'format_boolean',
    'format_count',
    'format_stats',
    'format_assignment_item',
    'format_submission_item',
    'format_user_item',
]