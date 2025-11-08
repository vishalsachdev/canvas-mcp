"""Tests for type definitions."""

from canvas_mcp.core.types import (
    AnnouncementInfo,
    AssignmentInfo,
    CourseInfo,
    PageInfo,
)


def test_course_info_type() -> None:
    """Test CourseInfo type definition."""
    course: CourseInfo = {
        "id": 12345,
        "name": "Test Course",
        "course_code": "TEST_101",
        "start_at": "2024-01-01T00:00:00Z",
        "end_at": "2024-12-31T23:59:59Z",
        "time_zone": "America/Chicago",
        "default_view": "modules",
        "is_public": False,
        "blueprint": False,
    }
    assert course["id"] == 12345
    assert course["name"] == "Test Course"


def test_assignment_info_type() -> None:
    """Test AssignmentInfo type definition."""
    assignment: AssignmentInfo = {
        "id": 67890,
        "name": "Test Assignment",
        "due_at": "2024-03-15T23:59:59Z",
        "points_possible": 100.0,
        "submission_types": ["online_text_entry"],
        "published": True,
        "locked_for_user": False,
    }
    assert assignment["id"] == 67890
    assert assignment["points_possible"] == 100.0


def test_page_info_type() -> None:
    """Test PageInfo type definition."""
    page: PageInfo = {
        "page_id": 11111,
        "url": "test-page",
        "title": "Test Page",
        "published": True,
        "front_page": False,
        "locked_for_user": False,
    }
    assert page["page_id"] == 11111
    assert page["title"] == "Test Page"


def test_announcement_info_type() -> None:
    """Test AnnouncementInfo type definition."""
    announcement: AnnouncementInfo = {
        "id": 22222,
        "title": "Test Announcement",
        "message": "This is a test",
        "posted_at": "2024-02-01T12:00:00Z",
        "published": True,
        "is_announcement": True,
    }
    assert announcement["id"] == 22222
    assert announcement["is_announcement"] is True
