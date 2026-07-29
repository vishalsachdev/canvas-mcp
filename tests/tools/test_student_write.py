"""Tests for Tier 1 student write tools (#170).

These cover the behaviour an operator and a student see. The security
invariants that must hold regardless of behaviour live in
``tests/security/test_student_write_invariants.py``.
"""

from unittest.mock import AsyncMock, patch

import pytest
from fastmcp import FastMCP

from canvas_mcp.core.config import reset_config
from canvas_mcp.core.course_policy import reset_policy_cache
from canvas_mcp.tools.student_write import (
    register_student_write_tools,
    reset_pending_confirmations,
)

# A real 1x1 JPEG. Used to prove binary content survives the upload path byte
# for byte, which is the specific failure another implementation hit (it OCR'd
# the image and demanded text instead).
JPEG_BYTES = bytes.fromhex(
    "ffd8ffe000104a46494600010100000100010000ffdb00430008060607060508070707"
    "0909080a0c140d0c0b0b0c1912130f141d1a1f1e1d1a1c1c20242e2720222c231c1c28"
    "37292c30313434341f27393d38323c2e333432ffc0000b080001000101011100ffc400"
    "1f0000010501010101010100000000000000000102030405060708090a0bffc400b510"
    "0002010303020403050504040000017d01020300041105122131410613516107227114"
    "328191a1082342b1c11552d1f02433627282090a161718191a25262728292a3435363738"
    "393a434445464748494a535455565758595a636465666768696a737475767778797a8384"
    "85868788898a92939495969798999aa2a3a4a5a6a7a8a9aab2b3b4b5b6b7b8b9bac2c3c4"
    "c5c6c7c8c9cad2d3d4d5d6d7d8d9dae1e2e3e4e5e6e7e8e9eaf1f2f3f4f5f6f7f8f9fa"
    "ffda0008010100003f00fbfeffd9"
)


def get_tools(**env):
    """Register the write tools under a given operator configuration.

    Returns a dict of tool name -> callable. A tool the operator has not
    enabled is genuinely absent from this dict, which is the point: it was
    never registered, so no agent can see it.
    """
    captured = {}
    mcp = FastMCP("test")
    original_tool = mcp.tool

    def capturing_tool(*args, **kwargs):
        decorator = original_tool(*args, **kwargs)

        def wrapper(fn):
            captured[fn.__name__] = fn
            return decorator(fn)

        return wrapper

    mcp.tool = capturing_tool
    with patch.dict("os.environ", env, clear=False):
        reset_config()
        register_student_write_tools(mcp)
    return captured


@pytest.fixture(autouse=True)
def _clean_state():
    reset_config()
    reset_policy_cache()
    reset_pending_confirmations()
    yield
    reset_config()
    reset_policy_cache()
    reset_pending_confirmations()


class TestOperatorCeiling:
    """STUDENT_WRITE_TOOLS is the campus-wide ceiling. Default is nothing."""

    def test_no_write_tools_by_default(self):
        tools = get_tools(STUDENT_WRITE_TOOLS="")
        assert "submit_assignment" not in tools
        assert "comment_on_my_submission" not in tools
        assert "mark_module_item_done" not in tools

    def test_read_tool_always_registered(self):
        tools = get_tools(STUDENT_WRITE_TOOLS="")
        assert "get_my_submission" in tools

    def test_only_named_tools_register(self):
        tools = get_tools(STUDENT_WRITE_TOOLS="submit_assignment")
        assert "submit_assignment" in tools
        assert "comment_on_my_submission" not in tools

    def test_accepts_comma_and_space_separated(self):
        tools = get_tools(
            STUDENT_WRITE_TOOLS="submit_assignment, mark_module_item_done"
        )
        assert "submit_assignment" in tools
        assert "mark_module_item_done" in tools

    def test_unknown_names_do_not_register_anything(self):
        tools = get_tools(STUDENT_WRITE_TOOLS="take_quiz_for_me")
        assert "submit_assignment" not in tools


def _mock_assignment(**overrides):
    base = {
        "id": 42,
        "name": "Essay 1",
        "submission_types": ["online_text_entry"],
        "allowed_attempts": 3,
        "due_at": "2026-08-01T23:59:00Z",
    }
    base.update(overrides)
    return base


class TestSubmitAssignment:
    """The preview/confirm protocol and its guards."""

    @pytest.mark.asyncio
    async def test_preview_does_not_submit(self):
        tools = get_tools(
            STUDENT_WRITE_TOOLS="submit_assignment",
            COURSE_AGENT_POLICY_ENABLED="false",
        )
        with patch(
            "canvas_mcp.tools.student_write.get_course_id",
            new=AsyncMock(return_value="123"),
        ), patch(
            "canvas_mcp.tools.student_write.make_canvas_request", new_callable=AsyncMock
        ) as request:
            request.side_effect = [_mock_assignment(), {"attempt": 1}]
            result = await tools["submit_assignment"](
                course_identifier="TEST", assignment_id=42,
                submission_type="online_text_entry", body="hello",
            )

        assert "NOTHING has been submitted" in result
        assert "confirmation_token=" in result
        # Only the two reads happened. No POST.
        assert all(call.args[0] == "get" for call in request.call_args_list)

    @pytest.mark.asyncio
    async def test_confirm_submits(self):
        tools = get_tools(
            STUDENT_WRITE_TOOLS="submit_assignment",
            COURSE_AGENT_POLICY_ENABLED="false",
        )
        with patch(
            "canvas_mcp.tools.student_write.get_course_id",
            new=AsyncMock(return_value="123"),
        ), patch(
            "canvas_mcp.tools.student_write.make_canvas_request", new_callable=AsyncMock
        ) as request:
            request.side_effect = [_mock_assignment(), {"attempt": 1}]
            preview = await tools["submit_assignment"](
                course_identifier="TEST", assignment_id=42,
                submission_type="online_text_entry", body="hello",
            )
            token = preview.split("confirmation_token='")[1].split("'")[0]

            request.side_effect = [
                _mock_assignment(),
                {"attempt": 1},
                {"submitted_at": "2026-07-30T10:00:00Z", "attempt": 2},
            ]
            result = await tools["submit_assignment"](
                course_identifier="TEST", assignment_id=42,
                submission_type="online_text_entry", body="hello",
                confirmation_token=token,
            )

        assert "✅ Submitted." in result
        post = [c for c in request.call_args_list if c.args[0] == "post"]
        assert len(post) == 1
        assert post[0].args[1] == "/courses/123/assignments/42/submissions"

    @pytest.mark.asyncio
    async def test_token_is_single_use(self):
        tools = get_tools(
            STUDENT_WRITE_TOOLS="submit_assignment",
            COURSE_AGENT_POLICY_ENABLED="false",
        )
        with patch(
            "canvas_mcp.tools.student_write.get_course_id",
            new=AsyncMock(return_value="123"),
        ), patch(
            "canvas_mcp.tools.student_write.make_canvas_request", new_callable=AsyncMock
        ) as request:
            request.side_effect = [_mock_assignment(), {"attempt": 1}]
            preview = await tools["submit_assignment"](
                course_identifier="TEST", assignment_id=42,
                submission_type="online_text_entry", body="hello",
            )
            token = preview.split("confirmation_token='")[1].split("'")[0]

            request.side_effect = [
                _mock_assignment(), {"attempt": 1}, {"attempt": 2},
                _mock_assignment(), {"attempt": 1},
            ]
            await tools["submit_assignment"](
                course_identifier="TEST", assignment_id=42,
                submission_type="online_text_entry", body="hello",
                confirmation_token=token,
            )
            second = await tools["submit_assignment"](
                course_identifier="TEST", assignment_id=42,
                submission_type="online_text_entry", body="hello",
                confirmation_token=token,
            )

        assert "already-used" in second

    @pytest.mark.asyncio
    async def test_changed_content_voids_token(self):
        """The token commits to the previewed bytes, not just the target."""
        tools = get_tools(
            STUDENT_WRITE_TOOLS="submit_assignment",
            COURSE_AGENT_POLICY_ENABLED="false",
        )
        with patch(
            "canvas_mcp.tools.student_write.get_course_id",
            new=AsyncMock(return_value="123"),
        ), patch(
            "canvas_mcp.tools.student_write.make_canvas_request", new_callable=AsyncMock
        ) as request:
            request.side_effect = [_mock_assignment(), {"attempt": 1}]
            preview = await tools["submit_assignment"](
                course_identifier="TEST", assignment_id=42,
                submission_type="online_text_entry", body="original",
            )
            token = preview.split("confirmation_token='")[1].split("'")[0]

            request.side_effect = [_mock_assignment(), {"attempt": 1}]
            result = await tools["submit_assignment"](
                course_identifier="TEST", assignment_id=42,
                submission_type="online_text_entry", body="SWAPPED",
                confirmation_token=token,
            )

        assert "changed since the preview" in result
        assert not [c for c in request.call_args_list if c.args[0] == "post"]

    @pytest.mark.asyncio
    async def test_attempt_drift_voids_token(self):
        """A submission landing between preview and confirm invalidates it."""
        tools = get_tools(
            STUDENT_WRITE_TOOLS="submit_assignment",
            COURSE_AGENT_POLICY_ENABLED="false",
        )
        with patch(
            "canvas_mcp.tools.student_write.get_course_id",
            new=AsyncMock(return_value="123"),
        ), patch(
            "canvas_mcp.tools.student_write.make_canvas_request", new_callable=AsyncMock
        ) as request:
            request.side_effect = [_mock_assignment(), {"attempt": 1}]
            preview = await tools["submit_assignment"](
                course_identifier="TEST", assignment_id=42,
                submission_type="online_text_entry", body="hello",
            )
            token = preview.split("confirmation_token='")[1].split("'")[0]

            # Attempt count moved from 1 to 2 in the meantime.
            request.side_effect = [_mock_assignment(), {"attempt": 2}]
            result = await tools["submit_assignment"](
                course_identifier="TEST", assignment_id=42,
                submission_type="online_text_entry", body="hello",
                confirmation_token=token,
            )

        assert "changed since the preview" in result

    @pytest.mark.asyncio
    async def test_unknown_token_rejected(self):
        tools = get_tools(
            STUDENT_WRITE_TOOLS="submit_assignment",
            COURSE_AGENT_POLICY_ENABLED="false",
        )
        with patch(
            "canvas_mcp.tools.student_write.get_course_id",
            new=AsyncMock(return_value="123"),
        ), patch(
            "canvas_mcp.tools.student_write.make_canvas_request", new_callable=AsyncMock
        ) as request:
            request.side_effect = [_mock_assignment(), {"attempt": 1}]
            result = await tools["submit_assignment"](
                course_identifier="TEST", assignment_id=42,
                submission_type="online_text_entry", body="hello",
                confirmation_token="made-up-token",
            )

        assert "Unknown or already-used" in result

    @pytest.mark.asyncio
    async def test_group_assignment_refused(self):
        tools = get_tools(
            STUDENT_WRITE_TOOLS="submit_assignment",
            COURSE_AGENT_POLICY_ENABLED="false",
        )
        with patch(
            "canvas_mcp.tools.student_write.get_course_id",
            new=AsyncMock(return_value="123"),
        ), patch(
            "canvas_mcp.tools.student_write.make_canvas_request", new_callable=AsyncMock
        ) as request:
            request.side_effect = [_mock_assignment(group_category_id=7)]
            result = await tools["submit_assignment"](
                course_identifier="TEST", assignment_id=42,
                submission_type="online_text_entry", body="hello",
            )

        assert "group assignment" in result

    @pytest.mark.asyncio
    async def test_rejects_type_the_assignment_does_not_accept(self):
        tools = get_tools(
            STUDENT_WRITE_TOOLS="submit_assignment",
            COURSE_AGENT_POLICY_ENABLED="false",
        )
        with patch(
            "canvas_mcp.tools.student_write.get_course_id",
            new=AsyncMock(return_value="123"),
        ), patch(
            "canvas_mcp.tools.student_write.make_canvas_request", new_callable=AsyncMock
        ) as request:
            request.side_effect = [_mock_assignment(submission_types=["online_upload"])]
            result = await tools["submit_assignment"](
                course_identifier="TEST", assignment_id=42,
                submission_type="online_text_entry", body="hello",
            )

        assert "does not accept" in result

    @pytest.mark.asyncio
    async def test_unsupported_submission_type_rejected(self):
        tools = get_tools(
            STUDENT_WRITE_TOOLS="submit_assignment",
            COURSE_AGENT_POLICY_ENABLED="false",
        )
        result = await tools["submit_assignment"](
            course_identifier="TEST", assignment_id=42,
            submission_type="online_quiz",
        )
        assert "must be one of" in result


class TestBinaryUpload:
    """Michigan's requirement A: real binary files, not text."""

    @pytest.mark.asyncio
    async def test_jpeg_bytes_survive_unmodified(self):
        """The exact bytes handed in must reach Canvas storage untouched."""
        tools = get_tools(
            STUDENT_WRITE_TOOLS="submit_assignment",
            COURSE_AGENT_POLICY_ENABLED="false",
        )
        import base64

        encoded = base64.b64encode(JPEG_BYTES).decode()
        seen = {}

        async def fake_storage(upload_url, upload_params, file_path, filename, content_type):
            with open(file_path, "rb") as handle:
                seen["bytes"] = handle.read()
            seen["content_type"] = content_type
            return {"id": 999}

        with patch(
            "canvas_mcp.tools.student_write.get_course_id",
            new=AsyncMock(return_value="123"),
        ), patch(
            "canvas_mcp.tools.student_write.make_canvas_request", new_callable=AsyncMock
        ) as request, patch(
            "canvas_mcp.tools.student_write.upload_file_to_storage", new=fake_storage
        ):
            assignment = _mock_assignment(submission_types=["online_upload"])
            request.side_effect = [assignment, {"attempt": 0}]
            preview = await tools["submit_assignment"](
                course_identifier="TEST", assignment_id=42,
                submission_type="online_upload",
                file_contents=[{"name": "photo.jpg", "content_base64": encoded}],
            )
            token = preview.split("confirmation_token='")[1].split("'")[0]

            request.side_effect = [
                assignment,
                {"attempt": 0},
                {"upload_url": "https://storage.example/x", "upload_params": {}},
                {"submitted_at": "2026-07-30T10:00:00Z", "attempt": 1},
            ]
            result = await tools["submit_assignment"](
                course_identifier="TEST", assignment_id=42,
                submission_type="online_upload",
                file_contents=[{"name": "photo.jpg", "content_base64": encoded}],
                confirmation_token=token,
            )

        assert "✅ Submitted." in result
        assert seen["bytes"] == JPEG_BYTES, "JPEG bytes were altered in transit"
        assert seen["content_type"] == "image/jpeg"

    @pytest.mark.asyncio
    async def test_invalid_base64_rejected(self):
        tools = get_tools(
            STUDENT_WRITE_TOOLS="submit_assignment",
            COURSE_AGENT_POLICY_ENABLED="false",
        )
        with patch(
            "canvas_mcp.tools.student_write.get_course_id",
            new=AsyncMock(return_value="123"),
        ), patch(
            "canvas_mcp.tools.student_write.make_canvas_request", new_callable=AsyncMock
        ) as request:
            request.side_effect = [
                _mock_assignment(submission_types=["online_upload"]),
                {"attempt": 0},
            ]
            result = await tools["submit_assignment"](
                course_identifier="TEST", assignment_id=42,
                submission_type="online_upload",
                file_contents=[{"name": "x.jpg", "content_base64": "not!base64!"}],
            )
        assert "not valid base64" in result

    @pytest.mark.asyncio
    async def test_disallowed_extension_rejected(self):
        tools = get_tools(
            STUDENT_WRITE_TOOLS="submit_assignment",
            COURSE_AGENT_POLICY_ENABLED="false",
        )
        import base64

        with patch(
            "canvas_mcp.tools.student_write.get_course_id",
            new=AsyncMock(return_value="123"),
        ), patch(
            "canvas_mcp.tools.student_write.make_canvas_request", new_callable=AsyncMock
        ) as request:
            request.side_effect = [
                _mock_assignment(submission_types=["online_upload"]),
                {"attempt": 0},
            ]
            result = await tools["submit_assignment"](
                course_identifier="TEST", assignment_id=42,
                submission_type="online_upload",
                file_contents=[
                    {"name": "evil.exe", "content_base64": base64.b64encode(b"MZ").decode()}
                ],
            )
        assert "Cannot submit" in result
