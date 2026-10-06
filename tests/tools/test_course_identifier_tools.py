"""Course codes with spaces work in the file tools and the upstream tools.

Course codes often contain spaces (``COMPSCI 161``). The file tools
(read_course_file, download_course_file,
list_course_files) resolve through ``resolve_numeric_course_id``: the code is
found in the caller's course list and only the numeric ID reaches a request
path; anything that resolves to no course is refused with ``Could not find
course`` before any file request. Other tools resolve through
``get_course_id``, which now also looks a code up in the course list on a miss.

Every test runs the real resolver on a cold course cache; only the Canvas
boundary is replaced.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from fastmcp import FastMCP

CACHE = "canvas_mcp.core.cache"
FILES = "canvas_mcp.tools.files"
STUDENT = "canvas_mcp.tools.student_tools"

MY_COURSES = [{"id": 4242, "course_code": "COMPSCI 161",
               "name": "Design and Analysis of Algorithms"}]
NOT_FOUND = {"error": "HTTP error: 404, Details: not found"}


def capture(register: Callable[[FastMCP], None]) -> dict[str, Any]:
    mcp = FastMCP("test")
    captured: dict[str, Any] = {}
    original_tool = mcp.tool

    def capturing_tool(*args: Any, **kwargs: Any) -> Any:
        decorator = original_tool(*args, **kwargs)

        def wrapper(fn: Any) -> Any:
            captured[fn.__name__] = fn
            return decorator(fn)

        return wrapper

    mcp.tool = capturing_tool  # type: ignore[method-assign]
    register(mcp)
    return captured


def file_tools() -> dict[str, Any]:
    from canvas_mcp.tools.files import register_shared_file_tools

    return capture(register_shared_file_tools)


class Canvas:
    """The course list for the resolver, and a record of every other request."""

    def __init__(self) -> None:
        self.course_list_reads = 0
        self.cache_gets: list[str] = []
        self.paths: list[str] = []

    async def course_list(self, endpoint: str, params: Any = None, **_: Any) -> Any:
        assert endpoint == "/courses", endpoint
        self.course_list_reads += 1
        return MY_COURSES

    async def cache_get(self, method: str, endpoint: str, **_: Any) -> Any:
        self.cache_gets.append(endpoint)
        return NOT_FOUND

    async def request(self, method: str, endpoint: str, *args: Any, **_: Any) -> Any:
        self.paths.append(endpoint)
        return NOT_FOUND

    async def paginate(self, endpoint: str, *args: Any, **_: Any) -> Any:
        self.paths.append(endpoint)
        return []


@pytest.fixture
def canvas():
    fake = Canvas()
    with patch(f"{CACHE}.fetch_all_paginated_results", new=fake.course_list), \
         patch(f"{CACHE}.make_canvas_request", new=fake.cache_get), \
         patch(f"{FILES}.make_canvas_request", new=fake.request), \
         patch(f"{FILES}.fetch_all_paginated_results", new=fake.paginate), \
         patch(f"{FILES}.get_course_code", new=AsyncMock(return_value="COMPSCI 161")), \
         patch(f"{STUDENT}.fetch_all_paginated_results", new=fake.paginate), \
         patch(f"{STUDENT}.get_course_code", new=AsyncMock(return_value="COMPSCI 161")):
        yield fake


async def call_file_tool(name: str, identifier: str, tmp_path: Any) -> Any:
    tool = file_tools()[name]
    if name == "list_course_files":
        return await tool(course_identifier=identifier)
    if name == "download_course_file":
        return await tool(course_identifier=identifier, file_id=1, save_directory=str(tmp_path))
    return await tool(course_identifier=identifier, file_id=1)


FILE_TOOL_PATHS = {
    "read_course_file": "/courses/4242/files/1",
    "download_course_file": "/courses/4242/files/1",
    "list_course_files": "/courses/4242/files",
}


class TestFileToolsResolveCourseCodes:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("name", sorted(FILE_TOOL_PATHS))
    @pytest.mark.parametrize("identifier", ["COMPSCI 161", "  compsci 161 ",
                                            "Design and Analysis of Algorithms"])
    async def test_code_with_spaces_on_a_cold_cache(self, canvas, tmp_path, name, identifier):
        await call_file_tool(name, identifier, tmp_path)
        assert canvas.course_list_reads == 1
        assert canvas.paths[0] == FILE_TOOL_PATHS[name]
        assert not any("compsci" in path.lower() or "design" in path.lower()
                       for path in canvas.paths)
        assert list(tmp_path.iterdir()) == []

    @pytest.mark.asyncio
    @pytest.mark.parametrize("name", sorted(FILE_TOOL_PATHS))
    @pytest.mark.parametrize("identifier", [
        "MATH 2B", "1/users/503", "../accounts/1", "1?as_user_id=2", "badm_350",
    ])
    async def test_unknown_or_path_shaped_course_is_refused_before_any_file_request(
        self, canvas, tmp_path, name, identifier
    ):
        result = await call_file_tool(name, identifier, tmp_path)
        assert isinstance(result, str)
        assert result.startswith(f"Error: Could not find course {identifier}")
        assert canvas.paths == []
        assert canvas.cache_gets == []
        assert list(tmp_path.iterdir()) == []

    @pytest.mark.asyncio
    @pytest.mark.parametrize("name", sorted(FILE_TOOL_PATHS))
    @pytest.mark.parametrize("identifier", [
        "sis_course_id:x/../../users/self", "sis_course_id:a\\b", "sis_course_id:x?as_user_id=1",
        "sis_course_id:a b",
    ])
    async def test_path_shaped_sis_form_makes_no_request_at_all(
        self, canvas, tmp_path, name, identifier
    ):
        result = await call_file_tool(name, identifier, tmp_path)
        assert isinstance(result, str)
        assert result.startswith("Error: Could not find course sis_course_id:")
        assert canvas.paths == [] and canvas.cache_gets == []
        assert canvas.course_list_reads == 0

    @pytest.mark.asyncio
    @pytest.mark.parametrize("name", sorted(FILE_TOOL_PATHS))
    async def test_numeric_id_is_used_without_a_course_list_read(self, canvas, tmp_path, name):
        await call_file_tool(name, "4242", tmp_path)
        assert canvas.course_list_reads == 0
        assert canvas.paths[0] == FILE_TOOL_PATHS[name]


class TestUpstreamToolsThroughGetCourseId:
    """get_my_submission_status is an upstream tool on get_course_id."""

    @staticmethod
    def tool() -> Any:
        from canvas_mcp.tools.student_tools import register_student_tools

        return capture(register_student_tools)["get_my_submission_status"]

    @pytest.mark.asyncio
    @pytest.mark.parametrize("identifier", ["COMPSCI 161", " compsci 161 "])
    async def test_code_with_spaces_on_a_cold_cache(self, canvas, identifier):
        result = await self.tool()(course_identifier=identifier)
        assert not result.startswith("Error"), result
        assert canvas.course_list_reads == 1
        assert canvas.paths == ["/courses/4242/assignments"]
