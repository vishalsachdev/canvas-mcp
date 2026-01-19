"""Shared pytest fixtures for Canvas MCP tests."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.fixture
def mock_canvas_request():
    """Mock Canvas API request function."""
    with patch('canvas_mcp.core.client.make_canvas_request') as mock:
        mock.return_value = AsyncMock()
        yield mock


@pytest.fixture
def mock_fetch_paginated():
    """Mock paginated fetch function."""
    with patch('canvas_mcp.core.client.fetch_all_paginated_results') as mock:
        mock.return_value = AsyncMock()
        yield mock


@pytest.fixture
def mock_course_id_resolver():
    """Mock course ID resolver."""
    with patch('canvas_mcp.core.cache.get_course_id') as mock:
        # Default to returning the input as-is (assuming it's already an ID)
        async def resolve_id(identifier):
            return str(identifier) if isinstance(identifier, int) else identifier
        mock.side_effect = resolve_id
        yield mock


@pytest.fixture
def mock_course_code_resolver():
    """Mock course code resolver."""
    with patch('canvas_mcp.core.cache.get_course_code') as mock:
        async def resolve_code(course_id):
            return f"course_{course_id}"
        mock.side_effect = resolve_code
        yield mock


@pytest.fixture
def sample_course_data():
    """Sample course data for testing."""
    return {
        "id": 12345,
        "name": "Introduction to Computer Science",
        "course_code": "CS101_2024",
        "start_at": "2024-01-15T08:00:00Z",
        "end_at": "2024-05-15T17:00:00Z",
        "time_zone": "America/Chicago",
        "default_view": "modules",
        "is_public": False,
        "blueprint": False
    }


@pytest.fixture
def sample_assignment_data():
    """Sample assignment data for testing."""
    return {
        "id": 67890,
        "name": "Python Programming Project",
        "description": "<p>Build a Python application</p>",
        "due_at": "2024-02-15T23:59:00Z",
        "points_possible": 100,
        "submission_types": ["online_upload", "online_text_entry"],
        "published": True,
        "locked_for_user": False
    }


@pytest.fixture
def sample_submission_data():
    """Sample submission data for testing."""
    return {
        "id": 111,
        "user_id": 1001,
        "submitted_at": "2024-02-14T18:30:00Z",
        "score": 85,
        "grade": "85",
        "workflow_state": "graded",
        "late": False,
        "missing": False,
        "excused": False
    }


@pytest.fixture
def sample_page_data():
    """Sample page data for testing."""
    return {
        "page_id": 222,
        "url": "module-1-overview",
        "title": "Module 1: Overview",
        "body": "<h1>Welcome to Module 1</h1><p>Content here</p>",
        "published": True,
        "front_page": False,
        "updated_at": "2024-01-20T10:00:00Z"
    }


@pytest.fixture
def sample_rubric_data():
    """Sample rubric data for testing."""
    return {
        "id": 333,
        "title": "Programming Assignment Rubric",
        "context_id": 12345,
        "context_type": "Course",
        "points_possible": 100,
        "criteria": [
            {
                "id": "crit1",
                "description": "Code Quality",
                "points": 40,
                "ratings": [
                    {"id": "r1", "description": "Excellent", "points": 40},
                    {"id": "r2", "description": "Good", "points": 30},
                    {"id": "r3", "description": "Fair", "points": 20},
                    {"id": "r4", "description": "Poor", "points": 0}
                ]
            },
            {
                "id": "crit2",
                "description": "Documentation",
                "points": 30,
                "ratings": [
                    {"id": "r5", "description": "Excellent", "points": 30},
                    {"id": "r6", "description": "Good", "points": 20},
                    {"id": "r7", "description": "Fair", "points": 10},
                    {"id": "r8", "description": "Poor", "points": 0}
                ]
            }
        ]
    }


@pytest.fixture
def sample_discussion_topic_data():
    """Sample discussion topic data for testing."""
    return {
        "id": 444,
        "title": "Week 1 Discussion",
        "message": "Discuss this week's topics",
        "posted_at": "2024-01-15T09:00:00Z",
        "published": True,
        "discussion_type": "threaded",
        "user_can_see_posts": True
    }


@pytest.fixture
def sample_announcement_data():
    """Sample announcement data for testing."""
    return {
        "id": 555,
        "title": "Important: Exam Schedule",
        "message": "<p>The midterm exam will be on March 1st</p>",
        "posted_at": "2024-02-01T12:00:00Z",
        "author": {"id": 2000, "display_name": "Prof. Smith"}
    }
