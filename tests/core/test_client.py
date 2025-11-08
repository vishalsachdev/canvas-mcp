"""Tests for HTTP client and Canvas API utilities."""

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from canvas_mcp.core.client import (
    _determine_data_type,
    _should_anonymize_endpoint,
    fetch_all_paginated_results,
    make_canvas_request,
)


def test_determine_data_type() -> None:
    """Test data type determination from endpoints."""
    assert _determine_data_type("/courses/123/users") == "users"
    assert _determine_data_type("/courses/123/discussion_topics/456/entries") == "discussions"
    assert _determine_data_type("/courses/123/assignments/456/submissions") == "submissions"
    assert _determine_data_type("/courses/123/assignments") == "assignments"
    assert _determine_data_type("/courses/123/enrollments") == "users"
    assert _determine_data_type("/courses/123") == "general"


def test_should_anonymize_endpoint() -> None:
    """Test endpoint anonymization detection."""
    # Should anonymize
    assert _should_anonymize_endpoint("/courses/123/users") is True
    assert _should_anonymize_endpoint("/courses/123/discussion_topics/456/entries") is True
    assert _should_anonymize_endpoint("/courses/123/submissions") is True
    assert _should_anonymize_endpoint("/courses/123/enrollments") is True

    # Should not anonymize
    assert _should_anonymize_endpoint("/courses") is False
    assert _should_anonymize_endpoint("/users/self") is False
    assert _should_anonymize_endpoint("/accounts") is False
    assert _should_anonymize_endpoint("/courses/123/terms") is False


@pytest.mark.asyncio
async def test_make_canvas_request_success(mock_env: dict[str, str]) -> None:
    """Test successful Canvas API request."""
    mock_response = AsyncMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"id": 123, "name": "Test"}
    mock_response.raise_for_status = MagicMock()

    with patch("canvas_mcp.core.client.httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response
        mock_client_class.return_value = mock_client

        result = await make_canvas_request("get", "/courses/123")

        assert result == {"id": 123, "name": "Test"}
        mock_client.get.assert_called_once()


@pytest.mark.asyncio
async def test_make_canvas_request_with_params(mock_env: dict[str, str]) -> None:
    """Test Canvas API request with parameters."""
    mock_response = AsyncMock()
    mock_response.status_code = 200
    mock_response.json.return_value = [{"id": 1}, {"id": 2}]
    mock_response.raise_for_status = MagicMock()

    with patch("canvas_mcp.core.client.httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response
        mock_client_class.return_value = mock_client

        params = {"per_page": 100, "include[]": "term"}
        result = await make_canvas_request("get", "/courses", params=params)

        assert result == [{"id": 1}, {"id": 2}]
        mock_client.get.assert_called_once()


@pytest.mark.asyncio
async def test_make_canvas_request_post_with_data(mock_env: dict[str, str]) -> None:
    """Test Canvas API POST request with data."""
    mock_response = AsyncMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"id": 456, "created": True}
    mock_response.raise_for_status = MagicMock()

    with patch("canvas_mcp.core.client.httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client_class.return_value = mock_client

        data = {"name": "New Item", "published": True}
        result = await make_canvas_request("post", "/courses/123/items", data=data)

        assert result == {"id": 456, "created": True}
        mock_client.post.assert_called_once()


@pytest.mark.asyncio
async def test_make_canvas_request_http_error(mock_env: dict[str, str]) -> None:
    """Test Canvas API request with HTTP error."""
    mock_response = AsyncMock()
    mock_response.status_code = 404
    mock_response.text = "Not Found"
    mock_response.json.side_effect = ValueError("No JSON")

    with patch("canvas_mcp.core.client.httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response
        mock_client.get.return_value.raise_for_status.side_effect = httpx.HTTPStatusError(
            "404 Not Found", request=MagicMock(), response=mock_response
        )
        mock_client_class.return_value = mock_client

        result = await make_canvas_request("get", "/courses/999")

        assert "error" in result
        assert "HTTP error" in result["error"]


@pytest.mark.asyncio
async def test_make_canvas_request_unsupported_method(mock_env: dict[str, str]) -> None:
    """Test Canvas API request with unsupported method."""
    result = await make_canvas_request("patch", "/courses/123")
    assert "error" in result
    assert "Unsupported method" in result["error"]


@pytest.mark.asyncio
async def test_fetch_all_paginated_results(mock_env: dict[str, str]) -> None:
    """Test fetching all paginated results."""
    page1_response = AsyncMock()
    page1_response.status_code = 200
    page1_response.json.return_value = [{"id": 1}, {"id": 2}, {"id": 3}]
    page1_response.raise_for_status = MagicMock()

    page2_response = AsyncMock()
    page2_response.status_code = 200
    page2_response.json.return_value = [{"id": 4}, {"id": 5}]
    page2_response.raise_for_status = MagicMock()

    page3_response = AsyncMock()
    page3_response.status_code = 200
    page3_response.json.return_value = []
    page3_response.raise_for_status = MagicMock()

    with patch("canvas_mcp.core.client.httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.get.side_effect = [page1_response, page2_response, page3_response]
        mock_client_class.return_value = mock_client

        result = await fetch_all_paginated_results("/courses")

        assert len(result) == 5
        assert result[0]["id"] == 1
        assert result[4]["id"] == 5


@pytest.mark.asyncio
async def test_fetch_all_paginated_results_with_params(mock_env: dict[str, str]) -> None:
    """Test fetching paginated results with custom parameters."""
    page_response = AsyncMock()
    page_response.status_code = 200
    page_response.json.return_value = [{"id": 1}]
    page_response.raise_for_status = MagicMock()

    empty_response = AsyncMock()
    empty_response.status_code = 200
    empty_response.json.return_value = []
    empty_response.raise_for_status = MagicMock()

    with patch("canvas_mcp.core.client.httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.get.side_effect = [page_response, empty_response]
        mock_client_class.return_value = mock_client

        params = {"include[]": "term"}
        result = await fetch_all_paginated_results("/courses", params=params)

        assert len(result) == 1
        assert result[0]["id"] == 1


@pytest.mark.asyncio
async def test_make_canvas_request_with_form_data(mock_env: dict[str, str]) -> None:
    """Test Canvas API request with form data."""
    mock_response = AsyncMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"success": True}
    mock_response.raise_for_status = MagicMock()

    with patch("canvas_mcp.core.client.httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client_class.return_value = mock_client

        data = {"field1": "value1", "field2": "value2"}
        result = await make_canvas_request("post", "/endpoint", data=data, use_form_data=True)

        assert result == {"success": True}
        mock_client.post.assert_called_once()
