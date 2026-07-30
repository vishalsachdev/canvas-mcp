"""Tests for the caller-scoped identity tools (issue #171).

These tools exist because ``check_enrollment`` cannot answer "am I enrolled?"
with a student's own token — Canvas withholds the roster identifier fields. They
must therefore work with NO roster permission, and must never be corrupted by
the anonymizer (a caller told their own name is ``Student_<hash>`` is worse than
no answer at all).
"""

import os
from unittest.mock import AsyncMock, patch

import pytest

from canvas_mcp.core.config import reset_config
from canvas_mcp.tools.self_identity import _own_roles


def get_tool_function(tool_name: str):
    """Capture a registered self-identity tool coroutine by name."""
    from fastmcp import FastMCP

    from canvas_mcp.tools.self_identity import register_self_identity_tools

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
    register_self_identity_tools(mcp)
    return captured.get(tool_name)


def _course(cid=101, code="BADM 350", name="Intro", enrollments=None):
    """A /courses record shaped as Canvas returns it.

    Note the short/long form split that the implementation must not mix:
    ``type`` is lowercase short form, ``role`` is the long form.
    """
    course = {"id": cid, "course_code": code, "name": name}
    course["enrollments"] = (
        [] if enrollments is None else enrollments
    )
    return course


def _enrollment(short="student", long_="StudentEnrollment", state="active"):
    return {
        "type": short,
        "role": long_,
        "role_id": 3,
        "enrollment_state": state,
    }


# --------------------------------------------------------------------------
# _own_roles (pure)
# --------------------------------------------------------------------------


class TestOwnRoles:
    def test_reports_long_form_role(self):
        course = _course(enrollments=[_enrollment()])
        assert _own_roles(course) == ["StudentEnrollment"]

    def test_empty_enrollments_array_does_not_raise(self):
        assert _own_roles(_course(enrollments=[])) == []

    def test_missing_enrollments_key_does_not_raise(self):
        assert _own_roles({"id": 1}) == []

    def test_null_enrollments_does_not_raise(self):
        assert _own_roles({"id": 1, "enrollments": None}) == []

    def test_two_enrollments_in_one_course_reports_both(self):
        course = _course(
            enrollments=[
                _enrollment("ta", "TaEnrollment"),
                _enrollment("student", "StudentEnrollment"),
            ]
        )
        assert _own_roles(course) == ["TaEnrollment", "StudentEnrollment"]

    def test_duplicate_roles_are_deduplicated(self):
        course = _course(enrollments=[_enrollment(), _enrollment()])
        assert _own_roles(course) == ["StudentEnrollment"]

    def test_falls_back_to_short_type_when_role_absent(self):
        course = _course(enrollments=[{"type": "teacher"}])
        assert _own_roles(course) == ["teacher"]

    def test_ignores_non_dict_entries(self):
        course = _course(enrollments=["nonsense", _enrollment()])
        assert _own_roles(course) == ["StudentEnrollment"]


# --------------------------------------------------------------------------
# get_my_enrollments
# --------------------------------------------------------------------------


class TestGetMyEnrollments:
    @staticmethod
    async def _call(return_value, **kwargs):
        with patch(
            "canvas_mcp.tools.self_identity.fetch_all_paginated_results",
            new_callable=AsyncMock,
        ) as mock_fetch:
            mock_fetch.return_value = return_value
            tool = get_tool_function("get_my_enrollments")
            result = await tool(**kwargs)
        return result, mock_fetch

    @pytest.mark.asyncio
    async def test_happy_path_lists_course_and_role(self):
        result, _ = await self._call(
            [_course(enrollments=[_enrollment()])]
        )
        assert "BADM 350" in result
        assert "Intro" in result
        assert "101" in result
        assert "StudentEnrollment" in result

    @pytest.mark.asyncio
    async def test_uses_courses_endpoint_with_expected_params(self):
        _, mock_fetch = await self._call([_course(enrollments=[_enrollment()])])
        endpoint, params = mock_fetch.call_args[0][:2]
        assert endpoint == "/courses"
        assert params["enrollment_state"] == "active"
        assert params["state[]"] == ["available"]
        assert params["include[]"] == ["term"]
        assert params["per_page"] == 100

    @pytest.mark.asyncio
    async def test_include_concluded_widens_both_filters(self):
        """Both filters must widen together or the flag silently does nothing.

        Broadening the course `state[]` while leaving `enrollment_state` pinned
        to "active" means Canvas still drops every completed enrollment, so a
        caller asking for concluded history would get only active courses back
        and have no way to tell.
        """
        _, mock_fetch = await self._call(
            [_course(enrollments=[_enrollment()])], include_concluded=True
        )
        params = mock_fetch.call_args[0][1]
        assert params["state[]"] == ["available", "completed"]
        assert params["enrollment_state"] == ["active", "completed"]

    @pytest.mark.asyncio
    async def test_default_run_keeps_enrollment_state_active(self):
        _, mock_fetch = await self._call([_course(enrollments=[_enrollment()])])
        params = mock_fetch.call_args[0][1]
        assert params["enrollment_state"] == "active"

    @pytest.mark.asyncio
    async def test_default_scope_is_stated_explicitly(self):
        result, _ = await self._call([_course(enrollments=[_enrollment()])])
        assert "active enrollments" in result
        assert "include_concluded" in result

    @pytest.mark.asyncio
    async def test_concluded_run_omits_the_scope_note(self):
        result, _ = await self._call(
            [_course(enrollments=[_enrollment()])], include_concluded=True
        )
        assert "include_concluded" not in result

    @pytest.mark.asyncio
    async def test_no_courses_gives_an_explicit_message(self):
        result, _ = await self._call([])
        assert "no active course enrollments" in result.lower()

    @pytest.mark.asyncio
    async def test_empty_enrollments_array_does_not_indexerror(self):
        """A course with enrollments: [] must degrade, not crash."""
        result, _ = await self._call([_course(enrollments=[])])
        assert "BADM 350" in result
        assert "no enrollment reported" in result

    @pytest.mark.asyncio
    async def test_two_roles_in_one_course_both_reported(self):
        result, _ = await self._call(
            [
                _course(
                    enrollments=[
                        _enrollment("ta", "TaEnrollment"),
                        _enrollment("student", "StudentEnrollment"),
                    ]
                )
            ]
        )
        assert "TaEnrollment" in result
        assert "StudentEnrollment" in result

    @pytest.mark.asyncio
    async def test_canvas_error_is_surfaced(self):
        result, _ = await self._call({"error": "401 Unauthorized"})
        assert "Error fetching your enrollments" in result
        assert "401" in result


# --------------------------------------------------------------------------
# get_my_profile
# --------------------------------------------------------------------------


class TestGetMyProfile:
    @staticmethod
    async def _call(return_value):
        with patch(
            "canvas_mcp.tools.self_identity.make_canvas_request",
            new_callable=AsyncMock,
        ) as mock_request:
            mock_request.return_value = return_value
            tool = get_tool_function("get_my_profile")
            result = await tool()
        return result, mock_request

    PROFILE = {
        "id": 4242,
        "name": "Jane Doe",
        "login_id": "jdoe",
        "primary_email": "jdoe@illinois.edu",
        "sis_user_id": "999888777",
    }

    @pytest.mark.asyncio
    async def test_happy_path_reports_id_name_login(self):
        result, mock_request = await self._call(self.PROFILE)
        assert "4242" in result
        assert "Jane Doe" in result
        assert "jdoe" in result
        assert mock_request.call_args[0][1] == "/users/self/profile"

    @pytest.mark.asyncio
    async def test_email_and_sis_id_are_deliberately_omitted(self):
        result, _ = await self._call(self.PROFILE)
        assert "jdoe@illinois.edu" not in result
        assert "999888777" not in result

    @pytest.mark.asyncio
    async def test_canvas_error_is_surfaced(self):
        result, _ = await self._call({"error": "401 Unauthorized"})
        assert "Error fetching your profile" in result
        assert "401" in result

    @pytest.mark.asyncio
    async def test_unexpected_shape_does_not_crash(self):
        result, _ = await self._call([])
        assert "Error fetching your profile" in result

    @pytest.mark.asyncio
    async def test_missing_fields_degrade_to_na(self):
        result, _ = await self._call({"id": 1})
        assert "N/A" in result


# --------------------------------------------------------------------------
# The anonymizer must NOT rewrite the caller's own identity (#171 item 4)
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_my_profile_returns_real_name_with_anonymization_on():
    """End-to-end through make_canvas_request with anonymization ENABLED.

    Without the /users/self/profile carve-out in _should_anonymize_endpoint the
    caller is told their own name is "Student_<hash>". This is the test that
    fails if that allowlist is removed.
    """
    payload = {
        "id": 4242,
        "name": "Jane Doe",
        "login_id": "jdoe",
        "primary_email": "jdoe@illinois.edu",
    }

    class _Resp:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return dict(payload)

    class _Client:
        is_closed = False

        async def get(self, url, params=None):
            return _Resp()

        async def aclose(self):
            return None

    with patch.dict(
        os.environ,
        {
            "ENABLE_DATA_ANONYMIZATION": "true",
            "CANVAS_API_TOKEN": "test-token",
            "CANVAS_API_URL": "https://canvas.example.edu/api/v1",
        },
        clear=False,
    ):
        reset_config()
        with patch(
            "canvas_mcp.core.client._get_http_client", return_value=_Client()
        ):
            tool = get_tool_function("get_my_profile")
            result = await tool()
        reset_config()

    assert "Jane Doe" in result
    assert "Student_" not in result
