"""Tests for the enrollment-check capability (core + matcher)."""

from unittest.mock import AsyncMock, patch

import pytest

from canvas_mcp.core.enrollment import (
    EnrollmentResult,
    _match_enrollment,
    check_enrollment,
)


def _enr(login_id=None, sis=None, state="active", etype="StudentEnrollment"):
    return {
        "enrollment_state": state,
        "type": etype,
        "user": {"login_id": login_id, "sis_user_id": sis},
    }


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
