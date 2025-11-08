"""File and folder management MCP tools for Canvas API."""

from mcp.server.fastmcp import FastMCP

from ..core.cache import get_course_code, get_course_id
from ..core.client import fetch_all_paginated_results, make_canvas_request
from ..core.dates import format_date
from ..core.validation import validate_params


def format_file_size(size_bytes: int) -> str:
    """Format file size in human-readable format.

    Args:
        size_bytes: Size in bytes

    Returns:
        Formatted size string (e.g., "1.5 MB")
    """
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.1f} GB"


def register_file_tools(mcp: FastMCP) -> None:
    """Register all file and folder management MCP tools."""

    @mcp.tool()
    @validate_params
    async def list_course_files(
        course_identifier: str | int,
        search_term: str | None = None,
        content_types: list[str] | None = None,
        sort: str = "updated_at",
        order: str = "desc"
    ) -> str:
        """List files in a course.

        Args:
            course_identifier: The Canvas course code (e.g., badm_554_120251_246794) or ID
            search_term: Optional search term to filter files by name
            content_types: Optional list of content types (e.g., ["application/pdf", "image/jpeg"])
            sort: Sort field (name, size, created_at, updated_at, content_type)
            order: Sort order (asc or desc)
        """
        course_id = await get_course_id(course_identifier)

        params: dict = {
            "per_page": 100,
            "sort": sort,
            "order": order
        }

        if search_term:
            params["search_term"] = search_term

        if content_types:
            params["content_types[]"] = content_types

        files = await fetch_all_paginated_results(f"/courses/{course_id}/files", params)

        if isinstance(files, dict) and "error" in files:
            return f"Error fetching files: {files['error']}"

        if not files:
            return f"No files found for course {course_identifier}."

        files_info = []
        total_size = 0

        for file in files:
            file_id = file.get("id")
            filename = file.get("display_name", file.get("filename", "Unknown"))
            size = file.get("size", 0)
            content_type = file.get("content-type", "unknown")
            created = format_date(file.get("created_at"))
            modified = format_date(file.get("modified_at"))
            url = file.get("url", "N/A")

            total_size += size

            files_info.append(
                f"ID: {file_id}\n"
                f"Name: {filename}\n"
                f"Size: {format_file_size(size)}\n"
                f"Type: {content_type}\n"
                f"Created: {created}\n"
                f"Modified: {modified}\n"
                f"URL: {url}\n"
            )

        course_display = await get_course_code(course_id) or course_identifier
        header = f"Files for Course {course_display}:\n"
        header += f"Total Files: {len(files)}\n"
        header += f"Total Size: {format_file_size(total_size)}\n\n"

        return header + "\n".join(files_info)

    @mcp.tool()
    @validate_params
    async def get_file_details(file_id: str | int) -> str:
        """Get detailed information about a specific file.

        Args:
            file_id: The Canvas file ID
        """
        file_id_str = str(file_id)

        response = await make_canvas_request("get", f"/files/{file_id_str}")

        if "error" in response:
            return f"Error fetching file details: {response['error']}"

        details = [
            f"ID: {response.get('id')}",
            f"Name: {response.get('display_name', response.get('filename', 'N/A'))}",
            f"Size: {format_file_size(response.get('size', 0))}",
            f"Content Type: {response.get('content-type', 'N/A')}",
            f"Created: {format_date(response.get('created_at'))}",
            f"Modified: {format_date(response.get('modified_at'))}",
            f"Locked: {response.get('locked', False)}",
            f"Hidden: {response.get('hidden', False)}",
            f"Lock at: {format_date(response.get('lock_at'))}",
            f"Unlock at: {format_date(response.get('unlock_at'))}",
            f"URL: {response.get('url', 'N/A')}"
        ]

        return f"File Details:\n\n" + "\n".join(details)

    @mcp.tool()
    @validate_params
    async def list_course_folders(
        course_identifier: str | int,
        sort: str = "name",
        order: str = "asc"
    ) -> str:
        """List folders in a course.

        Args:
            course_identifier: The Canvas course code (e.g., badm_554_120251_246794) or ID
            sort: Sort field (name, created_at, updated_at, position)
            order: Sort order (asc or desc)
        """
        course_id = await get_course_id(course_identifier)

        params = {
            "per_page": 100,
            "sort": sort,
            "order": order
        }

        folders = await fetch_all_paginated_results(f"/courses/{course_id}/folders", params)

        if isinstance(folders, dict) and "error" in folders:
            return f"Error fetching folders: {folders['error']}"

        if not folders:
            return f"No folders found for course {course_identifier}."

        folders_info = []
        for folder in folders:
            folder_id = folder.get("id")
            name = folder.get("name", "Unknown")
            full_name = folder.get("full_name", "")
            files_count = folder.get("files_count", 0)
            folders_count = folder.get("folders_count", 0)
            locked = folder.get("locked", False)
            hidden = folder.get("hidden", False)
            position = folder.get("position")

            folders_info.append(
                f"ID: {folder_id}\n"
                f"Name: {name}\n"
                f"Path: {full_name}\n"
                f"Files: {files_count}, Subfolders: {folders_count}\n"
                f"Position: {position}\n"
                f"Locked: {locked}, Hidden: {hidden}\n"
            )

        course_display = await get_course_code(course_id) or course_identifier
        return f"Folders for Course {course_display}:\n\n" + "\n".join(folders_info)

    @mcp.tool()
    @validate_params
    async def get_folder_details(folder_id: str | int) -> str:
        """Get detailed information about a specific folder.

        Args:
            folder_id: The Canvas folder ID
        """
        folder_id_str = str(folder_id)

        response = await make_canvas_request("get", f"/folders/{folder_id_str}")

        if "error" in response:
            return f"Error fetching folder details: {response['error']}"

        details = [
            f"ID: {response.get('id')}",
            f"Name: {response.get('name', 'N/A')}",
            f"Full Path: {response.get('full_name', 'N/A')}",
            f"Files Count: {response.get('files_count', 0)}",
            f"Folders Count: {response.get('folders_count', 0)}",
            f"Position: {response.get('position')}",
            f"Locked: {response.get('locked', False)}",
            f"Hidden: {response.get('hidden', False)}",
            f"Lock at: {format_date(response.get('lock_at'))}",
            f"Unlock at: {format_date(response.get('unlock_at'))}",
            f"Created: {format_date(response.get('created_at'))}",
            f"Updated: {format_date(response.get('updated_at'))}"
        ]

        return f"Folder Details:\n\n" + "\n".join(details)

    @mcp.tool()
    @validate_params
    async def list_folder_files(
        folder_id: str | int,
        search_term: str | None = None,
        content_types: list[str] | None = None,
        sort: str = "name",
        order: str = "asc"
    ) -> str:
        """List files in a specific folder.

        Args:
            folder_id: The Canvas folder ID
            search_term: Optional search term to filter files by name
            content_types: Optional list of content types (e.g., ["application/pdf"])
            sort: Sort field (name, size, created_at, updated_at, content_type)
            order: Sort order (asc or desc)
        """
        folder_id_str = str(folder_id)

        params: dict = {
            "per_page": 100,
            "sort": sort,
            "order": order
        }

        if search_term:
            params["search_term"] = search_term

        if content_types:
            params["content_types[]"] = content_types

        files = await fetch_all_paginated_results(f"/folders/{folder_id_str}/files", params)

        if isinstance(files, dict) and "error" in files:
            return f"Error fetching files: {files['error']}"

        if not files:
            return f"No files found in folder {folder_id}."

        files_info = []
        total_size = 0

        for file in files:
            file_id = file.get("id")
            filename = file.get("display_name", file.get("filename", "Unknown"))
            size = file.get("size", 0)
            content_type = file.get("content-type", "unknown")
            created = format_date(file.get("created_at"))
            url = file.get("url", "N/A")

            total_size += size

            files_info.append(
                f"ID: {file_id}\n"
                f"Name: {filename}\n"
                f"Size: {format_file_size(size)}\n"
                f"Type: {content_type}\n"
                f"Created: {created}\n"
                f"URL: {url}\n"
            )

        header = f"Files in Folder {folder_id}:\n"
        header += f"Total Files: {len(files)}\n"
        header += f"Total Size: {format_file_size(total_size)}\n\n"

        return header + "\n".join(files_info)

    @mcp.tool()
    @validate_params
    async def create_course_folder(
        course_identifier: str | int,
        name: str,
        parent_folder_id: str | int | None = None,
        locked: bool = False,
        hidden: bool = False
    ) -> str:
        """Create a new folder in a course.

        Args:
            course_identifier: The Canvas course code (e.g., badm_554_120251_246794) or ID
            name: Name for the new folder
            parent_folder_id: Optional parent folder ID (creates in root if not specified)
            locked: Whether the folder should be locked
            hidden: Whether the folder should be hidden
        """
        course_id = await get_course_id(course_identifier)

        data = {
            "name": name,
            "locked": locked,
            "hidden": hidden
        }

        if parent_folder_id:
            data["parent_folder_id"] = str(parent_folder_id)

        response = await make_canvas_request(
            "post",
            f"/courses/{course_id}/folders",
            data=data
        )

        if "error" in response:
            return f"Error creating folder: {response['error']}"

        folder_id = response.get("id")
        folder_name = response.get("name")
        full_name = response.get("full_name")

        course_display = await get_course_code(course_id) or course_identifier
        return (f"Successfully created folder in course {course_display}:\n"
                f"Folder ID: {folder_id}\n"
                f"Name: {folder_name}\n"
                f"Path: {full_name}")

    @mcp.tool()
    @validate_params
    async def update_folder(
        folder_id: str | int,
        name: str | None = None,
        locked: bool | None = None,
        hidden: bool | None = None,
        position: int | None = None
    ) -> str:
        """Update a folder's properties.

        Args:
            folder_id: The Canvas folder ID
            name: New name for the folder
            locked: Whether the folder should be locked
            hidden: Whether the folder should be hidden
            position: Position in folder list
        """
        folder_id_str = str(folder_id)

        data: dict = {}
        if name is not None:
            data["name"] = name
        if locked is not None:
            data["locked"] = locked
        if hidden is not None:
            data["hidden"] = hidden
        if position is not None:
            data["position"] = position

        if not data:
            return "Error: No update parameters provided"

        response = await make_canvas_request(
            "put",
            f"/folders/{folder_id_str}",
            data=data
        )

        if "error" in response:
            return f"Error updating folder: {response['error']}"

        return (f"Successfully updated folder {folder_id}:\n"
                f"Name: {response.get('name')}\n"
                f"Locked: {response.get('locked')}\n"
                f"Hidden: {response.get('hidden')}")

    @mcp.tool()
    @validate_params
    async def delete_folder(folder_id: str | int, force: bool = False) -> str:
        """Delete a folder.

        Args:
            folder_id: The Canvas folder ID
            force: If true, delete folder even if it contains files/folders
        """
        folder_id_str = str(folder_id)

        params = {"force": "true" if force else "false"}

        response = await make_canvas_request(
            "delete",
            f"/folders/{folder_id_str}",
            params=params
        )

        if "error" in response:
            return f"Error deleting folder: {response['error']}"

        return f"Successfully deleted folder {folder_id}"

    @mcp.tool()
    @validate_params
    async def update_file(
        file_id: str | int,
        name: str | None = None,
        locked: bool | None = None,
        hidden: bool | None = None
    ) -> str:
        """Update a file's properties.

        Args:
            file_id: The Canvas file ID
            name: New display name for the file
            locked: Whether the file should be locked
            hidden: Whether the file should be hidden
        """
        file_id_str = str(file_id)

        data: dict = {}
        if name is not None:
            data["name"] = name
        if locked is not None:
            data["locked"] = locked
        if hidden is not None:
            data["hidden"] = hidden

        if not data:
            return "Error: No update parameters provided"

        response = await make_canvas_request(
            "put",
            f"/files/{file_id_str}",
            data=data
        )

        if "error" in response:
            return f"Error updating file: {response['error']}"

        return (f"Successfully updated file {file_id}:\n"
                f"Name: {response.get('display_name')}\n"
                f"Locked: {response.get('locked')}\n"
                f"Hidden: {response.get('hidden')}")

    @mcp.tool()
    @validate_params
    async def delete_file(file_id: str | int) -> str:
        """Delete a file.

        Args:
            file_id: The Canvas file ID
        """
        file_id_str = str(file_id)

        response = await make_canvas_request("delete", f"/files/{file_id_str}")

        if "error" in response:
            return f"Error deleting file: {response['error']}"

        return f"Successfully deleted file {file_id}"
