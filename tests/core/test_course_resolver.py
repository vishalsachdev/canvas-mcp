"""Unit tests for the shared course resolver, ``resolve_numeric_course_id``.

The requirement (not the implementation) drives every assertion: a course
identifier is either resolved to the numeric Canvas course ID or refused with a
``Could not find course`` error, and an identifier that has not been validated
as a single plain SIS segment is never put in a request path. Course codes
often contain spaces (``COMPSCI 161``, ``I&C SCI 33``), so they must resolve too.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from canvas_mcp.core import cache
from canvas_mcp.core.cache import resolve_numeric_course_id

COURSES = [
    {"id": 4242, "course_code": "COMPSCI 161", "name": "Design and Analysis of Algorithms"},
    {"id": 5151, "course_code": "I&C SCI 33", "name": "Intermediate Programming",
     "sis_course_id": "2026F-ICS33"},
    {"id": 7070, "course_code": "badm_554_120251_246794", "name": "Business Analytics"},
]


class FakeCanvas:
    """Records every request; serves the course list and SIS lookups."""

    def __init__(
        self,
        courses: list[dict[str, Any]] | dict[str, Any] | None = None,
        sis: dict[str, Any] | None = None,
    ) -> None:
        self.courses = COURSES if courses is None else courses
        self.sis = sis or {}
        self.requests: list[tuple[str, str]] = []

    async def paginate(self, endpoint: str, params: dict[str, Any] | None = None, **_: Any) -> Any:
        self.requests.append(("paginate", endpoint))
        assert endpoint == "/courses", f"unexpected list {endpoint}"
        return self.courses

    async def request(self, method: str, endpoint: str, **_: Any) -> Any:
        self.requests.append((method, endpoint))
        assert method == "get"
        if endpoint in self.sis:
            return self.sis[endpoint]
        return {"error": "HTTP error: 404, Details: not found"}

    @property
    def list_reads(self) -> int:
        return self.requests.count(("paginate", "/courses"))

    def paths(self) -> list[str]:
        return [endpoint for _, endpoint in self.requests]


@pytest.fixture
def canvas(monkeypatch: pytest.MonkeyPatch) -> FakeCanvas:
    fake = FakeCanvas()
    monkeypatch.setattr(cache, "fetch_all_paginated_results", fake.paginate)
    monkeypatch.setattr(cache, "make_canvas_request", fake.request)
    return fake


def warm(courses: list[dict[str, Any]]) -> None:
    """Fill the cache as a previous refresh would have."""
    cache.course_records_cache[:] = cache.course_records(courses)
    for course in courses:
        cache.course_code_to_id_cache[course["course_code"]] = str(course["id"])
        cache.id_to_course_code_cache[str(course["id"])] = course["course_code"]


class TestNumeric:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(("identifier", "expected"), [
        (4242, "4242"), ("4242", "4242"), (" 4242 ", "4242"), ("007", "007"),
    ])
    async def test_numeric_id_is_returned_without_a_request(self, canvas, identifier, expected):
        assert await resolve_numeric_course_id(identifier) == (expected, None)
        assert canvas.requests == []


class TestCourseCodes:
    @pytest.mark.asyncio
    async def test_code_with_spaces_on_a_cold_cache(self, canvas):
        assert await resolve_numeric_course_id("COMPSCI 161") == ("4242", None)
        assert canvas.requests == [("paginate", "/courses")]

    @pytest.mark.asyncio
    async def test_code_with_ampersand_and_spaces(self, canvas):
        assert await resolve_numeric_course_id("I&C SCI 33") == ("5151", None)

    @pytest.mark.asyncio
    async def test_code_with_spaces_on_a_warm_cache_makes_no_request(self, canvas):
        warm(COURSES)
        assert await resolve_numeric_course_id("COMPSCI 161") == ("4242", None)
        assert canvas.requests == []

    @pytest.mark.asyncio
    async def test_code_missing_from_a_warm_cache_refreshes_once(self, canvas):
        warm([{"id": 1, "course_code": "OLD 1"}])
        assert await resolve_numeric_course_id("COMPSCI 161") == ("4242", None)
        assert canvas.list_reads == 1

    @pytest.mark.asyncio
    async def test_second_lookup_uses_the_refreshed_cache(self, canvas):
        await resolve_numeric_course_id("COMPSCI 161")
        assert await resolve_numeric_course_id("I&C SCI 33") == ("5151", None)
        assert canvas.list_reads == 1

    @pytest.mark.asyncio
    @pytest.mark.parametrize("identifier", ["compsci 161", "  COMPSCI 161\t", "CompSci 161"])
    async def test_case_and_surrounding_whitespace_are_ignored(self, canvas, identifier):
        assert await resolve_numeric_course_id(identifier) == ("4242", None)

    @pytest.mark.asyncio
    async def test_course_name_matches(self, canvas):
        assert await resolve_numeric_course_id("design and analysis of algorithms") == ("4242", None)

    @pytest.mark.asyncio
    async def test_bare_sis_id_matches_from_the_course_list(self, canvas):
        assert await resolve_numeric_course_id("2026f-ics33") == ("5151", None)
        assert ("get", "/courses/2026f-ics33") not in canvas.requests

    @pytest.mark.asyncio
    async def test_underscore_code_on_a_cold_cache(self, canvas):
        assert await resolve_numeric_course_id("badm_554_120251_246794") == ("7070", None)
        assert canvas.requests == [("paginate", "/courses")]

    @pytest.mark.asyncio
    async def test_underscore_code_missing_from_a_warm_cache_is_not_turned_into_a_sis_lookup(
        self, canvas
    ):
        """get_course_id would return sis_course_id:<code> here; the resolver
        refreshes and finds the course instead."""
        warm([{"id": 1, "course_code": "old_course_1"}])
        assert await resolve_numeric_course_id("badm_554_120251_246794") == ("7070", None)
        assert not any(path.startswith("/courses/") for path in canvas.paths())

    @pytest.mark.asyncio
    @pytest.mark.parametrize(("other", "identifier"), [
        ({"id": 2, "course_code": "COMPSCI 161", "name": "Algorithms"}, "Algorithms"),
        ({"id": 2, "course_code": "STATS 8", "name": "stats 7"}, "Stats 7"),
        ({"id": 2, "course_code": "STATS 8", "sis_course_id": "STATS 7"}, "stats 7"),
    ])
    async def test_value_naming_different_courses_under_different_aliases_is_refused(
        self, canvas, other, identifier
    ):
        """One course's code that is another's name or SIS ID is ambiguous; a
        write tool must not silently pick the code's course."""
        first_code = "Algorithms" if identifier == "Algorithms" else "STATS 7"
        canvas.courses = [{"id": 1, "course_code": first_code, "name": "Intro"}, other]
        course_id, error = await resolve_numeric_course_id(identifier)
        assert course_id is None
        assert error is not None and error.startswith(f"Could not find course {identifier}")
        assert "IDs 1, 2" in error and "numeric" in error

    @pytest.mark.asyncio
    async def test_one_course_matching_under_several_aliases_is_not_ambiguous(self, canvas):
        canvas.courses = [{"id": 4242, "course_code": "COMPSCI 161", "name": "COMPSCI 161",
                           "sis_course_id": "compsci 161"}]
        assert await resolve_numeric_course_id("COMPSCI 161") == ("4242", None)

    @pytest.mark.asyncio
    async def test_ambiguous_code_is_refused_with_the_candidates(self, canvas):
        canvas.courses = [
            {"id": 11, "course_code": "COMPSCI 161", "name": "Fall"},
            {"id": 22, "course_code": "COMPSCI 161", "name": "Winter"},
        ]
        course_id, error = await resolve_numeric_course_id("COMPSCI 161")
        assert course_id is None
        assert error is not None and error.startswith("Could not find course COMPSCI 161")
        assert "11" in error and "22" in error and "numeric" in error


class TestUnknown:
    @pytest.mark.asyncio
    async def test_unknown_code_is_refused_after_one_refresh(self, canvas):
        course_id, error = await resolve_numeric_course_id("MATH 2B")
        assert course_id is None
        assert error is not None and error.startswith("Could not find course MATH 2B")
        assert canvas.requests == [("paginate", "/courses")]

    @pytest.mark.asyncio
    @pytest.mark.parametrize("identifier", ["", "   "])
    async def test_blank_is_refused_without_a_request(self, canvas, identifier):
        course_id, error = await resolve_numeric_course_id(identifier)
        assert course_id is None and error is not None
        assert error.startswith("Could not find course")
        assert canvas.requests == []

    @pytest.mark.asyncio
    async def test_course_list_failure_is_reported(self, canvas):
        canvas.courses = {"error": "HTTP error: 500"}
        course_id, error = await resolve_numeric_course_id("COMPSCI 161")
        assert course_id is None
        assert error is not None and error.startswith("Could not find course COMPSCI 161")
        assert "could not be loaded" in error

    @pytest.mark.asyncio
    @pytest.mark.parametrize("identifier", [
        "101/assignments/4242", "../accounts/1", "1?as_user_id=2", "1#x", "a\\b", "50%2F1",
        "-5", "course_4242",
    ])
    async def test_path_shaped_identifier_only_reads_the_course_list(self, canvas, identifier):
        course_id, error = await resolve_numeric_course_id(identifier)
        assert course_id is None
        assert error is not None and error.startswith("Could not find course")
        assert canvas.requests == [("paginate", "/courses")]


class TestSisForm:
    @pytest.mark.asyncio
    async def test_valid_sis_form_is_looked_up_by_canvas(self, canvas):
        canvas.sis["/courses/sis_course_id:2026F-ICS33"] = {"id": 5151, "course_code": "I&C SCI 33"}
        assert await resolve_numeric_course_id("sis_course_id:2026F-ICS33") == ("5151", None)
        assert canvas.requests == [("get", "/courses/sis_course_id:2026F-ICS33")]

    @pytest.mark.asyncio
    async def test_surrounding_whitespace_is_trimmed_before_the_lookup(self, canvas):
        canvas.sis["/courses/sis_course_id:CS161.F26"] = {"id": 4242}
        assert await resolve_numeric_course_id("  sis_course_id:CS161.F26 ") == ("4242", None)

    @pytest.mark.asyncio
    async def test_unknown_sis_id_is_refused(self, canvas):
        course_id, error = await resolve_numeric_course_id("sis_course_id:NOPE")
        assert course_id is None
        assert error is not None and error.startswith("Could not find course sis_course_id:NOPE")
        assert canvas.requests == [("get", "/courses/sis_course_id:NOPE")]

    @pytest.mark.asyncio
    async def test_sis_lookup_without_a_numeric_id_is_refused(self, canvas):
        canvas.sis["/courses/sis_course_id:X"] = {"id": "x/1"}
        course_id, error = await resolve_numeric_course_id("sis_course_id:X")
        assert course_id is None and error is not None

    @pytest.mark.asyncio
    @pytest.mark.parametrize("identifier", [
        "sis_course_id:", "sis_course_id:   ", "sis_course_id:x/users", "sis_course_id:x\\users",
        "sis_course_id:x?as_user_id=1", "sis_course_id:x#frag", "sis_course_id:x%2Fusers",
        "sis_course_id:..", "sis_course_id:a..b", "sis_course_id:a b", "sis_course_id:a\nb",
        "sis_course_id:a\x00b",
    ])
    async def test_path_shaped_sis_form_makes_no_request(self, canvas, identifier):
        course_id, error = await resolve_numeric_course_id(identifier)
        assert course_id is None
        assert error is not None and error.startswith("Could not find course")
        assert canvas.requests == []


class TestCandidateCourses:
    """``courses=`` restricts code/name matching to the given list (no refresh)."""

    @pytest.mark.asyncio
    async def test_matches_only_the_given_courses(self, canvas):
        given = [{"id": 9, "course_code": "MATH 2B"}]
        assert await resolve_numeric_course_id("math 2b", courses=given) == ("9", None)
        course_id, error = await resolve_numeric_course_id("COMPSCI 161", courses=given)
        assert course_id is None and error is not None
        assert canvas.requests == []

    @pytest.mark.asyncio
    async def test_numeric_ids_are_not_restricted(self, canvas):
        assert await resolve_numeric_course_id("4242", courses=[]) == ("4242", None)


class TestForeignCourseInTheCodeCache:
    """get_course_code caches courses outside the caller's list (a past course
    looked up by numeric ID). Codes are often reused every term, so such a course
    must not make the caller's own course ambiguous or take it over."""

    @pytest.mark.asyncio
    async def test_foreign_course_with_the_same_code_does_not_make_it_ambiguous(self, canvas):
        canvas.courses = [{"id": 4242, "course_code": "COMPSCI 161"}]
        canvas.sis["/courses/999"] = {"id": 999, "course_code": "COMPSCI 161"}
        assert await resolve_numeric_course_id("COMPSCI 161") == ("4242", None)
        assert await cache.get_course_code("999") == "COMPSCI 161"
        canvas.requests.clear()

        assert await resolve_numeric_course_id("COMPSCI 161") == ("4242", None)
        assert await resolve_numeric_course_id("compsci 161") == ("4242", None)
        assert await cache.get_course_id("COMPSCI 161") == "4242"
        assert await cache.get_course_id("compsci 161") == "4242"
        assert canvas.requests == []

    @pytest.mark.asyncio
    async def test_foreign_course_looked_up_first_does_not_take_over_the_code(self, canvas):
        """get_course_code as the very first lookup reads the course list and
        then fetches the foreign course; the code still names the caller's."""
        canvas.courses = [{"id": 4242, "course_code": "COMPSCI 161"}]
        canvas.sis["/courses/999"] = {"id": 999, "course_code": "COMPSCI 161"}
        assert await cache.get_course_code("999") == "COMPSCI 161"
        assert await resolve_numeric_course_id("COMPSCI 161") == ("4242", None)
        assert await cache.get_course_id("COMPSCI 161") == "4242"


class TestRefreshRateLimit:
    """A miss re-reads /courses at most once per window, shared by
    concurrent callers, so garbage or a retried typo cannot page through the
    course list on every call."""

    @pytest.mark.asyncio
    async def test_back_to_back_misses_read_the_course_list_once(self, canvas):
        for identifier in ("MATH 2B", "Algorithms", "１２３", "1/users/503", "COMPSCI 161"):
            await resolve_numeric_course_id(identifier)
        assert canvas.list_reads == 1

    @pytest.mark.asyncio
    async def test_a_miss_after_the_window_reads_it_again(self, canvas, monkeypatch):
        await resolve_numeric_course_id("MATH 2B")
        monkeypatch.setattr(
            cache, "_last_refresh_at",
            cache._last_refresh_at - cache.REFRESH_ON_MISS_INTERVAL_SECONDS - 1,
        )
        canvas.courses = COURSES + [{"id": 8080, "course_code": "MATH 2B"}]
        assert await resolve_numeric_course_id("MATH 2B") == ("8080", None)
        assert canvas.list_reads == 2

    @pytest.mark.asyncio
    async def test_concurrent_misses_share_one_read(self, canvas, monkeypatch):
        gate = asyncio.Event()
        inner = canvas.paginate

        async def slow_paginate(endpoint: str, params: dict[str, Any] | None = None, **kw: Any):
            await gate.wait()
            return await inner(endpoint, params, **kw)

        monkeypatch.setattr(cache, "fetch_all_paginated_results", slow_paginate)
        lookups = asyncio.gather(
            resolve_numeric_course_id("COMPSCI 161"),
            resolve_numeric_course_id("I&C SCI 33"),
            cache.get_course_id("NOPE 1"),
        )
        await asyncio.sleep(0)
        gate.set()
        assert await lookups == [("4242", None), ("5151", None), "NOPE 1"]
        assert canvas.list_reads == 1

    @pytest.mark.asyncio
    async def test_a_failed_read_is_retried_on_the_next_miss(self, canvas):
        canvas.courses = {"error": "HTTP error: 500"}
        _, error = await resolve_numeric_course_id("COMPSCI 161")
        assert error is not None and "could not be loaded" in error
        canvas.courses = COURSES
        assert await resolve_numeric_course_id("COMPSCI 161") == ("4242", None)
        assert canvas.list_reads == 2


class TestSisFormOfAListedCourse:
    @pytest.mark.asyncio
    async def test_cached_sis_id_resolves_without_a_request(self, canvas):
        warm(COURSES)
        assert await resolve_numeric_course_id("sis_course_id:2026F-ICS33") == ("5151", None)
        assert canvas.requests == []

    @pytest.mark.asyncio
    async def test_cached_sis_id_with_a_space_resolves_without_a_request(self, canvas):
        """The token is never sent, so the path-segment rule does not apply."""
        warm([{"id": 6, "course_code": "PHYS 7C", "sis_course_id": "2026F PHYS 7C"}])
        assert await resolve_numeric_course_id("sis_course_id:2026F PHYS 7C") == ("6", None)
        assert canvas.requests == []

    @pytest.mark.asyncio
    async def test_given_courses_are_matched_by_sis_form(self, canvas):
        given = [{"id": 9, "course_code": "MATH 2B", "sis_course_id": "M 2B"}]
        assert await resolve_numeric_course_id("sis_course_id:M 2B", courses=given) == ("9", None)
        assert canvas.requests == []


class TestGetCourseIdLooksUpOnMiss:
    """Upstream tools resolve through get_course_id; a code with spaces must
    work there too, and its fallback for unknown identifiers is unchanged."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("identifier", ["COMPSCI 161", " compsci 161 ",
                                            "Design and Analysis of Algorithms", "2026F-ICS33"])
    async def test_code_name_or_sis_id_on_a_cold_cache(self, canvas, identifier):
        expected = "5151" if identifier == "2026F-ICS33" else "4242"
        assert await cache.get_course_id(identifier) == expected
        assert canvas.requests == [("paginate", "/courses")]

    @pytest.mark.asyncio
    async def test_code_missing_from_a_warm_cache_is_found_after_a_refresh(self, canvas):
        warm([{"id": 1, "course_code": "OLD 1"}])
        assert await cache.get_course_id("I&C SCI 33") == "5151"
        assert canvas.list_reads == 1

    @pytest.mark.asyncio
    @pytest.mark.parametrize(("identifier", "fallback"), [
        ("MATH 2B", "MATH 2B"),
        ("no_such_course", "sis_course_id:no_such_course"),
    ])
    async def test_unknown_identifier_keeps_the_upstream_fallback(self, canvas, identifier, fallback):
        assert await cache.get_course_id(identifier) == fallback
        assert canvas.requests == [("paginate", "/courses")]

    @pytest.mark.asyncio
    async def test_unknown_identifier_on_a_failed_course_list_keeps_the_fallback(self, canvas):
        canvas.courses = {"error": "HTTP error: 500"}
        assert await cache.get_course_id("no_such_course") == "sis_course_id:no_such_course"

    @pytest.mark.asyncio
    @pytest.mark.parametrize("identifier", ["4242", 4242, "sis_course_id:anything"])
    async def test_numeric_and_sis_forms_are_unchanged_without_a_request(self, canvas, identifier):
        assert await cache.get_course_id(identifier) == str(identifier)
        assert canvas.requests == []

    @pytest.mark.asyncio
    async def test_ambiguous_code_falls_back_without_a_second_read(self, canvas):
        canvas.courses = [{"id": 11, "course_code": "COMPSCI 161", "name": "Fall"},
                          {"id": 22, "course_code": "compsci 161", "name": "Winter"}]
        assert await cache.get_course_id("Compsci 161") == "Compsci 161"
        assert canvas.list_reads == 1
