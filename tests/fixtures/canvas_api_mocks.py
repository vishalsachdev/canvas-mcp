"""Mock Canvas API responses for testing."""

from typing import Any


def mock_course_list() -> list[dict[str, Any]]:
    """Mock response for list courses API."""
    return [
        {
            "id": 12345,
            "name": "Introduction to Testing",
            "course_code": "TEST_101_F2024",
            "start_at": "2024-01-15T00:00:00Z",
            "end_at": "2024-05-15T23:59:59Z",
            "time_zone": "America/Chicago",
            "is_public": False,
            "blueprint": False,
            "total_students": 25,
        },
        {
            "id": 67890,
            "name": "Advanced Testing",
            "course_code": "TEST_201_F2024",
            "start_at": "2024-01-15T00:00:00Z",
            "end_at": "2024-05-15T23:59:59Z",
            "time_zone": "America/Chicago",
            "is_public": False,
            "blueprint": False,
            "total_students": 30,
        },
    ]


def mock_assignment_list() -> list[dict[str, Any]]:
    """Mock response for list assignments API."""
    return [
        {
            "id": 11111,
            "name": "Assignment 1",
            "due_at": "2024-02-15T23:59:59Z",
            "points_possible": 100.0,
            "submission_types": ["online_text_entry"],
            "published": True,
            "locked_for_user": False,
        },
        {
            "id": 22222,
            "name": "Assignment 2",
            "due_at": "2024-03-15T23:59:59Z",
            "points_possible": 150.0,
            "submission_types": ["online_upload"],
            "published": True,
            "locked_for_user": False,
        },
    ]


def mock_submission_list() -> list[dict[str, Any]]:
    """Mock response for list submissions API."""
    return [
        {
            "id": 111,
            "user_id": 1001,
            "assignment_id": 11111,
            "submitted_at": "2024-02-14T10:30:00Z",
            "score": 85.0,
            "grade": "85",
            "workflow_state": "graded",
            "late": False,
        },
        {
            "id": 222,
            "user_id": 1002,
            "assignment_id": 11111,
            "submitted_at": "2024-02-15T08:00:00Z",
            "score": 92.0,
            "grade": "92",
            "workflow_state": "graded",
            "late": False,
        },
        {
            "id": 333,
            "user_id": 1003,
            "assignment_id": 11111,
            "submitted_at": "2024-02-16T12:00:00Z",
            "score": 78.0,
            "grade": "78",
            "workflow_state": "graded",
            "late": True,
        },
    ]


def mock_discussion_list() -> list[dict[str, Any]]:
    """Mock response for list discussions API."""
    return [
        {
            "id": 54321,
            "title": "Week 1 Discussion",
            "message": "Discuss the assigned reading",
            "posted_at": "2024-01-20T12:00:00Z",
            "discussion_type": "threaded",
            "published": True,
            "read_state": "read",
        },
        {
            "id": 54322,
            "title": "Week 2 Discussion",
            "message": "Share your thoughts on the case study",
            "posted_at": "2024-01-27T12:00:00Z",
            "discussion_type": "threaded",
            "published": True,
            "read_state": "unread",
        },
    ]


def mock_user_list() -> list[dict[str, Any]]:
    """Mock response for list users API."""
    return [
        {
            "id": 1001,
            "name": "Student One",
            "sortable_name": "One, Student",
            "short_name": "S. One",
            "email": "student1@test.edu",
        },
        {
            "id": 1002,
            "name": "Student Two",
            "sortable_name": "Two, Student",
            "short_name": "S. Two",
            "email": "student2@test.edu",
        },
        {
            "id": 1003,
            "name": "Student Three",
            "sortable_name": "Three, Student",
            "short_name": "S. Three",
            "email": "student3@test.edu",
        },
    ]


def mock_rubric() -> dict[str, Any]:
    """Mock response for rubric API."""
    return {
        "id": 99999,
        "title": "Test Rubric",
        "criteria": [
            {
                "id": "crit1",
                "description": "Content Quality",
                "points": 40,
                "ratings": [
                    {"id": "r1", "description": "Excellent", "points": 40},
                    {"id": "r2", "description": "Good", "points": 30},
                    {"id": "r3", "description": "Fair", "points": 20},
                    {"id": "r4", "description": "Poor", "points": 10},
                ],
            },
            {
                "id": "crit2",
                "description": "Organization",
                "points": 30,
                "ratings": [
                    {"id": "r1", "description": "Excellent", "points": 30},
                    {"id": "r2", "description": "Good", "points": 20},
                    {"id": "r3", "description": "Poor", "points": 10},
                ],
            },
        ],
    }


def mock_error_response(error_message: str = "API Error") -> dict[str, str]:
    """Mock error response."""
    return {"error": error_message}
