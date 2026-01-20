"""File-related MCP tools for Canvas API.

Provides tools for uploading files to Canvas courses. Uploaded files can be
used with other tools like add_module_item (for adding files to modules)
and send_conversation (for attaching files to messages).

The Canvas file upload process uses a 3-step protocol:
1. Request upload URL from Canvas API
2. Upload file to external storage (S3/Instructure)
3. Confirm upload and get final file object

This module handles all three steps transparently.
"""

from typing import Optional, Union

from mcp.server.fastmcp import FastMCP

from ..core.cache import get_course_code, get_course_id
from ..core.client import make_canvas_request, upload_file_to_storage
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
        course_identifier: Union[str, int],
        file_path: str,
        folder_path: Optional[str] = None,
        display_name: Optional[str] = None,
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

        result = f"✅ File uploaded successfully!\n\n"
        result += f"**{file_name}**\n"
        result += f"  File ID: {file_id}\n"
        result += f"  Course: {course_display}\n"
        result += f"  Size: {file_size_str}\n"
        result += f"  Type: {validation.mime_type}\n"

        if file_folder_id:
            result += f"  Folder ID: {file_folder_id}\n"

        if folder_path:
            result += f"  Folder Path: {folder_path}\n"

        result += f"\n**Next steps:**\n"
        result += f"  - Add to module: add_module_item(..., item_type='File', content_id={file_id})\n"
        result += f"  - Attach to message: send_conversation(..., attachment_ids=['{file_id}'])\n"

        if file_url:
            result += f"  - Direct URL: {file_url}\n"

        return result
