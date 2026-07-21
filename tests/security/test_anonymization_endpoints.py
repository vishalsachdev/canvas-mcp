"""
Anonymization endpoint-gating tests (issue #164).

Direct unit tests for _should_anonymize_endpoint() — the central gate that
decides whether a Canvas API response is anonymized before reaching the model.
Prior to #164 no test exercised this function, which let a safe-endpoint
short-circuit silently skip anonymization for nearly all /courses/-scoped
student-data endpoints.

Also covers the two response shapes the anonymizer previously passed through
untouched: the discussion /view wrapper dict and enrollment records with a
nested `user` dict.
"""

import pytest

from canvas_mcp.core.anonymization import (
    anonymize_response_data,
    anonymize_user_data,
)
from canvas_mcp.core.client import _determine_data_type, _should_anonymize_endpoint


class TestShouldAnonymizeEndpoint:
    """Student-data endpoints must anonymize even when nested under /courses."""

    @pytest.mark.parametrize("endpoint", [
        "/courses/123/enrollments",
        "/sections/45/enrollments",
        "/courses/123/assignments/456/submissions",
        "/courses/123/assignments/456/submissions/789",
        "/courses/123/students/submissions",
        "/courses/123/analytics/student_summaries",
        "/courses/123/analytics/users/77/activity",
        "/courses/123/users",
        "/courses/123/users/456",
        "/groups/55/users",
        "/courses/123/discussion_topics/9/entries",
        "/courses/123/discussion_topics/9/entries/1/replies",
        "/courses/123/discussion_topics/9/view",
        "/courses/123/discussion_topics/9/entry_list",
    ])
    def test_student_data_endpoints_anonymized(self, endpoint):
        assert _should_anonymize_endpoint(endpoint) is True

    @pytest.mark.parametrize("endpoint", [
        "/courses",
        "/courses/123",
        "/courses/123/pages",
        "/courses/123/pages/intro",
        "/courses/123/modules",
        "/courses/123/modules/5/items",
        "/courses/123/assignments",       # assignment definitions, no student data
        "/courses/123/assignments/456",
        "/courses/123/front_page",
        "/courses/123/rubrics/12",
        "/accounts/1/terms",
        # Group *listings* carry group names, not student names; membership is
        # fetched via /groups/{id}/users which the /users rule covers.
        "/courses/123/groups",
        # Topic listings (incl. announcements) are typically instructor-authored;
        # student content lives under /entries|/view|/entry_list|/replies.
        "/courses/123/discussion_topics",
        # Page slugs are user-controlled: a page named "users"/"submissions"
        # must not trip the sensitive-segment match (PR #165 review).
        "/courses/123/pages/users",
        "/courses/123/pages/submissions",
        "/courses/123/pages/analytics",
    ])
    def test_non_student_endpoints_not_anonymized(self, endpoint):
        assert _should_anonymize_endpoint(endpoint) is False

    def test_case_insensitive(self):
        assert _should_anonymize_endpoint("/COURSES/123/ENROLLMENTS") is True

    def test_querystring_stripped_before_matching(self):
        assert _should_anonymize_endpoint("/courses/123/enrollments?per_page=100") is True
        assert _should_anonymize_endpoint("/courses/123/pages?search_term=users") is False

    def test_enrollments_map_to_users_data_type(self):
        assert _determine_data_type("/courses/123/enrollments") == "users"

    def test_discussion_view_maps_to_discussions_data_type(self):
        assert _determine_data_type("/courses/123/discussion_topics/9/view") == "discussions"


class TestDiscussionViewAnonymization:
    """The /view endpoint returns {"view": [...], "participants": [...]} —
    both lists carry student names and must be anonymized recursively."""

    def _view_response(self):
        return {
            "unread_entries": [],
            "participants": [
                {"id": 101, "display_name": "Alice Student", "avatar_image_url": "http://x/a.png"},
                {"id": 102, "display_name": "Bob Learner", "avatar_image_url": "http://x/b.png"},
            ],
            "view": [
                {
                    "id": 1,
                    "user_id": 101,
                    "user_name": "Alice Student",
                    "message": "My email is alice@example.com",
                    "replies": [
                        {"id": 2, "user_id": 102, "user_name": "Bob Learner", "message": "Hi Alice"},
                    ],
                },
            ],
            # Returned when the caller passes include_new_entries=1
            "new_entries": [
                {"id": 3, "user_id": 102, "user_name": "Bob Learner", "message": "A new post"},
            ],
        }

    def test_view_entries_anonymized(self):
        result = anonymize_response_data(self._view_response(), data_type="discussions")
        entry = result["view"][0]
        assert entry["user_name"] != "Alice Student"
        assert entry["user_name"].startswith("Student_")
        assert "alice@example.com" not in entry["message"]

    def test_nested_replies_anonymized(self):
        result = anonymize_response_data(self._view_response(), data_type="discussions")
        reply = result["view"][0]["replies"][0]
        assert reply["user_name"] != "Bob Learner"
        assert reply["user_name"].startswith("Student_")

    def test_participants_anonymized(self):
        result = anonymize_response_data(self._view_response(), data_type="discussions")
        names = [p["display_name"] for p in result["participants"]]
        assert "Alice Student" not in names
        assert "Bob Learner" not in names

    def test_new_entries_anonymized(self):
        result = anonymize_response_data(self._view_response(), data_type="discussions")
        entry = result["new_entries"][0]
        assert entry["user_name"] != "Bob Learner"
        assert entry["user_name"].startswith("Student_")


class TestEnrollmentAnonymization:
    """Enrollment records embed the student in a nested `user` dict."""

    def test_nested_user_anonymized(self):
        enrollment = {
            "id": 9001,  # enrollment id, not a student id
            "course_id": 123,
            "type": "StudentEnrollment",
            "sis_user_id": "670001234",
            "user": {
                "id": 101,
                "name": "Alice Student",
                "sortable_name": "Student, Alice",
                "login_id": "alice1",
            },
        }
        result = anonymize_user_data(enrollment)
        assert result["user"]["name"] != "Alice Student"
        assert result["user"]["name"].startswith("Student_")
        assert result["user"]["id"] == 101  # IDs preserved for functionality
        # Wrapper-level identity fields are scrubbed, not fabricated:
        # no fake name/email keyed to the enrollment's own id (PR #165 review)
        assert "name" not in result
        assert "email" not in result
        assert result["sis_user_id"] is None
        assert result["type"] == "StudentEnrollment"  # non-identity fields intact

    def test_enrollment_list_via_response_data(self):
        enrollments = [{
            "id": 9002,
            "user_id": 102,
            "user": {"id": 102, "name": "Bob Learner", "login_id": "bob2"},
        }]
        result = anonymize_response_data(enrollments, data_type="users")
        assert result[0]["user"]["name"] != "Bob Learner"
