"""
File Tools Unit Tests

Tests for the Canvas file upload tools:
- upload_course_file
- file validation utilities

These tests use mocking to avoid requiring real Canvas API access.
"""

import pytest
from unittest.mock import patch, AsyncMock


# Sample mock data for Canvas API responses
MOCK_UPLOAD_REQUEST_RESPONSE = {
    "upload_url": "https://instructure-uploads.s3.amazonaws.com/upload",
    "upload_params": {
        "key": "account_12345/attachments/67890",
        "Policy": "eyJleHBpcmF0aW9uIjoiMjAyNi0wMS0yMFQwMDowMDowMFoifQ==",
        "x-amz-signature": "abc123signature",
        "x-amz-credential": "AKIA.../s3/aws4_request",
        "x-amz-algorithm": "AWS4-HMAC-SHA256",
        "x-amz-date": "20260120T000000Z",
        "success_action_redirect": "https://canvas.example.com/api/v1/files/confirm"
    }
}

MOCK_UPLOAD_SUCCESS_RESPONSE = {
    "id": 12345,
    "uuid": "abc123-def456",
    "folder_id": 67890,
    "display_name": "syllabus.pdf",
    "filename": "syllabus.pdf",
    "content-type": "application/pdf",
    "url": "https://canvas.example.com/files/12345/download",
    "size": 102400,
    "created_at": "2026-01-20T12:00:00Z",
    "updated_at": "2026-01-20T12:00:00Z"
}


@pytest.fixture
def mock_canvas_api():
    """Fixture to mock Canvas API calls."""
    with patch('canvas_mcp.tools.files.get_course_id') as mock_get_id, \
         patch('canvas_mcp.tools.files.get_course_code') as mock_get_code, \
         patch('canvas_mcp.tools.files.make_canvas_request') as mock_request, \
         patch('canvas_mcp.tools.files.upload_file_to_storage') as mock_upload:

        mock_get_id.return_value = "60366"
        mock_get_code.return_value = "badm_350_120251"

        yield {
            'get_course_id': mock_get_id,
            'get_course_code': mock_get_code,
            'make_canvas_request': mock_request,
            'upload_file_to_storage': mock_upload
        }


@pytest.fixture
def mock_file_validation():
    """Fixture to mock file validation."""
    with patch('canvas_mcp.tools.files.validate_file_for_upload') as mock_validate:
        yield mock_validate


def get_tool_function(tool_name: str):
    """Get a tool function by name from the registered tools."""
    from mcp.server.fastmcp import FastMCP
    from canvas_mcp.tools.files import register_file_tools

    # Create a mock MCP server and register tools
    mcp = FastMCP("test")

    # Store captured functions
    captured_functions = {}

    # Override the tool decorator to capture the function
    original_tool = mcp.tool

    def capturing_tool(*args, **kwargs):
        decorator = original_tool(*args, **kwargs)
        def wrapper(fn):
            captured_functions[fn.__name__] = fn
            return decorator(fn)
        return wrapper

    mcp.tool = capturing_tool
    register_file_tools(mcp)

    return captured_functions.get(tool_name)


class TestFileValidation:
    """Tests for file validation utilities."""

    def test_validate_existing_file(self, tmp_path):
        """Test validation of a valid file."""
        from canvas_mcp.core.file_validation import validate_file_for_upload

        # Create a test file
        test_file = tmp_path / "test.pdf"
        test_file.write_bytes(b"PDF content here" * 100)

        result = validate_file_for_upload(str(test_file))

        assert result.valid is True
        assert result.error is None
        assert result.file_size > 0
        assert result.mime_type == "application/pdf"
        assert result.sanitized_name == "test.pdf"

    def test_validate_nonexistent_file(self):
        """Test validation fails for missing file."""
        from canvas_mcp.core.file_validation import validate_file_for_upload

        result = validate_file_for_upload("/nonexistent/path/file.pdf")

        assert result.valid is False
        assert "not found" in result.error.lower()

    def test_validate_empty_file(self, tmp_path):
        """Test validation fails for empty file."""
        from canvas_mcp.core.file_validation import validate_file_for_upload

        # Create an empty file
        test_file = tmp_path / "empty.pdf"
        test_file.touch()

        result = validate_file_for_upload(str(test_file))

        assert result.valid is False
        assert "empty" in result.error.lower()

    def test_validate_file_too_large(self, tmp_path):
        """Test validation fails for oversized file."""
        from canvas_mcp.core.file_validation import validate_file_for_upload

        # Create a test file
        test_file = tmp_path / "large.pdf"
        test_file.write_bytes(b"x" * 1000)

        # Validate with a tiny limit
        result = validate_file_for_upload(str(test_file), max_size_bytes=500)

        assert result.valid is False
        assert "too large" in result.error.lower()

    def test_validate_disallowed_extension(self, tmp_path):
        """Test validation fails for disallowed extension."""
        from canvas_mcp.core.file_validation import validate_file_for_upload

        # Create a file with disallowed extension
        test_file = tmp_path / "script.exe"
        test_file.write_bytes(b"binary content")

        result = validate_file_for_upload(str(test_file))

        assert result.valid is False
        assert "not allowed" in result.error.lower()

    def test_validate_custom_allowed_extensions(self, tmp_path):
        """Test validation with custom allowed extensions."""
        from canvas_mcp.core.file_validation import validate_file_for_upload

        # Create a test file
        test_file = tmp_path / "data.custom"
        test_file.write_bytes(b"custom content")

        # Validate with custom extensions
        result = validate_file_for_upload(
            str(test_file),
            allowed_extensions={".custom"}
        )

        assert result.valid is True


class TestMimeTypeDetection:
    """Tests for MIME type detection."""

    def test_detect_pdf_mime_type(self, tmp_path):
        """Test PDF MIME type detection."""
        from canvas_mcp.core.file_validation import detect_mime_type

        test_file = tmp_path / "doc.pdf"
        test_file.touch()

        assert detect_mime_type(str(test_file)) == "application/pdf"

    def test_detect_docx_mime_type(self, tmp_path):
        """Test DOCX MIME type detection."""
        from canvas_mcp.core.file_validation import detect_mime_type

        test_file = tmp_path / "doc.docx"
        test_file.touch()

        mime = detect_mime_type(str(test_file))
        assert "word" in mime.lower() or "document" in mime.lower()

    def test_detect_png_mime_type(self, tmp_path):
        """Test PNG MIME type detection."""
        from canvas_mcp.core.file_validation import detect_mime_type

        test_file = tmp_path / "image.png"
        test_file.touch()

        assert detect_mime_type(str(test_file)) == "image/png"

    def test_detect_unknown_mime_type(self, tmp_path):
        """Test fallback for unknown extension."""
        from canvas_mcp.core.file_validation import detect_mime_type

        test_file = tmp_path / "data.xyz123"
        test_file.touch()

        mime = detect_mime_type(str(test_file))
        assert mime == "application/octet-stream"


class TestFilenameSanitization:
    """Tests for filename sanitization."""

    def test_sanitize_basic_filename(self):
        """Test basic filename passes through."""
        from canvas_mcp.core.file_validation import sanitize_filename

        assert sanitize_filename("document.pdf") == "document.pdf"

    def test_sanitize_filename_with_spaces(self):
        """Test spaces are converted to underscores."""
        from canvas_mcp.core.file_validation import sanitize_filename

        result = sanitize_filename("my document.pdf")
        assert " " not in result
        assert result == "my_document.pdf"

    def test_sanitize_filename_with_special_chars(self):
        """Test special characters are removed."""
        from canvas_mcp.core.file_validation import sanitize_filename

        result = sanitize_filename("file (1) [v2].pdf")
        assert "(" not in result
        assert ")" not in result
        assert "[" not in result
        assert "]" not in result
        assert result.endswith(".pdf")

    def test_sanitize_preserves_extension(self):
        """Test file extension is preserved."""
        from canvas_mcp.core.file_validation import sanitize_filename

        result = sanitize_filename("weird@#$name.DOCX")
        assert result.endswith(".docx")

    def test_sanitize_collapses_multiple_underscores(self):
        """Test multiple underscores are collapsed."""
        from canvas_mcp.core.file_validation import sanitize_filename

        result = sanitize_filename("file___with___many.pdf")
        assert "___" not in result


class TestFileSizeFormatting:
    """Tests for file size formatting."""

    def test_format_bytes(self):
        """Test formatting bytes."""
        from canvas_mcp.core.file_validation import format_file_size

        assert format_file_size(500) == "500 B"

    def test_format_kilobytes(self):
        """Test formatting kilobytes."""
        from canvas_mcp.core.file_validation import format_file_size

        result = format_file_size(1536)
        assert "KB" in result

    def test_format_megabytes(self):
        """Test formatting megabytes."""
        from canvas_mcp.core.file_validation import format_file_size

        result = format_file_size(1536000)
        assert "MB" in result

    def test_format_gigabytes(self):
        """Test formatting gigabytes."""
        from canvas_mcp.core.file_validation import format_file_size

        result = format_file_size(1536000000)
        assert "GB" in result


class TestUploadCourseFile:
    """Tests for upload_course_file tool."""

    @pytest.mark.asyncio
    async def test_upload_success(self, mock_canvas_api, mock_file_validation, tmp_path):
        """Test successful file upload."""
        from canvas_mcp.core.file_validation import FileValidationResult

        # Create a test file
        test_file = tmp_path / "syllabus.pdf"
        test_file.write_bytes(b"PDF content" * 100)

        # Mock validation to succeed
        mock_file_validation.return_value = FileValidationResult(
            valid=True,
            error=None,
            file_size=1100,
            mime_type="application/pdf",
            sanitized_name="syllabus.pdf"
        )

        # Mock Canvas API responses
        mock_canvas_api['make_canvas_request'].return_value = MOCK_UPLOAD_REQUEST_RESPONSE
        mock_canvas_api['upload_file_to_storage'].return_value = MOCK_UPLOAD_SUCCESS_RESPONSE

        upload_course_file = get_tool_function('upload_course_file')
        result = await upload_course_file("badm_350_120251", str(test_file))

        # Verify success
        assert "successfully" in result.lower()
        assert "12345" in result  # File ID
        assert "syllabus.pdf" in result

    @pytest.mark.asyncio
    async def test_upload_validation_failure(self, mock_canvas_api, mock_file_validation):
        """Test upload fails when file validation fails."""
        from canvas_mcp.core.file_validation import FileValidationResult

        # Mock validation to fail
        mock_file_validation.return_value = FileValidationResult(
            valid=False,
            error="File not found: /nonexistent/file.pdf",
            file_size=0,
            mime_type="",
            sanitized_name=""
        )

        upload_course_file = get_tool_function('upload_course_file')
        result = await upload_course_file("60366", "/nonexistent/file.pdf")

        assert "❌" in result
        assert "validation failed" in result.lower()
        assert "not found" in result.lower()

    @pytest.mark.asyncio
    async def test_upload_api_request_failure(self, mock_canvas_api, mock_file_validation, tmp_path):
        """Test upload fails when Canvas API rejects request."""
        from canvas_mcp.core.file_validation import FileValidationResult

        test_file = tmp_path / "test.pdf"
        test_file.write_bytes(b"content")

        mock_file_validation.return_value = FileValidationResult(
            valid=True,
            error=None,
            file_size=7,
            mime_type="application/pdf",
            sanitized_name="test.pdf"
        )

        # Mock Canvas API to return error
        mock_canvas_api['make_canvas_request'].return_value = {
            "error": "Insufficient permissions"
        }

        upload_course_file = get_tool_function('upload_course_file')
        result = await upload_course_file("60366", str(test_file))

        assert "❌" in result
        assert "failed to request upload url" in result.lower()

    @pytest.mark.asyncio
    async def test_upload_storage_failure(self, mock_canvas_api, mock_file_validation, tmp_path):
        """Test upload fails when storage upload fails."""
        from canvas_mcp.core.file_validation import FileValidationResult

        test_file = tmp_path / "test.pdf"
        test_file.write_bytes(b"content")

        mock_file_validation.return_value = FileValidationResult(
            valid=True,
            error=None,
            file_size=7,
            mime_type="application/pdf",
            sanitized_name="test.pdf"
        )

        # Mock step 1 to succeed
        mock_canvas_api['make_canvas_request'].return_value = MOCK_UPLOAD_REQUEST_RESPONSE

        # Mock step 2 to fail
        mock_canvas_api['upload_file_to_storage'].return_value = {
            "error": "Storage upload timed out"
        }

        upload_course_file = get_tool_function('upload_course_file')
        result = await upload_course_file("60366", str(test_file))

        assert "❌" in result
        assert "upload failed" in result.lower()

    @pytest.mark.asyncio
    async def test_upload_with_custom_display_name(self, mock_canvas_api, mock_file_validation, tmp_path):
        """Test upload with custom display name."""
        from canvas_mcp.core.file_validation import FileValidationResult

        test_file = tmp_path / "doc.pdf"
        test_file.write_bytes(b"content")

        mock_file_validation.return_value = FileValidationResult(
            valid=True,
            error=None,
            file_size=7,
            mime_type="application/pdf",
            sanitized_name="doc.pdf"
        )

        mock_canvas_api['make_canvas_request'].return_value = MOCK_UPLOAD_REQUEST_RESPONSE
        mock_canvas_api['upload_file_to_storage'].return_value = {
            **MOCK_UPLOAD_SUCCESS_RESPONSE,
            "display_name": "Course Syllabus 2026.pdf"
        }

        upload_course_file = get_tool_function('upload_course_file')
        result = await upload_course_file(
            "60366",
            str(test_file),
            display_name="Course Syllabus 2026.pdf"
        )

        assert "successfully" in result.lower()
        # Verify display_name was used in the API call
        call_args = mock_canvas_api['make_canvas_request'].call_args
        assert call_args is not None
        # The name should be in the data parameter
        data = call_args[1].get('data', {})
        assert data.get('name') == "Course Syllabus 2026.pdf"

    @pytest.mark.asyncio
    async def test_upload_with_folder_path(self, mock_canvas_api, mock_file_validation, tmp_path):
        """Test upload to specific folder."""
        from canvas_mcp.core.file_validation import FileValidationResult

        test_file = tmp_path / "reading.pdf"
        test_file.write_bytes(b"content")

        mock_file_validation.return_value = FileValidationResult(
            valid=True,
            error=None,
            file_size=7,
            mime_type="application/pdf",
            sanitized_name="reading.pdf"
        )

        mock_canvas_api['make_canvas_request'].return_value = MOCK_UPLOAD_REQUEST_RESPONSE
        mock_canvas_api['upload_file_to_storage'].return_value = MOCK_UPLOAD_SUCCESS_RESPONSE

        upload_course_file = get_tool_function('upload_course_file')
        result = await upload_course_file(
            "60366",
            str(test_file),
            folder_path="Week 1/Readings"
        )

        assert "successfully" in result.lower()
        # Verify folder_path was passed to API
        call_args = mock_canvas_api['make_canvas_request'].call_args
        data = call_args[1].get('data', {})
        assert data.get('parent_folder_path') == "Week 1/Readings"

    @pytest.mark.asyncio
    async def test_upload_invalid_on_duplicate(self, mock_canvas_api, mock_file_validation, tmp_path):
        """Test upload fails with invalid on_duplicate value."""
        from canvas_mcp.core.file_validation import FileValidationResult

        test_file = tmp_path / "test.pdf"
        test_file.write_bytes(b"content")

        mock_file_validation.return_value = FileValidationResult(
            valid=True,
            error=None,
            file_size=7,
            mime_type="application/pdf",
            sanitized_name="test.pdf"
        )

        upload_course_file = get_tool_function('upload_course_file')
        result = await upload_course_file(
            "60366",
            str(test_file),
            on_duplicate="invalid"
        )

        assert "invalid on_duplicate" in result.lower()

    @pytest.mark.asyncio
    async def test_upload_overwrite_mode(self, mock_canvas_api, mock_file_validation, tmp_path):
        """Test upload with overwrite mode."""
        from canvas_mcp.core.file_validation import FileValidationResult

        test_file = tmp_path / "test.pdf"
        test_file.write_bytes(b"content")

        mock_file_validation.return_value = FileValidationResult(
            valid=True,
            error=None,
            file_size=7,
            mime_type="application/pdf",
            sanitized_name="test.pdf"
        )

        mock_canvas_api['make_canvas_request'].return_value = MOCK_UPLOAD_REQUEST_RESPONSE
        mock_canvas_api['upload_file_to_storage'].return_value = MOCK_UPLOAD_SUCCESS_RESPONSE

        upload_course_file = get_tool_function('upload_course_file')
        result = await upload_course_file(
            "60366",
            str(test_file),
            on_duplicate="overwrite"
        )

        assert "successfully" in result.lower()
        # Verify on_duplicate was passed
        call_args = mock_canvas_api['make_canvas_request'].call_args
        data = call_args[1].get('data', {})
        assert data.get('on_duplicate') == "overwrite"


class TestUploadResponseParsing:
    """Tests for upload response parsing edge cases."""

    @pytest.mark.asyncio
    async def test_upload_no_upload_url(self, mock_canvas_api, mock_file_validation, tmp_path):
        """Test handling when Canvas doesn't return upload URL."""
        from canvas_mcp.core.file_validation import FileValidationResult

        test_file = tmp_path / "test.pdf"
        test_file.write_bytes(b"content")

        mock_file_validation.return_value = FileValidationResult(
            valid=True,
            error=None,
            file_size=7,
            mime_type="application/pdf",
            sanitized_name="test.pdf"
        )

        # Return response without upload_url
        mock_canvas_api['make_canvas_request'].return_value = {
            "status": "ok"
        }

        upload_course_file = get_tool_function('upload_course_file')
        result = await upload_course_file("60366", str(test_file))

        assert "❌" in result
        assert "upload url" in result.lower()

    @pytest.mark.asyncio
    async def test_upload_no_file_id_in_response(self, mock_canvas_api, mock_file_validation, tmp_path):
        """Test handling when storage response lacks file ID."""
        from canvas_mcp.core.file_validation import FileValidationResult

        test_file = tmp_path / "test.pdf"
        test_file.write_bytes(b"content")

        mock_file_validation.return_value = FileValidationResult(
            valid=True,
            error=None,
            file_size=7,
            mime_type="application/pdf",
            sanitized_name="test.pdf"
        )

        mock_canvas_api['make_canvas_request'].return_value = MOCK_UPLOAD_REQUEST_RESPONSE
        # Return response without id field
        mock_canvas_api['upload_file_to_storage'].return_value = {
            "success": True,
            "status_code": 201
        }

        upload_course_file = get_tool_function('upload_course_file')
        result = await upload_course_file("60366", str(test_file))

        # Should warn about missing file ID
        assert "⚠️" in result or "verification" in result.lower()


class TestAllowedExtensions:
    """Tests for allowed file extension list."""

    def test_common_document_extensions_allowed(self, tmp_path):
        """Test common document extensions are allowed."""
        from canvas_mcp.core.file_validation import validate_file_for_upload

        extensions = [".pdf", ".doc", ".docx", ".txt", ".csv"]

        for ext in extensions:
            test_file = tmp_path / f"test{ext}"
            test_file.write_bytes(b"content")
            result = validate_file_for_upload(str(test_file))
            assert result.valid is True, f"Extension {ext} should be allowed"

    def test_image_extensions_allowed(self, tmp_path):
        """Test image extensions are allowed."""
        from canvas_mcp.core.file_validation import validate_file_for_upload

        extensions = [".png", ".jpg", ".jpeg", ".gif"]

        for ext in extensions:
            test_file = tmp_path / f"image{ext}"
            test_file.write_bytes(b"image content")
            result = validate_file_for_upload(str(test_file))
            assert result.valid is True, f"Extension {ext} should be allowed"

    def test_code_extensions_allowed(self, tmp_path):
        """Test code file extensions are allowed."""
        from canvas_mcp.core.file_validation import validate_file_for_upload

        extensions = [".py", ".js", ".ts", ".html", ".css", ".json"]

        for ext in extensions:
            test_file = tmp_path / f"code{ext}"
            test_file.write_bytes(b"code content")
            result = validate_file_for_upload(str(test_file))
            assert result.valid is True, f"Extension {ext} should be allowed"

    def test_executable_extensions_blocked(self, tmp_path):
        """Test executable extensions are blocked."""
        from canvas_mcp.core.file_validation import validate_file_for_upload

        extensions = [".exe", ".bat", ".sh", ".dll", ".so"]

        for ext in extensions:
            test_file = tmp_path / f"file{ext}"
            test_file.write_bytes(b"content")
            result = validate_file_for_upload(str(test_file))
            assert result.valid is False, f"Extension {ext} should be blocked"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
