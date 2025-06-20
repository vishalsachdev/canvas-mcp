"""MCP resources and prompts for Canvas integration."""

from typing import Union, List, Dict, Any
from mcp.server.fastmcp import FastMCP

from ..core.client import fetch_all_paginated_results, make_canvas_request
from ..core.cache import get_course_id, get_course_code
from ..core.validation import validate_params


def register_resources_and_prompts(mcp: FastMCP):
    """Register all MCP resources and prompts."""
    
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