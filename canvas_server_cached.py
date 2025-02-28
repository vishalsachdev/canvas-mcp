#!/usr/bin/env python3
from typing import Any, Dict, List, Optional, Union, TypedDict
import os
import sys
import httpx
import json
from mcp.server.fastmcp import FastMCP

# Initialize FastMCP server
mcp = FastMCP("canvas-api")

# Constants
API_BASE_URL = os.environ.get("CANVAS_API_URL", "https://canvas.illinois.edu/api/v1")
API_TOKEN = os.environ.get("CANVAS_API_TOKEN", "")

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

# Initialize HTTP client with auth
http_client = httpx.AsyncClient(
    headers={
        'Authorization': f'Bearer {API_TOKEN}'
    },
    timeout=30.0
)

# Helper functions
def format_date(date_str: Optional[str]) -> str:
    """Format a date string for display or return 'N/A' if None."""
    if not date_str:
        return "N/A"
    
    try:
        # You could add more formatting here if needed
        return date_str
    except:
        return date_str

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

async def get_course_id(course_identifier: str) -> Optional[str]:
    """Get course ID from either course code or ID, with caching."""
    global course_code_to_id_cache, id_to_course_code_cache
    
    # If it looks like a numeric ID
    if str(course_identifier).isdigit():
        return str(course_identifier)
    
    # If it's a SIS ID format
    if course_identifier.startswith("sis_course_id:"):
        return course_identifier
    
    # If it's in our cache, return the ID
    if course_identifier in course_code_to_id_cache:
        return course_code_to_id_cache[course_identifier]
    
    # If it looks like a course code (contains underscores)
    if "_" in course_identifier:
        # Try to refresh cache if it's not there
        if not course_code_to_id_cache:
            await refresh_course_cache()
            if course_identifier in course_code_to_id_cache:
                return course_code_to_id_cache[course_identifier]
        
        # Return SIS format as a fallback
        return f"sis_course_id:{course_identifier}"
    
    # Last resort, return as is
    return course_identifier

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
async def get_course_details(course_identifier: str) -> str:
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
async def list_assignments(course_identifier: str) -> str:
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
async def get_assignment_details(course_identifier: str, assignment_id: str) -> str:
    """Get detailed information about a specific assignment.
    
    Args:
        course_identifier: The Canvas course code (e.g., badm_554_120251_246794) or ID
        assignment_id: The Canvas assignment ID
    """
    course_id = await get_course_id(course_identifier)
    
    response = await make_canvas_request(
        "get", f"/courses/{course_id}/assignments/{assignment_id}"
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

# ===== SUBMISSIONS TOOLS =====

@mcp.tool()
async def list_submissions(course_identifier: str, assignment_id: str) -> str:
    """List submissions for a specific assignment.
    
    Args:
        course_identifier: The Canvas course code (e.g., badm_554_120251_246794) or ID
        assignment_id: The Canvas assignment ID
    """
    course_id = await get_course_id(course_identifier)
    
    params = {
        "per_page": 100
    }
    
    submissions = await fetch_all_paginated_results(
        f"/courses/{course_id}/assignments/{assignment_id}/submissions", params
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
        posted_at = announcement.get("posted_at", "Unknown date")
        author = announcement.get("author", {}).get("display_name", "Unknown")
        
        announcements_info.append(
            f"Title: {title}\nPosted: {posted_at}\nAuthor: {author}\n"
        )
    
    # Try to get the course code for display
    course_display = await get_course_code(course_id) or course_identifier
    return f"Announcements for Course {course_display}:\n\n" + "\n".join(announcements_info)

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
async def get_assignment_description(course_identifier: str, assignment_id: str) -> str:
    """Get the description for a specific assignment."""
    course_id = await get_course_id(course_identifier)
    
    response = await make_canvas_request(
        "get", f"/courses/{course_id}/assignments/{assignment_id}"
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