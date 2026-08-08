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
from canvas_mcp.core.client import (
    ANONYMIZE_FREE_TEXT,
    ANONYMIZE_FULL,
    ANONYMIZE_IDENTITY,
    ANONYMIZE_NONE,
    _determine_data_type,
    _endpoint_anonymization_mode,
    _should_anonymize_endpoint,
)


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
        "/courses/123/modules",
        "/courses/123/modules/5/items",
        "/courses/123/assignments",       # assignment definitions, no student data
        "/courses/123/assignments/456",
        "/courses/123/rubrics/12",
        "/accounts/1/terms",
        # Group *listings* carry group names, not student names; membership is
        # fetched via /groups/{id}/users which the /users rule covers.
        "/courses/123/groups",
        # Topic listings (incl. announcements) are typically instructor-authored;
        # student content lives under /entries|/view|/entry_list|/replies.
        "/courses/123/discussion_topics",
    ])
    def test_non_student_endpoints_not_anonymized(self, endpoint):
        assert _should_anonymize_endpoint(endpoint) is False

    @pytest.mark.parametrize("endpoint", [
        "/api/quiz/v1/courses/123/enrollments",
        "/api/quiz/v1/courses/123/users",
        "/api/quiz/v1/courses/123/assignments/456/submissions",
        "/api/quiz/v1/courses/123/analytics/student_summaries",
    ])
    def test_quiz_root_student_data_endpoints_still_anonymized(self, endpoint):
        """Adding /api/quiz/v1 must not bypass sensitive-segment matching."""
        assert _should_anonymize_endpoint(endpoint) is True

    @pytest.mark.parametrize("endpoint", [
        "/api/quiz/v1/courses/123/modules",
        "/api/quiz/v1/courses/123/assignments",
    ])
    def test_quiz_root_non_student_endpoints_not_anonymized(self, endpoint):
        assert _should_anonymize_endpoint(endpoint) is False

    def test_case_insensitive(self):
        assert _should_anonymize_endpoint("/COURSES/123/ENROLLMENTS") is True

    def test_querystring_stripped_before_matching(self):
        assert _should_anonymize_endpoint("/courses/123/enrollments?per_page=100") is True
        assert _should_anonymize_endpoint("/courses/123/modules?search_term=users") is False

    def test_enrollments_map_to_users_data_type(self):
        assert _determine_data_type("/courses/123/enrollments") == "users"

    def test_discussion_view_maps_to_discussions_data_type(self):
        assert _determine_data_type("/courses/123/discussion_topics/9/view") == "discussions"


class TestAnonymizationTierMapping:
    """Issue #179: /conversations and /pages were completely ungated, and the
    correct treatment for each is a different HALF of the scrubber. A boolean
    gate could only over- or under-protect them, so the gate returns a tier.
    """

    @pytest.mark.parametrize("endpoint", [
        "/conversations",
        "/conversations/123",
        "/conversations?scope=unread",
        "/CONVERSATIONS",
        "/conversations/123/add_message",
    ])
    def test_conversations_are_free_text_tier(self, endpoint):
        assert _endpoint_anonymization_mode(endpoint) == ANONYMIZE_FREE_TEXT

    @pytest.mark.parametrize("endpoint", [
        "/courses/123/pages",
        "/courses/123/pages/syllabus",
        "/courses/123/pages/intro?include[]=body",
        "/groups/55/pages",
        # Page slugs are user-controlled: a page named "users"/"submissions"
        # must not escalate the tier to full (PR #165 review). The slug rule
        # still holds, it just now lands on identity instead of none.
        "/courses/123/pages/users",
        "/courses/123/pages/submissions",
        "/courses/123/pages/analytics",
        # The front page is a page and returns the same last_edited_by block,
        # but its path carries no 'pages' segment so the slug rule missed it.
        # Measured live: last_edited_by came back with display_name, pronouns
        # and avatar_image_url while /pages/{slug} was gated.
        "/courses/123/front_page",
        "/groups/55/front_page",
    ])
    def test_pages_are_identity_tier(self, endpoint):
        assert _endpoint_anonymization_mode(endpoint) == ANONYMIZE_IDENTITY

    @pytest.mark.parametrize("endpoint", [
        "/courses/123/users",
        "/courses/123/enrollments",
        "/courses/123/assignments/1/submissions",
        "/courses/123/analytics/student_summaries",
        "/courses/123/discussion_topics/9/view",
    ])
    def test_student_record_endpoints_are_full_tier(self, endpoint):
        assert _endpoint_anonymization_mode(endpoint) == ANONYMIZE_FULL

    @pytest.mark.parametrize("endpoint", [
        "/courses",
        "/courses/123/modules",
        "/courses/123/assignments",
        "/accounts/1/terms",
        "/users/self/profile",
    ])
    def test_unmatched_endpoints_are_none_tier(self, endpoint):
        assert _endpoint_anonymization_mode(endpoint) == ANONYMIZE_NONE

    def test_full_tier_wins_over_partial_tiers(self):
        """Tiers are ordered most-protective-first: a path that touches both a
        student-record segment and a partially gated one must not be downgraded.
        """
        assert _endpoint_anonymization_mode(
            "/courses/123/users/9/pages"
        ) == ANONYMIZE_FULL

    def test_boolean_wrapper_agrees_with_mode(self):
        for endpoint in ("/conversations", "/courses/1/pages", "/courses/1/users"):
            assert _should_anonymize_endpoint(endpoint) is True
        for endpoint in ("/courses", "/users/self/profile"):
            assert _should_anonymize_endpoint(endpoint) is False


class TestSelfOnlyEndpointExemption:
    """The caller's OWN identity is exempt (issue #171) — by EXACT path only.

    Anonymizing these corrupts the caller's own record (they get told their name
    is "Student_<hash>"). FERPA protects a record from OTHERS, never from its
    subject. But this is a loosening of a privacy control, so the allowlist is an
    exact full-path match; the non-regression class below is the real test.
    """

    @pytest.mark.parametrize("endpoint", [
        "/users/self",
        "/users/self/profile",
        "users/self/profile",              # leading slash is optional
        "/users/self/profile?include[]=x",  # query string stripped first
        "/USERS/SELF/PROFILE",             # case-insensitive
        "/users/self/profile/",            # trailing slash
    ])
    def test_self_only_endpoints_exempt(self, endpoint):
        assert _should_anonymize_endpoint(endpoint) is False


class TestSelfExemptionDoesNotLeakToOtherPaths:
    """Anti-bypass. #164 and #166 were both over-broad 'safe endpoint' rules;
    every path here must STILL anonymize."""

    @pytest.mark.parametrize("endpoint", [
        # Other people, reached through the caller's own /users/self namespace.
        "/users/self/observees",
        # Looks self-only, but Canvas expands it with include[]=observed_users,
        # which returns OTHER students. The gate cannot see request params.
        "/users/self/enrollments",
        "/users/self/observees/55",
        "/users/self/courses/123/users",
        "/users/self/enrollments/999",   # a specific enrollment, not the list
        "/users/self/profile/extra",
        # Rosters.
        "/courses/123/enrollments",
        "/courses/123/users",
        "/sections/45/enrollments",
        # Somebody else's profile.
        "/users/456/profile",
        "/users/456",
        "/users/self_service/profile",
        # A user literally named/slugged "self" elsewhere in the path.
        "/courses/self/users",
        # Prefix/suffix games.
        "/api/v1/users/self/profile",
        "/api/quiz/v1/users/self/profile",
        "/accounts/1/users/self/profile",
    ])
    def test_still_anonymized(self, endpoint):
        assert _should_anonymize_endpoint(endpoint) is True

    def test_allowlist_is_exactly_two_paths(self):
        """Growing this set is a FERPA decision, not a refactor.

        `users/self/enrollments` was in this set and was deliberately removed:
        Canvas expands it with `include[]=observed_users`, which returns other
        students' records on observer enrollments. The gate sees only the path
        and cannot inspect request parameters, so exempting it would let those
        records bypass anonymization. `get_my_enrollments` reads `/courses`
        instead, so nothing depends on the exemption.
        """
        from canvas_mcp.core.client import _SELF_ONLY_ENDPOINTS

        assert _SELF_ONLY_ENDPOINTS == frozenset({
            "users/self",
            "users/self/profile",
        })


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

    def test_flat_non_user_record_not_fabricated(self):
        # A flat enrollment (no include[]=user) or todo item has an id that
        # belongs to no user — the flat-user branch must not fabricate
        # name/email from it.
        flat_enrollment = {"id": 9003, "course_id": 123, "type": "StudentEnrollment"}
        result = anonymize_user_data(flat_enrollment)
        assert "name" not in result
        assert "email" not in result

    def test_enrollment_list_via_response_data(self):
        enrollments = [{
            "id": 9002,
            "user_id": 102,
            "user": {"id": 102, "name": "Bob Learner", "login_id": "bob2"},
        }]
        result = anonymize_response_data(enrollments, data_type="users")
        assert result[0]["user"]["name"] != "Bob Learner"
