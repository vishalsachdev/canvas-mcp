"""Tests for the enrollment-check capability (core + matcher)."""

from unittest.mock import AsyncMock, patch

import pytest

from canvas_mcp.core.enrollment import (
    AmbiguousIdentifier,
    EnrollmentCheckUnavailable,
    EnrollmentResult,
    _match_enrollment,
    check_enrollment,
)


def _enr(login_id=None, sis=None, state="active", etype="StudentEnrollment", uid=None):
    return {
        "enrollment_state": state,
        "type": etype,
        "user": {
            "id": uid if uid is not None else abs(hash((login_id, sis))) % 100000,
            "login_id": login_id,
            "sis_user_id": sis,
        },
    }


def _enr_permission_stripped(state="active", etype="StudentEnrollment", uid=7):
    """An enrollment as Canvas ACTUALLY returns it to a non-roster-admin token.

    Measured live (issue #171): HTTP 200, full roster, but every ``user`` object
    is reduced to exactly these keys — ``login_id`` and ``sis_user_id`` are
    OMITTED, not null. The original fixture above always supplied ``login_id``,
    which is precisely why the false-negative bug survived its tests.
    """
    return {
        "enrollment_state": state,
        "type": etype,
        "user": {
            "created_at": "2026-01-05T00:00:00Z",
            "id": uid,
            "name": "Some Student",
            "short_name": "Some Student",
            "sortable_name": "Student, Some",
        },
    }


def _get_check_enrollment_tool():
    """Capture the registered ``check_enrollment`` MCP tool coroutine."""
    from fastmcp import FastMCP

    from canvas_mcp.tools.enrollment import register_enrollment_tools

    mcp = FastMCP("test")
    captured = {}
    original_tool = mcp.tool

    def capturing_tool(*args, **kwargs):
        decorator = original_tool(*args, **kwargs)

        def wrapper(fn):
            captured[fn.__name__] = fn
            return decorator(fn)

        return wrapper

    mcp.tool = capturing_tool
    register_enrollment_tools(mcp)
    return captured["check_enrollment"]


# --------------------------------------------------------------------------
# Pure matcher
# --------------------------------------------------------------------------


class TestMatchEnrollment:
    def test_match_on_login_id(self):
        roster = [_enr(login_id="netid1"), _enr(login_id="jdoe")]
        match = _match_enrollment(roster, "jdoe", active_only=True)
        assert match is not None
        enrollment, matched_on = match
        assert matched_on == "login_id"
        assert enrollment["user"]["login_id"] == "jdoe"

    def test_match_on_sis_user_id(self):
        roster = [_enr(login_id="someone", sis="jdoe-sis")]
        match = _match_enrollment(roster, "jdoe-sis", active_only=True)
        assert match is not None
        assert match[1] == "sis_user_id"

    def test_match_is_case_insensitive(self):
        roster = [_enr(login_id="JDoe")]
        assert _match_enrollment(roster, "jdoe", active_only=True) is not None

    def test_no_match_returns_none(self):
        roster = [_enr(login_id="alice"), _enr(login_id="bob")]
        assert _match_enrollment(roster, "carol", active_only=True) is None

    def test_active_only_excludes_concluded(self):
        roster = [_enr(login_id="jdoe", state="completed")]
        # active_only -> the concluded enrollment is skipped
        assert _match_enrollment(roster, "jdoe", active_only=True) is None
        # without active_only -> it matches
        assert _match_enrollment(roster, "jdoe", active_only=False) is not None


# --------------------------------------------------------------------------
# Async check_enrollment (mocks the Canvas layer)
# --------------------------------------------------------------------------


@pytest.fixture
def mock_course_id():
    with patch(
        "canvas_mcp.core.enrollment.get_course_id",
        new=AsyncMock(return_value="12345"),
    ) as m:
        yield m


@pytest.fixture
def mock_request():
    with patch(
        "canvas_mcp.core.enrollment.make_canvas_request", new=AsyncMock()
    ) as m:
        yield m


@pytest.mark.asyncio
async def test_check_enrollment_enrolled(mock_course_id, mock_request):
    mock_request.return_value = [_enr(login_id="jdoe", state="active")]
    result = await check_enrollment("BADM 350", "jdoe")
    assert isinstance(result, EnrollmentResult)
    assert result.enrolled is True
    assert result.course_id == "12345"
    assert result.enrollment_state == "active"
    assert result.matched_on == "login_id"


@pytest.mark.asyncio
async def test_check_enrollment_not_enrolled(mock_course_id, mock_request):
    mock_request.return_value = [_enr(login_id="someoneelse")]
    result = await check_enrollment("BADM 350", "jdoe")
    assert result.enrolled is False
    assert result.course_id == "12345"
    # The roster must NOT leak into the result.
    assert result.role is None and result.matched_on is None


@pytest.mark.asyncio
async def test_check_enrollment_invalid_netid_raises(mock_course_id, mock_request):
    with pytest.raises(ValueError, match="net_id"):
        await check_enrollment("BADM 350", "bad netid!")
    # Invalid input must be rejected before any Canvas call.
    mock_request.assert_not_called()


@pytest.mark.asyncio
async def test_check_enrollment_canvas_error_raises(mock_course_id, mock_request):
    mock_request.return_value = {"error": "403 Forbidden"}
    with pytest.raises(RuntimeError, match="403"):
        await check_enrollment("BADM 350", "jdoe")


@pytest.mark.asyncio
async def test_check_enrollment_unresolvable_course_raises(mock_request):
    with patch(
        "canvas_mcp.core.enrollment.get_course_id",
        new=AsyncMock(return_value=None),
    ):
        with pytest.raises(ValueError, match="resolve course"):
            await check_enrollment("NOPE 999", "jdoe")
    mock_request.assert_not_called()


# --------------------------------------------------------------------------
# Permission-blindness is not absence (issue #171)
# --------------------------------------------------------------------------


class TestIdentifierVisibilityGuard:
    """A roster with no visible identifiers must never yield a confident 'no'."""

    @pytest.mark.asyncio
    async def test_roster_without_identifiers_raises_unavailable(
        self, mock_course_id, mock_request
    ):
        mock_request.return_value = [
            _enr_permission_stripped(uid=1),
            _enr_permission_stripped(uid=2),
        ]
        with pytest.raises(EnrollmentCheckUnavailable):
            await check_enrollment("BADM 350", "jdoe")

    @pytest.mark.asyncio
    async def test_stripped_roster_is_not_reported_as_not_enrolled(
        self, mock_course_id, mock_request
    ):
        """The regression that shipped: an enrolled=False result for this input."""
        mock_request.return_value = [_enr_permission_stripped()]
        try:
            result = await check_enrollment("BADM 350", "jdoe")
        except EnrollmentCheckUnavailable:
            return  # correct behavior
        pytest.fail(
            f"Expected EnrollmentCheckUnavailable, got a definite answer: {result}"
        )

    @pytest.mark.asyncio
    async def test_empty_roster_still_returns_no(self, mock_course_id, mock_request):
        """An EMPTY roster is genuine absence — it must stay a real NO."""
        mock_request.return_value = []
        result = await check_enrollment("BADM 350", "jdoe")
        assert result.enrolled is False
        assert result.course_id == "12345"

    @pytest.mark.asyncio
    async def test_partial_identifier_visibility_still_matches(
        self, mock_course_id, mock_request
    ):
        """One visible identifier proves the fields are not stripped."""
        mock_request.return_value = [
            _enr_permission_stripped(uid=1),
            _enr(login_id="jdoe"),
        ]
        result = await check_enrollment("BADM 350", "jdoe")
        assert result.enrolled is True
        assert result.matched_on == "login_id"

    @pytest.mark.asyncio
    async def test_partial_visibility_yields_indeterminate_for_a_stranger(
        self, mock_course_id, mock_request
    ):
        """A NO is only trustworthy when every row could have matched.

        This previously asserted a definitive NO, which was the same false
        negative the guard exists to prevent: the requested NetID could be
        sitting in the row whose identifiers Canvas stripped.
        """
        mock_request.return_value = [
            _enr_permission_stripped(uid=1),
            _enr(login_id="alice"),
        ]
        with pytest.raises(EnrollmentCheckUnavailable):
            await check_enrollment("BADM 350", "jdoe")

    @pytest.mark.asyncio
    async def test_full_visibility_yields_a_real_no_for_a_stranger(
        self, mock_course_id, mock_request
    ):
        """Every row visible + no match = trustworthy NO."""
        mock_request.return_value = [
            _enr(login_id="bob"),
            _enr(login_id="alice"),
        ]
        result = await check_enrollment("BADM 350", "jdoe")
        assert result.enrolled is False

    @pytest.mark.asyncio
    async def test_sis_only_visibility_does_not_trip_the_guard(
        self, mock_course_id, mock_request
    ):
        mock_request.return_value = [_enr(login_id=None, sis="123456")]
        result = await check_enrollment("BADM 350", "123456")
        assert result.enrolled is True
        assert result.matched_on == "sis_user_id"


class TestCheckEnrollmentToolMessages:
    """The tool-layer wording is the actual product here — assert it."""

    @pytest.mark.asyncio
    async def test_indeterminate_message_never_says_no(
        self, mock_course_id, mock_request
    ):
        mock_request.return_value = [_enr_permission_stripped()]
        tool = _get_check_enrollment_tool()
        out = await tool(course_identifier="BADM 350", net_id="jdoe")
        assert "INDETERMINATE" in out
        assert not out.startswith("NO")
        assert "NO —" not in out
        assert "get_my_enrollments" in out

    @pytest.mark.asyncio
    async def test_canvas_error_message_names_the_self_tool_and_never_says_no(
        self, mock_course_id, mock_request
    ):
        mock_request.return_value = {"error": "403 Forbidden"}
        tool = _get_check_enrollment_tool()
        out = await tool(course_identifier="BADM 350", net_id="jdoe")
        assert "NO —" not in out
        assert "get_my_enrollments" in out
        assert "403" in out

    @pytest.mark.asyncio
    async def test_empty_roster_message_is_a_real_no(
        self, mock_course_id, mock_request
    ):
        mock_request.return_value = []
        tool = _get_check_enrollment_tool()
        out = await tool(course_identifier="BADM 350", net_id="jdoe")
        assert out.startswith("NO —")
        assert "INDETERMINATE" not in out

    @pytest.mark.asyncio
    async def test_enrolled_message_still_says_yes(self, mock_course_id, mock_request):
        mock_request.return_value = [_enr(login_id="jdoe")]
        tool = _get_check_enrollment_tool()
        out = await tool(course_identifier="BADM 350", net_id="jdoe")
        assert out.startswith("YES —")


# --------------------------------------------------------------------------
# Institution-neutral identifiers (issue #199)
#
# The matcher assumed ``login_id`` is the bare campus ID — true at UIUC
# (measured live: 7-8 char NetIDs), NOT a Canvas guarantee. Instances that
# provision Canvas logins from email addresses store ``login_id`` as
# ``uniqname@umich.edu``, so an exact-equality match against ``uniqname``
# silently failed and the tool reported a confident, wrong NO.
# --------------------------------------------------------------------------


class TestEmailStyleIdentifiers:
    def test_bare_needle_matches_email_style_login_id(self):
        """UMich shape: login_id is the full email, caller passes the uniqname."""
        roster = [_enr(login_id="zqian@umich.edu")]
        match = _match_enrollment(roster, "zqian", active_only=True)
        assert match is not None, "bare uniqname must match an email-style login_id"
        assert match[1] == "login_id"

    def test_email_needle_matches_bare_login_id(self):
        """The inverse: caller pastes an email, Canvas stores the bare ID."""
        roster = [_enr(login_id="jdoe")]
        match = _match_enrollment(roster, "jdoe@illinois.edu", active_only=True)
        assert match is not None
        assert match[1] == "login_id"

    def test_exact_match_wins_over_local_part_match(self):
        """Two users sharing a local part must not be confused for each other."""
        roster = [_enr(login_id="jdoe@other.edu"), _enr(login_id="jdoe")]
        match = _match_enrollment(roster, "jdoe", active_only=True)
        assert match is not None
        assert match[0]["user"]["login_id"] == "jdoe"

    def test_local_part_match_applies_to_sis_user_id_too(self):
        roster = [_enr(login_id=None, sis="zqian@umich.edu")]
        match = _match_enrollment(roster, "zqian", active_only=True)
        assert match is not None
        assert match[1] == "sis_user_id"

    def test_unrelated_identifier_still_does_not_match(self):
        roster = [_enr(login_id="alice@umich.edu")]
        assert _match_enrollment(roster, "bob", active_only=True) is None


class TestLocalPartMatchIsNotOverEager:
    """Local-part fallback must never manufacture a confident wrong YES.

    This tool is documented as an external access gate, so a false positive is
    an authorization defect, not a cosmetic one.
    """

    def test_two_fully_qualified_addresses_never_match_across_domains(self):
        """jdoe@school.edu and jdoe@other.edu are different people."""
        roster = [_enr(login_id="jdoe@other.edu")]
        assert _match_enrollment(roster, "jdoe@school.edu", active_only=True) is None

    def test_bare_needle_against_two_domains_is_ambiguous_not_a_guess(self):
        """Picking the first of several candidates would be roster-order luck."""
        roster = [
            _enr(login_id="jdoe@a.edu", uid=1),
            _enr(login_id="jdoe@b.edu", uid=2),
        ]
        with pytest.raises(AmbiguousIdentifier):
            _match_enrollment(roster, "jdoe", active_only=True)

    def test_one_user_holding_two_enrollments_is_not_ambiguous(self):
        """Ambiguity is about distinct PEOPLE, not distinct enrollment rows."""
        roster = [
            _enr(login_id="jdoe@a.edu", etype="TeacherEnrollment", uid=7),
            _enr(login_id="jdoe@a.edu", etype="DesignerEnrollment", uid=7),
        ]
        match = _match_enrollment(roster, "jdoe", active_only=True)
        assert match is not None
        assert match[0]["user"]["id"] == 7

    def test_exact_match_beats_an_otherwise_ambiguous_roster(self):
        """An unambiguous exact hit must not be spoiled by local-part noise."""
        roster = [
            _enr(login_id="jdoe@a.edu", uid=1),
            _enr(login_id="jdoe@b.edu", uid=2),
            _enr(login_id="jdoe", uid=3),
        ]
        match = _match_enrollment(roster, "jdoe", active_only=True)
        assert match is not None
        assert match[0]["user"]["id"] == 3

    @pytest.mark.asyncio
    async def test_tool_reports_ambiguity_without_ever_saying_yes_or_no(
        self, mock_course_id, mock_request
    ):
        mock_request.return_value = [
            _enr(login_id="jdoe@a.edu", uid=1),
            _enr(login_id="jdoe@b.edu", uid=2),
        ]
        tool = _get_check_enrollment_tool()
        out = await tool(course_identifier="505", net_id="jdoe")
        assert "AMBIGUOUS" in out
        assert not out.startswith("YES")
        assert not out.startswith("NO")

    @pytest.mark.asyncio
    async def test_email_form_identifier_is_accepted_not_rejected(
        self, mock_course_id, mock_request
    ):
        """``@`` used to fail the input guard before any Canvas call was made."""
        mock_request.return_value = [_enr(login_id="jdoe@illinois.edu")]
        result = await check_enrollment("BADM 350", "jdoe@illinois.edu")
        assert result.enrolled is True

    @pytest.mark.asyncio
    async def test_genuinely_malformed_identifier_is_still_rejected(
        self, mock_course_id, mock_request
    ):
        with pytest.raises(ValueError):
            await check_enrollment("BADM 350", "not a valid id!")
        mock_request.assert_not_called()


# --------------------------------------------------------------------------
# A role-scoped NO must say what the subject actually IS (issue #199)
#
# ``role`` defaults to "student". Asking about a teacher therefore produced
# "NO — <id> has no active 'student' enrollment", which reads as "not in the
# course" — the reporter's exact complaint. The subject's real role is already
# in the payload; withholding it turned a narrow true answer into a misleading
# broad one.
# --------------------------------------------------------------------------


class TestRoleScopedNegative:
    @pytest.mark.asyncio
    async def test_teacher_checked_as_student_reports_the_real_role(
        self, mock_course_id, mock_request
    ):
        mock_request.return_value = [
            _enr(login_id="zqian", etype="TeacherEnrollment", uid=42)
        ]
        result = await check_enrollment("505", "zqian", role="student")
        assert result.enrolled is False
        assert result.roles_held == ("TeacherEnrollment",)

    @pytest.mark.asyncio
    async def test_role_any_matches_a_teacher(self, mock_course_id, mock_request):
        mock_request.return_value = [
            _enr(login_id="zqian", etype="TeacherEnrollment", uid=42)
        ]
        result = await check_enrollment("505", "zqian", role="any")
        assert result.enrolled is True
        assert result.role == "TeacherEnrollment"

    @pytest.mark.asyncio
    async def test_multiple_roles_are_all_reported(self, mock_course_id, mock_request):
        mock_request.return_value = [
            _enr(login_id="zqian", etype="TeacherEnrollment", uid=42),
            _enr(login_id="zqian", etype="DesignerEnrollment", uid=42),
        ]
        result = await check_enrollment("505", "zqian", role="student")
        assert result.enrolled is False
        assert set(result.roles_held) == {"TeacherEnrollment", "DesignerEnrollment"}

    @pytest.mark.asyncio
    async def test_a_true_stranger_reports_no_roles(self, mock_course_id, mock_request):
        mock_request.return_value = [_enr(login_id="alice"), _enr(login_id="bob")]
        result = await check_enrollment("505", "carol", role="student")
        assert result.enrolled is False
        assert result.roles_held == ()

    @pytest.mark.asyncio
    async def test_role_filter_is_not_pushed_to_canvas(
        self, mock_course_id, mock_request
    ):
        """The whole roster must be fetched, or the other roles are invisible."""
        mock_request.return_value = []
        await check_enrollment("505", "zqian", role="student")
        params = mock_request.await_args.kwargs["params"]
        assert "type[]" not in params

    @pytest.mark.asyncio
    async def test_tool_message_names_the_role_actually_held(
        self, mock_course_id, mock_request
    ):
        mock_request.return_value = [
            _enr(login_id="zqian", etype="TeacherEnrollment", uid=42)
        ]
        tool = _get_check_enrollment_tool()
        out = await tool(course_identifier="505", net_id="zqian", role="student")
        assert out.startswith("NO —")
        assert "TeacherEnrollment" in out, (
            "a role-scoped NO must disclose the role the subject does hold, "
            "otherwise it reads as 'not in the course'"
        )

    @pytest.mark.asyncio
    async def test_tool_message_for_a_true_stranger_has_no_role_clause(
        self, mock_course_id, mock_request
    ):
        mock_request.return_value = [_enr(login_id="alice")]
        tool = _get_check_enrollment_tool()
        out = await tool(course_identifier="505", net_id="carol", role="student")
        assert out.startswith("NO —")
        assert "Enrollment" not in out
