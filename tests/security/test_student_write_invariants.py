"""Security invariants for Tier 1 student write tools (#170).

These tests exist to make specific public promises falsifiable. Each one
corresponds to a claim made to institutions evaluating this server, and each
should fail loudly if a future change quietly breaks it.
"""

import inspect
from unittest.mock import AsyncMock, patch

import pytest
from fastmcp import FastMCP

from canvas_mcp.core.config import get_config, reset_config
from canvas_mcp.core.course_policy import (
    assert_no_identity_override,
    check_student_write_allowed,
    get_course_policy,
    parse_policy_body,
    reset_policy_cache,
)
from canvas_mcp.tools.student_write import (
    register_student_write_tools,
    reset_pending_confirmations,
)

ALL_WRITE_TOOLS = "submit_assignment,comment_on_my_submission,mark_module_item_done"

# Any parameter that could let a caller name someone other than themselves.
IDENTITY_PARAMS = {
    "user_id", "as_user_id", "student_id", "assessor_id",
    "user", "student", "on_behalf_of", "group_id",
}


def get_tools(**env):
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


class TestNoIdentityOverride:
    """A student write must not be able to name another student."""

    def test_no_write_tool_accepts_an_identity_parameter(self):
        tools = get_tools(STUDENT_WRITE_TOOLS=ALL_WRITE_TOOLS)
        for name, fn in tools.items():
            params = set(inspect.signature(fn).parameters)
            offending = params & IDENTITY_PARAMS
            assert not offending, f"{name} exposes identity parameter(s): {offending}"

    @pytest.mark.parametrize(
        "field",
        [
            "as_user_id",
            "submission[user_id]",
            "user_id",
            "submission[group_id]",
            "group_id",
            "student_id",
        ],
    )
    def test_guard_rejects_each_identity_field(self, field):
        """The wire-level guard, not just the Python signature.

        This matters because the submit endpoint is NOT structurally
        self-scoped: Canvas honours submission[user_id] there when the token
        carries grading permission, and a person can hold both student and TA
        enrollments.
        """
        with pytest.raises(ValueError, match="identity-override"):
            assert_no_identity_override({"submission[body]": "x", field: "999"})

    def test_guard_allows_a_legitimate_body(self):
        assert_no_identity_override(
            {
                "submission[submission_type]": "online_text_entry",
                "submission[body]": "my essay",
                "comment[text_comment]": "here you go",
            }
        )

    @pytest.mark.asyncio
    async def test_submitted_body_carries_no_identity_fields(self):
        """Assert on what actually goes over the wire."""
        tools = get_tools(
            STUDENT_WRITE_TOOLS=ALL_WRITE_TOOLS, COURSE_AGENT_POLICY_ENABLED="false"
        )
        assignment = {
            "id": 42, "name": "Essay", "submission_types": ["online_text_entry"],
            "allowed_attempts": -1,
        }
        with patch(
            "canvas_mcp.tools.student_write.get_course_id",
            new=AsyncMock(return_value="123"),
        ), patch(
            "canvas_mcp.tools.student_write.make_canvas_request", new_callable=AsyncMock
        ) as request:
            request.side_effect = [assignment, {"attempt": 0}]
            preview = await tools["submit_assignment"](
                course_identifier="T", assignment_id=42,
                submission_type="online_text_entry", body="essay",
            )
            token = preview.split("confirmation_token='")[1].split("'")[0]
            request.side_effect = [assignment, {"attempt": 0}, {"attempt": 1}]
            await tools["submit_assignment"](
                course_identifier="T", assignment_id=42,
                submission_type="online_text_entry", body="essay",
                confirmation_token=token,
            )

        post = [c for c in request.call_args_list if c.args[0] == "post"][0]
        sent = post.kwargs["data"]
        assert set(sent) <= {
            "submission[submission_type]", "submission[body]",
            "submission[url]", "submission[file_ids][]", "comment[text_comment]",
        }, f"unexpected outbound fields: {set(sent)}"


class TestConfirmationIsCallerBound:
    """On a hosted server every request carries a different student's token."""

    def test_fingerprint_differs_per_caller(self):
        """Otherwise one student could redeem another's confirmation.

        Without caller binding, two students at the same attempt number on the
        same assignment produce the same fingerprint, so a token issued to one
        would verify for the other.
        """
        import canvas_mcp.tools.student_write as sw

        class _Creds:
            def __init__(self, token):
                self.api_token = token

        with patch.object(sw, "get_request_credentials", return_value=_Creds("aaa")):
            first = sw._fingerprint("1", "2", "online_text_entry", "digest", 0)
        with patch.object(sw, "get_request_credentials", return_value=_Creds("bbb")):
            second = sw._fingerprint("1", "2", "online_text_entry", "digest", 0)

        assert first != second

    def test_token_issued_to_one_student_fails_for_another(self):
        import canvas_mcp.tools.student_write as sw

        class _Creds:
            def __init__(self, token):
                self.api_token = token

        with patch.object(sw, "get_request_credentials", return_value=_Creds("aaa")):
            fingerprint = sw._fingerprint("1", "2", "online_text_entry", "d", 0)
            token = sw._issue_token(fingerprint)
        with patch.object(sw, "get_request_credentials", return_value=_Creds("bbb")):
            other = sw._fingerprint("1", "2", "online_text_entry", "d", 0)

        assert sw._check_token(token, fingerprint) is None
        assert sw._check_token(token, other) is not None

    def test_caller_identity_does_not_expose_the_credential(self):
        """The handle must not be the token, nor reversible to it."""
        import canvas_mcp.tools.student_write as sw

        class _Creds:
            api_token = "super-secret-canvas-token"

        with patch.object(sw, "get_request_credentials", return_value=_Creds()):
            identity = sw._caller_identity()

        assert "super-secret-canvas-token" not in identity
        assert len(identity) == 64  # sha256 hex


class TestInlineFilenames:
    """A hosted caller supplies the filename, so it is untrusted input."""

    def test_path_traversal_in_a_supplied_name_is_stripped(self):
        from canvas_mcp.tools.student_write import _prepare_files

        prepared, error = _prepare_files(
            None,
            [{"name": "../../essay.pdf", "content_base64": "cGRmYnl0ZXM="}],
        )
        assert error is None
        assert ".." not in prepared[0].name
        assert "/" not in prepared[0].name

    def test_disallowed_extension_is_refused(self):
        from canvas_mcp.tools.student_write import _prepare_files

        _, error = _prepare_files(
            None, [{"name": "payload.exe", "content_base64": "TVo="}]
        )
        assert error is not None
        assert "not an allowed file type" in error

    def test_odd_extension_returns_an_error_not_an_exception(self):
        from canvas_mcp.tools.student_write import _prepare_files

        for name in ["noextension", "trailing.", "x" * 300 + ".pdf", ".hidden"]:
            _, error = _prepare_files(
                None, [{"name": name, "content_base64": "YWJj"}]
            )
            assert isinstance(error, (str, type(None)))


class TestHostedFileIngress:
    """file_paths reads the SERVER's disk. That must not be reachable remotely."""

    @pytest.mark.asyncio
    async def test_local_paths_refused_over_http_transport(self):
        """Otherwise a remote caller could exfiltrate server files.

        They would name any path the server process can read and upload it into
        their own Canvas submission.
        """
        tools = get_tools(
            STUDENT_WRITE_TOOLS=ALL_WRITE_TOOLS, COURSE_AGENT_POLICY_ENABLED="false"
        )
        assignment = {
            "id": 42, "name": "E", "submission_types": ["online_upload"],
            "allowed_attempts": -1,
        }
        with patch(
            "canvas_mcp.tools.student_write.get_course_id",
            new=AsyncMock(return_value="123"),
        ), patch(
            "canvas_mcp.tools.student_write.make_canvas_request", new_callable=AsyncMock
        ) as request, patch(
            "canvas_mcp.tools.student_write.is_http_request_active", return_value=True
        ):
            request.side_effect = [assignment, {"attempt": 0}]
            result = await tools["submit_assignment"](
                course_identifier="T", assignment_id=42,
                submission_type="online_upload", file_paths=["/etc/passwd"],
            )

        assert "only available on a local (stdio) server" in result
        assert not [c for c in request.call_args_list if c.args[0] == "post"]


class TestPolicyParsing:
    """A policy only grants when it definitively says so."""

    def test_deny_is_parsed(self):
        assert parse_policy_body("agent_writes: deny").allow_writes is False

    def test_allow_is_parsed(self):
        policy = parse_policy_body("agent_writes: allow")
        assert policy.allow_writes is True
        assert policy.allow_tools is None

    def test_allow_can_narrow_to_named_tools(self):
        policy = parse_policy_body(
            "agent_writes: allow\nallow_tools: submit_assignment"
        )
        assert policy.allow_tools == frozenset({"submit_assignment"})

    def test_survives_canvas_rich_text_markup(self):
        policy = parse_policy_body("<p>agent_writes: allow</p><p>note: go ahead</p>")
        assert policy.allow_writes is True
        assert policy.note == "go ahead"

    def test_malformed_policy_denies(self):
        """A typo must never become a grant."""
        assert parse_policy_body("agent_writes: yes please").allow_writes is False
        assert parse_policy_body("total gibberish").allow_writes is False
        assert parse_policy_body("").allow_writes is False


class TestPolicyResolution:
    """Failure modes must all fail closed, except a definitively absent policy."""

    @pytest.mark.asyncio
    async def test_read_error_denies_even_when_default_is_allow(self):
        """A Canvas outage must not silently grant writes everywhere."""
        with patch.dict(
            "os.environ", {"COURSE_AGENT_POLICY_DEFAULT": "allow"}, clear=False
        ):
            reset_config()
            with patch(
                "canvas_mcp.core.course_policy.make_canvas_request",
                new=AsyncMock(return_value={"error": "HTTP error: 500"}),
            ):
                policy = await get_course_policy("123")
        assert policy.allow_writes is False
        assert policy.source == "read_error"

    @pytest.mark.asyncio
    async def test_absent_policy_uses_configured_default(self):
        for posture, expected in (("allow", True), ("deny", False)):
            reset_policy_cache()
            with patch.dict(
                "os.environ", {"COURSE_AGENT_POLICY_DEFAULT": posture}, clear=False
            ):
                reset_config()
                with patch(
                    "canvas_mcp.core.course_policy.make_canvas_request",
                    new=AsyncMock(return_value={"syllabus_body": "<p>Welcome!</p>"}),
                ):
                    policy = await get_course_policy("123")
            assert policy.allow_writes is expected
            assert policy.source == "default"

    @pytest.mark.asyncio
    async def test_default_posture_is_deny(self):
        reset_config()
        assert get_config().course_agent_policy_default == "deny"

    @pytest.mark.asyncio
    async def test_syllabus_is_the_default_carrier(self):
        """The carrier must be one students cannot edit."""
        reset_config()
        assert get_config().course_agent_policy_source == "syllabus"

    @pytest.mark.asyncio
    async def test_student_editable_page_is_not_trusted(self):
        """A page a student could have written is not an instructor statement."""
        with patch.dict(
            "os.environ",
            {"COURSE_AGENT_POLICY_SOURCE": "page", "COURSE_AGENT_POLICY_DEFAULT": "allow"},
            clear=False,
        ):
            reset_config()
            with patch(
                "canvas_mcp.core.course_policy.make_canvas_request",
                new=AsyncMock(
                    return_value={
                        "body": "agent_writes: allow",
                        "editing_roles": "teachers,students",
                    }
                ),
            ):
                policy = await get_course_policy("123")
        assert policy.allow_writes is False
        assert policy.source == "untrusted_artifact"

    @pytest.mark.parametrize(
        "editing_roles",
        [None, "", "teachers,students", "students", "anyone", "members", "public"],
    )
    @pytest.mark.asyncio
    async def test_page_is_trusted_only_when_explicitly_teacher_only(self, editing_roles):
        """Ambiguity must fail closed.

        A denylist of known-bad role names would trust a page whose
        editing_roles is missing, empty, or a value Canvas introduces later.
        """
        reset_policy_cache()
        with patch.dict(
            "os.environ",
            {"COURSE_AGENT_POLICY_SOURCE": "page", "COURSE_AGENT_POLICY_DEFAULT": "allow"},
            clear=False,
        ):
            reset_config()
            page = {"body": "agent_writes: allow"}
            if editing_roles is not None:
                page["editing_roles"] = editing_roles
            with patch(
                "canvas_mcp.core.course_policy.make_canvas_request",
                new=AsyncMock(return_value=page),
            ):
                policy = await get_course_policy("123")
        assert policy.allow_writes is False
        assert policy.source == "untrusted_artifact"

    @pytest.mark.asyncio
    async def test_teacher_only_page_is_trusted(self):
        with patch.dict(
            "os.environ", {"COURSE_AGENT_POLICY_SOURCE": "page"}, clear=False
        ):
            reset_config()
            with patch(
                "canvas_mcp.core.course_policy.make_canvas_request",
                new=AsyncMock(
                    return_value={
                        "body": "agent_writes: allow",
                        "editing_roles": "teachers",
                    }
                ),
            ):
                policy = await get_course_policy("123")
        assert policy.allow_writes is True


class TestErrorClassification:
    """Only a real 404 may be read as "no policy artifact"."""

    @pytest.mark.parametrize(
        "error_message",
        [
            "HTTP error: 500, Details: {'message': 'upstream 404 from origin'}",
            "HTTP error: 403",
            "HTTP error: 429",
            "Request failed: connection reset after 404 retries",
            "Max retries exceeded",
        ],
    )
    @pytest.mark.asyncio
    async def test_non_404_failures_still_deny_under_permissive_default(
        self, error_message
    ):
        """A substring test for "404" would turn a 500 into a grant."""
        reset_policy_cache()
        with patch.dict(
            "os.environ", {"COURSE_AGENT_POLICY_DEFAULT": "allow"}, clear=False
        ):
            reset_config()
            with patch(
                "canvas_mcp.core.course_policy.make_canvas_request",
                new=AsyncMock(return_value={"error": error_message}),
            ):
                policy = await get_course_policy("123")
        assert policy.allow_writes is False
        assert policy.source == "read_error"

    @pytest.mark.asyncio
    async def test_genuine_404_is_treated_as_absent(self):
        reset_policy_cache()
        with patch.dict(
            "os.environ", {"COURSE_AGENT_POLICY_DEFAULT": "allow"}, clear=False
        ):
            reset_config()
            with patch(
                "canvas_mcp.core.course_policy.make_canvas_request",
                new=AsyncMock(return_value={"error": "HTTP error: 404"}),
            ):
                policy = await get_course_policy("123")
        assert policy.allow_writes is True
        assert policy.source == "default"


class TestLayering:
    """A course artifact can restrict within the operator ceiling, never past it."""

    @pytest.mark.asyncio
    async def test_course_cannot_enable_a_tool_the_operator_disabled(self):
        with patch.dict(
            "os.environ", {"STUDENT_WRITE_TOOLS": "comment_on_my_submission"}, clear=False
        ):
            reset_config()
            with patch(
                "canvas_mcp.core.course_policy.make_canvas_request",
                new=AsyncMock(
                    return_value={
                        "syllabus_body": "agent_writes: allow\n"
                                         "allow_tools: submit_assignment"
                    }
                ),
            ):
                allowed, reason = await check_student_write_allowed(
                    "123", "submit_assignment"
                )
        assert allowed is False
        assert "STUDENT_WRITE_TOOLS" in reason

    @pytest.mark.asyncio
    async def test_course_can_restrict_within_the_ceiling(self):
        with patch.dict(
            "os.environ", {"STUDENT_WRITE_TOOLS": ALL_WRITE_TOOLS}, clear=False
        ):
            reset_config()
            with patch(
                "canvas_mcp.core.course_policy.make_canvas_request",
                new=AsyncMock(
                    return_value={
                        "syllabus_body": "agent_writes: allow\n"
                                         "allow_tools: comment_on_my_submission"
                    }
                ),
            ):
                allowed_comment, _ = await check_student_write_allowed(
                    "123", "comment_on_my_submission"
                )
                allowed_submit, reason = await check_student_write_allowed(
                    "123", "submit_assignment"
                )
        assert allowed_comment is True
        assert allowed_submit is False
        assert "not 'submit_assignment'" in reason

    @pytest.mark.asyncio
    async def test_course_deny_blocks_an_operator_enabled_tool(self):
        with patch.dict(
            "os.environ", {"STUDENT_WRITE_TOOLS": ALL_WRITE_TOOLS}, clear=False
        ):
            reset_config()
            with patch(
                "canvas_mcp.core.course_policy.make_canvas_request",
                new=AsyncMock(
                    return_value={
                        "syllabus_body": "agent_writes: deny\n"
                                         "note: Please submit in Canvas directly."
                    }
                ),
            ):
                allowed, reason = await check_student_write_allowed(
                    "123", "submit_assignment"
                )
        assert allowed is False
        assert "Please submit in Canvas directly." in reason
