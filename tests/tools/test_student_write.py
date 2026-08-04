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
# Comfortably past the confirmation TTL.
_EXPIRED_BY = 10_000

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


def make_responder(assignment, submission=None, submit_result=None, upload=None):
    """Answer Canvas calls by endpoint rather than by call order.

    Ordered side_effect lists are brittle here: the confirm path re-reads
    attempt state immediately before submitting, so the number of GETs is an
    implementation detail that tests should not encode.
    """
    submission = submission if submission is not None else {"attempt": 0}
    posts = []

    async def responder(method, endpoint, **kwargs):
        if method == "get":
            if endpoint.endswith("/submissions/self"):
                return submission
            return assignment
        if endpoint.endswith("/submissions/self/files"):
            return upload or {
                "upload_url": "https://storage.example/x",
                "upload_params": {},
            }
        posts.append({"endpoint": endpoint, "data": kwargs.get("data")})
        return submit_result or {
            "submitted_at": "2026-07-30T10:00:00Z",
            "attempt": (submission.get("attempt") or 0) + 1,
        }

    responder.posts = posts
    return responder


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
        responder = make_responder(_mock_assignment(), {"attempt": 1})
        with patch(
            "canvas_mcp.tools.student_write.get_course_id",
            new=AsyncMock(return_value="123"),
        ), patch(
            "canvas_mcp.tools.student_write.make_canvas_request", new=responder
        ):
            preview = await tools["submit_assignment"](
                course_identifier="TEST", assignment_id=42,
                submission_type="online_text_entry", body="hello",
            )
            token = preview.split("confirmation_token='")[1].split("'")[0]
            result = await tools["submit_assignment"](
                course_identifier="TEST", assignment_id=42,
                submission_type="online_text_entry", body="hello",
                confirmation_token=token,
            )

        assert "✅ Submitted." in result
        assert len(responder.posts) == 1
        assert responder.posts[0]["endpoint"] == "/courses/123/assignments/42/submissions"

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
            "canvas_mcp.tools.student_write.make_canvas_request",
            new=make_responder(_mock_assignment(), {"attempt": 1}),
        ):
            preview = await tools["submit_assignment"](
                course_identifier="TEST", assignment_id=42,
                submission_type="online_text_entry", body="hello",
            )
            token = preview.split("confirmation_token='")[1].split("'")[0]
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

        assert "already used" in second

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

        assert "malformed" in result

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


class TestConfirmationIntegrity:
    """Regressions found by code review. Each was a real bypass."""

    def test_digest_frames_fields_unambiguously(self):
        """Concatenation would let one payload impersonate another.

        Without length-prefixing, a file named 'a.txt' holding b'XPAYLOAD'
        digests identically to one named 'a.txtX' holding b'PAYLOAD', so a
        token could authorize content that was never previewed.
        """
        from canvas_mcp.tools.student_write import _digest_payload, _PreparedFile

        first = _digest_payload(
            None, None, None, [_PreparedFile("a.txt", b"XPAYLOAD", "text/plain")]
        )
        second = _digest_payload(
            None, None, None, [_PreparedFile("a.txtX", b"PAYLOAD", "text/plain")]
        )
        assert first != second

    def test_digest_covers_the_comment(self):
        from canvas_mcp.tools.student_write import _digest_payload

        assert _digest_payload("essay", None, "please regrade", []) != _digest_payload(
            "essay", None, "something else entirely", []
        )

    @pytest.mark.asyncio
    async def test_swapping_the_comment_voids_the_token(self):
        """The preview shows the comment, so confirmation must commit to it."""
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
                comment="Sorry this is late.",
            )
            token = preview.split("confirmation_token='")[1].split("'")[0]

            request.side_effect = [_mock_assignment(), {"attempt": 1}]
            result = await tools["submit_assignment"](
                course_identifier="TEST", assignment_id=42,
                submission_type="online_text_entry", body="hello",
                comment="My professor said this was fine.",
                confirmation_token=token,
            )

        assert "changed since the preview" in result
        assert not [c for c in request.call_args_list if c.args[0] == "post"]

    @pytest.mark.asyncio
    async def test_unreadable_attempt_state_stops_everything(self):
        """A false attempt count would make the drift check vacuous."""
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
            request.side_effect = [_mock_assignment(), {"error": "HTTP error: 500"}]
            result = await tools["submit_assignment"](
                course_identifier="TEST", assignment_id=42,
                submission_type="online_text_entry", body="hello",
            )

        assert "attempt count is unknown" in result
        assert "Nothing was submitted" in result
        assert not [c for c in request.call_args_list if c.args[0] == "post"]

    def test_abandoned_previews_hold_no_server_state(self):
        """Tokens are self-contained, so an abandoned preview costs nothing.

        The previous design kept every issued token in a process-global map,
        which a caller could grow without bound by previewing and never
        confirming. Signed tokens remove the map entirely.
        """
        import canvas_mcp.tools.student_write as sw

        for _ in range(1000):
            sw._issue_token("some-fingerprint")
        assert not sw._redeemed

    def test_expired_token_is_rejected(self):
        import time as time_module

        import canvas_mcp.tools.student_write as sw

        expired = sw._issue_token("fp", now=time_module.time() - _EXPIRED_BY)
        assert "expired" in (sw._check_token(expired, "fp") or "")

    def test_token_does_not_verify_against_a_different_payload(self):
        import canvas_mcp.tools.student_write as sw

        token = sw._issue_token("fingerprint-a")
        assert sw._check_token(token, "fingerprint-a") is None
        assert sw._check_token(token, "fingerprint-b") is not None

    def test_reservation_is_exclusive(self):
        import canvas_mcp.tools.student_write as sw

        assert sw._reserve_confirmation("fp") is True
        assert sw._reserve_confirmation("fp") is False

    def test_released_reservation_can_be_reclaimed(self):
        import canvas_mcp.tools.student_write as sw

        assert sw._reserve_confirmation("fp") is True
        sw._release_confirmation("fp")
        assert sw._reserve_confirmation("fp") is True

    def test_redeemed_claims_expire(self):
        """Otherwise memory grows with the lifetime submission count."""
        import canvas_mcp.tools.student_write as sw

        sw._reserve_confirmation("old")
        sw._redeemed["old"] = 0.0  # already past
        sw._reserve_confirmation("new")
        assert "old" not in sw._redeemed
        assert "new" in sw._redeemed

    @pytest.mark.asyncio
    async def test_concurrent_confirmations_submit_only_once(self):
        """Two overlapping confirms must not both spend an attempt.

        The reservation is taken before any awaited work precisely so that the
        gap between validating a token and claiming it cannot be interleaved.
        """
        import asyncio

        tools = get_tools(
            STUDENT_WRITE_TOOLS="submit_assignment",
            COURSE_AGENT_POLICY_ENABLED="false",
        )
        assignment = _mock_assignment()
        posts = []

        async def responder(method, endpoint, **kwargs):
            if method == "get" and endpoint.endswith("/submissions/self"):
                return {"attempt": 1}
            if method == "get":
                return assignment
            posts.append(endpoint)
            return {"submitted_at": "2026-07-30T10:00:00Z", "attempt": 2}

        with patch(
            "canvas_mcp.tools.student_write.get_course_id",
            new=AsyncMock(return_value="123"),
        ), patch(
            "canvas_mcp.tools.student_write.make_canvas_request", new=responder
        ):
            preview = await tools["submit_assignment"](
                course_identifier="TEST", assignment_id=42,
                submission_type="online_text_entry", body="hello",
            )
            token = preview.split("confirmation_token='")[1].split("'")[0]

            results = await asyncio.gather(*[
                tools["submit_assignment"](
                    course_identifier="TEST", assignment_id=42,
                    submission_type="online_text_entry", body="hello",
                    confirmation_token=token,
                )
                for _ in range(2)
            ])

        assert len(posts) == 1, f"submitted {len(posts)} times, expected exactly 1"
        assert sum("✅ Submitted." in r for r in results) == 1
        assert sum("already used" in r for r in results) == 1

    def test_fingerprint_covers_the_attempt_limit(self):
        """An instructor can change allowed_attempts between preview and confirm.

        A preview that said "unlimited" must not be confirmable against a
        freshly capped assignment, spending what is now the final attempt.
        """
        import canvas_mcp.tools.student_write as sw

        unlimited = sw._fingerprint("1", "2", "online_text_entry", "d", 0, -1)
        capped = sw._fingerprint("1", "2", "online_text_entry", "d", 0, 1)
        assert unlimited != capped

    @pytest.mark.asyncio
    async def test_changed_attempt_limit_voids_the_token(self):
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
                _mock_assignment(allowed_attempts=-1), {"attempt": 0},
            ]
            preview = await tools["submit_assignment"](
                course_identifier="TEST", assignment_id=42,
                submission_type="online_text_entry", body="hello",
            )
            assert "unlimited" in preview
            token = preview.split("confirmation_token='")[1].split("'")[0]

            # Instructor caps attempts in the meantime.
            request.side_effect = [
                _mock_assignment(allowed_attempts=1), {"attempt": 0},
            ]
            result = await tools["submit_assignment"](
                course_identifier="TEST", assignment_id=42,
                submission_type="online_text_entry", body="hello",
                confirmation_token=token,
            )

        assert "does not match" in result
        assert not [c for c in request.call_args_list if c.args[0] == "post"]

    @pytest.mark.asyncio
    async def test_attempt_landing_during_upload_aborts_the_submit(self):
        """State is re-verified after uploads, immediately before the POST.

        A file upload is a multi-step round trip per file. Another submission can
        land during it, so confirming against the attempt count read before the
        uploads would spend an attempt the student never agreed to.
        """
        tools = get_tools(
            STUDENT_WRITE_TOOLS="submit_assignment",
            COURSE_AGENT_POLICY_ENABLED="false",
        )
        import base64

        encoded = base64.b64encode(JPEG_BYTES).decode()
        assignment = _mock_assignment(submission_types=["online_upload"])
        state = {"attempt": 0}
        posts = []

        async def responder(method, endpoint, **kwargs):
            if method == "get":
                if endpoint.endswith("/submissions/self"):
                    return dict(state)
                return assignment
            if endpoint.endswith("/submissions/self/files"):
                return {"upload_url": "https://storage.example/x", "upload_params": {}}
            posts.append(endpoint)
            return {"submitted_at": "2026-07-30T10:00:00Z", "attempt": 2}

        async def storage_then_race(**kwargs):
            # Someone else submits while this upload is in flight.
            state["attempt"] = 1
            return {"id": 999}

        with patch(
            "canvas_mcp.tools.student_write.get_course_id",
            new=AsyncMock(return_value="123"),
        ), patch(
            "canvas_mcp.tools.student_write.make_canvas_request", new=responder
        ), patch(
            "canvas_mcp.tools.student_write.upload_file_to_storage",
            new=storage_then_race,
        ):
            preview = await tools["submit_assignment"](
                course_identifier="TEST", assignment_id=42,
                submission_type="online_upload",
                file_contents=[{"name": "photo.jpg", "content_base64": encoded}],
            )
            token = preview.split("confirmation_token='")[1].split("'")[0]
            result = await tools["submit_assignment"](
                course_identifier="TEST", assignment_id=42,
                submission_type="online_upload",
                file_contents=[{"name": "photo.jpg", "content_base64": encoded}],
                confirmation_token=token,
            )

        assert "changed while this was being prepared" in result
        assert not posts, "submitted despite the attempt count moving"

    @pytest.mark.asyncio
    async def test_unreadable_state_at_submit_time_aborts(self):
        tools = get_tools(
            STUDENT_WRITE_TOOLS="submit_assignment",
            COURSE_AGENT_POLICY_ENABLED="false",
        )
        calls = {"n": 0}
        posts = []

        async def responder(method, endpoint, **kwargs):
            if method == "get":
                if endpoint.endswith("/submissions/self"):
                    calls["n"] += 1
                    # Fine during the preview, broken at submit time.
                    if calls["n"] > 1:
                        return {"error": "HTTP error: 500"}
                    return {"attempt": 0}
                return _mock_assignment()
            posts.append(endpoint)
            return {"attempt": 1}

        with patch(
            "canvas_mcp.tools.student_write.get_course_id",
            new=AsyncMock(return_value="123"),
        ), patch(
            "canvas_mcp.tools.student_write.make_canvas_request", new=responder
        ):
            preview = await tools["submit_assignment"](
                course_identifier="TEST", assignment_id=42,
                submission_type="online_text_entry", body="hello",
            )
            token = preview.split("confirmation_token='")[1].split("'")[0]
            result = await tools["submit_assignment"](
                course_identifier="TEST", assignment_id=42,
                submission_type="online_text_entry", body="hello",
                confirmation_token=token,
            )

        assert "attempt count" in result
        assert not posts

    @pytest.mark.asyncio
    async def test_policy_revoked_during_upload_aborts_the_submit(self):
        """The authoritative policy check is the last one before the write.

        An instructor can revoke agent writes while uploads are running, and the
        grant used earlier may have come from a cache that has since expired.
        """
        import base64

        tools = get_tools(STUDENT_WRITE_TOOLS="submit_assignment")
        encoded = base64.b64encode(JPEG_BYTES).decode()
        assignment = _mock_assignment(submission_types=["online_upload"])
        posts = []
        syllabus = {"body": "agent_writes: allow"}

        async def policy_reader(method, endpoint, **kwargs):
            return {"syllabus_body": syllabus["body"]}

        async def responder(method, endpoint, **kwargs):
            if method == "get":
                if endpoint.endswith("/submissions/self"):
                    return {"attempt": 0}
                return assignment
            if endpoint.endswith("/submissions/self/files"):
                return {"upload_url": "https://storage.example/x", "upload_params": {}}
            posts.append(endpoint)
            return {"attempt": 1}

        async def storage_then_revoke(**kwargs):
            # Instructor revokes while the bytes are in flight.
            syllabus["body"] = "agent_writes: deny"
            reset_policy_cache()
            return {"id": 999}

        with patch(
            "canvas_mcp.tools.student_write.get_course_id",
            new=AsyncMock(return_value="123"),
        ), patch(
            "canvas_mcp.tools.student_write.make_canvas_request", new=responder
        ), patch(
            "canvas_mcp.core.course_policy.make_canvas_request", new=policy_reader
        ), patch(
            "canvas_mcp.tools.student_write.upload_file_to_storage",
            new=storage_then_revoke,
        ):
            preview = await tools["submit_assignment"](
                course_identifier="TEST", assignment_id=42,
                submission_type="online_upload",
                file_contents=[{"name": "photo.jpg", "content_base64": encoded}],
            )
            token = preview.split("confirmation_token='")[1].split("'")[0]
            result = await tools["submit_assignment"](
                course_identifier="TEST", assignment_id=42,
                submission_type="online_upload",
                file_contents=[{"name": "photo.jpg", "content_base64": encoded}],
                confirmation_token=token,
            )

        assert "blocked" in result
        assert not posts, "submitted after the instructor revoked agent writes"

    @pytest.mark.asyncio
    async def test_becoming_a_group_assignment_during_upload_aborts(self):
        """The group refusal must hold at submit time, not only at preview."""
        import base64

        tools = get_tools(
            STUDENT_WRITE_TOOLS="submit_assignment",
            COURSE_AGENT_POLICY_ENABLED="false",
        )
        encoded = base64.b64encode(JPEG_BYTES).decode()
        state = {"assignment": _mock_assignment(submission_types=["online_upload"])}
        posts = []

        async def responder(method, endpoint, **kwargs):
            if method == "get":
                if endpoint.endswith("/submissions/self"):
                    return {"attempt": 0}
                return state["assignment"]
            if endpoint.endswith("/submissions/self/files"):
                return {"upload_url": "https://storage.example/x", "upload_params": {}}
            posts.append(endpoint)
            return {"attempt": 1}

        async def storage_then_convert(**kwargs):
            state["assignment"] = _mock_assignment(
                submission_types=["online_upload"], group_category_id=7
            )
            return {"id": 999}

        with patch(
            "canvas_mcp.tools.student_write.get_course_id",
            new=AsyncMock(return_value="123"),
        ), patch(
            "canvas_mcp.tools.student_write.make_canvas_request", new=responder
        ), patch(
            "canvas_mcp.tools.student_write.upload_file_to_storage",
            new=storage_then_convert,
        ):
            preview = await tools["submit_assignment"](
                course_identifier="TEST", assignment_id=42,
                submission_type="online_upload",
                file_contents=[{"name": "photo.jpg", "content_base64": encoded}],
            )
            token = preview.split("confirmation_token='")[1].split("'")[0]
            result = await tools["submit_assignment"](
                course_identifier="TEST", assignment_id=42,
                submission_type="online_upload",
                file_contents=[{"name": "photo.jpg", "content_base64": encoded}],
                confirmation_token=token,
            )

        assert "group assignment" in result
        assert not posts, "submitted on behalf of a group"

    def test_token_does_not_verify_under_a_forged_signature(self):
        import canvas_mcp.tools.student_write as sw

        token = sw._issue_token("fp")
        expiry, _, _mac = token.partition(".")
        assert sw._check_token(f"{expiry}.{'0' * 32}", "fp") is not None


class TestPreviewShowsWhatIsAuthorized:
    """The token covers the whole body, so the preview must show the whole body."""

    @pytest.mark.asyncio
    async def test_long_essay_is_not_truncated_in_the_preview(self):
        tools = get_tools(
            STUDENT_WRITE_TOOLS="submit_assignment",
            COURSE_AGENT_POLICY_ENABLED="false",
        )
        essay = "Paragraph. " * 300  # well past any excerpt limit
        with patch(
            "canvas_mcp.tools.student_write.get_course_id",
            new=AsyncMock(return_value="123"),
        ), patch(
            "canvas_mcp.tools.student_write.make_canvas_request", new_callable=AsyncMock
        ) as request:
            request.side_effect = [_mock_assignment(), {"attempt": 0}]
            preview = await tools["submit_assignment"](
                course_identifier="TEST", assignment_id=42,
                submission_type="online_text_entry", body=essay,
            )

        assert essay in preview, "the student must see everything the token authorizes"
        assert "..." not in preview.split("Content (")[1][:len(essay) + 50]


class TestUploadFailureHandling:
    """An upload problem must not cost the student their confirmation."""

    @pytest.mark.asyncio
    async def test_upload_failure_preserves_the_token(self):
        import canvas_mcp.tools.student_write as sw

        tools = get_tools(
            STUDENT_WRITE_TOOLS="submit_assignment",
            COURSE_AGENT_POLICY_ENABLED="false",
        )
        import base64

        encoded = base64.b64encode(JPEG_BYTES).decode()
        assignment = _mock_assignment(submission_types=["online_upload"])

        async def failing_storage(**kwargs):
            return {"error": "Upload timed out"}

        with patch(
            "canvas_mcp.tools.student_write.get_course_id",
            new=AsyncMock(return_value="123"),
        ), patch(
            "canvas_mcp.tools.student_write.make_canvas_request", new_callable=AsyncMock
        ) as request, patch(
            "canvas_mcp.tools.student_write.upload_file_to_storage", new=failing_storage
        ):
            request.side_effect = [assignment, {"attempt": 0}]
            preview = await tools["submit_assignment"](
                course_identifier="TEST", assignment_id=42,
                submission_type="online_upload",
                file_contents=[{"name": "photo.jpg", "content_base64": encoded}],
            )
            token = preview.split("confirmation_token='")[1].split("'")[0]

            request.side_effect = [
                assignment, {"attempt": 0},
                {"upload_url": "https://storage.example/x", "upload_params": {}},
            ]
            result = await tools["submit_assignment"](
                course_identifier="TEST", assignment_id=42,
                submission_type="online_upload",
                file_contents=[{"name": "photo.jpg", "content_base64": encoded}],
                confirmation_token=token,
            )

        assert "Nothing was submitted" in result
        # The token must survive: the failure had nothing to do with the
        # student's content, so it should not cost them a fresh preview.
        assert not sw._redeemed, "token retired despite nothing being submitted"
        assert token  # issued and still syntactically usable for a retry

    @pytest.mark.asyncio
    async def test_id_recovered_from_nested_attachment_shape(self):
        """Canvas storage does not always answer with a top-level id."""
        tools = get_tools(
            STUDENT_WRITE_TOOLS="submit_assignment",
            COURSE_AGENT_POLICY_ENABLED="false",
        )
        import base64

        encoded = base64.b64encode(JPEG_BYTES).decode()
        assignment = _mock_assignment(submission_types=["online_upload"])

        async def nested_storage(**kwargs):
            return {"attachment": {"id": 4242}}

        responder = make_responder(assignment)
        with patch(
            "canvas_mcp.tools.student_write.get_course_id",
            new=AsyncMock(return_value="123"),
        ), patch(
            "canvas_mcp.tools.student_write.make_canvas_request", new=responder
        ), patch(
            "canvas_mcp.tools.student_write.upload_file_to_storage", new=nested_storage
        ):
            preview = await tools["submit_assignment"](
                course_identifier="TEST", assignment_id=42,
                submission_type="online_upload",
                file_contents=[{"name": "photo.jpg", "content_base64": encoded}],
            )
            token = preview.split("confirmation_token='")[1].split("'")[0]
            result = await tools["submit_assignment"](
                course_identifier="TEST", assignment_id=42,
                submission_type="online_upload",
                file_contents=[{"name": "photo.jpg", "content_base64": encoded}],
                confirmation_token=token,
            )

        assert "✅ Submitted." in result
        assert responder.posts[-1]["data"]["submission[file_ids][]"] == ["4242"]


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
            "canvas_mcp.tools.student_write.make_canvas_request",
            new=make_responder(_mock_assignment(submission_types=["online_upload"])),
        ), patch(
            "canvas_mcp.tools.student_write.upload_file_to_storage", new=fake_storage
        ):
            preview = await tools["submit_assignment"](
                course_identifier="TEST", assignment_id=42,
                submission_type="online_upload",
                file_contents=[{"name": "photo.jpg", "content_base64": encoded}],
            )
            token = preview.split("confirmation_token='")[1].split("'")[0]
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
    async def test_assignment_restriction_is_enforced_end_to_end(self):
        """The instructor's allowed_extensions reaches the upload check."""
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
                _mock_assignment(
                    submission_types=["online_upload"], allowed_extensions=["pdf"]
                ),
                {"attempt": 0},
            ]
            result = await tools["submit_assignment"](
                course_identifier="TEST", assignment_id=42,
                submission_type="online_upload",
                file_contents=[
                    {"name": "notes.txt", "content_base64": base64.b64encode(b"hi").decode()}
                ],
            )
        assert "does not accept" in result
        assert not [c for c in request.call_args_list if c.args[0] == "post"]


class TestMarkModuleItemDone:
    """#221: PUT .../done returns success even for items without a
    'must_mark_done' completion requirement — Canvas accepts it and changes
    nothing (measured live: plain Page/File items carry
    completion_requirement: null). The tool must check the requirement first
    and confirm the write actually landed.
    """

    def _tools(self):
        return get_tools(
            STUDENT_WRITE_TOOLS="mark_module_item_done",
            COURSE_AGENT_POLICY_ENABLED="false",
        )

    @staticmethod
    def _responder(item_states, put_result=None):
        """item_states: successive GET responses for the module item."""
        gets = list(item_states)
        calls = []

        async def responder(method, endpoint, **kwargs):
            calls.append((method, endpoint))
            if method == "get":
                return gets.pop(0) if len(gets) > 1 else gets[0]
            if method == "put":
                return put_result if put_result is not None else {}
            raise AssertionError(f"unexpected call {method} {endpoint}")

        responder.calls = calls
        return responder

    @pytest.mark.asyncio
    async def test_item_without_mark_done_requirement_is_refused(self):
        tools = self._tools()
        responder = self._responder(
            [{"id": 2, "title": "Spec page", "type": "Page",
              "completion_requirement": None}]
        )
        with patch(
            "canvas_mcp.tools.student_write.get_course_id",
            new=AsyncMock(return_value="123"),
        ), patch(
            "canvas_mcp.tools.student_write.make_canvas_request", new=responder
        ):
            result = await tools["mark_module_item_done"](
                course_identifier="TEST", module_id=1, item_id=2
            )

        assert "✅" not in result
        assert "must_mark_done" in result
        assert not [c for c in responder.calls if c[0] == "put"]

    @pytest.mark.asyncio
    async def test_wrong_requirement_type_is_refused(self):
        tools = self._tools()
        responder = self._responder(
            [{"id": 2, "title": "Quiz", "type": "Quiz",
              "completion_requirement": {"type": "min_score", "min_score": 5}}]
        )
        with patch(
            "canvas_mcp.tools.student_write.get_course_id",
            new=AsyncMock(return_value="123"),
        ), patch(
            "canvas_mcp.tools.student_write.make_canvas_request", new=responder
        ):
            result = await tools["mark_module_item_done"](
                course_identifier="TEST", module_id=1, item_id=2
            )

        assert "✅" not in result
        assert "min_score" in result
        assert not [c for c in responder.calls if c[0] == "put"]

    @pytest.mark.asyncio
    async def test_confirmed_mark_done_reports_success(self):
        tools = self._tools()
        responder = self._responder([
            {"id": 2, "title": "Reading", "type": "Page",
             "completion_requirement": {"type": "must_mark_done", "completed": False}},
            {"id": 2, "title": "Reading", "type": "Page",
             "completion_requirement": {"type": "must_mark_done", "completed": True}},
        ])
        with patch(
            "canvas_mcp.tools.student_write.get_course_id",
            new=AsyncMock(return_value="123"),
        ), patch(
            "canvas_mcp.tools.student_write.make_canvas_request", new=responder
        ):
            result = await tools["mark_module_item_done"](
                course_identifier="TEST", module_id=1, item_id=2
            )

        assert "✅" in result
        assert [c for c in responder.calls if c[0] == "put"]

    @pytest.mark.asyncio
    async def test_unconfirmed_write_is_not_reported_as_success(self):
        """PUT accepted but the item still shows completed=False."""
        tools = self._tools()
        responder = self._responder([
            {"id": 2, "title": "Reading", "type": "Page",
             "completion_requirement": {"type": "must_mark_done", "completed": False}},
            {"id": 2, "title": "Reading", "type": "Page",
             "completion_requirement": {"type": "must_mark_done", "completed": False}},
        ])
        with patch(
            "canvas_mcp.tools.student_write.get_course_id",
            new=AsyncMock(return_value="123"),
        ), patch(
            "canvas_mcp.tools.student_write.make_canvas_request", new=responder
        ):
            result = await tools["mark_module_item_done"](
                course_identifier="TEST", module_id=1, item_id=2
            )

        assert "Could not confirm" in result
        assert "✅" not in result

    @pytest.mark.asyncio
    async def test_already_done_is_a_no_op_success(self):
        tools = self._tools()
        responder = self._responder([
            {"id": 2, "title": "Reading", "type": "Page",
             "completion_requirement": {"type": "must_mark_done", "completed": True}},
        ])
        with patch(
            "canvas_mcp.tools.student_write.get_course_id",
            new=AsyncMock(return_value="123"),
        ), patch(
            "canvas_mcp.tools.student_write.make_canvas_request", new=responder
        ):
            result = await tools["mark_module_item_done"](
                course_identifier="TEST", module_id=1, item_id=2
            )

        assert "already" in result
        assert not [c for c in responder.calls if c[0] == "put"]
