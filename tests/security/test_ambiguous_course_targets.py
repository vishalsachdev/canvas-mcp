"""Legacy shared tools must not select one of several matching courses."""

from unittest.mock import AsyncMock

import pytest

from canvas_mcp.core import cache
from canvas_mcp.core.credentials import (
    clear_http_request_context,
    set_http_request_active,
)


@pytest.mark.asyncio
@pytest.mark.parametrize("other", [
    {"id": 2, "course_code": "HISTORY", "name": "Other"},
    {"id": 2, "course_code": "OTHER", "name": "HISTORY"},
])
async def test_legacy_resolver_refuses_ambiguous_exact_code(monkeypatch, other):
    courses = [{"id": 1, "course_code": "HISTORY", "name": "First"}, other]
    monkeypatch.setattr(cache, "course_records_cache", cache.course_records(courses))
    monkeypatch.setattr(cache, "course_code_to_id_cache", {"HISTORY": "1", "OTHER": "2"})
    with pytest.raises(ValueError, match="IDs 1, 2"):
        await cache.get_course_id("HISTORY")


@pytest.mark.asyncio
async def test_http_ambiguous_underscore_alias_is_not_reinterpreted_as_sis(monkeypatch):
    monkeypatch.setattr(cache, "fetch_all_paginated_results", AsyncMock(return_value=[
        {"id": 1, "course_code": "BADM_554"},
        {"id": 2, "course_code": "OTHER", "name": "BADM_554"},
    ]))
    set_http_request_active()
    try:
        with pytest.raises(ValueError, match="IDs 1, 2"):
            await cache.get_course_id("BADM_554")
    finally:
        clear_http_request_context()
