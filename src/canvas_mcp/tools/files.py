"""File-related MCP tools for Canvas API.

Provides tools for uploading, downloading, and listing files in Canvas courses.
Uploaded files can be used with other tools like add_module_item (for adding
files to modules) and send_conversation (for attaching files to messages).

The Canvas file upload process uses a 3-step protocol:
1. Request upload URL from Canvas API
2. Upload file to external storage (S3/Instructure)
3. Confirm upload and get final file object

This module handles all three steps transparently.
"""

import os

from mcp.server.fastmcp import FastMCP

from ..core.cache import get_course_code, get_course_id
from ..core.client import (
    _get_http_client,
    fetch_all_paginated_results,
    make_canvas_request,
    upload_file_to_storage,
)
from ..core.file_validation import (
    FileValidationResult,
    format_file_size,
    validate_file_for_upload,
)
from ..core.validation import validate_params


def register_file_tools(mcp: FastMCP):
    """Register all file-related MCP tools."""

    @mcp.tool()
    @validate_params
    async def upload_course_file(
        course_identifier: str | int,
        file_path: str,
        folder_path: str | None = None,
        display_name: str | None = None,
        on_duplicate: str = "rename"
    ) -> str:
        """Upload a file to Canvas course storage.

        Uploads a local file to a Canvas course. The returned file ID can be used with:
        - add_module_item(item_type='File', content_id=<file_id>) to add to modules
        - send_conversation(attachment_ids=[<file_id>]) to attach to messages

        Args:
            course_identifier: The Canvas course code (e.g., badm_554_120251_246794) or ID
            file_path: Absolute path to the local file to upload
            folder_path: Canvas folder path (default: "course files" root).
                        Examples: "Syllabus", "Week 1/Readings", "Uploads"
            display_name: Override the filename shown in Canvas. If not provided,
                         uses the original filename (sanitized).
            on_duplicate: How to handle duplicate filenames:
                         "rename" (default) - add number suffix
                         "overwrite" - replace existing file

        Returns:
            Success message with file ID and details, or error message.

        Example usage:
            1. Upload a PDF:
               upload_course_file("CS101", "/path/to/syllabus.pdf")
               → "✅ Uploaded! File ID: 12345, Name: syllabus.pdf"

            2. Then add to a module:
               add_module_item("CS101", module_id, "File", content_id=12345)

            3. Or attach to a message:
               send_conversation("CS101", ["student_id"], "Subject", "Body",
                               attachment_ids=["12345"])
        """
        # Validate on_duplicate parameter
        if on_duplicate not in ("rename", "overwrite"):
            return f"Invalid on_duplicate value: '{on_duplicate}'. Must be 'rename' or 'overwrite'."

        # Step 0: Validate the file locally first
        validation: FileValidationResult = validate_file_for_upload(file_path)

        if not validation.valid:
            return f"❌ File validation failed: {validation.error}"

        # Get course ID for API calls
        course_id = await get_course_id(course_identifier)

        # Determine the filename to use in Canvas
        upload_filename = display_name if display_name else validation.sanitized_name

        # Step 1: Request upload URL from Canvas API
        upload_request_params = {
            "name": upload_filename,
            "size": validation.file_size,
            "content_type": validation.mime_type,
            "on_duplicate": on_duplicate,
        }

        # Add folder path if specified
        if folder_path:
            # Canvas expects folder path relative to course files
            upload_request_params["parent_folder_path"] = folder_path

        # Request the upload slot
        step1_response = await make_canvas_request(
            "post",
            f"/courses/{course_id}/files",
            data=upload_request_params,
            use_form_data=True
        )

        if isinstance(step1_response, dict) and "error" in step1_response:
            return f"❌ Failed to request upload URL: {step1_response['error']}"

        # Extract upload URL and parameters
        upload_url = step1_response.get("upload_url")
        upload_params = step1_response.get("upload_params", {})

        if not upload_url:
            return "❌ Canvas API did not return an upload URL. Check API permissions."

        # Step 2: Upload file to external storage
        step2_response = await upload_file_to_storage(
            upload_url=upload_url,
            upload_params=upload_params,
            file_path=file_path,
            filename=upload_filename,
            content_type=validation.mime_type
        )

        if isinstance(step2_response, dict) and "error" in step2_response:
            error_msg = step2_response.get("error", "Unknown error")
            details = step2_response.get("details", "")
            if details:
                return f"❌ File upload failed: {error_msg}\nDetails: {details}"
            return f"❌ File upload failed: {error_msg}"

        # Step 3: Extract file information from response
        # The response could be from:
        # - Direct storage response (200/201)
        # - Redirect confirmation from Canvas API

        file_id = step2_response.get("id")
        file_name = step2_response.get("display_name") or step2_response.get("filename") or upload_filename
        file_url = step2_response.get("url", "")
        file_folder_id = step2_response.get("folder_id")

        # If we got a success but no file ID, the file might need confirmation
        # This can happen with some storage backends
        if not file_id and step2_response.get("success"):
            # Try to find the file by name in the course
            # This is a fallback for edge cases
            return (
                "⚠️ Upload appears successful but file ID not returned. "
                "The file may need manual verification in Canvas."
            )

        if not file_id:
            return (
                "❌ Upload completed but no file ID received. "
                f"Response: {step2_response}"
            )

        # Format success response
        course_display = await get_course_code(course_id) or course_identifier
        file_size_str = format_file_size(validation.file_size)

        result = "✅ File uploaded successfully!\n\n"
        result += f"**{file_name}**\n"
        result += f"  File ID: {file_id}\n"
        result += f"  Course: {course_display}\n"
        result += f"  Size: {file_size_str}\n"
        result += f"  Type: {validation.mime_type}\n"

        if file_folder_id:
            result += f"  Folder ID: {file_folder_id}\n"

        if folder_path:
            result += f"  Folder Path: {folder_path}\n"

        result += "\n**Next steps:**\n"
        result += f"  - Add to module: add_module_item(..., item_type='File', content_id={file_id})\n"
        result += f"  - Attach to message: send_conversation(..., attachment_ids=['{file_id}'])\n"

        if file_url:
            result += f"  - Direct URL: {file_url}\n"

        return result

    @mcp.tool()
    @validate_params
    async def download_course_file(
        course_identifier: str | int,
        file_id: str | int,
        save_directory: str | None = None,
    ) -> str:
        """Download a file from a Canvas course to the local filesystem.

        Fetches a file from Canvas by its file ID and saves it locally. Use
        list_course_files or list_module_items to find file IDs.

        Args:
            course_identifier: The Canvas course code (e.g., badm_554_120251_246794) or ID
            file_id: The Canvas file ID (from list_module_items content_id or list_course_files)
            save_directory: Local directory to save the file. Defaults to /tmp.
                           The directory must already exist.

        Returns:
            Success message with local file path, or error message.

        Example usage:
            1. Find files in a module:
               list_module_items("52607", module_id=356544)
               → Shows files with Content IDs

            2. Download a specific file:
               download_course_file("52607", file_id=14069275)
               → "Downloaded: Midterm_Review_2026.pdf | Path: /tmp/Midterm_Review_2026.pdf"

            3. Download to a specific directory:
               download_course_file("52607", 14069275, save_directory="/Users/me/Downloads")
        """
        course_id = await get_course_id(course_identifier)

        # Get file metadata from Canvas API
        file_info = await make_canvas_request(
            "get",
            f"/courses/{course_id}/files/{file_id}"
        )

        if isinstance(file_info, dict) and "error" in file_info:
            return f"Error getting file info: {file_info['error']}"

        filename = file_info.get("display_name") or file_info.get("filename", f"file_{file_id}")
        download_url = file_info.get("url")
        file_size = file_info.get("size", 0)
        content_type = file_info.get("content-type", "unknown")

        if not download_url:
            return "Error: No download URL available for this file. Check permissions."

        # Determine save path
        save_dir = save_directory or "/tmp"
        if not os.path.isdir(save_dir):
            return f"Error: Directory does not exist: {save_dir}"

        save_path = os.path.join(save_dir, filename)

        # Download the file using the authenticated client
        client = _get_http_client()
        try:
            response = await client.get(download_url, follow_redirects=True)
            response.raise_for_status()

            with open(save_path, 'wb') as f:
                f.write(response.content)

            size_str = format_file_size(len(response.content))
            course_display = await get_course_code(course_id) or course_identifier

            result = f"Downloaded: {filename}\n"
            result += f"  Path: {save_path}\n"
            result += f"  Size: {size_str}\n"
            result += f"  Type: {content_type}\n"
            result += f"  Course: {course_display}\n"
            return result

        except Exception as e:
            return f"Error downloading file: {str(e)}"

    @mcp.tool()
    @validate_params
    async def list_course_files(
        course_identifier: str | int,
        search_term: str | None = None,
        sort: str = "updated_at",
        order: str = "desc",
    ) -> str:
        """List files in a Canvas course with optional search.

        Browse all files uploaded to a course. Useful for finding file IDs
        needed by download_course_file.

        Args:
            course_identifier: The Canvas course code (e.g., badm_554_120251_246794) or ID
            search_term: Optional search string to filter files by name
            sort: Sort field - one of: name, size, created_at, updated_at, content_type
                  (default: updated_at)
            order: Sort order - "asc" or "desc" (default: desc)

        Returns:
            Formatted list of files with IDs, names, sizes, and types.

        Example usage:
            list_course_files("52607")
            list_course_files("52607", search_term="midterm")
        """
        course_id = await get_course_id(course_identifier)

        params = {
            "per_page": 100,
            "sort": sort,
            "order": order,
        }
        if search_term:
            params["search_term"] = search_term

        files = await fetch_all_paginated_results(
            f"/courses/{course_id}/files",
            params
        )

        if isinstance(files, dict) and "error" in files:
            return f"Error listing files: {files['error']}"

        if not files:
            msg = "No files found"
            if search_term:
                msg += f" matching '{search_term}'"
            return msg

        course_display = await get_course_code(course_id) or course_identifier
        result = f"Files in {course_display}:\n\n"

        for f in files:
            fid = f.get("id", "?")
            name = f.get("display_name") or f.get("filename", "unknown")
            size = format_file_size(f.get("size", 0))
            ctype = f.get("content-type", "unknown")
            result += f"  ID: {fid} | {name} ({size}, {ctype})\n"

        result += f"\nTotal: {len(files)} file(s)"
        return result
