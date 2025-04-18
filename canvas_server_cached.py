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

# ===== GROUPS TOOLS =====

@mcp.tool()
async def list_groups(course_identifier: str) -> str:
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
async def get_assignment_analytics(course_identifier: str, assignment_id: str) -> str:
    """Get detailed analytics about student performance on a specific assignment.
    
    Args:
        course_identifier: The Canvas course code (e.g., badm_554_120251_246794) or ID
        assignment_id: The Canvas assignment ID
    """
    import datetime
    from statistics import mean, median, stdev
    
    course_id = await get_course_id(course_identifier)
    
    # Get assignment details
    assignment = await make_canvas_request(
        "get", f"/courses/{course_id}/assignments/{assignment_id}"
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
