"""Module-related MCP tools for Canvas API.

Provides tools for creating, updating, and managing Canvas course modules
and module items. Modules are the primary content organization system in Canvas.
"""


from mcp.server.fastmcp import FastMCP

from ..core.cache import get_course_code, get_course_id
from ..core.client import fetch_all_paginated_results, make_canvas_request
from ..core.dates import format_date, parse_date
from ..core.validation import validate_params


def register_module_tools(mcp: FastMCP):
    """Register all module-related MCP tools."""

    @mcp.tool()
    @validate_params
    async def list_modules(
        course_identifier: str | int,
        include_items: bool = False,
        search_term: str | None = None
    ) -> str:
        """List all modules in a course.

        Args:
            course_identifier: The Canvas course code (e.g., badm_554_120251_246794) or ID
            include_items: Whether to include a summary of items in each module
            search_term: Optional search term to filter modules by name
        """
        course_id = await get_course_id(course_identifier)

        params = {"per_page": 100}
        if include_items:
            params["include[]"] = ["items"]
        if search_term:
            params["search_term"] = search_term

        modules = await fetch_all_paginated_results(
            f"/courses/{course_id}/modules", params
        )

        if isinstance(modules, dict) and "error" in modules:
            return f"Error fetching modules: {modules['error']}"

        if not modules:
            return "No modules found in course."

        course_display = await get_course_code(course_id) or course_identifier
        result = f"Modules in {course_display}:\n\n"

        for module in modules:
            module_id = module.get("id")
            name = module.get("name", "Unnamed")
            position = module.get("position", 0)
            state = module.get("state", "unknown")
            published = module.get("published", False)
            items_count = module.get("items_count", 0)
            unlock_at = module.get("unlock_at")
            require_sequential = module.get("require_sequential_progress", False)
            prerequisite_ids = module.get("prerequisite_module_ids", [])

            result += f"**{name}**\n"
            result += f"  ID: {module_id}\n"
            result += f"  Position: {position}\n"
            result += f"  Status: {state} | Published: {'Yes' if published else 'No'}\n"
            result += f"  Items: {items_count}\n"

            if unlock_at:
                result += f"  Unlocks: {format_date(unlock_at)}\n"
            if require_sequential:
                result += "  Sequential Progress: Required\n"
            if prerequisite_ids:
                result += f"  Prerequisites: {prerequisite_ids}\n"

            # Include item summary if requested
            if include_items and "items" in module:
                items = module.get("items", [])
                if items:
                    result += "  Items:\n"
                    for item in items[:5]:  # Show first 5 items
                        item_title = item.get("title", "Untitled")
                        item_type = item.get("type", "Unknown")
                        result += f"    - {item_title} ({item_type})\n"
                    if len(items) > 5:
                        result += f"    ... and {len(items) - 5} more items\n"

            result += "\n"

        return result

    @mcp.tool()
    @validate_params
    async def create_module(
        course_identifier: str | int,
        name: str,
        position: int | None = None,
        unlock_at: str | None = None,
        require_sequential_progress: bool = False,
        prerequisite_module_ids: str | None = None,
        published: bool = True
    ) -> str:
        """Create a new module in a course.

        Args:
            course_identifier: The Canvas course code (e.g., badm_554_120251_246794) or ID
            name: The name of the module (required)
            position: Position in the module list (1-indexed, lower = earlier)
            unlock_at: Date/time when the module unlocks (ISO 8601 format)
            require_sequential_progress: If true, students must complete items in order
            prerequisite_module_ids: Comma-separated list of module IDs that must be completed first
            published: Whether the module is published (default: True)
        """
        course_id = await get_course_id(course_identifier)

        # Build module parameters
        module_params = {
            "module[name]": name,
            "module[published]": str(published).lower()
        }

        if position is not None:
            module_params["module[position]"] = position

        if unlock_at:
            parsed_date = parse_date(unlock_at)
            if parsed_date:
                module_params["module[unlock_at]"] = parsed_date.isoformat()

        if require_sequential_progress:
            module_params["module[require_sequential_progress]"] = "true"

        # Handle prerequisite module IDs - need list of tuples for httpx form data
        prereq_tuples = []
        if prerequisite_module_ids:
            # Parse comma-separated IDs
            prereq_ids = [id.strip() for id in prerequisite_module_ids.split(",")]
            prereq_tuples = [("module[prerequisite_module_ids][]", prereq_id) for prereq_id in prereq_ids]

        # Convert module_params dict to list of tuples and append prereq tuples
        form_data = list(module_params.items()) + prereq_tuples

        response = await make_canvas_request(
            "post",
            f"/courses/{course_id}/modules",
            data=form_data,
            use_form_data=True
        )

        if "error" in response:
            return f"Error creating module: {response['error']}"

        # Format success response
        module_id = response.get("id")
        module_name = response.get("name")
        module_position = response.get("position")
        module_published = response.get("published", False)

        course_display = await get_course_code(course_id) or course_identifier
        result = "✅ Module created successfully!\n\n"
        result += f"**{module_name}**\n"
        result += f"  Course: {course_display}\n"
        result += f"  Module ID: {module_id}\n"
        result += f"  Position: {module_position}\n"
        result += f"  Published: {'Yes' if module_published else 'No'}\n"

        if unlock_at:
            result += f"  Unlocks: {format_date(response.get('unlock_at'))}\n"
        if require_sequential_progress:
            result += "  Sequential Progress: Required\n"

        return result

    @mcp.tool()
    @validate_params
    async def update_module(
        course_identifier: str | int,
        module_id: str | int,
        name: str | None = None,
        position: int | None = None,
        unlock_at: str | None = None,
        require_sequential_progress: bool | None = None,
        prerequisite_module_ids: str | None = None,
        published: bool | None = None
    ) -> str:
        """Update an existing module's settings.

        Args:
            course_identifier: The Canvas course code (e.g., badm_554_120251_246794) or ID
            module_id: The ID of the module to update
            name: New name for the module
            position: New position in the module list
            unlock_at: New unlock date/time (ISO 8601 format), or empty string to remove
            require_sequential_progress: Whether students must complete items in order
            prerequisite_module_ids: Comma-separated list of prerequisite module IDs, or empty to clear
            published: Whether the module is published
        """
        course_id = await get_course_id(course_identifier)

        # Build update parameters (only include changed fields)
        module_params = {}

        if name is not None:
            module_params["module[name]"] = name

        if position is not None:
            module_params["module[position]"] = position

        if unlock_at is not None:
            if unlock_at == "":
                module_params["module[unlock_at]"] = ""
            else:
                parsed_date = parse_date(unlock_at)
                if parsed_date:
                    module_params["module[unlock_at]"] = parsed_date.isoformat()

        if require_sequential_progress is not None:
            module_params["module[require_sequential_progress]"] = str(require_sequential_progress).lower()

        # Handle prerequisite module IDs - need list of tuples for httpx form data
        prereq_tuples = []
        if prerequisite_module_ids is not None:
            if prerequisite_module_ids == "":
                module_params["module[prerequisite_module_ids][]"] = ""
            else:
                prereq_ids = [id.strip() for id in prerequisite_module_ids.split(",")]
                prereq_tuples = [("module[prerequisite_module_ids][]", prereq_id) for prereq_id in prereq_ids]

        if published is not None:
            module_params["module[published]"] = str(published).lower()

        if not module_params and not prereq_tuples:
            return "No changes specified. Please provide at least one field to update."

        # Convert module_params dict to list of tuples and append prereq tuples
        form_data = list(module_params.items()) + prereq_tuples

        response = await make_canvas_request(
            "put",
            f"/courses/{course_id}/modules/{module_id}",
            data=form_data,
            use_form_data=True
        )

        if "error" in response:
            return f"Error updating module: {response['error']}"

        # Format success response
        module_name = response.get("name")
        module_position = response.get("position")
        module_published = response.get("published", False)

        course_display = await get_course_code(course_id) or course_identifier
        result = "✅ Module updated successfully!\n\n"
        result += f"**{module_name}**\n"
        result += f"  Course: {course_display}\n"
        result += f"  Module ID: {module_id}\n"
        result += f"  Position: {module_position}\n"
        result += f"  Published: {'Yes' if module_published else 'No'}\n"

        if response.get("unlock_at"):
            result += f"  Unlocks: {format_date(response.get('unlock_at'))}\n"
        if response.get("require_sequential_progress"):
            result += "  Sequential Progress: Required\n"

        return result

    @mcp.tool()
    @validate_params
    async def delete_module(
        course_identifier: str | int,
        module_id: str | int
    ) -> str:
        """Delete a module from a course.

        Warning: This permanently removes the module and all its item associations.
        The actual content (pages, assignments, etc.) is NOT deleted, only the
        module organization.

        Args:
            course_identifier: The Canvas course code (e.g., badm_554_120251_246794) or ID
            module_id: The ID of the module to delete
        """
        course_id = await get_course_id(course_identifier)

        # First get module info for confirmation
        module_response = await make_canvas_request(
            "get",
            f"/courses/{course_id}/modules/{module_id}"
        )

        module_name = "Unknown"
        items_count = 0
        if "error" not in module_response:
            module_name = module_response.get("name", "Unknown")
            items_count = module_response.get("items_count", 0)

        # Delete the module
        response = await make_canvas_request(
            "delete",
            f"/courses/{course_id}/modules/{module_id}"
        )

        if isinstance(response, dict) and "error" in response:
            return f"Error deleting module: {response['error']}"

        course_display = await get_course_code(course_id) or course_identifier
        result = "✅ Module deleted successfully!\n\n"
        result += f"  Deleted: **{module_name}**\n"
        result += f"  Course: {course_display}\n"
        result += f"  Module ID: {module_id}\n"
        result += f"  Items affected: {items_count} (items unlinked, content preserved)\n"

        return result

    @mcp.tool()
    @validate_params
    async def add_module_item(
        course_identifier: str | int,
        module_id: str | int,
        item_type: str,
        content_id: str | int | None = None,
        title: str | None = None,
        position: int | None = None,
        indent: int | None = None,
        page_url: str | None = None,
        external_url: str | None = None,
        new_tab: bool = False,
        completion_requirement_type: str | None = None,
        completion_requirement_min_score: int | None = None
    ) -> str:
        """Add an item to a module.

        Args:
            course_identifier: The Canvas course code (e.g., badm_554_120251_246794) or ID
            module_id: The ID of the module to add the item to
            item_type: Type of item - one of: File, Page, Discussion, Assignment, Quiz,
                      SubHeader, ExternalUrl, ExternalTool
            content_id: The Canvas ID of the content (required for File, Discussion,
                       Assignment, Quiz, ExternalTool). Not needed for Page, SubHeader, ExternalUrl.
            title: Title for the item (required for SubHeader, ExternalUrl; optional for others)
            position: Position within the module (1-indexed)
            indent: Indentation level (0-4, for visual hierarchy)
            page_url: The URL slug of the page (required for Page type, e.g., "my-page-title")
            external_url: The URL for ExternalUrl type items
            new_tab: Whether external links open in a new tab (default: False)
            completion_requirement_type: One of: must_view, must_submit, must_contribute,
                                        min_score, must_mark_done
            completion_requirement_min_score: Minimum score required (only for min_score type)
        """
        course_id = await get_course_id(course_identifier)

        # Validate item type
        valid_types = ["File", "Page", "Discussion", "Assignment", "Quiz",
                      "SubHeader", "ExternalUrl", "ExternalTool"]
        if item_type not in valid_types:
            return f"Invalid item_type '{item_type}'. Must be one of: {', '.join(valid_types)}"

        # Build item parameters
        item_params = {
            "module_item[type]": item_type
        }

        # Handle content_id requirement
        types_requiring_content_id = ["File", "Discussion", "Assignment", "Quiz", "ExternalTool"]
        if item_type in types_requiring_content_id:
            if content_id is None:
                return f"content_id is required for {item_type} items"
            item_params["module_item[content_id]"] = content_id

        # Handle Page type
        if item_type == "Page":
            if page_url is None:
                return "page_url is required for Page items (e.g., 'my-page-title')"
            item_params["module_item[page_url]"] = page_url

        # Handle ExternalUrl type
        if item_type == "ExternalUrl":
            if external_url is None:
                return "external_url is required for ExternalUrl items"
            if title is None:
                return "title is required for ExternalUrl items"
            item_params["module_item[external_url]"] = external_url

        # Handle SubHeader type
        if item_type == "SubHeader":
            if title is None:
                return "title is required for SubHeader items"

        # Optional parameters
        if title is not None:
            item_params["module_item[title]"] = title

        if position is not None:
            item_params["module_item[position]"] = position

        if indent is not None:
            if indent < 0 or indent > 4:
                return "indent must be between 0 and 4"
            item_params["module_item[indent]"] = indent

        if new_tab:
            item_params["module_item[new_tab]"] = "true"

        # Completion requirements
        if completion_requirement_type:
            valid_completion_types = ["must_view", "must_submit", "must_contribute",
                                     "min_score", "must_mark_done"]
            if completion_requirement_type not in valid_completion_types:
                return f"Invalid completion_requirement_type. Must be one of: {', '.join(valid_completion_types)}"

            item_params["module_item[completion_requirement][type]"] = completion_requirement_type

            if completion_requirement_type == "min_score":
                if completion_requirement_min_score is None:
                    return "completion_requirement_min_score is required when type is 'min_score'"
                item_params["module_item[completion_requirement][min_score]"] = completion_requirement_min_score

        response = await make_canvas_request(
            "post",
            f"/courses/{course_id}/modules/{module_id}/items",
            data=item_params,
            use_form_data=True
        )

        if "error" in response:
            return f"Error adding module item: {response['error']}"

        # Format success response
        item_id = response.get("id")
        item_title = response.get("title", title or "Untitled")
        item_position = response.get("position")
        item_indent = response.get("indent", 0)

        course_display = await get_course_code(course_id) or course_identifier
        result = "✅ Module item added successfully!\n\n"
        result += f"**{item_title}**\n"
        result += f"  Course: {course_display}\n"
        result += f"  Module ID: {module_id}\n"
        result += f"  Item ID: {item_id}\n"
        result += f"  Type: {item_type}\n"
        result += f"  Position: {item_position}\n"

        if item_indent > 0:
            result += f"  Indent: {item_indent}\n"

        if content_id:
            result += f"  Content ID: {content_id}\n"

        if external_url:
            result += f"  URL: {external_url}\n"
            result += f"  Opens in new tab: {'Yes' if new_tab else 'No'}\n"

        if completion_requirement_type:
            result += f"  Completion: {completion_requirement_type}"
            if completion_requirement_min_score:
                result += f" (min score: {completion_requirement_min_score})"
            result += "\n"

        return result

    @mcp.tool()
    @validate_params
    async def update_module_item(
        course_identifier: str | int,
        module_id: str | int,
        item_id: str | int,
        title: str | None = None,
        position: int | None = None,
        indent: int | None = None,
        external_url: str | None = None,
        new_tab: bool | None = None,
        completion_requirement_type: str | None = None,
        completion_requirement_min_score: int | None = None,
        published: bool | None = None,
        move_to_module_id: str | int | None = None
    ) -> str:
        """Update an existing module item.

        Args:
            course_identifier: The Canvas course code (e.g., badm_554_120251_246794) or ID
            module_id: The ID of the module containing the item
            item_id: The ID of the item to update
            title: New title for the item
            position: New position within the module
            indent: New indentation level (0-4)
            external_url: New URL (for ExternalUrl items only)
            new_tab: Whether external links open in a new tab
            completion_requirement_type: New completion requirement type, or empty string to remove
            completion_requirement_min_score: New minimum score (for min_score type)
            published: Whether the item is published
            move_to_module_id: Move this item to a different module
        """
        course_id = await get_course_id(course_identifier)

        # Build update parameters
        item_params = {}

        if title is not None:
            item_params["module_item[title]"] = title

        if position is not None:
            item_params["module_item[position]"] = position

        if indent is not None:
            if indent < 0 or indent > 4:
                return "indent must be between 0 and 4"
            item_params["module_item[indent]"] = indent

        if external_url is not None:
            item_params["module_item[external_url]"] = external_url

        if new_tab is not None:
            item_params["module_item[new_tab]"] = str(new_tab).lower()

        if published is not None:
            item_params["module_item[published]"] = str(published).lower()

        if move_to_module_id is not None:
            item_params["module_item[module_id]"] = move_to_module_id

        # Handle completion requirements
        if completion_requirement_type is not None:
            if completion_requirement_type == "":
                # Remove completion requirement
                item_params["module_item[completion_requirement][type]"] = ""
            else:
                valid_completion_types = ["must_view", "must_submit", "must_contribute",
                                         "min_score", "must_mark_done"]
                if completion_requirement_type not in valid_completion_types:
                    return f"Invalid completion_requirement_type. Must be one of: {', '.join(valid_completion_types)}"

                item_params["module_item[completion_requirement][type]"] = completion_requirement_type

                if completion_requirement_type == "min_score":
                    if completion_requirement_min_score is None:
                        return "completion_requirement_min_score is required when type is 'min_score'"
                    item_params["module_item[completion_requirement][min_score]"] = completion_requirement_min_score

        if not item_params:
            return "No changes specified. Please provide at least one field to update."

        response = await make_canvas_request(
            "put",
            f"/courses/{course_id}/modules/{module_id}/items/{item_id}",
            data=item_params,
            use_form_data=True
        )

        if "error" in response:
            return f"Error updating module item: {response['error']}"

        # Format success response
        item_title = response.get("title", "Untitled")
        item_type = response.get("type", "Unknown")
        item_position = response.get("position")
        item_published = response.get("published", False)

        course_display = await get_course_code(course_id) or course_identifier
        result = "✅ Module item updated successfully!\n\n"
        result += f"**{item_title}**\n"
        result += f"  Course: {course_display}\n"
        result += f"  Module ID: {response.get('module_id', module_id)}\n"
        result += f"  Item ID: {item_id}\n"
        result += f"  Type: {item_type}\n"
        result += f"  Position: {item_position}\n"
        result += f"  Published: {'Yes' if item_published else 'No'}\n"

        if move_to_module_id and str(response.get("module_id")) == str(move_to_module_id):
            result += f"  ✓ Moved to module {move_to_module_id}\n"

        return result

    @mcp.tool()
    @validate_params
    async def delete_module_item(
        course_identifier: str | int,
        module_id: str | int,
        item_id: str | int
    ) -> str:
        """Remove an item from a module.

        Note: This only removes the item from the module. The actual content
        (page, assignment, etc.) is NOT deleted.

        Args:
            course_identifier: The Canvas course code (e.g., badm_554_120251_246794) or ID
            module_id: The ID of the module containing the item
            item_id: The ID of the item to remove
        """
        course_id = await get_course_id(course_identifier)

        # First get item info for confirmation
        item_response = await make_canvas_request(
            "get",
            f"/courses/{course_id}/modules/{module_id}/items/{item_id}"
        )

        item_title = "Unknown"
        item_type = "Unknown"
        if "error" not in item_response:
            item_title = item_response.get("title", "Unknown")
            item_type = item_response.get("type", "Unknown")

        # Delete the item
        response = await make_canvas_request(
            "delete",
            f"/courses/{course_id}/modules/{module_id}/items/{item_id}"
        )

        if isinstance(response, dict) and "error" in response:
            return f"Error deleting module item: {response['error']}"

        course_display = await get_course_code(course_id) or course_identifier
        result = "✅ Module item removed successfully!\n\n"
        result += f"  Removed: **{item_title}** ({item_type})\n"
        result += f"  Course: {course_display}\n"
        result += f"  Module ID: {module_id}\n"
        result += f"  Item ID: {item_id}\n"
        result += "\n  Note: The underlying content was NOT deleted, only unlinked from this module.\n"

        return result
