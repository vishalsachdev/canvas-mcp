"""Pytest configuration and shared fixtures."""

import os
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.fixture
def mock_env(monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    """Set up environment variables for testing."""
    env_vars = {
        "CANVAS_API_TOKEN": "test_token_123",
        "CANVAS_API_URL": "https://canvas.test.edu/api/v1",
        "MCP_SERVER_NAME": "test-canvas-api",
        "DEBUG": "false",
        "API_TIMEOUT": "30",
        "CACHE_TTL": "300",
        "ENABLE_DATA_ANONYMIZATION": "false",
        "LOG_API_REQUESTS": "false",
    }
    for key, value in env_vars.items():
        monkeypatch.setenv(key, value)
    return env_vars


@pytest.fixture
def mock_canvas_response() -> dict[str, Any]:
    """Mock Canvas API response data."""
    return {
        "id": 12345,
        "name": "Test Course",
        "course_code": "TEST_101",
        "start_at": "2024-01-01T00:00:00Z",
        "end_at": "2024-12-31T23:59:59Z",
    }


@pytest.fixture
def mock_http_client() -> AsyncMock:
    """Mock HTTP client for Canvas API requests."""
    client = AsyncMock()
    response = AsyncMock()
    response.status_code = 200
    response.json.return_value = {"success": True}
    response.raise_for_status = MagicMock()
    client.get.return_value = response
    client.post.return_value = response
    client.put.return_value = response
    client.delete.return_value = response
    return client


@pytest.fixture
def sample_course_data() -> dict[str, Any]:
    """Sample course data for testing."""
    return {
        "id": 60366,
        "name": "Introduction to Testing",
        "course_code": "TEST_101_F2024",
        "start_at": "2024-01-15T00:00:00Z",
        "end_at": "2024-05-15T23:59:59Z",
        "time_zone": "America/Chicago",
        "is_public": False,
        "blueprint": False,
    }


@pytest.fixture
def sample_assignment_data() -> dict[str, Any]:
    """Sample assignment data for testing."""
    return {
        "id": 12345,
        "name": "Test Assignment",
        "due_at": "2024-03-15T23:59:59Z",
        "points_possible": 100.0,
        "submission_types": ["online_text_entry"],
        "published": True,
        "locked_for_user": False,
    }


@pytest.fixture
def sample_submission_data() -> dict[str, Any]:
    """Sample submission data for testing."""
    return {
        "id": 67890,
        "user_id": 11111,
        "assignment_id": 12345,
        "submitted_at": "2024-03-14T10:30:00Z",
        "score": 85.0,
        "grade": "85",
        "workflow_state": "graded",
        "late": False,
    }


@pytest.fixture
def sample_discussion_data() -> dict[str, Any]:
    """Sample discussion data for testing."""
    return {
        "id": 54321,
        "title": "Test Discussion",
        "message": "This is a test discussion",
        "posted_at": "2024-02-01T12:00:00Z",
        "discussion_type": "threaded",
        "published": True,
    }


@pytest.fixture(autouse=True)
def reset_config() -> None:
    """Reset global configuration before each test."""
    # Import here to avoid circular dependencies
    from canvas_mcp.core import config

    # Reset the global config instance
    config._config = None
