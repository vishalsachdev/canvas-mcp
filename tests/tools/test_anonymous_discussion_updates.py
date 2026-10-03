"""Issue 421: anonymous topics must never reach an update request."""

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from .test_discussions import get_tool_function


@pytest.mark.asyncio
@pytest.mark.parametrize("guarded", [False, True])
@pytest.mark.parametrize(
    "detail_status, state, listing_status, listed, outcome",
    [
        (404, "full_anonymity", 200, True, "anonymous"),
        (200, "partial_anonymity", 200, True, "anonymous"),
        (404, None, 200, True, "listed"),
        (404, None, 200, False, "missing"),
        (404, "full_anonymity", 403, True, "missing"),
        (403, None, 200, True, "forbidden"),
        (200, None, 200, True, "updated"),
    ],
)
async def test_update_checks_topic_before_any_write(
    monkeypatch, guarded, detail_status, state, listing_status, listed, outcome
) -> None:
    """A missing anonymity check would send PUT or misreport a listed 404."""
    from canvas_mcp.core import client as cm
    from canvas_mcp.core import config as config_module

    monkeypatch.setenv("CANVAS_API_URL", "https://canvas.example/api/v1")
    monkeypatch.setenv("CANVAS_API_TOKEN", "synthetic-test-token")
    # Even an enabled read fallback must never enable GraphQL writes.
    monkeypatch.setenv("DISCUSSION_GRAPHQL_ENABLED", "true")
    monkeypatch.setattr(config_module, "_config", config_module.Config())

    topic = {
        "id": 555,
        "title": "Synthetic feedback topic",
        "message": "<p>Before</p>",
        "anonymous_state": state,
        "html_url": "https://canvas.example/courses/60366/discussion_topics/555",
    }
    requested = []
    detail_path = "/api/v1/courses/60366/discussion_topics/555"
    listing_path = "/api/v1/courses/60366/discussion_topics"

    async def transport(request: httpx.Request) -> httpx.Response:
        requested.append((request.method, request.url.path))
        if request.url.path == detail_path:
            if request.method == "PUT":
                return httpx.Response(200, json=dict(topic, message="<p>After</p>"))
            if detail_status != 200:
                return httpx.Response(detail_status, json={"errors": [{"message": "Unavailable"}]})
            body = "<p>After</p>" if any(method == "PUT" for method, _ in requested) else "<p>Before</p>"
            return httpx.Response(200, json=dict(topic, message=body))
        if request.method == "GET" and request.url.path == listing_path:
            return httpx.Response(listing_status, json=[topic] if listed else [])
        raise AssertionError(f"Unexpected request: {request.method} {request.url.path}")

    kwargs = {"find": "Before", "replace": "After"} if guarded else {"message": "<p>After</p>"}
    async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as client:
        with patch.object(cm, "_get_http_client", return_value=client), \
             patch("canvas_mcp.tools.discussions.get_course_id", AsyncMock(return_value="60366")), \
             patch("canvas_mcp.tools.discussions.get_course_code", AsyncMock(return_value="TEST101")):
            result = await get_tool_function("update_discussion_topic")("TEST101", 555, **kwargs)

    if outcome == "updated":
        expected = [("GET", detail_path), ("PUT", detail_path)]
        if guarded:
            expected.append(("GET", detail_path))
        assert requested == expected
        assert "successfully" in result.lower() or "verified" in result.lower(), result
    else:
        assert all(method == "GET" for method, _ in requested), requested
        assert requested[0] == ("GET", detail_path)
        if detail_status == 404:
            assert requested == [("GET", detail_path), ("GET", listing_path)]
        else:
            assert requested == [("GET", detail_path)]
        if outcome in {"anonymous", "listed"}:
            assert "topic 555 exists" in result, result
            assert "Canvas UI" in result
            assert "Nothing was written" in result
            if state:
                assert state in result
        else:
            assert f"HTTP error: {403 if outcome == 'forbidden' else 404}" in result
            assert "topic 555 exists" not in result
