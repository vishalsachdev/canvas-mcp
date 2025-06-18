#!/usr/bin/env python3
from typing import Any, Dict, List, Optional, Union, TypedDict, Callable, TypeVar, cast, get_type_hints
import os
import sys
import httpx
import json
import datetime
import functools
import inspect
import re
from mcp.server.fastmcp import FastMCP

# Date/Time Formatting Standard
# ---------------------------
# This MCP server standardizes all date/time values to ISO 8601 format (YYYY-MM-DDTHH:MM:SSZ)
# with the following conventions:
# - All dates include time components (even if they're 00:00:00)
# - All dates include timezone information (Z for UTC or +/-HH:MM offset)
# - UTC timezone is used for all internal date handling
# - Dates without timezone information are assumed to be in UTC
# - The format_date() function handles conversion of various formats to this standard

# Initialize FastMCP server
mcp = FastMCP("canvas-api")

# Type definitions for parameter validation
T = TypeVar('T')
F = TypeVar('F', bound=Callable[..., Any])

# Constants
API_BASE_URL = os.environ.get("CANVAS_API_URL", "https://canvas.illinois.edu/api/v1")
API_TOKEN = os.environ.get("CANVAS_API_TOKEN", "")

# Parameter validation and conversion system
def validate_parameter(param_name: str, value: Any, expected_type: Any) -> Any:
    """
    Validate and convert a parameter to the expected type.
    
    Args:
        param_name: Name of the parameter (for error messages)
        value: The value to validate and convert
        expected_type: The expected Python type
        
    Returns:
        The validated and converted value
        
    Raises:
        ValueError: If validation fails
    """
    # Special handling for Union types (e.g., Union[int, str])
    origin = getattr(expected_type, "__origin__", None)
    args = getattr(expected_type, "__args__", None)
    
    # Handle Optional types (which are Union[type, None])
    is_optional = False
    if origin is Union and type(None) in args:
        is_optional = True
        # Extract the non-None type(s)
        non_none_types = [t for t in args if t is not type(None)]
        if len(non_none_types) == 1:
            expected_type = non_none_types[0]
        else:
            # It's a Union of multiple types plus None
            expected_type = Union[tuple(non_none_types)]
    
    # Handle None values for optional parameters
    if value is None:
        if is_optional:
            return None
        else:
            raise ValueError(f"Parameter '{param_name}' cannot be None")
    
    # Handle Union types (including those extracted from Optional)
    if origin is Union:
        # Try each type in the Union
        errors = []
        for arg_type in args:
            if arg_type is type(None) and value is None:
                return None
                
            try:
                return validate_parameter(param_name, value, arg_type)
            except ValueError as e:
                errors.append(str(e))
        
        # If we get here, none of the types worked
        type_names = ", ".join(str(t) for t in args)
        raise ValueError(f"Parameter '{param_name}' with value '{value}' (type: {type(value).__name__}) "
                        f"could not be converted to any of the expected types: {type_names}")
    
    # Handle basic types with conversion
    if expected_type is str:
        return str(value)
    elif expected_type is int:
        try:
            if isinstance(value, str) and not value.strip():
                raise ValueError(f"Parameter '{param_name}' is an empty string, cannot convert to int")
            return int(value)
        except (ValueError, TypeError):
            raise ValueError(f"Parameter '{param_name}' with value '{value}' could not be converted to int")
    elif expected_type is float:
        try:
            if isinstance(value, str) and not value.strip():
                raise ValueError(f"Parameter '{param_name}' is an empty string, cannot convert to float")
            return float(value)
        except (ValueError, TypeError):
            raise ValueError(f"Parameter '{param_name}' with value '{value}' could not be converted to float")
    elif expected_type is bool:
        if isinstance(value, bool):
            return value
        elif isinstance(value, str):
            value_lower = value.lower().strip()
            if value_lower in ("true", "yes", "1", "t", "y"):
                return True
            elif value_lower in ("false", "no", "0", "f", "n"):
                return False
            else:
                raise ValueError(f"Parameter '{param_name}' with value '{value}' could not be converted to bool")
        elif isinstance(value, (int, float)):
            return bool(value)
        else:
            raise ValueError(f"Parameter '{param_name}' with value '{value}' could not be converted to bool")
    elif expected_type is list or origin is list:
        if isinstance(value, list):
            return value
        elif isinstance(value, str):
            # Try to parse as JSON array
            try:
                parsed = json.loads(value)
                if isinstance(parsed, list):
                    return parsed
            except json.JSONDecodeError:
                pass
                
            # Try comma-separated values
            return [item.strip() for item in value.split(',') if item.strip()]
        else:
            raise ValueError(f"Parameter '{param_name}' with value '{value}' could not be converted to list")
    elif expected_type is dict or origin is dict:
        if isinstance(value, dict):
            return value
        elif isinstance(value, str):
            try:
                parsed = json.loads(value)
                if isinstance(parsed, dict):
                    return parsed
                else:
                    raise ValueError(f"Parameter '{param_name}' parsed as JSON but is not a dict")
            except json.JSONDecodeError:
                raise ValueError(f"Parameter '{param_name}' with value '{value}' could not be parsed as JSON dict")
        else:
            raise ValueError(f"Parameter '{param_name}' with value '{value}' could not be converted to dict")
    
    # For other types, just check if it's an instance
    if isinstance(value, expected_type):
        return value
    
    # If we get here, validation failed
    raise ValueError(f"Parameter '{param_name}' with value '{value}' (type: {type(value).__name__}) "
                    f"is not compatible with expected type: {expected_type}")

def validate_params(func: F) -> F:
    """Decorator to validate function parameters based on type hints."""
    sig = inspect.signature(func)
    type_hints = get_type_hints(func)
    
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        # Combine args and kwargs based on function signature
        bound_args = sig.bind(*args, **kwargs)
        bound_args.apply_defaults()
        
        # Validate each parameter
        for param_name, param_value in bound_args.arguments.items():
            if param_name in type_hints:
                expected_type = type_hints[param_name]
                try:
                    # Skip return type annotation
                    if param_name != "return":
                        bound_args.arguments[param_name] = validate_parameter(param_name, param_value, expected_type)
                except ValueError as e:
                    # Return error as JSON response
                    error_message = str(e)
                    print(f"Parameter validation error: {error_message}", file=sys.stderr)
                    return json.dumps({"error": error_message})
        
        # Call the original function with validated parameters
        return await func(**bound_args.arguments)
    
    return cast(F, wrapper)

# Global cache for course codes to IDs
course_code_to_id_cache = {}
id_to_course_code_cache = {}

# Custom type definitions
class CourseInfo(TypedDict, total=False):
    id: Union[int, str]
    name: str
    course_code: str
    start_at: str
    end_at: str
    time_zone: str
    default_view: str
    is_public: bool
    blueprint: bool

class AssignmentInfo(TypedDict, total=False):
    id: Union[int, str]
    name: str
    due_at: Optional[str]
    points_possible: float
    submission_types: List[str]
    published: bool
    locked_for_user: bool

class PageInfo(TypedDict, total=False):
    page_id: Union[int, str]
    url: str
    title: str
    published: bool
    front_page: bool
    locked_for_user: bool
    last_edited_by: Dict[str, Any]
    editing_roles: str

class AnnouncementInfo(TypedDict, total=False):
    id: Union[int, str]
    title: str
    message: str
    posted_at: Optional[str]
    delayed_post_at: Optional[str]
    lock_at: Optional[str]
    published: bool
    is_announcement: bool

# Initialize HTTP client with auth
http_client = httpx.AsyncClient(
    headers={
        'Authorization': f'Bearer {API_TOKEN}'
    },
    timeout=30.0
)

# Helper functions
def parse_date(date_str: Optional[str]) -> Optional[datetime.datetime]:
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

def format_date(date_str: Optional[str]) -> str:
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

# Helper function for API requests
async def make_canvas_request(
    method: str, 
    endpoint: str, 
    params: Optional[Dict[str, Any]] = None,
    data: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Make a request to the Canvas API with proper error handling."""
    
    try:
        # Ensure the endpoint starts with a slash
        if not endpoint.startswith('/'):
            endpoint = f"/{endpoint}"
            
        # Construct the full URL
        url = f"{API_BASE_URL.rstrip('/')}{endpoint}"
        
        # Log the request for debugging
        print(f"Making {method.upper()} request to {url}", file=sys.stderr)
        
        if method.lower() == "get":
            response = await http_client.get(url, params=params)
        elif method.lower() == "post":
            response = await http_client.post(url, json=data)
        elif method.lower() == "put":
            response = await http_client.put(url, json=data)
        elif method.lower() == "delete":
            response = await http_client.delete(url, params=params)
        else:
            return {"error": f"Unsupported method: {method}"}
        
        response.raise_for_status()
        return response.json()
    except httpx.HTTPStatusError as e:
        error_message = f"HTTP error: {e.response.status_code}"
        try:
            error_details = e.response.json()
            error_message += f", Details: {error_details}"
        except:
            error_details = e.response.text
            error_message += f", Text: {error_details}"
            
        print(f"API error: {error_message}", file=sys.stderr)
        return {"error": error_message}
    except Exception as e:
        print(f"Request failed: {str(e)}", file=sys.stderr)
        return {"error": f"Request failed: {str(e)}"}

async def fetch_all_paginated_results(endpoint: str, params: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """Fetch all results from a paginated Canvas API endpoint."""
    if params is None:
        params = {}
    
    # Ensure we get a reasonable number per page
    if "per_page" not in params:
        params["per_page"] = 100
        
    all_results = []
    page = 1
    
    while True:
        current_params = {**params, "page": page}
        response = await make_canvas_request("get", endpoint, params=current_params)
        
        if isinstance(response, dict) and "error" in response:
            print(f"Error fetching page {page}: {response['error']}", file=sys.stderr)
            return response
            
        if not response or not isinstance(response, list) or len(response) == 0:
            break
            
        all_results.extend(response)
        
        # If we got fewer results than requested per page, we're done
        if len(response) < params.get("per_page", 100):
            break
            
        page += 1
        
    return all_results

async def refresh_course_cache() -> bool:
    """Refresh the global course cache."""
    global course_code_to_id_cache, id_to_course_code_cache
    
    print("Refreshing course cache...", file=sys.stderr)
    courses = await fetch_all_paginated_results("/courses", {"per_page": 100})
    
    if isinstance(courses, dict) and "error" in courses:
        print(f"Error building course cache: {courses.get('error')}", file=sys.stderr)
        return False
        
    # Build caches for bidirectional lookups
    course_code_to_id_cache = {}
    id_to_course_code_cache = {}
    
    for course in courses:
        course_id = str(course.get("id"))
        course_code = course.get("course_code")
        
        if course_code and course_id:
            course_code_to_id_cache[course_code] = course_id
            id_to_course_code_cache[course_id] = course_code
    
    print(f"Cached {len(course_code_to_id_cache)} course codes", file=sys.stderr)
    return True

@validate_params
async def get_course_id(course_identifier: Union[str, int]) -> Optional[str]:
    """Get course ID from either course code or ID, with caching.
    
    Args:
        course_identifier: The course identifier, which can be:
                          - A course code (e.g., 'badm_554_120251_246794')
                          - A numeric course ID (as string or int)
                          - A SIS ID format (e.g., 'sis_course_id:xxx')
    
    Returns:
        The course ID as a string
    """
    global course_code_to_id_cache, id_to_course_code_cache
    
    # Convert to string for consistent handling
    course_str = str(course_identifier)
    
    # If it looks like a numeric ID
    if course_str.isdigit():
        return course_str
    
    # If it's a SIS ID format
    if course_str.startswith("sis_course_id:"):
        return course_str
    
    # If it's in our cache, return the ID
    if course_str in course_code_to_id_cache:
        return course_code_to_id_cache[course_str]
    
    # If it looks like a course code (contains underscores)
    if "_" in course_str:
        # Try to refresh cache if it's not there
        if not course_code_to_id_cache:
            await refresh_course_cache()
            if course_str in course_code_to_id_cache:
                return course_code_to_id_cache[course_str]
        
        # Return SIS format as a fallback
        return f"sis_course_id:{course_str}"
    
    # Last resort, return as is
    return course_str

async def get_course_code(course_id: str) -> Optional[str]:
    """Get course code from ID, with caching."""
    global id_to_course_code_cache
    
    # If it's already a code-like string with underscores
    if "_" in course_id:
        return course_id
    
    # If it's in our cache, return the code
    if course_id in id_to_course_code_cache:
        return id_to_course_code_cache[course_id]
    
    # Try to refresh cache if it's not there
    if not id_to_course_code_cache:
        await refresh_course_cache()
        if course_id in id_to_course_code_cache:
            return id_to_course_code_cache[course_id]
    
    # If we can't find a code, try to fetch the course directly
    response = await make_canvas_request("get", f"/courses/{course_id}")
    if "error" not in response and "course_code" in response:
        code = response.get("course_code")
        # Update our cache
        id_to_course_code_cache[course_id] = code
        course_code_to_id_cache[code] = course_id
        return code
    
    # Last resort, return the ID
    return course_id

# ===== COURSES TOOLS =====

@mcp.tool()
async def list_courses(include_concluded: bool = False, include_all: bool = False) -> str:
    """List courses for the authenticated user."""
    
    params = {
        "include[]": ["term", "teachers", "total_students"],
        "per_page": 100
    }
    
    if not include_all:
        params["enrollment_type"] = "teacher"
    
    if include_concluded:
        params["state[]"] = ["available", "completed"]
    else:
        params["state[]"] = ["available"]
    
    courses = await fetch_all_paginated_results("/courses", params)
    
    if isinstance(courses, dict) and "error" in courses:
        return f"Error fetching courses: {courses['error']}"
    
    if not courses:
        return "No courses found."
    
    # Refresh our caches with the course data
    for course in courses:
        course_id = str(course.get("id"))
        course_code = course.get("course_code")
        
        if course_code and course_id:
            course_code_to_id_cache[course_code] = course_id
            id_to_course_code_cache[course_id] = course_code
    
    courses_info = []
    for course in courses:
        course_id = course.get("id")
        name = course.get("name", "Unnamed course")
        code = course.get("course_code", "No code")
        
        # Emphasize code in the output
        courses_info.append(f"Code: {code}\nName: {name}\nID: {course_id}\n")
    
    return "Courses:\n\n" + "\n".join(courses_info)

@mcp.tool()
@validate_params
async def get_course_details(course_identifier: Union[str, int]) -> str:
    """Get detailed information about a specific course.
    
    Args:
        course_identifier: The Canvas course code (e.g., badm_554_120251_246794) or ID
    """
    course_id = await get_course_id(course_identifier)
    
    response = await make_canvas_request("get", f"/courses/{course_id}")
    
    if "error" in response:
        return f"Error fetching course details: {response['error']}"
    
    # Update our caches with the course data
    if "id" in response and "course_code" in response:
        course_code_to_id_cache[response["course_code"]] = str(response["id"])
        id_to_course_code_cache[str(response["id"])] = response["course_code"]
    
    details = [
        f"Code: {response.get('course_code', 'N/A')}",
        f"Name: {response.get('name', 'N/A')}",
        f"Start Date: {format_date(response.get('start_at'))}",
        f"End Date: {format_date(response.get('end_at'))}",
        f"Time Zone: {response.get('time_zone', 'N/A')}",
        f"Default View: {response.get('default_view', 'N/A')}",
        f"Public: {response.get('is_public', False)}",
        f"Blueprint: {response.get('blueprint', False)}"
    ]
    
    # Prefer to show course code in the output
    course_display = response.get("course_code", course_identifier)
    return f"Course Details for {course_display}:\n\n" + "\n".join(details)

# ===== ASSIGNMENTS TOOLS =====

@mcp.tool()
@validate_params
async def list_assignments(course_identifier: Union[str, int]) -> str:
    """List assignments for a specific course.
    
    Args:
        course_identifier: The Canvas course code (e.g., badm_554_120251_246794) or ID
    """
    course_id = await get_course_id(course_identifier)
    
    params = {
        "per_page": 100,
        "include[]": ["all_dates", "submission"]
    }
    
    all_assignments = await fetch_all_paginated_results(f"/courses/{course_id}/assignments", params)
    
    if isinstance(all_assignments, dict) and "error" in all_assignments:
        return f"Error fetching assignments: {all_assignments['error']}"
    
    if not all_assignments:
        return f"No assignments found for course {course_identifier}."
    
    assignments_info = []
    for assignment in all_assignments:
        assignment_id = assignment.get("id")
        name = assignment.get("name", "Unnamed assignment")
        due_at = assignment.get("due_at", "No due date")
        points = assignment.get("points_possible", 0)
        
        assignments_info.append(
            f"ID: {assignment_id}\nName: {name}\nDue: {due_at}\nPoints: {points}\n"
        )
    
    # Try to get the course code for display
    course_display = await get_course_code(course_id) or course_identifier
    return f"Assignments for Course {course_display}:\n\n" + "\n".join(assignments_info)


@mcp.tool()
@validate_params
async def get_assignment_details(course_identifier: Union[str, int], assignment_id: Union[str, int]) -> str:
    """Get detailed information about a specific assignment.
    
    Args:
        course_identifier: The Canvas course code (e.g., badm_554_120251_246794) or ID
        assignment_id: The Canvas assignment ID
    """
    course_id = await get_course_id(course_identifier)
    
    # Ensure assignment_id is a string
    assignment_id_str = str(assignment_id)
    
    response = await make_canvas_request(
        "get", f"/courses/{course_id}/assignments/{assignment_id_str}"
    )
    
    if "error" in response:
        return f"Error fetching assignment details: {response['error']}"
    
    details = [
        f"Name: {response.get('name', 'N/A')}",
        f"Description: {truncate_text(response.get('description', 'N/A'), 300)}",
        f"Due Date: {format_date(response.get('due_at'))}",
        f"Points Possible: {response.get('points_possible', 'N/A')}",
        f"Submission Types: {', '.join(response.get('submission_types', ['N/A']))}",
        f"Published: {response.get('published', False)}",
        f"Locked: {response.get('locked_for_user', False)}"
    ]
    
    # Try to get the course code for display
    course_display = await get_course_code(course_id) or course_identifier
    return f"Assignment Details for ID {assignment_id} in course {course_display}:\n\n" + "\n".join(details)

@mcp.tool()
async def assign_peer_review(course_identifier: str, assignment_id: str, reviewer_id: str, reviewee_id: str) -> str:
    """Manually assign a peer review to a student for a specific assignment.
    
    Args:
        course_identifier: The Canvas course code (e.g., badm_554_120251_246794) or ID
        assignment_id: The Canvas assignment ID
        reviewer_id: The Canvas user ID of the student who will do the review
        reviewee_id: The Canvas user ID of the student whose submission will be reviewed
    """
    course_id = await get_course_id(course_identifier)
    
    # First, we need to get the submission ID for the reviewee
    submissions = await make_canvas_request(
        "get", 
        f"/courses/{course_id}/assignments/{assignment_id}/submissions",
        params={"per_page": 100}
    )
    
    if "error" in submissions:
        return f"Error fetching submissions: {submissions['error']}"
    
    # Find the submission for the reviewee
    reviewee_submission = None
    for submission in submissions:
        if str(submission.get("user_id")) == str(reviewee_id):
            reviewee_submission = submission
            break
    
    # If no submission exists, we need to create a placeholder submission
    if not reviewee_submission:
        # Create a placeholder submission for the reviewee
        placeholder_data = {
            "submission": {
                "user_id": reviewee_id,
                "submission_type": "online_text_entry",
                "body": "Placeholder submission for peer review"
            }
        }
        
        reviewee_submission = await make_canvas_request(
            "post",
            f"/courses/{course_id}/assignments/{assignment_id}/submissions",
            data=placeholder_data
        )
        
        if "error" in reviewee_submission:
            return f"Error creating placeholder submission: {reviewee_submission['error']}"
    
    # Now assign the peer review using the submission ID
    submission_id = reviewee_submission.get("id")
    
    # Data for the peer review assignment
    data = {
        "user_id": reviewer_id  # The user who will do the review
    }
    
    # Make the API request to create the peer review
    response = await make_canvas_request(
        "post", 
        f"/courses/{course_id}/assignments/{assignment_id}/submissions/{submission_id}/peer_reviews",
        data=data
    )
    
    if "error" in response:
        return f"Error assigning peer review: {response['error']}"
    
    # Try to get the course code for display
    course_display = await get_course_code(course_id) or course_identifier
    
    return f"Successfully assigned peer review in course {course_display}:\n" + \
           f"Assignment ID: {assignment_id}\n" + \
           f"Reviewer ID: {reviewer_id}\n" + \
           f"Reviewee ID: {reviewee_id}\n" + \
           f"Submission ID: {submission_id}"

@mcp.tool()
async def list_peer_reviews(course_identifier: str, assignment_id: str) -> str:
    """List all peer review assignments for a specific assignment.
    
    Args:
        course_identifier: The Canvas course code (e.g., badm_554_120251_246794) or ID
        assignment_id: The Canvas assignment ID
    """
    course_id = await get_course_id(course_identifier)
    
    # Get all submissions for this assignment
    submissions = await fetch_all_paginated_results(
        f"/courses/{course_id}/assignments/{assignment_id}/submissions",
        {"include[]": "submission_comments", "per_page": 100}
    )
    
    if isinstance(submissions, dict) and "error" in submissions:
        return f"Error fetching submissions: {submissions['error']}"
    
    if not submissions:
        return f"No submissions found for assignment {assignment_id}."
    
    # Get all users in the course for name lookups
    users = await fetch_all_paginated_results(
        f"/courses/{course_id}/users",
        {"per_page": 100}
    )
    
    if isinstance(users, dict) and "error" in users:
        return f"Error fetching users: {users['error']}"
    
    # Create a mapping of user IDs to names
    user_map = {}
    for user in users:
        user_id = str(user.get("id"))
        user_name = user.get("name", "Unknown")
        user_map[user_id] = user_name
    
    # Collect peer review data
    peer_reviews_by_submission = {}
    
    for submission in submissions:
        submission_id = submission.get("id")
        user_id = str(submission.get("user_id"))
        user_name = user_map.get(user_id, f"User {user_id}")
        
        # Get peer reviews for this submission
        peer_reviews = await make_canvas_request(
            "get",
            f"/courses/{course_id}/assignments/{assignment_id}/submissions/{submission_id}/peer_reviews"
        )
        
        if "error" in peer_reviews:
            continue  # Skip if error
        
        if peer_reviews:
            peer_reviews_by_submission[submission_id] = {
                "user_id": user_id,
                "user_name": user_name,
                "peer_reviews": peer_reviews
            }
    
    # Format the output
    course_display = await get_course_code(course_id) or course_identifier
    output = f"Peer Reviews for Assignment {assignment_id} in course {course_display}:\n\n"
    
    if not peer_reviews_by_submission:
        output += "No peer reviews found for this assignment."
        return output
    
    # Display peer reviews grouped by reviewee
    for submission_id, data in peer_reviews_by_submission.items():
        reviewee_name = data["user_name"]
        reviewee_id = data["user_id"]
        reviews = data["peer_reviews"]
        
        output += f"Reviews for {reviewee_name} (ID: {reviewee_id}):\n"
        
        if not reviews:
            output += "  No peer reviews assigned.\n\n"
            continue
        
        for review in reviews:
            reviewer_id = str(review.get("user_id"))
            reviewer_name = user_map.get(reviewer_id, f"User {reviewer_id}")
            workflow_state = review.get("workflow_state", "Unknown")
            
            output += f"  Reviewer: {reviewer_name} (ID: {reviewer_id})\n"
            output += f"  Status: {workflow_state}\n"
            
            # Add assessment details if available
            if "assessment" in review and review["assessment"]:
                assessment = review["assessment"]
                score = assessment.get("score")
                if score is not None:
                    output += f"  Score: {score}\n"
            
            output += "\n"
    
    return output

# ===== SUBMISSIONS TOOLS =====

@mcp.tool()
@validate_params
async def list_submissions(course_identifier: Union[str, int], assignment_id: Union[str, int]) -> str:
    """List submissions for a specific assignment.
    
    Args:
        course_identifier: The Canvas course code (e.g., badm_554_120251_246794) or ID
        assignment_id: The Canvas assignment ID
    """
    course_id = await get_course_id(course_identifier)
    
    # Ensure assignment_id is a string
    assignment_id_str = str(assignment_id)
    
    params = {
        "per_page": 100
    }
    
    submissions = await fetch_all_paginated_results(
        f"/courses/{course_id}/assignments/{assignment_id_str}/submissions", params
    )
    
    if isinstance(submissions, dict) and "error" in submissions:
        return f"Error fetching submissions: {submissions['error']}"
    
    if not submissions:
        return f"No submissions found for assignment {assignment_id}."
    
    submissions_info = []
    for submission in submissions:
        user_id = submission.get("user_id")
        submitted_at = submission.get("submitted_at", "Not submitted")
        score = submission.get("score", "Not graded")
        grade = submission.get("grade", "Not graded")
        
        submissions_info.append(
            f"User ID: {user_id}\nSubmitted: {submitted_at}\nScore: {score}\nGrade: {grade}\n"
        )
    
    # Try to get the course code for display
    course_display = await get_course_code(course_id) or course_identifier
    return f"Submissions for Assignment {assignment_id} in course {course_display}:\n\n" + "\n".join(submissions_info)

# ===== USERS TOOLS =====

@mcp.tool()
async def list_users(course_identifier: str) -> str:
    """List users enrolled in a specific course.
    
    Args:
        course_identifier: The Canvas course code (e.g., badm_554_120251_246794) or ID
    """
    course_id = await get_course_id(course_identifier)
    
    params = {
        "per_page": 100
    }
    
    users = await fetch_all_paginated_results(f"/courses/{course_id}/users", params)
    
    if isinstance(users, dict) and "error" in users:
        return f"Error fetching users: {users['error']}"
    
    if not users:
        return f"No users found for course {course_identifier}."
    
    users_info = []
    for user in users:
        user_id = user.get("id")
        name = user.get("name", "Unnamed user")
        email = user.get("email", "No email")
        
        users_info.append(f"ID: {user_id}\nName: {name}\nEmail: {email}\n")
    
    # Try to get the course code for display
    course_display = await get_course_code(course_id) or course_identifier
    return f"Users for Course {course_display}:\n\n" + "\n".join(users_info)

# ===== ANNOUNCEMENTS TOOLS =====

@mcp.tool()
async def list_announcements(course_identifier: str) -> str:
    """List announcements for a specific course.
    
    Args:
        course_identifier: The Canvas course code (e.g., badm_554_120251_246794) or ID
    """
    course_id = await get_course_id(course_identifier)
    
    params = {
        "only_announcements": "true",
        "per_page": 100
    }
    
    announcements = await fetch_all_paginated_results(
        f"/courses/{course_id}/discussion_topics", params
    )
    
    if isinstance(announcements, dict) and "error" in announcements:
        return f"Error fetching announcements: {announcements['error']}"
    
    if not announcements:
        return f"No announcements found for course {course_identifier}."
    
    announcements_info = []
    for announcement in announcements:
        title = announcement.get("title", "Untitled")
        posted_at = announcement.get("posted_at")
        delayed_post_at = announcement.get("delayed_post_at")
        author = announcement.get("author", {}).get("display_name", "Unknown")
        published = announcement.get("published", True)
        lock_at = announcement.get("lock_at")
        
        # Determine announcement status and timing
        status_info = []
        time_info = ""
        
        if delayed_post_at:
            # Scheduled announcement
            scheduled_time = format_date(delayed_post_at)
            time_info = f"Scheduled: {scheduled_time}"
            status_info.append("SCHEDULED")
        elif posted_at:
            # Posted announcement
            posted_time = format_date(posted_at)
            time_info = f"Posted: {posted_time}"
        else:
            # Draft announcement
            time_info = "Status: Draft"
            status_info.append("DRAFT")
        
        if not published:
            status_info.append("UNPUBLISHED")
            
        if lock_at:
            lock_time = format_date(lock_at)
            if lock_time != "N/A":
                status_info.append(f"LOCKS: {lock_time}")
        
        # Build status string
        status_str = f" [{', '.join(status_info)}]" if status_info else ""
        
        announcements_info.append(
            f"Title: {title}{status_str}\n{time_info}\nAuthor: {author}\n"
        )
    
    # Try to get the course code for display
    course_display = await get_course_code(course_id) or course_identifier
    return f"Announcements for Course {course_display}:\n\n" + "\n".join(announcements_info)

@mcp.tool()
@validate_params
async def create_announcement(course_identifier: Union[str, int], 
                            title: str, 
                            message: str,
                            delayed_post_at: Optional[str] = None,
                            lock_at: Optional[str] = None) -> str:
    """Create a new announcement for a course with optional scheduling.
    
    Args:
        course_identifier: The Canvas course code (e.g., badm_554_120251_246794) or ID
        title: The title/subject of the announcement
        message: The content/body of the announcement
        delayed_post_at: Optional ISO 8601 datetime to schedule posting (e.g., "2024-01-15T12:00:00Z")
        lock_at: Optional ISO 8601 datetime to automatically lock the announcement
    """
    course_id = await get_course_id(course_identifier)
    
    data = {
        "title": title,
        "message": message,
        "is_announcement": True,
        "published": True
    }
    
    if delayed_post_at:
        data["delayed_post_at"] = delayed_post_at
    
    if lock_at:
        data["lock_at"] = lock_at
    
    response = await make_canvas_request(
        "post", f"/courses/{course_id}/discussion_topics", data=data
    )
    
    if "error" in response:
        return f"Error creating announcement: {response['error']}"
    
    # Extract response details
    announcement_id = response.get("id")
    announcement_title = response.get("title", title)
    created_at = format_date(response.get("created_at"))
    posted_at = format_date(response.get("posted_at"))
    delayed_post_at_response = format_date(response.get("delayed_post_at"))
    
    # Build response message
    course_display = await get_course_code(course_id) or course_identifier
    result = f"Announcement created successfully in course {course_display}:\n\n"
    result += f"ID: {announcement_id}\n"
    result += f"Title: {announcement_title}\n"
    result += f"Created: {created_at}\n"
    
    if delayed_post_at_response and delayed_post_at_response != "N/A":
        result += f"Scheduled to post: {delayed_post_at_response}\n"
        result += f"Status: Scheduled\n"
    else:
        result += f"Posted: {posted_at}\n"
        result += f"Status: Published\n"
    
    if lock_at:
        lock_at_formatted = format_date(response.get("lock_at"))
        if lock_at_formatted != "N/A":
            result += f"Will lock: {lock_at_formatted}\n"
    
    return result


# ===== GROUPS TOOLS =====

@mcp.tool()
@validate_params
async def list_groups(course_identifier: Union[str, int]) -> str:
    """List all groups and their members for a specific course.
    
    Args:
        course_identifier: The Canvas course code (e.g., badm_554_120251_246794) or ID
    """
    course_id = await get_course_id(course_identifier)
    
    # Get all groups in the course
    groups = await fetch_all_paginated_results(
        f"/courses/{course_id}/groups", {"per_page": 100}
    )
    
    if isinstance(groups, dict) and "error" in groups:
        return f"Error fetching groups: {groups['error']}"
    
    if not groups:
        return f"No groups found for course {course_identifier}."
    
    # Format the output
    course_display = await get_course_code(course_id) or course_identifier
    output = f"Groups for Course {course_display}:\n\n"
    
    for group in groups:
        group_id = group.get("id")
        group_name = group.get("name", "Unnamed group")
        group_category = group.get("group_category_id", "Uncategorized")
        member_count = group.get("members_count", 0)
        
        output += f"Group: {group_name}\n"
        output += f"ID: {group_id}\n"
        output += f"Category ID: {group_category}\n"
        output += f"Member Count: {member_count}\n"
        
        # Get members for this group
        members = await fetch_all_paginated_results(
            f"/groups/{group_id}/users", {"per_page": 100}
        )
        
        if isinstance(members, dict) and "error" in members:
            output += f"Error fetching members: {members['error']}\n"
        elif not members:
            output += "No members in this group.\n"
        else:
            output += "Members:\n"
            for member in members:
                member_id = member.get("id")
                member_name = member.get("name", "Unnamed user")
                member_email = member.get("email", "No email")
                
                output += f"  - {member_name} (ID: {member_id})\n"
        
        output += "\n"
    
    return output

# ===== ANALYTICS TOOLS =====

@mcp.tool()
async def get_student_analytics(course_identifier: str, 
                               current_only: bool = True,
                               include_participation: bool = True, 
                               include_assignment_stats: bool = True, 
                               include_access_stats: bool = True) -> str:
    """Get detailed analytics about student activity, participation, and progress in a course.
    
    Args:
        course_identifier: The Canvas course code (e.g., badm_554_120251_246794) or ID
        current_only: Whether to include only assignments due on or before today
        include_participation: Whether to include participation data (discussions, submissions)
        include_assignment_stats: Whether to include assignment completion statistics
        include_access_stats: Whether to include course access statistics
    """
    import datetime
    
    course_id = await get_course_id(course_identifier)
    
    # Get current date for filtering assignments
    today = datetime.datetime.now().isoformat()
    
    # Get all students in the course
    params = {
        "enrollment_type[]": "student",
        "per_page": 100
    }
    
    students = await fetch_all_paginated_results(
        f"/courses/{course_id}/users", params
    )
    
    if isinstance(students, dict) and "error" in students:
        return f"Error fetching students: {students['error']}"
    
    if not students:
        return f"No students found for course {course_identifier}."
    
    # Get all assignments in the course
    assignments = await fetch_all_paginated_results(
        f"/courses/{course_id}/assignments", {"per_page": 100}
    )
    
    if isinstance(assignments, dict) and "error" in assignments:
        return f"Error fetching assignments: {assignments['error']}"
    
    # Filter assignments to only include those due on or before today if current_only is True
    current_assignments = []
    future_assignments = []
    
    for assignment in assignments:
        due_at = assignment.get("due_at")
        
        # Skip assignments with no due date if filtering by current
        if current_only and not due_at:
            continue
            
        if due_at and due_at <= today:
            current_assignments.append(assignment)
        else:
            future_assignments.append(assignment)
    
    if current_only:
        filtered_assignments = current_assignments
    else:
        filtered_assignments = assignments
    
    # For each student, gather analytics
    student_analytics = []
    
    for student in students:
        student_id = student.get("id")
        student_name = student.get("name", "Unknown")
        
        analytics = {
            "id": student_id,
            "name": student_name,
            "participation": {},
            "assignments": {},
            "access": {}
        }
        
        # Get student analytics data
        if include_participation or include_access_stats:
            participation_data = await make_canvas_request(
                "get", f"/courses/{course_id}/analytics/users/{student_id}/activity"
            )
            if not isinstance(participation_data, dict) or "error" not in participation_data:
                if include_participation:
                    analytics["participation"] = {
                        "page_views": participation_data.get("page_views", 0),
                        "participations": participation_data.get("participations", 0),
                        "total_activity_time": participation_data.get("total_activity_time", 0)
                    }
                
                if include_access_stats:
                    # Extract view data by date if available
                    view_data = participation_data.get("page_views_by_day", {})
                    analytics["access"] = {
                        "last_access": "Unknown",
                        "access_count": sum(view_data.values()) if view_data else 0,
                        "access_pattern": "Regular" if len(view_data) > 5 else "Irregular"
                    }
                    
                    # Determine last access date
                    if view_data:
                        dates = sorted(view_data.keys(), reverse=True)
                        if dates:
                            analytics["access"]["last_access"] = dates[0]
        
        # Get assignment statistics
        if include_assignment_stats:
            assignment_data = await make_canvas_request(
                "get", f"/courses/{course_id}/analytics/users/{student_id}/assignments"
            )
            
            if not isinstance(assignment_data, dict) or "error" not in assignment_data:
                # Filter assignment data to match our filtered assignments
                if current_only:
                    filtered_assignment_data = []
                    for assign in assignment_data:
                        assignment_id = assign.get("assignment_id")
                        
                        # Check if this assignment is in our filtered list
                        if any(a.get("id") == assignment_id for a in current_assignments):
                            filtered_assignment_data.append(assign)
                else:
                    filtered_assignment_data = assignment_data
                
                # Process assignment data
                submitted_count = 0
                late_count = 0
                missing_count = 0
                graded_count = 0
                score_sum = 0
                recent_missing = 0  # Missing in last 7 days
                
                # Track the status of each assignment
                assignment_status = []
                
                for assign in filtered_assignment_data:
                    assign_id = assign.get("assignment_id")
                    assign_name = "Unknown"
                    due_date = None
                    points_possible = 0
                    
                    # Find the assignment details
                    for a in filtered_assignments:
                        if a.get("id") == assign_id:
                            assign_name = a.get("name", "Unknown")
                            due_date = a.get("due_at")
                            points_possible = a.get("points_possible", 0)
                            break
                    
                    submission = assign.get("submission", {})
                    
                    # IMPORTANT: In Canvas, an assignment can be graded without being "submitted"
                    # We'll consider an assignment as effectively submitted if it has a score
                    has_score = submission.get("score") is not None
                    is_submitted = submission.get("submitted", False) or has_score
                    
                    status = {
                        "id": assign_id,
                        "name": assign_name,
                        "due_date": due_date,
                        "points_possible": points_possible,
                        "submitted": is_submitted,
                        "score": submission.get("score"),
                        "late": submission.get("late", False),
                        "missing": submission.get("missing", False) and not has_score,
                        "workflow_state": submission.get("workflow_state", "unsubmitted"),
                        "graded": has_score
                    }
                    
                    assignment_status.append(status)
                    
                    if is_submitted:
                        submitted_count += 1
                    if submission.get("late"):
                        late_count += 1
                    # Only count as missing if it doesn't have a score
                    if submission.get("missing") and not has_score:
                        missing_count += 1
                        
                        # Check if the assignment was due in the last 7 days
                        if due_date:
                            due_date_obj = datetime.datetime.fromisoformat(due_date.replace('Z', '+00:00'))
                            now = datetime.datetime.now(datetime.timezone.utc)
                            if (now - due_date_obj).days <= 7:
                                recent_missing += 1
                                
                    if has_score:
                        graded_count += 1
                        score_sum += submission.get("score", 0)
                
                # Calculate statistics
                total_assignments = len(filtered_assignment_data) if filtered_assignment_data else 0
                
                # Use graded count for completion if it's higher than submitted count
                # This handles the case where assignments are graded but not marked as "submitted"
                effective_submitted = max(submitted_count, graded_count)
                completion_rate = (effective_submitted / total_assignments * 100) if total_assignments > 0 else 0
                average_score = (score_sum / graded_count) if graded_count > 0 else 0
                
                analytics["assignments"] = {
                    "total": total_assignments,
                    "submitted": submitted_count,
                    "graded": graded_count,
                    "effective_submitted": effective_submitted,
                    "completion_rate": round(completion_rate, 1),
                    "late": late_count,
                    "missing": missing_count,
                    "recent_missing": recent_missing,
                    "average_score": round(average_score, 1),
                    "assignment_status": assignment_status
                }
        
        student_analytics.append(analytics)
    
    # Format the response
    course_display = await get_course_code(course_id) or course_identifier
    if current_only:
        output = f"Current Assignment Analytics for Course {course_display} (Due on or before today):\n\n"
    else:
        output = f"Student Analytics for Course {course_display} (All assignments):\n\n"
    
    # Add assignment statistics
    if current_only and filtered_assignments:
        output += f"Current Assignments: {len(filtered_assignments)}\n"
        output += f"Future Assignments: {len(future_assignments)}\n\n"
    
    # Per-student analytics
    for student in student_analytics:
        output += f"Student: {student['name']}\n"
        
        if include_participation and student.get("participation"):
            p = student["participation"]
            output += f"Participation: {p.get('participations', 0)} activities, {p.get('page_views', 0)} page views\n"
        
        if include_assignment_stats and student.get("assignments"):
            a = student["assignments"]
            if current_only:
                output += f"Current Assignments: {a.get('effective_submitted', 0)}/{a.get('total', 0)} completed ({a.get('completion_rate', 0)}%)\n"
                output += f"  Formally Submitted: {a.get('submitted', 0)}, Graded: {a.get('graded', 0)}\n"
                output += f"  Late: {a.get('late', 0)}, Missing: {a.get('missing', 0)} (Recent: {a.get('recent_missing', 0)})\n"
                output += f"  Avg Score: {a.get('average_score', 0)}\n"
                
                # Add missing assignments detail if there are any
                if a.get("missing", 0) > 0 and a.get("assignment_status"):
                    missing_assignments = [ass for ass in a.get("assignment_status", []) if ass.get("missing")]
                    if missing_assignments:
                        output += "  Missing Assignments:\n"
                        for ma in missing_assignments[:3]:  # Limit to first 3 to keep output reasonable
                            due_date = ma.get("due_date", "Unknown")
                            if due_date and due_date != "Unknown":
                                due_date = due_date.split('T')[0]  # Just show the date part
                            output += f"    - {ma.get('name')} (Due: {due_date})\n"
                        if len(missing_assignments) > 3:
                            output += f"    - ... and {len(missing_assignments) - 3} more\n"
            else:
                output += f"Assignments: {a.get('submitted', 0)}/{a.get('total', 0)} submitted ({a.get('completion_rate', 0)}%)\n"
                output += f"  Late: {a.get('late', 0)}, Missing: {a.get('missing', 0)}, Avg Score: {a.get('average_score', 0)}\n"
        
        if include_access_stats and student.get("access"):
            a = student["access"]
            output += f"Access: Last seen {a.get('last_access', 'Unknown')}, Pattern: {a.get('access_pattern', 'Unknown')}\n"
        
        output += "\n"
    
    # Add summary statistics
    if include_assignment_stats and student_analytics:
        avg_completion = sum(s["assignments"].get("completion_rate", 0) for s in student_analytics) / len(student_analytics) if student_analytics else 0
        avg_graded = sum(s["assignments"].get("graded", 0) for s in student_analytics) / len(student_analytics) if student_analytics else 0
        avg_score = sum(s["assignments"].get("average_score", 0) for s in student_analytics) / len(student_analytics) if student_analytics else 0
        
        output += f"\nClass Summary:\n"
        
        if current_only:
            total_students = len(student_analytics)
            total_current_assignments = len(filtered_assignments) if filtered_assignments else 0
            
            # Calculate global stats
            graded_count = sum(s["assignments"].get("graded", 0) for s in student_analytics)
            submitted_count = sum(s["assignments"].get("submitted", 0) for s in student_analytics)
            effective_count = sum(s["assignments"].get("effective_submitted", 0) for s in student_analytics)
            missing_count = sum(s["assignments"].get("missing", 0) for s in student_analytics)
            
            # Calculate maximum possible number of all student/assignment combinations
            total_possible = total_students * total_current_assignments if total_current_assignments > 0 else 0
            
            output += f"Average Current Assignment Completion Rate: {round(avg_completion, 1)}%\n"
            output += f"Average Graded Assignments Per Student: {round(avg_graded, 1)}\n"
            output += f"Class Average Score: {round(avg_score, 1)}\n"
            
            if total_possible > 0:
                output += f"\nGlobal Stats:\n"
                output += f"  Total Students: {total_students}\n"
                output += f"  Current Assignments: {total_current_assignments}\n"
                output += f"  Formally Submitted: {submitted_count}/{total_possible} ({round(submitted_count/total_possible*100, 1)}%)\n"
                output += f"  Graded: {graded_count}/{total_possible} ({round(graded_count/total_possible*100, 1)}%)\n"
                output += f"  Effective Completion: {effective_count}/{total_possible} ({round(effective_count/total_possible*100, 1)}%)\n"
                output += f"  Missing: {missing_count}/{total_possible} ({round(missing_count/total_possible*100, 1)}%)\n"
        else:
            output += f"Average Assignment Completion Rate: {round(avg_completion, 1)}%\n"
            output += f"Average Graded Assignments Per Student: {round(avg_graded, 1)}\n"
            output += f"Class Average Score: {round(avg_score, 1)}\n"
        
        # Find assignments with lowest completion rates
        if filtered_assignments:
            assignment_completion = {}
            assignment_due_dates = {}
            
            for assignment in filtered_assignments:
                assignment_id = assignment.get("id")
                assignment_name = assignment.get("name", "Unknown")
                assignment_due_date = assignment.get("due_at", "Unknown")
                if assignment_due_date and assignment_due_date != "Unknown":
                    assignment_due_date = assignment_due_date.split('T')[0]  # Just show the date part
                
                # Count submissions for this assignment
                submission_count = 0
                total_students = len(student_analytics)
                
                for student in student_analytics:
                    # Look for this specific assignment in the student's assignment status
                    if "assignments" in student and "assignment_status" in student["assignments"]:
                        for status in student["assignments"]["assignment_status"]:
                            if status.get("id") == assignment_id and status.get("submitted"):
                                submission_count += 1
                                break
                
                completion_rate = (submission_count / total_students * 100) if total_students > 0 else 0
                assignment_completion[assignment_name] = completion_rate
                assignment_due_dates[assignment_name] = assignment_due_date
            
            # Get assignments with lowest completion rates
            lowest_completion = sorted(assignment_completion.items(), key=lambda x: x[1])[:3]
            if lowest_completion:
                output += "\nAssignments with Lowest Completion Rates:\n"
                for name, rate in lowest_completion:
                    due_date = assignment_due_dates.get(name, "Unknown")
                    output += f"  {name} (Due: {due_date}): {round(rate, 1)}% completion\n"
    
    return output

@mcp.tool()
@validate_params
async def get_assignment_analytics(course_identifier: Union[str, int], assignment_id: Union[str, int]) -> str:
    """Get detailed analytics about student performance on a specific assignment.
    
    Args:
        course_identifier: The Canvas course code (e.g., badm_554_120251_246794) or ID
        assignment_id: The Canvas assignment ID
    """
    import datetime
    from statistics import mean, median, stdev
    
    course_id = await get_course_id(course_identifier)
    
    # Ensure assignment_id is a string
    assignment_id_str = str(assignment_id)
    
    # Get assignment details
    assignment = await make_canvas_request(
        "get", f"/courses/{course_id}/assignments/{assignment_id_str}"
    )
    
    if isinstance(assignment, dict) and "error" in assignment:
        return f"Error fetching assignment: {assignment['error']}"
    
    # Get all students in the course
    params = {
        "enrollment_type[]": "student",
        "per_page": 100
    }
    
    students = await fetch_all_paginated_results(
        f"/courses/{course_id}/users", params
    )
    
    if isinstance(students, dict) and "error" in students:
        return f"Error fetching students: {students['error']}"
    
    if not students:
        return f"No students found for course {course_identifier}."
    
    # Get submissions for this assignment
    submissions = await fetch_all_paginated_results(
        f"/courses/{course_id}/assignments/{assignment_id}/submissions", 
        {"per_page": 100, "include[]": ["user"]}
    )
    
    if isinstance(submissions, dict) and "error" in submissions:
        return f"Error fetching submissions: {submissions['error']}"
    
    # Extract assignment details
    assignment_name = assignment.get("name", "Unknown Assignment")
    assignment_description = assignment.get("description", "No description")
    due_date = assignment.get("due_at")
    points_possible = assignment.get("points_possible", 0)
    is_published = assignment.get("published", False)
    
    # Format the due date
    due_date_str = "No due date"
    if due_date:
        try:
            due_date_obj = datetime.datetime.fromisoformat(due_date.replace('Z', '+00:00'))
            due_date_str = due_date_obj.strftime("%Y-%m-%d %H:%M")
            now = datetime.datetime.now(datetime.timezone.utc)
            is_past_due = due_date_obj < now
        except (ValueError, AttributeError):
            due_date_str = due_date
            is_past_due = False
    else:
        is_past_due = False
    
    # Process submissions
    submission_stats = {
        "total_students": len(students),
        "submitted_count": 0,
        "missing_count": 0,
        "late_count": 0,
        "graded_count": 0,
        "excused_count": 0,
        "scores": [],
        "status_counts": {
            "submitted": 0,
            "unsubmitted": 0,
            "graded": 0,
            "pending_review": 0
        }
    }
    
    # Student status tracking
    student_status = []
    missing_students = []
    low_scoring_students = []
    high_scoring_students = []
    
    # Track which students have submissions
    student_ids_with_submissions = set()
    
    for submission in submissions:
        student_id = submission.get("user_id")
        student_ids_with_submissions.add(student_id)
        
        # Find student name
        student_name = "Unknown"
        for student in students:
            if student.get("id") == student_id:
                student_name = student.get("name", "Unknown")
                break
        
        # Process submission data
        score = submission.get("score")
        is_submitted = submission.get("submitted_at") is not None
        is_late = submission.get("late", False)
        is_missing = submission.get("missing", False)
        is_excused = submission.get("excused", False)
        is_graded = score is not None
        status = submission.get("workflow_state", "unsubmitted")
        submitted_at = submission.get("submitted_at")
        
        if submitted_at:
            try:
                submitted_at = datetime.datetime.fromisoformat(
                    submitted_at.replace('Z', '+00:00')
                ).strftime("%Y-%m-%d %H:%M")
            except (ValueError, AttributeError):
                pass
        
        # Update statistics
        if is_submitted:
            submission_stats["submitted_count"] += 1
        if is_late:
            submission_stats["late_count"] += 1
        if is_missing:
            submission_stats["missing_count"] += 1
            missing_students.append(student_name)
        if is_excused:
            submission_stats["excused_count"] += 1
        if is_graded:
            submission_stats["graded_count"] += 1
            submission_stats["scores"].append(score)
            
            # Track high/low scoring students
            if points_possible > 0:
                percentage = (score / points_possible) * 100
                if percentage < 70:
                    low_scoring_students.append((student_name, score, percentage))
                if percentage > 90:
                    high_scoring_students.append((student_name, score, percentage))
        
        # Update status counts
        if status in submission_stats["status_counts"]:
            submission_stats["status_counts"][status] += 1
        
        # Add to student status
        student_status.append({
            "name": student_name,
            "submitted": is_submitted,
            "submitted_at": submitted_at,
            "late": is_late,
            "missing": is_missing,
            "excused": is_excused,
            "score": score,
            "status": status
        })
    
    # Find students with no submissions
    for student in students:
        if student.get("id") not in student_ids_with_submissions:
            student_name = student.get("name", "Unknown")
            missing_students.append(student_name)
            
            # Add to student status
            student_status.append({
                "name": student_name,
                "submitted": False,
                "submitted_at": None,
                "late": False,
                "missing": True,
                "excused": False,
                "score": None,
                "status": "unsubmitted"
            })
    
    # Compute grade statistics
    scores = submission_stats["scores"]
    avg_score = mean(scores) if scores else 0
    median_score = median(scores) if scores else 0
    
    try:
        std_dev = stdev(scores) if len(scores) > 1 else 0
    except:
        std_dev = 0
    
    if points_possible > 0:
        avg_percentage = (avg_score / points_possible) * 100
    else:
        avg_percentage = 0
    
    # Format the output
    course_display = await get_course_code(course_id) or course_identifier
    output = f"Assignment Analytics for '{assignment_name}' in Course {course_display}\n\n"
    
    # Assignment details
    output += "Assignment Details:\n"
    output += f"  Due: {due_date_str}"
    if is_past_due:
        output += " (Past Due)"
    output += "\n"
    
    output += f"  Points Possible: {points_possible}\n"
    output += f"  Published: {'Yes' if is_published else 'No'}\n\n"
    
    # Submission statistics
    output += "Submission Statistics:\n"
    total_students = submission_stats["total_students"]
    submitted = submission_stats["submitted_count"]
    graded = submission_stats["graded_count"]
    missing = submission_stats["missing_count"] + (total_students - len(submissions))
    late = submission_stats["late_count"]
    
    # Calculate percentages
    submitted_pct = (submitted / total_students * 100) if total_students > 0 else 0
    graded_pct = (graded / total_students * 100) if total_students > 0 else 0
    missing_pct = (missing / total_students * 100) if total_students > 0 else 0
    late_pct = (late / submitted * 100) if submitted > 0 else 0
    
    output += f"  Submitted: {submitted}/{total_students} ({round(submitted_pct, 1)}%)\n"
    output += f"  Graded: {graded}/{total_students} ({round(graded_pct, 1)}%)\n"
    output += f"  Missing: {missing}/{total_students} ({round(missing_pct, 1)}%)\n"
    if submitted > 0:
        output += f"  Late: {late}/{submitted} ({round(late_pct, 1)}% of submissions)\n"
    output += f"  Excused: {submission_stats['excused_count']}\n\n"
    
    # Grade statistics
    if scores:
        output += "Grade Statistics:\n"
        output += f"  Average Score: {round(avg_score, 2)}/{points_possible} ({round(avg_percentage, 1)}%)\n"
        output += f"  Median Score: {round(median_score, 2)}/{points_possible} ({round((median_score/points_possible)*100, 1)}%)\n"
        output += f"  Standard Deviation: {round(std_dev, 2)}\n"
        
        # High/Low scores
        if low_scoring_students:
            output += "\nStudents Scoring Below 70%:\n"
            for name, score, percentage in sorted(low_scoring_students, key=lambda x: x[2]):
                output += f"  {name}: {round(score, 1)}/{points_possible} ({round(percentage, 1)}%)\n"
        
        if high_scoring_students:
            output += "\nStudents Scoring Above 90%:\n"
            for name, score, percentage in sorted(high_scoring_students, key=lambda x: x[2], reverse=True):
                output += f"  {name}: {round(score, 1)}/{points_possible} ({round(percentage, 1)}%)\n"
    
    # Missing students
    if missing_students:
        output += "\nStudents Missing Submission:\n"
        # Sort alphabetically and show first 10
        for name in sorted(missing_students)[:10]:
            output += f"  {name}\n"
        if len(missing_students) > 10:
            output += f"  ...and {len(missing_students) - 10} more\n"
    
    return output

# ===== PAGES TOOLS =====

@mcp.tool()
@validate_params
async def list_pages(course_identifier: Union[str, int], 
                    sort: Optional[str] = "title", 
                    order: Optional[str] = "asc",
                    search_term: Optional[str] = None,
                    published: Optional[bool] = None) -> str:
    """List pages for a specific course.
    
    Args:
        course_identifier: The Canvas course code (e.g., badm_554_120251_246794) or ID
        sort: Sort criteria ('title', 'created_at', 'updated_at')
        order: Sort order ('asc' or 'desc')
        search_term: Search for pages containing this term in title or body
        published: Filter by published status (True, False, or None for all)
    """
    course_id = await get_course_id(course_identifier)
    
    params = {
        "per_page": 100
    }
    
    if sort:
        params["sort"] = sort
    if order:
        params["order"] = order
    if search_term:
        params["search_term"] = search_term
    if published is not None:
        params["published"] = str(published).lower()
    
    pages = await fetch_all_paginated_results(f"/courses/{course_id}/pages", params)
    
    if isinstance(pages, dict) and "error" in pages:
        return f"Error fetching pages: {pages['error']}"
    
    if not pages:
        return f"No pages found for course {course_identifier}."
    
    pages_info = []
    for page in pages:
        page_id = page.get("page_id", "N/A")
        url = page.get("url", "N/A")
        title = page.get("title", "Untitled")
        created_at = format_date(page.get("created_at"))
        updated_at = format_date(page.get("updated_at"))
        published_status = page.get("published", False)
        front_page = page.get("front_page", False)
        
        status_indicators = []
        if front_page:
            status_indicators.append("FRONT PAGE")
        if not published_status:
            status_indicators.append("UNPUBLISHED")
        
        status_str = f" [{', '.join(status_indicators)}]" if status_indicators else ""
        
        pages_info.append(
            f"URL: {url}\n"
            f"Title: {title}{status_str}\n"
            f"ID: {page_id}\n"
            f"Created: {created_at}\n"
            f"Updated: {updated_at}\n"
        )
    
    # Try to get the course code for display
    course_display = await get_course_code(course_id) or course_identifier
    return f"Pages for Course {course_display}:\n\n" + "\n".join(pages_info)

@mcp.tool()
@validate_params  
async def get_page_details(course_identifier: Union[str, int], page_url_or_id: str) -> str:
    """Get detailed information about a specific page.
    
    Args:
        course_identifier: The Canvas course code (e.g., badm_554_120251_246794) or ID
        page_url_or_id: The page URL or page ID
    """
    course_id = await get_course_id(course_identifier)
    
    response = await make_canvas_request("get", f"/courses/{course_id}/pages/{page_url_or_id}")
    
    if "error" in response:
        return f"Error fetching page details: {response['error']}"
    
    title = response.get("title", "Untitled")
    url = response.get("url", "N/A")
    body = response.get("body", "")
    created_at = format_date(response.get("created_at"))
    updated_at = format_date(response.get("updated_at"))
    published = response.get("published", False)
    front_page = response.get("front_page", False)
    locked_for_user = response.get("locked_for_user", False)
    editing_roles = response.get("editing_roles", "")
    
    # Handle last edited by user info
    last_edited_by = response.get("last_edited_by", {})
    editor_name = last_edited_by.get("display_name", "Unknown") if last_edited_by else "Unknown"
    
    # Clean up body text for display
    if body:
        # Remove HTML tags for cleaner display
        import re
        body_clean = re.sub(r'<[^>]+>', '', body)
        body_clean = body_clean.strip()
        if len(body_clean) > 500:
            body_clean = body_clean[:500] + "..."
    else:
        body_clean = "No content"
    
    status_info = []
    if front_page:
        status_info.append("Front Page")
    if not published:
        status_info.append("Unpublished")
    if locked_for_user:
        status_info.append("Locked")
    
    details = [
        f"Title: {title}",
        f"URL: {url}",
        f"Status: {', '.join(status_info) if status_info else 'Published'}",
        f"Created: {created_at}",
        f"Updated: {updated_at}",
        f"Last Edited By: {editor_name}",
        f"Editing Roles: {editing_roles or 'Default'}",
        f"Content Preview:\n{body_clean}"
    ]
    
    # Try to get the course code for display
    course_display = await get_course_code(course_id) or course_identifier
    return f"Page Details for '{title}' in Course {course_display}:\n\n" + "\n".join(details)

@mcp.tool()
@validate_params
async def get_page_content(course_identifier: Union[str, int], page_url_or_id: str) -> str:
    """Get the full content body of a specific page.
    
    Args:
        course_identifier: The Canvas course code (e.g., badm_554_120251_246794) or ID
        page_url_or_id: The page URL or page ID
    """
    course_id = await get_course_id(course_identifier)
    
    response = await make_canvas_request("get", f"/courses/{course_id}/pages/{page_url_or_id}")
    
    if "error" in response:
        return f"Error fetching page content: {response['error']}"
    
    title = response.get("title", "Untitled")
    body = response.get("body", "")
    
    if not body:
        return f"Page '{title}' has no content."
    
    # Try to get the course code for display
    course_display = await get_course_code(course_id) or course_identifier
    return f"Content of page '{title}' in Course {course_display}:\n\n{body}"

@mcp.tool()
@validate_params
async def get_front_page(course_identifier: Union[str, int]) -> str:
    """Get the front page content for a course.
    
    Args:
        course_identifier: The Canvas course code (e.g., badm_554_120251_246794) or ID
    """
    course_id = await get_course_id(course_identifier)
    
    response = await make_canvas_request("get", f"/courses/{course_id}/front_page")
    
    if "error" in response:
        return f"Error fetching front page: {response['error']}"
    
    title = response.get("title", "Untitled")
    body = response.get("body", "")
    updated_at = format_date(response.get("updated_at"))
    
    if not body:
        return f"Course front page '{title}' has no content."
    
    # Try to get the course code for display
    course_display = await get_course_code(course_id) or course_identifier
    return f"Front Page '{title}' for Course {course_display} (Updated: {updated_at}):\n\n{body}"

@mcp.tool()
@validate_params
async def list_module_items(course_identifier: Union[str, int], 
                           module_id: Union[str, int],
                           include_content_details: bool = True) -> str:
    """List items within a specific module, including pages.
    
    Args:
        course_identifier: The Canvas course code (e.g., badm_554_120251_246794) or ID
        module_id: The module ID
        include_content_details: Whether to include additional details about content items
    """
    course_id = await get_course_id(course_identifier)
    
    # Ensure module_id is a string
    module_id_str = str(module_id)
    
    params = {
        "per_page": 100
    }
    
    if include_content_details:
        params["include[]"] = ["content_details"]
    
    items = await fetch_all_paginated_results(
        f"/courses/{course_id}/modules/{module_id_str}/items", params
    )
    
    if isinstance(items, dict) and "error" in items:
        return f"Error fetching module items: {items['error']}"
    
    if not items:
        return f"No items found in module {module_id}."
    
    # Get module name for context
    module_response = await make_canvas_request("get", f"/courses/{course_id}/modules/{module_id_str}")
    module_name = module_response.get("name", f"Module {module_id}") if "error" not in module_response else f"Module {module_id}"
    
    items_info = []
    for item in items:
        item_id = item.get("id", "N/A")
        title = item.get("title", "Untitled")
        item_type = item.get("type", "Unknown")
        position = item.get("position", "N/A")
        published = item.get("published", True)
        
        # Special handling for different item types
        type_info = []
        if item_type == "Page":
            page_url = item.get("page_url", "")
            if page_url:
                type_info.append(f"Page URL: {page_url}")
        elif item_type == "Assignment":
            content_id = item.get("content_id")
            if content_id:
                type_info.append(f"Assignment ID: {content_id}")
        elif item_type == "Discussion":
            content_id = item.get("content_id")
            if content_id:
                type_info.append(f"Discussion ID: {content_id}")
        elif item_type == "ExternalUrl":
            external_url = item.get("external_url", "")
            if external_url:
                type_info.append(f"URL: {external_url}")
        elif item_type == "File":
            content_id = item.get("content_id")
            if content_id:
                type_info.append(f"File ID: {content_id}")
        
        # Status indicators
        status_indicators = []
        if not published:
            status_indicators.append("UNPUBLISHED")
        
        status_str = f" [{', '.join(status_indicators)}]" if status_indicators else ""
        
        # Format item info
        item_details = [
            f"Position: {position}",
            f"Title: {title}{status_str}",
            f"Type: {item_type}",
            f"ID: {item_id}"
        ]
        
        if type_info:
            item_details.extend(type_info)
        
        items_info.append("\n".join(item_details) + "\n")
    
    # Try to get the course code for display
    course_display = await get_course_code(course_id) or course_identifier
    return f"Items in '{module_name}' (Course {course_display}):\n\n" + "\n".join(items_info)

@mcp.tool()
@validate_params
async def get_page_revisions(course_identifier: Union[str, int], page_url_or_id: str) -> str:
    """Get the revision history for a specific page.
    
    Args:
        course_identifier: The Canvas course code (e.g., badm_554_120251_246794) or ID
        page_url_or_id: The page URL or page ID
    """
    course_id = await get_course_id(course_identifier)
    
    revisions = await fetch_all_paginated_results(
        f"/courses/{course_id}/pages/{page_url_or_id}/revisions", 
        {"per_page": 100}
    )
    
    if isinstance(revisions, dict) and "error" in revisions:
        return f"Error fetching page revisions: {revisions['error']}"
    
    if not revisions:
        return f"No revisions found for page {page_url_or_id}."
    
    # Get page title for context
    page_response = await make_canvas_request("get", f"/courses/{course_id}/pages/{page_url_or_id}")
    page_title = page_response.get("title", page_url_or_id) if "error" not in page_response else page_url_or_id
    
    revisions_info = []
    for revision in revisions:
        revision_id = revision.get("revision_id", "N/A")
        updated_at = format_date(revision.get("updated_at"))
        user_name = revision.get("edited_by", {}).get("display_name", "Unknown")
        latest = revision.get("latest", False)
        
        status_str = " [LATEST]" if latest else ""
        
        revisions_info.append(
            f"Revision ID: {revision_id}{status_str}\n"
            f"Updated: {updated_at}\n"
            f"Edited By: {user_name}\n"
        )
    
    # Try to get the course code for display
    course_display = await get_course_code(course_id) or course_identifier
    return f"Revision History for '{page_title}' (Course {course_display}):\n\n" + "\n".join(revisions_info)

@mcp.tool()
@validate_params
async def get_course_content_overview(course_identifier: Union[str, int], 
                                    include_pages: bool = True,
                                    include_modules: bool = True) -> str:
    """Get a comprehensive overview of course content including pages and modules.
    
    Args:
        course_identifier: The Canvas course code (e.g., badm_554_120251_246794) or ID
        include_pages: Whether to include pages information
        include_modules: Whether to include modules and their items
    """
    course_id = await get_course_id(course_identifier)
    
    overview_sections = []
    
    # Get course details for context
    course_response = await make_canvas_request("get", f"/courses/{course_id}")
    if "error" not in course_response:
        course_name = course_response.get("name", "Unknown Course")
        overview_sections.append(f"Course: {course_name}")
    
    # Get pages if requested
    if include_pages:
        pages = await fetch_all_paginated_results(f"/courses/{course_id}/pages", {"per_page": 100})
        if isinstance(pages, list):
            published_pages = [p for p in pages if p.get("published", False)]
            unpublished_pages = [p for p in pages if not p.get("published", False)]
            front_pages = [p for p in pages if p.get("front_page", False)]
            
            pages_summary = [
                f"\nPages Summary:",
                f"  Total Pages: {len(pages)}",
                f"  Published: {len(published_pages)}",
                f"  Unpublished: {len(unpublished_pages)}",
                f"  Front Pages: {len(front_pages)}"
            ]
            
            if published_pages:
                pages_summary.append(f"\nRecent Published Pages:")
                # Sort by updated_at and show first 5
                sorted_pages = sorted(published_pages, 
                                    key=lambda x: x.get("updated_at", ""), 
                                    reverse=True)
                for page in sorted_pages[:5]:
                    title = page.get("title", "Untitled")
                    updated = format_date(page.get("updated_at"))
                    pages_summary.append(f"    {title} (Updated: {updated})")
            
            overview_sections.append("\n".join(pages_summary))
    
    # Get modules if requested
    if include_modules:
        modules = await fetch_all_paginated_results(f"/courses/{course_id}/modules", {"per_page": 100})
        if isinstance(modules, list):
            modules_summary = [
                f"\nModules Summary:",
                f"  Total Modules: {len(modules)}"
            ]
            
            # Count module items by type across all modules
            item_type_counts = {}
            total_items = 0
            
            for module in modules[:10]:  # Limit to first 10 modules to avoid too many API calls
                module_id = module.get("id")
                if module_id:
                    items = await fetch_all_paginated_results(
                        f"/courses/{course_id}/modules/{module_id}/items", 
                        {"per_page": 100}
                    )
                    if isinstance(items, list):
                        total_items += len(items)
                        for item in items:
                            item_type = item.get("type", "Unknown")
                            item_type_counts[item_type] = item_type_counts.get(item_type, 0) + 1
            
            modules_summary.append(f"  Total Items Analyzed: {total_items}")
            if item_type_counts:
                modules_summary.append(f"  Item Types:")
                for item_type, count in sorted(item_type_counts.items()):
                    modules_summary.append(f"    {item_type}: {count}")
            
            # Show module structure for first few modules
            if modules:
                modules_summary.append(f"\nModule Structure (first 3):")
                for module in modules[:3]:
                    name = module.get("name", "Unnamed")
                    state = module.get("state", "unknown")
                    modules_summary.append(f"    {name} (Status: {state})")
            
            overview_sections.append("\n".join(modules_summary))
    
    # Try to get the course code for display
    course_display = await get_course_code(course_id) or course_identifier
    result = f"Content Overview for Course {course_display}:" + "\n".join(overview_sections)
    
    return result

# ===== RESOURCES =====

@mcp.resource(
    name="course-syllabus",
    description="Get the syllabus for a specific course",
    uri="canvas://course/{course_identifier}/syllabus"
)
async def get_course_syllabus(course_identifier: str) -> str:
    """Get the syllabus for a specific course."""
    course_id = await get_course_id(course_identifier)
    
    response = await make_canvas_request("get", f"/courses/{course_id}")
    
    if "error" in response:
        return f"Error fetching syllabus: {response['error']}"
    
    syllabus_body = response.get("syllabus_body", "")
    
    if not syllabus_body:
        return "No syllabus available for this course."
    
    return syllabus_body

@mcp.resource(
    name="assignment-description",
    description="Get the description for a specific assignment",
    uri="canvas://course/{course_identifier}/assignment/{assignment_id}/description"
)
@validate_params
async def get_assignment_description(course_identifier: Union[str, int], assignment_id: Union[str, int]) -> str:
    """Get the description for a specific assignment."""
    course_id = await get_course_id(course_identifier)
    
    # Ensure assignment_id is a string
    assignment_id_str = str(assignment_id)
    
    response = await make_canvas_request(
        "get", f"/courses/{course_id}/assignments/{assignment_id_str}"
    )
    
    if "error" in response:
        return f"Error fetching assignment description: {response['error']}"
    
    description = response.get("description", "")
    
    if not description:
        return "No description available for this assignment."
    
    return description

@mcp.resource(
    name="course-modules",
    description="Get the modules for a specific course",
    uri="canvas://course/{course_identifier}/modules"
)
async def get_course_modules(course_identifier: str) -> str:
    """Get the modules for a specific course."""
    course_id = await get_course_id(course_identifier)
    
    params = {
        "per_page": 100
    }
    
    modules = await fetch_all_paginated_results(f"/courses/{course_id}/modules", params)
    
    if isinstance(modules, dict) and "error" in modules:
        return f"Error fetching modules: {modules['error']}"
    
    if not modules:
        return "No modules available for this course."
    
    modules_info = []
    for module in modules:
        module_id = module.get("id")
        name = module.get("name", "Unnamed module")
        status = module.get("state", "Unknown")
        
        modules_info.append(f"ID: {module_id}\nName: {name}\nStatus: {status}\n")
    
    return "Course Modules:\n\n" + "\n".join(modules_info)

@mcp.resource(
    name="page-content",
    description="Get the content for a specific page",
    uri="canvas://course/{course_identifier}/page/{page_url_or_id}/content"
)
@validate_params
async def get_page_content_resource(course_identifier: Union[str, int], page_url_or_id: str) -> str:
    """Get the content for a specific page."""
    course_id = await get_course_id(course_identifier)
    
    response = await make_canvas_request("get", f"/courses/{course_id}/pages/{page_url_or_id}")
    
    if "error" in response:
        return f"Error fetching page content: {response['error']}"
    
    body = response.get("body", "")
    
    if not body:
        return "No content available for this page."
    
    return body

@mcp.resource(
    name="course-front-page",
    description="Get the front page content for a course",
    uri="canvas://course/{course_identifier}/front_page"
)
async def get_course_front_page_resource(course_identifier: str) -> str:
    """Get the front page content for a course."""
    course_id = await get_course_id(course_identifier)
    
    response = await make_canvas_request("get", f"/courses/{course_id}/front_page")
    
    if "error" in response:
        return f"Error fetching front page: {response['error']}"
    
    body = response.get("body", "")
    
    if not body:
        return "No front page content available for this course."
    
    return body

# ===== PROMPTS =====

@mcp.prompt(
    name="summarize-course",
    description="Generate a summary of a Canvas course"
)
async def summarize_course(course_identifier: str) -> List[Dict[str, Any]]:
    """Generate a summary of a Canvas course."""
    course_id = await get_course_id(course_identifier)
    
    # Get course details
    course_response = await make_canvas_request("get", f"/courses/{course_id}")
    
    if "error" in course_response:
        return [{"role": "user", "content": f"Error fetching course: {course_response['error']}"}]
    
    # Get assignments
    assignments_response = await fetch_all_paginated_results(f"/courses/{course_id}/assignments")
    
    if isinstance(assignments_response, dict) and "error" in assignments_response:
        assignments_info = "Error fetching assignments"
    else:
        assignments_count = len(assignments_response)
        from datetime import datetime
        current_date = datetime.now().isoformat()
        upcoming_assignments = [
            a for a in assignments_response 
            if a.get("due_at") and a.get("due_at") > current_date
        ]
        upcoming_count = len(upcoming_assignments)
        assignments_info = f"{assignments_count} total assignments, {upcoming_count} upcoming"
    
    # Get modules
    modules_response = await fetch_all_paginated_results(f"/courses/{course_id}/modules")
    
    if isinstance(modules_response, dict) and "error" in modules_response:
        modules_info = "Error fetching modules"
    else:
        modules_count = len(modules_response)
        modules_info = f"{modules_count} modules"
    
    # Create prompt
    course_name = course_response.get("name", "Unknown course")
    course_code = course_response.get("course_code", "No code")
    
    # Update our caches with the course data
    if "id" in course_response and "course_code" in course_response:
        course_code_to_id_cache[course_code] = str(course_response["id"])
        id_to_course_code_cache[str(course_response["id"])] = course_code
    
    return [
        {"role": "system", "content": "You are a helpful assistant that summarizes Canvas course information."},
        {"role": "user", "content": f"""
Please provide a summary of the Canvas course:

Course: {course_name} ({course_code})
Code: {course_code}
Assignments: {assignments_info}
Modules: {modules_info}

Summarize the key information about this course and suggest what the user might want to know about it.
        """}
    ]

# ===== MAIN EXECUTION =====

if __name__ == "__main__":
    import sys
    
    # Check for API token
    if not API_TOKEN:
        print("Error: CANVAS_API_TOKEN environment variable is required", file=sys.stderr)
        print("Please set it to your Canvas API token", file=sys.stderr)
        sys.exit(1)
    
    print(f"Starting Canvas MCP server with API URL: {API_BASE_URL}", file=sys.stderr)
    print("Use Ctrl+C to stop the server", file=sys.stderr)
    
    try:
        # Run the server directly
        mcp.run()
    except KeyboardInterrupt:
        print("\nShutting down server...", file=sys.stderr)
    finally:
        # We'll rely on Python's cleanup to close the client
        pass
