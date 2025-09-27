"""Course caching system for Canvas API."""

import sys

from .client import fetch_all_paginated_results, make_canvas_request
from .validation import validate_params

# Global cache for course codes to IDs
course_code_to_id_cache: dict[str, str] = {}
id_to_course_code_cache: dict[str, str] = {}


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
async def get_course_id(course_identifier: str | int) -> str | None:
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


async def get_course_code(course_id: str) -> str | None:
    """Get course code from ID, with caching."""
    global id_to_course_code_cache, course_code_to_id_cache

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
        code = response.get("course_code", "")
        # Update our cache
        if code:
            id_to_course_code_cache[course_id] = code
            course_code_to_id_cache[code] = course_id
        return code

    # Last resort, return the ID
    return course_id
