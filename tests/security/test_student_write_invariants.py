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
        posts = []

        async def responder(method, endpoint, **kwargs):
            if method == "get":
                if endpoint.endswith("/submissions/self"):
                    return {"attempt": 0}
                return assignment
            posts.append(kwargs.get("data"))
            return {"submitted_at": "2026-07-30T10:00:00Z", "attempt": 1}

        with patch(
            "canvas_mcp.tools.student_write.get_course_id",
            new=AsyncMock(return_value="123"),
        ), patch(
            "canvas_mcp.tools.student_write.make_canvas_request", new=responder
        ):
            preview = await tools["submit_assignment"](
                course_identifier="T", assignment_id=42,
                submission_type="online_text_entry", body="essay",
            )
            token = preview.split("confirmation_token='")[1].split("'")[0]
            await tools["submit_assignment"](
                course_identifier="T", assignment_id=42,
                submission_type="online_text_entry", body="essay",
                confirmation_token=token,
            )

        assert posts, "nothing was submitted"
        sent = posts[0]
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

    def test_the_assignment_decides_which_types_are_allowed(self):
        """The instructor's allowed_extensions is the authority, not a global list.

        An earlier version enforced a hard-coded allowlist here, which could only
        ever disagree with the instructor, and which rejected ordinary student
        work such as .heic photos.
        """
        from canvas_mcp.tools.student_write import _prepare_files

        _, error = _prepare_files(
            None,
            [{"name": "photo.heic", "content_base64": "YWJj"}],
            allowed_extensions=frozenset({".pdf"}),
        )
        assert error is not None
        assert "does not accept" in error
        assert ".pdf" in error, "the student should be told what IS accepted"

    def test_types_the_assignment_permits_are_accepted(self):
        from canvas_mcp.tools.student_write import _prepare_files

        prepared, error = _prepare_files(
            None,
            [{"name": "photo.heic", "content_base64": "YWJj"}],
            allowed_extensions=frozenset({".heic", ".jpg"}),
        )
        assert error is None
        assert prepared[0].name == "photo.heic"

    def test_unrestricted_assignments_accept_any_type(self):
        """No global allowlist: .heic and .tex must both go through."""
        from canvas_mcp.tools.student_write import _prepare_files

        for name in ["photo.heic", "paper.tex", "data.dta"]:
            prepared, error = _prepare_files(
                None, [{"name": name, "content_base64": "YWJj"}]
            )
            assert error is None, f"{name} was rejected with no assignment restriction"
            assert prepared[0].name == name

    def test_canvas_extension_format_is_normalized(self):
        """Canvas stores allowed_extensions without dots and in mixed case."""
        from canvas_mcp.tools.student_write import _normalize_extensions

        assert _normalize_extensions(["PDF", "docx", ".Heic"]) == frozenset(
            {".pdf", ".docx", ".heic"}
        )
        assert _normalize_extensions([]) is None
        assert _normalize_extensions(None) is None

    def test_odd_extension_returns_an_error_not_an_exception(self):
        from canvas_mcp.tools.student_write import _prepare_files

        for name in ["noextension", "trailing.", "x" * 300 + ".pdf", ".hidden"]:
            _, error = _prepare_files(
                None, [{"name": name, "content_base64": "YWJj"}]
            )
            assert isinstance(error, (str, type(None)))


class TestUploadResourceBounds:
    """A per-file cap alone lets one request exhaust server memory."""

    def test_file_count_is_capped(self):
        import base64

        from canvas_mcp.tools.student_write import _MAX_UPLOAD_FILES, _prepare_files

        tiny = base64.b64encode(b"x").decode()
        _, error = _prepare_files(
            None,
            [
                {"name": f"f{i}.txt", "content_base64": tiny}
                for i in range(_MAX_UPLOAD_FILES + 1)
            ],
        )
        assert error is not None
        assert "Too many files" in error

    def test_aggregate_size_is_capped_without_decoding(self):
        """Many individually-legal files must not add up to an illegal request.

        The check runs on the encoded length, so an oversized request is refused
        before its bytes are ever materialized.
        """
        from canvas_mcp.tools.student_write import (
            _MAX_TOTAL_UPLOAD_BYTES,
            _prepare_files,
        )

        # Six ~20MB claims: each under the per-file cap, together over the total.
        chunk = "A" * ((20 * 1024 * 1024) // 3 * 4)
        _, error = _prepare_files(
            None,
            [{"name": f"f{i}.pdf", "content_base64": chunk} for i in range(6)],
        )
        assert error is not None
        assert "total more than" in error
        assert _MAX_TOTAL_UPLOAD_BYTES > 0

    def test_pre_decode_size_estimate_is_exact(self):
        """The size check must not overshoot, or it rejects legal uploads.

        The naive len(encoded)//4*3 overshoots by the padding count, so a file
        whose decoded size is exactly the documented limit would be refused
        before it was ever decoded. Checked across all three padding cases.
        """
        import base64

        from canvas_mcp.tools.student_write import _decoded_size

        for length in range(0, 40):
            payload = b"x" * length
            encoded = base64.b64encode(payload).decode()
            assert _decoded_size(encoded) == length, (
                f"estimate wrong for {length} bytes "
                f"(padding={encoded.count('=')})"
            )

    def test_boundary_file_is_not_rejected_by_the_estimate(self):
        """Exercise the limit comparison itself without allocating 100 MB."""
        import base64

        from canvas_mcp.tools.student_write import _decoded_size

        # Worst case for the naive formula: two padding characters.
        payload = b"x" * 100
        encoded = base64.b64encode(payload).decode()
        assert encoded.endswith("=="), "expected two padding characters"
        assert _decoded_size(encoded) == 100
        # The naive formula would have said 102 and could refuse a limit-sized file.
        assert len(encoded) // 4 * 3 == 102

    def test_a_normal_submission_still_works(self):
        """The bounds must not break the ordinary case."""
        import base64

        from canvas_mcp.tools.student_write import _prepare_files

        prepared, error = _prepare_files(
            None,
            [
                {"name": "essay.pdf", "content_base64": base64.b64encode(b"pdf").decode()},
                {"name": "chart.png", "content_base64": base64.b64encode(b"png").decode()},
            ],
        )
        assert error is None
        assert [p.name for p in prepared] == ["essay.pdf", "chart.png"]


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

    def test_a_later_deny_is_never_discarded(self):
        """An appended revocation must not be swallowed by an earlier allow.

        Keeping only the first occurrence of a key would let an instructor who
        adds "agent_writes: deny" below an existing "agent_writes: allow" have
        their revocation silently ignored, which is the worst direction for this
        to fail.
        """
        policy = parse_policy_body("agent_writes: allow\nagent_writes: deny")
        assert policy.allow_writes is False
        assert policy.source == "course_artifact_conflict"

    def test_conflict_denies_in_either_order(self):
        assert parse_policy_body(
            "agent_writes: deny\nagent_writes: allow"
        ).allow_writes is False

    def test_repeating_the_same_directive_is_not_a_conflict(self):
        policy = parse_policy_body("agent_writes: allow\nagent_writes: allow")
        assert policy.allow_writes is True

    def test_conflicting_allow_tools_denies(self):
        policy = parse_policy_body(
            "agent_writes: allow\n"
            "allow_tools: submit_assignment\n"
            "allow_tools: mark_module_item_done"
        )
        assert policy.allow_writes is False
        assert policy.source == "course_artifact_conflict"

    def test_present_but_empty_allow_tools_denies(self):
        """The most restrictive directive must not become the least restrictive.

        `tools or None` collapsed an empty allowlist into "no narrowing", i.e.
        every operator-enabled tool. An instructor who wrote `allow_tools:` and
        stopped, or deliberately named nothing, would have been granting
        everything.
        """
        policy = parse_policy_body("agent_writes: allow\nallow_tools:")
        assert policy.allow_writes is False
        assert policy.source == "course_artifact_empty_allowlist"

    def test_omitted_allow_tools_means_no_narrowing(self):
        """Absent is different from present-but-empty."""
        policy = parse_policy_body("agent_writes: allow")
        assert policy.allow_writes is True
        assert policy.allow_tools is None

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
    async def test_the_syllabus_is_the_only_carrier(self):
        """There is deliberately no way to select a weaker policy carrier.

        A course-page carrier was implemented and then removed: editing_roles
        describes who may edit a page NOW, not who wrote it, so a student who
        can create pages could author the policy and lock it teacher-only
        afterwards. Authorship cannot be established from a student's own token,
        so a page can never be trustworthy here however it is screened. This
        test exists to keep that option from being reintroduced as a config knob.
        """
        reset_config()
        config = get_config()
        assert not hasattr(config, "course_agent_policy_source")
        assert not hasattr(config, "course_agent_policy_page")

    @pytest.mark.asyncio
    async def test_policy_is_read_from_the_course_syllabus(self):
        reset_policy_cache()
        seen = {}

        async def recorder(method, endpoint, **kwargs):
            seen["endpoint"] = endpoint
            seen["params"] = kwargs.get("params")
            return {"syllabus_body": "agent_writes: allow"}

        with patch.dict(
            "os.environ", {"STUDENT_WRITE_TOOLS": ALL_WRITE_TOOLS}, clear=False
        ):
            reset_config()
            with patch(
                "canvas_mcp.core.course_policy.make_canvas_request", new=recorder
            ):
                policy = await get_course_policy("123")

        assert policy.allow_writes is True
        assert seen["endpoint"] == "/courses/123"
        assert "syllabus_body" in seen["params"]["include[]"]
        assert "pages" not in seen["endpoint"]


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
    async def test_read_errors_are_never_cached(self):
        """One bad caller must not deny writes for a whole course.

        A read error reflects the caller's request (expired token, not enrolled,
        transient failure), not a property of the course. Caching it under the
        course id alone would let any caller block every legitimate student in
        that course for a full deny TTL.
        """
        from canvas_mcp.core.course_policy import _policy_cache

        reset_policy_cache()
        with patch.dict(
            "os.environ", {"STUDENT_WRITE_TOOLS": ALL_WRITE_TOOLS}, clear=False
        ):
            reset_config()
            with patch(
                "canvas_mcp.core.course_policy.make_canvas_request",
                new=AsyncMock(return_value={"error": "HTTP error: 401"}),
            ):
                denied = await get_course_policy("123")
            assert denied.allow_writes is False
            assert "123" not in _policy_cache, "read error poisoned the cache"

            # A legitimate caller immediately afterwards sees the real policy.
            with patch(
                "canvas_mcp.core.course_policy.make_canvas_request",
                new=AsyncMock(
                    return_value={"syllabus_body": "agent_writes: allow"}
                ),
            ):
                policy = await get_course_policy("123")
        assert policy.allow_writes is True

    @pytest.mark.asyncio
    async def test_inaccessible_course_denies_and_is_not_cached(self):
        """A 404 on the course means this caller cannot see it, not "no policy".

        Caching that as an absence would let one caller without access install a
        global verdict, and under a permissive default that verdict would
        override an instructor's explicit denial.
        """
        from canvas_mcp.core.course_policy import _policy_cache

        reset_policy_cache()
        with patch.dict(
            "os.environ", {"COURSE_AGENT_POLICY_DEFAULT": "allow"}, clear=False
        ):
            reset_config()
            with patch(
                "canvas_mcp.core.course_policy.make_canvas_request",
                new=AsyncMock(return_value={"error": "HTTP error: 404"}),
            ):
                policy = await get_course_policy("999")
            assert policy.allow_writes is False
            assert "999" not in _policy_cache

            # An instructor's actual denial is what a real student then sees.
            with patch(
                "canvas_mcp.core.course_policy.make_canvas_request",
                new=AsyncMock(
                    return_value={"syllabus_body": "agent_writes: deny"}
                ),
            ):
                real = await get_course_policy("999")
        assert real.allow_writes is False
        assert real.source == "course_artifact"

    @pytest.mark.asyncio
    async def test_unmarked_syllabus_is_a_cacheable_absence(self):
        """A successful course read with no marker IS caller-independent."""
        from canvas_mcp.core.course_policy import _policy_cache

        reset_policy_cache()
        with patch.dict(
            "os.environ", {"COURSE_AGENT_POLICY_DEFAULT": "deny"}, clear=False
        ):
            reset_config()
            with patch(
                "canvas_mcp.core.course_policy.make_canvas_request",
                new=AsyncMock(return_value={"syllabus_body": "<p>Welcome</p>"}),
            ):
                policy = await get_course_policy("555")
        assert policy.allow_writes is False
        assert policy.source == "default"
        assert "555" in _policy_cache

    @pytest.mark.asyncio
    async def test_syllabus_mode_404_denies_rather_than_assuming_absence(self):
        """Deliberately stricter than an earlier version of this test.

        In syllabus mode the request is for the COURSE, so a 404 means this
        caller cannot see the course — not that the course states no policy.
        Reading it as an absence would, under a permissive default, hand a
        caller without access an allow (and cache it for everyone).
        """
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
        assert policy.allow_writes is False
        assert policy.source == "read_error"


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
