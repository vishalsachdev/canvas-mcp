"""Course export and import MCP tools for Canvas API."""

import json

from mcp.server.fastmcp import FastMCP

from ..core.cache import get_course_code, get_course_id
from ..core.client import fetch_all_paginated_results, make_canvas_request
from ..core.validation import validate_params


def register_export_import_tools(mcp: FastMCP) -> None:
    """Register export and import tools for courses."""

    @mcp.tool()
    @validate_params
    async def export_course_structure(
        course_identifier: str | int,
        include_assignments: bool = True,
        include_modules: bool = True,
        include_pages: bool = True,
        include_discussions: bool = True
    ) -> str:
        """Export course structure to JSON format.

        Args:
            course_identifier: The Canvas course code (e.g., badm_554_120251_246794) or ID
            include_assignments: Include assignments in export
            include_modules: Include modules in export
            include_pages: Include pages in export
            include_discussions: Include discussions in export
        """
        course_id = await get_course_id(course_identifier)

        export_data: dict = {
            "course": {},
            "assignments": [],
            "modules": [],
            "pages": [],
            "discussions": []
        }

        # Get course details
        course_response = await make_canvas_request("get", f"/courses/{course_id}")
        if "error" not in course_response:
            export_data["course"] = {
                "name": course_response.get("name"),
                "course_code": course_response.get("course_code"),
                "time_zone": course_response.get("time_zone"),
                "start_at": course_response.get("start_at"),
                "end_at": course_response.get("end_at")
            }

        # Export assignments
        if include_assignments:
            assignments = await fetch_all_paginated_results(
                f"/courses/{course_id}/assignments",
                {"per_page": 100}
            )
            if isinstance(assignments, list):
                for assignment in assignments:
                    export_data["assignments"].append({
                        "name": assignment.get("name"),
                        "description": assignment.get("description"),
                        "points_possible": assignment.get("points_possible"),
                        "due_at": assignment.get("due_at"),
                        "submission_types": assignment.get("submission_types"),
                        "grading_type": assignment.get("grading_type"),
                        "published": assignment.get("published")
                    })

        # Export modules
        if include_modules:
            modules = await fetch_all_paginated_results(
                f"/courses/{course_id}/modules",
                {"per_page": 100, "include[]": ["items"]}
            )
            if isinstance(modules, list):
                for module in modules:
                    module_data = {
                        "name": module.get("name"),
                        "position": module.get("position"),
                        "require_sequential_progress": module.get("require_sequential_progress"),
                        "published": module.get("published"),
                        "items": []
                    }

                    # Add module items
                    items = module.get("items", [])
                    for item in items:
                        module_data["items"].append({
                            "title": item.get("title"),
                            "type": item.get("type"),
                            "position": item.get("position"),
                            "indent": item.get("indent")
                        })

                    export_data["modules"].append(module_data)

        # Export pages
        if include_pages:
            pages = await fetch_all_paginated_results(
                f"/courses/{course_id}/pages",
                {"per_page": 100}
            )
            if isinstance(pages, list):
                for page in pages:
                    export_data["pages"].append({
                        "title": page.get("title"),
                        "body": page.get("body"),
                        "published": page.get("published"),
                        "front_page": page.get("front_page")
                    })

        # Export discussions
        if include_discussions:
            discussions = await fetch_all_paginated_results(
                f"/courses/{course_id}/discussion_topics",
                {"per_page": 100}
            )
            if isinstance(discussions, list):
                for discussion in discussions:
                    if not discussion.get("is_announcement"):  # Skip announcements
                        export_data["discussions"].append({
                            "title": discussion.get("title"),
                            "message": discussion.get("message"),
                            "discussion_type": discussion.get("discussion_type"),
                            "published": discussion.get("published"),
                            "allow_rating": discussion.get("allow_rating")
                        })

        # Format output
        export_json = json.dumps(export_data, indent=2)

        course_display = await get_course_code(course_id) or course_identifier

        summary = [
            f"Course Structure Export for {course_display}:",
            f"  Assignments: {len(export_data['assignments'])}",
            f"  Modules: {len(export_data['modules'])}",
            f"  Pages: {len(export_data['pages'])}",
            f"  Discussions: {len(export_data['discussions'])}",
            "",
            "Export Data:",
            export_json
        ]

        return "\n".join(summary)

    @mcp.tool()
    @validate_params
    async def get_course_export_status(
        course_identifier: str | int,
        export_id: str | int
    ) -> str:
        """Check the status of a course export job.

        Args:
            course_identifier: The Canvas course code (e.g., badm_554_120251_246794) or ID
            export_id: The Canvas content export ID
        """
        course_id = await get_course_id(course_identifier)
        export_id_str = str(export_id)

        response = await make_canvas_request(
            "get",
            f"/courses/{course_id}/content_exports/{export_id_str}"
        )

        if "error" in response:
            return f"Error fetching export status: {response['error']}"

        workflow_state = response.get("workflow_state", "unknown")
        progress = response.get("progress_percent", 0)
        created_at = response.get("created_at", "N/A")
        updated_at = response.get("updated_at", "N/A")

        details = [
            f"Export ID: {export_id}",
            f"Status: {workflow_state}",
            f"Progress: {progress}%",
            f"Created: {created_at}",
            f"Updated: {updated_at}"
        ]

        if workflow_state == "completed":
            attachment = response.get("attachment")
            if attachment:
                details.append(f"Download URL: {attachment.get('url', 'N/A')}")
                details.append(f"File Size: {attachment.get('size', 0)} bytes")

        course_display = await get_course_code(course_id) or course_identifier
        return f"Course Export Status for {course_display}:\n\n" + "\n".join(details)

    @mcp.tool()
    @validate_params
    async def start_course_export(
        course_identifier: str | int,
        export_type: str = "common_cartridge"
    ) -> str:
        """Start a course content export.

        Args:
            course_identifier: The Canvas course code (e.g., badm_554_120251_246794) or ID
            export_type: Export type (common_cartridge, qti, zip)
        """
        course_id = await get_course_id(course_identifier)

        data = {
            "export_type": export_type
        }

        response = await make_canvas_request(
            "post",
            f"/courses/{course_id}/content_exports",
            data=data
        )

        if "error" in response:
            return f"Error starting export: {response['error']}"

        export_id = response.get("id")
        workflow_state = response.get("workflow_state", "unknown")

        course_display = await get_course_code(course_id) or course_identifier

        return (f"Started course export for {course_display}:\n"
                f"Export ID: {export_id}\n"
                f"Type: {export_type}\n"
                f"Status: {workflow_state}\n\n"
                f"Use get_course_export_status with export_id={export_id} to check progress")

    @mcp.tool()
    @validate_params
    async def list_course_exports(course_identifier: str | int) -> str:
        """List all content exports for a course.

        Args:
            course_identifier: The Canvas course code (e.g., badm_554_120251_246794) or ID
        """
        course_id = await get_course_id(course_identifier)

        exports = await fetch_all_paginated_results(
            f"/courses/{course_id}/content_exports",
            {"per_page": 100}
        )

        if isinstance(exports, dict) and "error" in exports:
            return f"Error fetching exports: {exports['error']}"

        if not exports:
            course_display = await get_course_code(course_id) or course_identifier
            return f"No exports found for course {course_display}."

        exports_info = []
        for export in exports:
            export_id = export.get("id")
            export_type = export.get("export_type", "unknown")
            workflow_state = export.get("workflow_state", "unknown")
            progress = export.get("progress_percent", 0)
            created_at = export.get("created_at", "N/A")

            exports_info.append(
                f"ID: {export_id}\n"
                f"Type: {export_type}\n"
                f"Status: {workflow_state}\n"
                f"Progress: {progress}%\n"
                f"Created: {created_at}\n"
            )

        course_display = await get_course_code(course_id) or course_identifier
        return f"Content Exports for Course {course_display}:\n\n" + "\n".join(exports_info)
