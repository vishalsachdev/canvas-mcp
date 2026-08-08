"""Host-filesystem boundary invariants for the Canvas file tools.

``download_course_file`` writes to the server's filesystem and
``upload_course_file`` reads from it. Both are correct on a local stdio server
— that filesystem is the caller's own machine — and both are cross-boundary
primitives on a shared HTTP server, where the caller is remote:

- download lets the caller pick the destination directory while Canvas supplies
  the filename and bytes, i.e. an arbitrary write as the service account.
- upload lets the caller name any file the service account can read and copy it
  into their own Canvas course, i.e. an arbitrary read.

These tests pin the transport refusal for both, plus the local-mode hardening
that keeps a Canvas-controlled filename from clobbering an existing file.
"""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def get_tool_function(tool_name: str):
    """Get a tool function by name from the registered file tools."""
    from fastmcp import FastMCP

    from canvas_mcp.tools.files import (
        register_educator_file_tools,
        register_shared_file_tools,
    )

    mcp = FastMCP("test")
    captured: dict = {}
    original_tool = mcp.tool

    def capturing_tool(*args, **kwargs):
        decorator = original_tool(*args, **kwargs)

        def wrapper(fn):
            captured[fn.__name__] = fn
            return decorator(fn)

        return wrapper

    mcp.tool = capturing_tool
    register_shared_file_tools(mcp)
    register_educator_file_tools(mcp)
    return captured.get(tool_name)


def _mock_stream(mock_client, content=b"file content here", raise_on_status=None):
    """Build a mock streaming response for canvas_authenticated_client()."""
    mock_response = AsyncMock()
    if raise_on_status is None:
        mock_response.raise_for_status = MagicMock()
    else:
        mock_response.raise_for_status = MagicMock(side_effect=raise_on_status)

    async def aiter_bytes(chunk_size=8192):
        yield content

    mock_response.aiter_bytes = aiter_bytes

    stream_cm = AsyncMock()
    stream_cm.__aenter__ = AsyncMock(return_value=mock_response)
    stream_cm.__aexit__ = AsyncMock(return_value=False)

    http = AsyncMock()
    http.stream = MagicMock(return_value=stream_cm)

    client_cm = AsyncMock()
    client_cm.__aenter__ = AsyncMock(return_value=http)
    client_cm.__aexit__ = AsyncMock(return_value=False)
    mock_client.return_value = client_cm
    return http


FILE_INFO = {
    "id": 12345,
    "display_name": "syllabus.pdf",
    "url": "https://canvas.example.com/files/12345/download",
    "size": 1024,
    "content-type": "application/pdf",
}


class TestDownloadRefusedOverHttp:
    """A remote caller must never direct a write onto the server's filesystem."""

    @pytest.mark.asyncio
    async def test_download_refused_over_http(self, tmp_path):
        with patch(
            "canvas_mcp.tools.files.is_http_request_active", return_value=True
        ), patch(
            "canvas_mcp.tools.files.make_canvas_request", new_callable=AsyncMock
        ) as request, patch(
            "canvas_mcp.tools.files.get_course_id", new=AsyncMock(return_value="60366")
        ):
            download = get_tool_function("download_course_file")
            result = await download("badm_350", 12345, save_directory=str(tmp_path))

        assert "only available on a local (stdio) server" in result
        assert "read_course_file" in result
        # The guard runs before any Canvas call, so no request is issued at all.
        assert request.call_count == 0
        # Nothing was written into the caller-chosen directory.
        assert list(tmp_path.iterdir()) == []

    @pytest.mark.asyncio
    async def test_download_allowed_over_stdio(self, tmp_path):
        """The stdio path still works — the guard is transport-scoped, not a removal."""
        with patch(
            "canvas_mcp.tools.files.is_http_request_active", return_value=False
        ), patch(
            "canvas_mcp.tools.files.make_canvas_request",
            new=AsyncMock(return_value=FILE_INFO),
        ), patch(
            "canvas_mcp.tools.files.get_course_id", new=AsyncMock(return_value="60366")
        ), patch(
            "canvas_mcp.tools.files.get_course_code",
            new=AsyncMock(return_value="badm_350"),
        ), patch(
            "canvas_mcp.tools.files.canvas_authenticated_client"
        ) as client:
            _mock_stream(client)
            download = get_tool_function("download_course_file")
            result = await download("badm_350", 12345, save_directory=str(tmp_path))

        assert "Downloaded: syllabus.pdf" in result
        assert (tmp_path / "syllabus.pdf").read_bytes() == b"file content here"


class TestDownloadDoesNotClobber:
    """Canvas controls the filename, so the write must never truncate a real file."""

    @pytest.mark.asyncio
    async def test_existing_file_is_not_overwritten(self, tmp_path):
        victim = tmp_path / "syllabus.pdf"
        victim.write_bytes(b"important pre-existing content")

        with patch(
            "canvas_mcp.tools.files.is_http_request_active", return_value=False
        ), patch(
            "canvas_mcp.tools.files.make_canvas_request",
            new=AsyncMock(return_value=FILE_INFO),
        ), patch(
            "canvas_mcp.tools.files.get_course_id", new=AsyncMock(return_value="60366")
        ), patch(
            "canvas_mcp.tools.files.canvas_authenticated_client"
        ) as client:
            _mock_stream(client)
            download = get_tool_function("download_course_file")
            result = await download("badm_350", 12345, save_directory=str(tmp_path))

        assert "already exists" in result
        assert "Refusing to overwrite" in result
        assert victim.read_bytes() == b"important pre-existing content"

    @pytest.mark.asyncio
    async def test_symlink_destination_is_not_followed(self, tmp_path):
        """A pre-planted symlink must not redirect the write to its target."""
        outside = tmp_path / "outside.txt"
        outside.write_bytes(b"do not touch")
        save_dir = tmp_path / "downloads"
        save_dir.mkdir()
        (save_dir / "syllabus.pdf").symlink_to(outside)

        with patch(
            "canvas_mcp.tools.files.is_http_request_active", return_value=False
        ), patch(
            "canvas_mcp.tools.files.make_canvas_request",
            new=AsyncMock(return_value=FILE_INFO),
        ), patch(
            "canvas_mcp.tools.files.get_course_id", new=AsyncMock(return_value="60366")
        ), patch(
            "canvas_mcp.tools.files.canvas_authenticated_client"
        ) as client:
            _mock_stream(client)
            download = get_tool_function("download_course_file")
            result = await download("badm_350", 12345, save_directory=str(save_dir))

        assert result.lower().startswith("error")
        assert outside.read_bytes() == b"do not touch"

    @pytest.mark.asyncio
    async def test_partial_file_removed_on_failure(self, tmp_path):
        """A failed download must not leave a truncated file behind."""
        import httpx

        error = httpx.HTTPStatusError(
            "403 Forbidden", request=MagicMock(), response=MagicMock()
        )

        with patch(
            "canvas_mcp.tools.files.is_http_request_active", return_value=False
        ), patch(
            "canvas_mcp.tools.files.make_canvas_request",
            new=AsyncMock(return_value=FILE_INFO),
        ), patch(
            "canvas_mcp.tools.files.get_course_id", new=AsyncMock(return_value="60366")
        ), patch(
            "canvas_mcp.tools.files.canvas_authenticated_client"
        ) as client:
            _mock_stream(client, raise_on_status=error)
            download = get_tool_function("download_course_file")
            result = await download("badm_350", 12345, save_directory=str(tmp_path))

        assert "Error downloading file" in result
        assert not (tmp_path / "syllabus.pdf").exists()
        assert list(tmp_path.iterdir()) == []


class TestUploadRefusedOverHttp:
    """A remote caller must never make the server read its own filesystem."""

    @pytest.mark.asyncio
    async def test_upload_refused_over_http(self, tmp_path):
        secret = tmp_path / "secret.txt"
        secret.write_text("service-account readable content")

        with patch(
            "canvas_mcp.tools.files.is_http_request_active", return_value=True
        ), patch(
            "canvas_mcp.tools.files.make_canvas_request", new_callable=AsyncMock
        ) as request, patch(
            "canvas_mcp.tools.files.upload_file_to_storage", new_callable=AsyncMock
        ) as storage, patch(
            "canvas_mcp.tools.files.validate_file_for_upload"
        ) as validate, patch(
            "canvas_mcp.tools.files.get_course_id", new=AsyncMock(return_value="60366")
        ):
            upload = get_tool_function("upload_course_file")
            result = await upload("badm_350", str(secret))

        assert "only available on a local (stdio) server" in result
        # The refusal precedes every side effect: no Canvas call, no upload, and
        # not even a local stat of the requested path.
        assert request.call_count == 0
        assert storage.call_count == 0
        assert validate.call_count == 0

    @pytest.mark.asyncio
    async def test_upload_refusal_precedes_path_probing(self, tmp_path):
        """The error must not reveal whether the requested path exists."""
        with patch(
            "canvas_mcp.tools.files.is_http_request_active", return_value=True
        ), patch(
            "canvas_mcp.tools.files.get_course_id", new=AsyncMock(return_value="60366")
        ):
            upload = get_tool_function("upload_course_file")
            missing = await upload("badm_350", str(tmp_path / "does-not-exist"))
            present = await upload("badm_350", str(tmp_path))

        assert missing == present


class TestDownloadPermissions:
    """Downloads land owner-only; the bytes come from a third party."""

    @pytest.mark.asyncio
    async def test_downloaded_file_is_owner_only(self, tmp_path):
        with patch(
            "canvas_mcp.tools.files.is_http_request_active", return_value=False
        ), patch(
            "canvas_mcp.tools.files.make_canvas_request",
            new=AsyncMock(return_value=FILE_INFO),
        ), patch(
            "canvas_mcp.tools.files.get_course_id", new=AsyncMock(return_value="60366")
        ), patch(
            "canvas_mcp.tools.files.canvas_authenticated_client"
        ) as client:
            _mock_stream(client)
            download = get_tool_function("download_course_file")
            await download("badm_350", 12345, save_directory=str(tmp_path))

        mode = os.stat(tmp_path / "syllabus.pdf").st_mode & 0o777
        assert mode == 0o600
