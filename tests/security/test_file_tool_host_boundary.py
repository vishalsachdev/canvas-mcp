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
import sys
from pathlib import Path
from types import SimpleNamespace
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
    """Build a mock streaming response for canvas_file_download_client()."""
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
            "canvas_mcp.tools.files.resolve_numeric_course_id",
            new=AsyncMock(return_value=("60366", None)),
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
            "canvas_mcp.tools.files.resolve_numeric_course_id",
            new=AsyncMock(return_value=("60366", None)),
        ), patch(
            "canvas_mcp.tools.files.get_course_code",
            new=AsyncMock(return_value="badm_350"),
        ), patch(
            "canvas_mcp.tools.files.canvas_file_download_client"
        ) as client:
            _mock_stream(client)
            download = get_tool_function("download_course_file")
            result = await download("badm_350", 12345, save_directory=str(tmp_path))

        assert "syllabus.pdf" in result and "Downloaded:" in result
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
            "canvas_mcp.tools.files.resolve_numeric_course_id",
            new=AsyncMock(return_value=("60366", None)),
        ), patch(
            "canvas_mcp.tools.files.canvas_file_download_client"
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
        try:
            (save_dir / "syllabus.pdf").symlink_to(outside)
        except OSError as exc:
            if sys.platform != "win32":
                raise
            # Windows lets only administrators or Developer Mode create
            # symlinks (WinError 1314 otherwise), and there is no unprivileged
            # file-link equivalent: a junction targets directories only, and a
            # hard link is the plain existing-file case covered above. Where
            # the privilege exists (e.g. GitHub's Windows runners) this runs.
            pytest.skip(f"cannot create a file symlink without privilege: {exc}")

        with patch(
            "canvas_mcp.tools.files.is_http_request_active", return_value=False
        ), patch(
            "canvas_mcp.tools.files.make_canvas_request",
            new=AsyncMock(return_value=FILE_INFO),
        ), patch(
            "canvas_mcp.tools.files.resolve_numeric_course_id",
            new=AsyncMock(return_value=("60366", None)),
        ), patch(
            "canvas_mcp.tools.files.canvas_file_download_client"
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
            "canvas_mcp.tools.files.resolve_numeric_course_id",
            new=AsyncMock(return_value=("60366", None)),
        ), patch(
            "canvas_mcp.tools.files.canvas_file_download_client"
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
        secret.write_text("service-account readable content", encoding="utf-8")

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
    """POSIX downloads are owner-only; Windows discloses inherited access."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("platform", ["win32", "linux", "darwin"])
    @pytest.mark.parametrize("use_default_directory", [False, True])
    async def test_download_reports_windows_permission_limitation(
        self, tmp_path: Path, platform: str, use_default_directory: bool
    ) -> None:
        """Windows success must disclose that inherited access is not restricted.

        Removing the warning (or assuming the default temp folder is private)
        must fail this test. Real file creation and streaming are exercised;
        the platform decision and external Canvas boundary are controlled.
        """
        with patch(
            "canvas_mcp.tools.files.sys", SimpleNamespace(platform=platform), create=True
        ), patch(
            "canvas_mcp.tools.files.tempfile.gettempdir", return_value=str(tmp_path)
        ), patch(
            "canvas_mcp.tools.files.is_http_request_active", return_value=False
        ), patch(
            "canvas_mcp.tools.files.make_canvas_request",
            new=AsyncMock(return_value=FILE_INFO),
        ), patch(
            "canvas_mcp.tools.files.resolve_numeric_course_id",
            new=AsyncMock(return_value=("60366", None)),
        ), patch(
            "canvas_mcp.tools.files.get_course_code",
            new=AsyncMock(return_value="badm_350"),
        ), patch(
            "canvas_mcp.tools.files.canvas_file_download_client"
        ) as client:
            _mock_stream(client)
            download = get_tool_function("download_course_file")
            result = await download(
                "badm_350", 12345,
                save_directory=None if use_default_directory else str(tmp_path),
            )

        assert (tmp_path / "syllabus.pdf").read_bytes() == b"file content here"
        assert "Downloaded:" in result
        if platform == "win32":
            assert result.startswith("Warning:")
            assert "owner-only access is not enforced" in result
            assert "Other local users may be able to read this file" in result
            assert "read_course_file" in result
        else:
            assert "Warning:" not in result

    @pytest.mark.asyncio
    @pytest.mark.parametrize("failure", ["http", "metadata", "exists", "stream"])
    async def test_windows_warning_does_not_mask_download_errors(
        self, tmp_path: Path, failure: str
    ) -> None:
        """Failures retain their errors and never turn into a warned success."""
        target = tmp_path / "syllabus.pdf"
        if failure == "exists":
            target.write_bytes(b"original")
        info = {"error": "File not found"} if failure == "metadata" else FILE_INFO
        with patch(
            "canvas_mcp.tools.files.sys", SimpleNamespace(platform="win32")
        ), patch(
            "canvas_mcp.tools.files.is_http_request_active", return_value=failure == "http"
        ), patch(
            "canvas_mcp.tools.files.make_canvas_request", new=AsyncMock(return_value=info)
        ) as request, patch(
            "canvas_mcp.tools.files.resolve_numeric_course_id",
            new=AsyncMock(return_value=("60366", None)),
        ), patch(
            "canvas_mcp.tools.files.canvas_file_download_client"
        ) as client:
            _mock_stream(
                client, raise_on_status=OSError("transfer failed") if failure == "stream" else None
            )
            download = get_tool_function("download_course_file")
            result = await download("badm_350", 12345, save_directory=str(tmp_path))

        expected_error = {
            "http": "only available on a local (stdio) server",
            "metadata": "File not found",
            "exists": "Refusing to overwrite",
            "stream": "transfer failed",
        }[failure]
        assert result.startswith("Error")
        assert expected_error in result
        assert "Downloaded:" not in result
        assert "Warning:" not in result
        if failure == "exists":
            assert target.read_bytes() == b"original"
        else:
            assert list(tmp_path.iterdir()) == []
        if failure == "http":
            request.assert_not_called()
        if failure != "stream":
            client.assert_not_called()

    @pytest.mark.skipif(
        sys.platform == "win32",
        reason=(
            "POSIX permission bits: on Windows os.open's mode only sets the "
            "read-only attribute and st_mode always reports 0o666/0o444; access "
            "is governed by the ACL inherited from the destination directory."
        ),
    )
    @pytest.mark.asyncio
    async def test_downloaded_file_is_owner_only(self, tmp_path):
        with patch(
            "canvas_mcp.tools.files.is_http_request_active", return_value=False
        ), patch(
            "canvas_mcp.tools.files.make_canvas_request",
            new=AsyncMock(return_value=FILE_INFO),
        ), patch(
            "canvas_mcp.tools.files.resolve_numeric_course_id",
            new=AsyncMock(return_value=("60366", None)),
        ), patch(
            "canvas_mcp.tools.files.canvas_file_download_client"
        ) as client:
            _mock_stream(client)
            download = get_tool_function("download_course_file")
            await download("badm_350", 12345, save_directory=str(tmp_path))

        mode = os.stat(tmp_path / "syllabus.pdf").st_mode & 0o777
        assert mode == 0o600


class TestDownloadIsPortable:
    """The hardening must not break a supported platform.

    O_NOFOLLOW is POSIX-only. Naming os.O_NOFOLLOW directly raises AttributeError
    on Windows before os.open runs — and the handlers below it catch only
    FileExistsError and OSError, so every local download would fail there.
    """

    def test_open_flags_survive_a_missing_o_nofollow(self, monkeypatch):
        import canvas_mcp.tools.files as files_module

        monkeypatch.delattr(files_module.os, "O_NOFOLLOW", raising=False)
        flags = (
            files_module.os.O_WRONLY
            | files_module.os.O_CREAT
            | files_module.os.O_EXCL
            | getattr(files_module.os, "O_NOFOLLOW", 0)
        )
        # Exclusive creation — the bulk of the protection — is still requested.
        assert flags & files_module.os.O_EXCL

    @pytest.mark.asyncio
    async def test_download_works_without_o_nofollow(self, tmp_path, monkeypatch):
        """Simulates Windows: the platform flag is absent, download still works."""
        import canvas_mcp.tools.files as files_module

        monkeypatch.delattr(files_module.os, "O_NOFOLLOW", raising=False)

        with patch(
            "canvas_mcp.tools.files.is_http_request_active", return_value=False
        ), patch(
            "canvas_mcp.tools.files.make_canvas_request",
            new=AsyncMock(return_value=FILE_INFO),
        ), patch(
            "canvas_mcp.tools.files.resolve_numeric_course_id",
            new=AsyncMock(return_value=("60366", None)),
        ), patch(
            "canvas_mcp.tools.files.get_course_code",
            new=AsyncMock(return_value="badm_350"),
        ), patch(
            "canvas_mcp.tools.files.canvas_file_download_client"
        ) as client:
            _mock_stream(client)
            download = get_tool_function("download_course_file")
            result = await download("badm_350", 12345, save_directory=str(tmp_path))

        assert "syllabus.pdf" in result and "Downloaded:" in result
        assert (tmp_path / "syllabus.pdf").read_bytes() == b"file content here"

    @pytest.mark.asyncio
    async def test_overwrite_refusal_still_holds_without_o_nofollow(self, tmp_path, monkeypatch):
        import canvas_mcp.tools.files as files_module

        monkeypatch.delattr(files_module.os, "O_NOFOLLOW", raising=False)
        (tmp_path / "syllabus.pdf").write_bytes(b"pre-existing")

        with patch(
            "canvas_mcp.tools.files.is_http_request_active", return_value=False
        ), patch(
            "canvas_mcp.tools.files.make_canvas_request",
            new=AsyncMock(return_value=FILE_INFO),
        ), patch(
            "canvas_mcp.tools.files.resolve_numeric_course_id",
            new=AsyncMock(return_value=("60366", None)),
        ), patch(
            "canvas_mcp.tools.files.canvas_file_download_client"
        ) as client:
            _mock_stream(client)
            download = get_tool_function("download_course_file")
            result = await download("badm_350", 12345, save_directory=str(tmp_path))

        assert "already exists" in result
        assert (tmp_path / "syllabus.pdf").read_bytes() == b"pre-existing"
