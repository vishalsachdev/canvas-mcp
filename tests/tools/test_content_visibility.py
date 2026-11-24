"""Student-visible content survives unknown publication fields and HTML previews."""
import json
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from canvas_mcp.tools import courses, modules


class CaptureTools:
    def __init__(self) -> None:
        self.functions: dict[str, Any] = {}

    def tool(self, **kwargs: Any) -> Any:
        def register(fn: Any) -> Any:
            self.functions[fn.__name__] = fn
            return fn
        return register



@pytest.mark.asyncio
async def test_unknown_module_publication_is_retained_and_not_counted_as_unpublished() -> None:
    mcp = CaptureTools()
    modules.register_shared_module_tools(mcp)
    data = [{'id': 1, 'name': 'Visible', 'items': [
        {'id': 2, 'type': 'Page', 'title': 'Reading'},
        {'id': 3, 'type': 'Page', 'title': 'Draft', 'published': False},
    ]}, {'id': 4, 'name': 'Draft module', 'published': False}]
    with patch.object(modules, 'get_course_id', AsyncMock(return_value='101')), \
         patch.object(modules, 'fetch_all_paginated_results', AsyncMock(return_value=data)):
        result = json.loads(await mcp.functions['get_course_structure'](101, include_unpublished=False))
    assert len(result['modules']) == 1
    assert result['modules'][0]['published'] is None
    assert len(result['modules'][0]['items']) == 1
    assert result['modules'][0]['items'][0]['published'] is None
    assert result['summary']['unpublished_modules'] == 0



@pytest.mark.asyncio
async def test_overview_preserves_links_and_reports_unavailable_sections() -> None:
    mcp = CaptureTools()
    courses.register_course_tools(mcp)
    body = '<p>Read the <a href="https://example.org/syllabus?a=1&amp;b=2">course syllabus</a>.</p>'
    with patch.object(courses, 'get_course_id', AsyncMock(return_value='101')), \
         patch.object(courses, 'get_course_code', AsyncMock(return_value='TEST-101')), \
         patch.object(courses, 'make_canvas_request', AsyncMock(return_value={'syllabus_body': body})), \
         patch.object(courses, 'fetch_all_paginated_results', AsyncMock(return_value={'error': 'HTTP error: 404, Pages disabled'})):
        result = await mcp.functions['get_course_content_overview'](101)
    assert 'https://example.org/syllabus?a=1&b=2' in result
    assert 'Pages' in result and 'Modules' in result and '404' in result



@pytest.mark.asyncio
async def test_syllabus_links_beyond_preview_are_preserved_and_unsafe_links_are_omitted() -> None:
    mcp = CaptureTools()
    courses.register_course_tools(mcp)
    body = ('<p>Intro</p>' * 300 + '<a href="https://example.org/full">Full syllabus</a>'
            '<script><a href="https://example.org/fake">fake</a></script>'
            '<a href="javascript:alert(1)">unsafe</a>')
    with patch.object(courses, 'get_course_id', AsyncMock(return_value='101')), \
         patch.object(courses, 'get_course_code', AsyncMock(return_value='TEST-101')), \
         patch.object(courses, 'make_canvas_request', AsyncMock(return_value={'syllabus_body': body})):
        result = await mcp.functions['get_course_content_overview'](101, include_pages=False, include_modules=False)
    assert 'https://example.org/full' in result
    assert 'https://example.org/fake' not in result and 'javascript:alert' not in result
    assert 'Preview of the first 1000 characters' in result
