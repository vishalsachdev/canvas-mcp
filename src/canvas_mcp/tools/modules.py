"""Module management MCP tools for Canvas API."""

from mcp.server.fastmcp import FastMCP

from ..core.cache import get_course_code, get_course_id
from ..core.client import fetch_all_paginated_results, make_canvas_request
from ..core.validation import validate_params


def register_module_tools(mcp: FastMCP) -> None:
    """Register all module management MCP tools."""

    @mcp.tool()
    @validate_params
    async def list_course_modules(
        course_identifier: str | int,
        include: list[str] | None = None
    ) -> str:
        """List all modules in a course.

        Args:
            course_identifier: The Canvas course code (e.g., badm_554_120251_246794) or ID
            include: Optional list of items to include (items, content_details)
        """
        course_id = await get_course_id(course_identifier)

        params: dict = {"per_page": 100}

        if include:
            params["include[]"] = include

        modules = await fetch_all_paginated_results(f"/courses/{course_id}/modules", params)

        if isinstance(modules, dict) and "error" in modules:
            return f"Error fetching modules: {modules['error']}"

        if not modules:
            course_display = await get_course_code(course_id) or course_identifier
            return f"No modules found for course {course_display}."

        modules_info = []
        for module in modules:
            module_id = module.get("id")
            name = module.get("name", "Unnamed Module")
            position = module.get("position", 0)
            state = module.get("state", "unknown")
            published = module.get("published", False)
            items_count = module.get("items_count", 0)
            unlock_at = module.get("unlock_at", "")
            require_sequential = module.get("require_sequential_progress", False)

            modules_info.append(
                f"ID: {module_id}\n"
                f"Position: {position}\n"
                f"Name: {name}\n"
                f"State: {state}\n"
                f"Published: {published}\n"
                f"Items: {items_count}\n"
                f"Sequential: {require_sequential}\n"
                f"Unlock At: {unlock_at or 'N/A'}\n"
            )

        course_display = await get_course_code(course_id) or course_identifier
        return f"Modules for Course {course_display}:\n\n" + "\n".join(modules_info)

    @mcp.tool()
    @validate_params
    async def get_module_details(
        course_identifier: str | int,
        module_id: str | int,
        include: list[str] | None = None
    ) -> str:
        """Get detailed information about a specific module.

        Args:
            course_identifier: The Canvas course code (e.g., badm_554_120251_246794) or ID
            module_id: The Canvas module ID
            include: Optional list of items to include (items, content_details)
        """
        course_id = await get_course_id(course_identifier)
        module_id_str = str(module_id)

        params: dict = {}
        if include:
            params["include[]"] = include

        response = await make_canvas_request(
            "get",
            f"/courses/{course_id}/modules/{module_id_str}",
            params=params
        )

        if "error" in response:
            return f"Error fetching module details: {response['error']}"

        details = [
            f"ID: {response.get('id')}",
            f"Name: {response.get('name', 'N/A')}",
            f"Position: {response.get('position', 0)}",
            f"State: {response.get('state', 'unknown')}",
            f"Published: {response.get('published', False)}",
            f"Items Count: {response.get('items_count', 0)}",
            f"Unlock At: {response.get('unlock_at', 'N/A')}",
            f"Require Sequential Progress: {response.get('require_sequential_progress', False)}",
            f"Prerequisite Module IDs: {', '.join(map(str, response.get('prerequisite_module_ids', [])))}",
        ]

        # Include items if requested
        if include and "items" in include and "items" in response:
            items = response.get("items", [])
            if items:
                details.append(f"\nModule Items ({len(items)}):")
                for item in items:
                    item_id = item.get("id")
                    item_title = item.get("title", "Untitled")
                    item_type = item.get("type", "unknown")
                    published = item.get("published", False)
                    details.append(f"  - [{item_type}] {item_title} (ID: {item_id}, Published: {published})")

        course_display = await get_course_code(course_id) or course_identifier
        return f"Module Details for Course {course_display}:\n\n" + "\n".join(details)

    @mcp.tool()
    @validate_params
    async def create_module(
        course_identifier: str | int,
        name: str,
        position: int | None = None,
        require_sequential_progress: bool = False,
        prerequisite_module_ids: list[int] | None = None,
        publish_final_grade: bool = False
    ) -> str:
        """Create a new module in a course.

        Args:
            course_identifier: The Canvas course code (e.g., badm_554_120251_246794) or ID
            name: Name for the new module
            position: Position in the module list (1-based)
            require_sequential_progress: Students must complete items in order
            prerequisite_module_ids: IDs of modules that must be completed first
            publish_final_grade: Publish final grade when module is complete
        """
        course_id = await get_course_id(course_identifier)

        data: dict = {
            "module": {
                "name": name,
                "require_sequential_progress": require_sequential_progress,
                "publish_final_grade": publish_final_grade
            }
        }

        if position is not None:
            data["module"]["position"] = position

        if prerequisite_module_ids:
            data["module"]["prerequisite_module_ids"] = prerequisite_module_ids

        response = await make_canvas_request(
            "post",
            f"/courses/{course_id}/modules",
            data=data
        )

        if "error" in response:
            return f"Error creating module: {response['error']}"

        module_id = response.get("id")
        module_name = response.get("name")
        position = response.get("position")

        course_display = await get_course_code(course_id) or course_identifier
        return (f"Successfully created module in course {course_display}:\n"
                f"Module ID: {module_id}\n"
                f"Name: {module_name}\n"
                f"Position: {position}")

    @mcp.tool()
    @validate_params
    async def update_module(
        course_identifier: str | int,
        module_id: str | int,
        name: str | None = None,
        position: int | None = None,
        require_sequential_progress: bool | None = None,
        prerequisite_module_ids: list[int] | None = None,
        published: bool | None = None
    ) -> str:
        """Update a module's properties.

        Args:
            course_identifier: The Canvas course code (e.g., badm_554_120251_246794) or ID
            module_id: The Canvas module ID
            name: New name for the module
            position: New position in the module list
            require_sequential_progress: Students must complete items in order
            prerequisite_module_ids: IDs of modules that must be completed first
            published: Whether the module should be published
        """
        course_id = await get_course_id(course_identifier)
        module_id_str = str(module_id)

        data: dict = {"module": {}}

        if name is not None:
            data["module"]["name"] = name
        if position is not None:
            data["module"]["position"] = position
        if require_sequential_progress is not None:
            data["module"]["require_sequential_progress"] = require_sequential_progress
        if prerequisite_module_ids is not None:
            data["module"]["prerequisite_module_ids"] = prerequisite_module_ids
        if published is not None:
            data["module"]["published"] = published

        if not data["module"]:
            return "Error: No update parameters provided"

        response = await make_canvas_request(
            "put",
            f"/courses/{course_id}/modules/{module_id_str}",
            data=data
        )

        if "error" in response:
            return f"Error updating module: {response['error']}"

        course_display = await get_course_code(course_id) or course_identifier
        return (f"Successfully updated module {module_id} in course {course_display}:\n"
                f"Name: {response.get('name')}\n"
                f"Position: {response.get('position')}\n"
                f"Published: {response.get('published')}")

    @mcp.tool()
    @validate_params
    async def delete_module(
        course_identifier: str | int,
        module_id: str | int
    ) -> str:
        """Delete a module from a course.

        Args:
            course_identifier: The Canvas course code (e.g., badm_554_120251_246794) or ID
            module_id: The Canvas module ID
        """
        course_id = await get_course_id(course_identifier)
        module_id_str = str(module_id)

        response = await make_canvas_request(
            "delete",
            f"/courses/{course_id}/modules/{module_id_str}"
        )

        if "error" in response:
            return f"Error deleting module: {response['error']}"

        course_display = await get_course_code(course_id) or course_identifier
        return f"Successfully deleted module {module_id} from course {course_display}"

    @mcp.tool()
    @validate_params
    async def list_module_items(
        course_identifier: str | int,
        module_id: str | int,
        include: list[str] | None = None
    ) -> str:
        """List all items in a module.

        Args:
            course_identifier: The Canvas course code (e.g., badm_554_120251_246794) or ID
            module_id: The Canvas module ID
            include: Optional list of items to include (content_details)
        """
        course_id = await get_course_id(course_identifier)
        module_id_str = str(module_id)

        params: dict = {"per_page": 100}
        if include:
            params["include[]"] = include

        items = await fetch_all_paginated_results(
            f"/courses/{course_id}/modules/{module_id_str}/items",
            params
        )

        if isinstance(items, dict) and "error" in items:
            return f"Error fetching module items: {items['error']}"

        if not items:
            return f"No items found in module {module_id}."

        items_info = []
        for item in items:
            item_id = item.get("id")
            title = item.get("title", "Untitled")
            item_type = item.get("type", "unknown")
            position = item.get("position", 0)
            published = item.get("published", False)
            indent = item.get("indent", 0)

            items_info.append(
                f"ID: {item_id}\n"
                f"Position: {position}\n"
                f"Type: {item_type}\n"
                f"Title: {title}\n"
                f"Published: {published}\n"
                f"Indent: {indent}\n"
            )

        course_display = await get_course_code(course_id) or course_identifier
        return f"Module Items for Module {module_id} in Course {course_display}:\n\n" + "\n".join(items_info)

    @mcp.tool()
    @validate_params
    async def create_module_item(
        course_identifier: str | int,
        module_id: str | int,
        title: str,
        type: str,
        content_id: str | int | None = None,
        page_url: str | None = None,
        external_url: str | None = None,
        position: int | None = None,
        indent: int = 0
    ) -> str:
        """Create a new item in a module.

        Args:
            course_identifier: The Canvas course code (e.g., badm_554_120251_246794) or ID
            module_id: The Canvas module ID
            title: Item title
            type: Item type (File, Page, Discussion, Assignment, Quiz, SubHeader, ExternalUrl, ExternalTool)
            content_id: ID of the content (for File, Page, Discussion, Assignment, Quiz)
            page_url: URL for Page type items
            external_url: URL for ExternalUrl type items
            position: Position in the module (1-based)
            indent: Indentation level (0-3)
        """
        course_id = await get_course_id(course_identifier)
        module_id_str = str(module_id)

        data: dict = {
            "module_item": {
                "title": title,
                "type": type,
                "indent": indent
            }
        }

        if content_id is not None:
            data["module_item"]["content_id"] = str(content_id)
        if page_url is not None:
            data["module_item"]["page_url"] = page_url
        if external_url is not None:
            data["module_item"]["external_url"] = external_url
        if position is not None:
            data["module_item"]["position"] = position

        response = await make_canvas_request(
            "post",
            f"/courses/{course_id}/modules/{module_id_str}/items",
            data=data
        )

        if "error" in response:
            return f"Error creating module item: {response['error']}"

        item_id = response.get("id")
        item_title = response.get("title")
        item_type = response.get("type")

        course_display = await get_course_code(course_id) or course_identifier
        return (f"Successfully created module item in course {course_display}:\n"
                f"Item ID: {item_id}\n"
                f"Title: {item_title}\n"
                f"Type: {item_type}")

    @mcp.tool()
    @validate_params
    async def delete_module_item(
        course_identifier: str | int,
        module_id: str | int,
        item_id: str | int
    ) -> str:
        """Delete an item from a module.

        Args:
            course_identifier: The Canvas course code (e.g., badm_554_120251_246794) or ID
            module_id: The Canvas module ID
            item_id: The Canvas module item ID
        """
        course_id = await get_course_id(course_identifier)
        module_id_str = str(module_id)
        item_id_str = str(item_id)

        response = await make_canvas_request(
            "delete",
            f"/courses/{course_id}/modules/{module_id_str}/items/{item_id_str}"
        )

        if "error" in response:
            return f"Error deleting module item: {response['error']}"

        course_display = await get_course_code(course_id) or course_identifier
        return f"Successfully deleted module item {item_id} from module {module_id} in course {course_display}"
