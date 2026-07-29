"""
Anonymizer shape/recursion tests (issue #166).

Follow-up to #164. The endpoint gate was fixed there, but the anonymizer
itself was a single-shot exclusive router: exactly one typed handler ran per
payload, each handler only touched top-level fields, and none of them
recursed. Nested identity fields therefore reached the model verbatim.

These tests pin the three live leaks, the fabrication/mis-route defects, and
the structural invariants of the recursive scrubber:

- no identity sentinel survives anywhere in the serialized output
- anonymization never ADDS a key that was not in the input
- non-user objects keep their names (course/group/module labels)
- an explicit data_type suppresses duck-typed handlers
- unknown shapes on sensitive endpoints still get scrubbed (fail-closed)
- f(f(x)) == f(x)
- /submissions/self is readable by its owner; /submissions/{id} is not
"""

import json

import pytest

from canvas_mcp.core.anonymization import (
    anonymize_response_data,
    scrub_identity,
)
from canvas_mcp.core.client import _determine_data_type, _should_anonymize_endpoint

# Sentinels that must never survive anonymization, in any nesting position.
SENTINELS = (
    "jdoe2",
    "Bob Smith",
    "Alice Example",
    "@illinois.edu",
    "670001234",
    "Doe, John",
)


def assert_no_pii(payload) -> None:
    """No identity sentinel may appear anywhere in the serialized output."""
    blob = json.dumps(payload)
    for sentinel in SENTINELS:
        assert sentinel not in blob, f"PII leaked: {sentinel!r} survived in {blob}"


def collect_key_sets(node, path="$"):
    """Flatten a payload into {path: frozenset(keys)} for key-set comparison."""
    found = {}
    if isinstance(node, dict):
        found[path] = frozenset(node.keys())
        for key, value in node.items():
            found.update(collect_key_sets(value, f"{path}.{key}"))
    elif isinstance(node, list):
        for index, item in enumerate(node):
            found.update(collect_key_sets(item, f"{path}[{index}]"))
    return found


# ---------------------------------------------------------------------------
# Fixtures modelled on real Canvas responses
# ---------------------------------------------------------------------------

def users_with_enrollments():
    """GET /courses/{id}/users?include[]=enrollments&include[]=email

    admin_tools.list_users requests exactly this. Pre-#166 the top-level
    sis_user_id was nulled but enrollments[].sis_user_id and the nested
    enrollments[].user survived verbatim.
    """
    return [
        {
            "id": 101,
            "name": "John Doe",
            "sortable_name": "Doe, John",
            "short_name": "John",
            "login_id": "jdoe2",
            "email": "jdoe2@illinois.edu",
            "sis_user_id": "670001234",
            "avatar_url": "https://canvas.example.edu/images/jdoe2.png",
            "enrollments": [
                {
                    "id": 9001,
                    "user_id": 101,
                    "course_id": 55,
                    "type": "StudentEnrollment",
                    "sis_user_id": "670001234",
                    "html_url": "https://canvas.example.edu/courses/55/users/101",
                    "user": {
                        "id": 101,
                        "name": "John Doe",
                        "login_id": "jdoe2",
                    },
                }
            ],
        }
    ]


def submissions_with_comments():
    """GET .../submissions?include[]=submission_comments (list_peer_reviews)."""
    return [
        {
            "id": 7001,
            "user_id": 101,
            "assignment_id": 42,
            "submitted_at": "2026-03-01T12:00:00Z",
            "body": "My essay, by John Doe",
            "submission_comments": [
                {
                    "id": 3001,
                    "author_id": 202,
                    "author_name": "Bob Smith",
                    "comment": "Nice work! Ping me at bob@illinois.edu or 217-555-0134.",
                    "avatar_path": "/images/thumbnails/bob.png",
                    "author": {
                        "id": 202,
                        "display_name": "Bob Smith",
                        "avatar_image_url": "https://canvas.example.edu/bob.png",
                        "html_url": "https://canvas.example.edu/courses/55/users/202",
                    },
                }
            ],
        }
    ]


def rubric_assessment_submission():
    """GET .../submissions/{user_id}?include[]=full_rubric_assessment."""
    return {
        "id": 7002,
        "user_id": 101,
        "submitted_at": "2026-03-01T12:00:00Z",
        "full_rubric_assessment": {
            "id": 5001,
            "assessor_id": 202,
            "assessor_name": "Bob Smith",
            "assessment_type": "peer_review",
            "assessor": {
                "id": 202,
                "display_name": "Bob Smith",
                "avatar_image_url": "https://canvas.example.edu/bob.png",
            },
            "data": [
                {
                    "criterion_id": "_1234",
                    "points": 4,
                    "comments": "Great thesis - reach me at bob@illinois.edu",
                }
            ],
        },
    }


ALL_FIXTURES = {
    "users_with_enrollments": users_with_enrollments,
    "submissions_with_comments": submissions_with_comments,
    "rubric_assessment_submission": rubric_assessment_submission,
}


# ---------------------------------------------------------------------------
# Live leak regressions
# ---------------------------------------------------------------------------

class TestNestedLeaks:

    def test_enrollment_nested_identity_scrubbed(self):
        result = anonymize_response_data(users_with_enrollments(), data_type="users")
        assert_no_pii(result)

        user = result[0]
        enrollment = user["enrollments"][0]
        assert enrollment["sis_user_id"] is None
        assert enrollment["user"]["name"].startswith("Student_")
        assert enrollment["user"]["login_id"] == user["login_id"]
        # IDs are preserved for functionality
        assert user["id"] == 101
        assert enrollment["user"]["id"] == 101
        assert enrollment["type"] == "StudentEnrollment"

    def test_submission_comment_authors_scrubbed(self):
        result = anonymize_response_data(submissions_with_comments(), data_type="submissions")
        assert_no_pii(result)

        comment = result[0]["submission_comments"][0]
        assert comment["author_name"].startswith("Student_")
        assert comment["author"]["display_name"] == comment["author_name"]
        assert comment["author"]["avatar_image_url"] is None
        assert "[EMAIL_REDACTED]" in comment["comment"]
        assert "[PHONE_REDACTED]" in comment["comment"]
        # Author id preserved so peer-review analytics still work
        assert comment["author_id"] == 202

    def test_full_rubric_assessment_scrubbed(self):
        result = anonymize_response_data(
            rubric_assessment_submission(), data_type="submissions"
        )
        assert_no_pii(result)

        assessment = result["full_rubric_assessment"]
        assert assessment["assessor_name"].startswith("Student_")
        assert assessment["assessor"]["display_name"] == assessment["assessor_name"]
        assert "[EMAIL_REDACTED]" in assessment["data"][0]["comments"]
        assert assessment["data"][0]["points"] == 4

    def test_submitter_and_reviewer_get_different_pseudonyms(self):
        result = anonymize_response_data(submissions_with_comments(), data_type="submissions")
        from canvas_mcp.core.anonymization import generate_anonymous_id
        assert result[0]["submission_comments"][0]["author_name"] == generate_anonymous_id(202)
        assert generate_anonymous_id(202) != generate_anonymous_id(101)


# ---------------------------------------------------------------------------
# Structural invariants
# ---------------------------------------------------------------------------

class TestKeySetInvariant:
    """Anonymization may remove information, never invent it."""

    @pytest.mark.parametrize("name", sorted(ALL_FIXTURES))
    def test_no_keys_added(self, name):
        original = ALL_FIXTURES[name]()
        result = anonymize_response_data(original, data_type="submissions")
        before = collect_key_sets(ALL_FIXTURES[name]())
        after = collect_key_sets(result)
        assert set(after) == set(before)
        for path, keys in before.items():
            assert after[path] == keys, f"key set changed at {path}"

    def test_minimal_user_gains_no_fabricated_fields(self):
        record = {"id": 101, "name": "John Doe", "login_id": "jdoe2"}
        result = scrub_identity(record)
        assert set(result.keys()) == {"id", "name", "login_id"}
        assert "email" not in result
        assert "sortable_name" not in result


class TestNonUserObjectsPreserved:
    """The bare-`name` fabrication defect: id + name is not enough."""

    def test_bare_name_without_user_signal_preserved(self):
        group = {"id": 77, "name": "Project Teams", "members_count": 4}
        result = scrub_identity(group)
        assert result["name"] == "Project Teams"
        assert result["members_count"] == 4

    def test_course_name_not_rewritten(self):
        course = {"id": 55, "name": "BADM 350 Fall 2026", "course_code": "BADM350"}
        result = anonymize_response_data(course, data_type="users")
        assert result["name"] == "BADM 350 Fall 2026"

    def test_course_with_enrollments_not_treated_as_user(self):
        """Course objects carry an `enrollments` list too — that must not
        corroborate them as a person and rewrite the course title."""
        course = {
            "id": 55,
            "name": "BADM 350 Fall 2026",
            "course_code": "BADM350",
            "enrollments": [{"type": "teacher", "role": "TeacherEnrollment"}],
        }
        result = anonymize_response_data(course, data_type="users")
        assert result["name"] == "BADM 350 Fall 2026"

    def test_attachment_display_name_preserved(self):
        submission = {
            "id": 7003,
            "user_id": 101,
            "attachments": [{"id": 88, "display_name": "essay.pdf", "size": 1024}],
        }
        # scrub_identity alone (no submission content redaction) must leave the
        # filename intact — it is not a person's name.
        result = scrub_identity(submission)
        assert result["attachments"][0]["display_name"] == "essay.pdf"


class TestDataTypeRouting:

    def test_explicit_data_type_suppresses_duck_typing(self):
        """An assignment carrying a `message` key must not be treated as a
        discussion, and its long description must still be truncated."""
        assignment = {
            "id": 42,
            "name": "Reflection Essay",
            "due_at": "2026-03-01T23:59:00Z",
            "message": "See instructions",
            "description": "x" * 1200,
        }
        result = anonymize_response_data(assignment, data_type="assignments")
        assert result["description"] == "[LONG_DESCRIPTION_REDACTED_FOR_PRIVACY]"
        assert result["name"] == "Reflection Essay"

    def test_explicit_users_type_does_not_redact_submission_content(self):
        record = {"id": 1, "user_id": 101, "submitted_at": "2026-03-01T00:00:00Z", "body": "hello"}
        result = anonymize_response_data(record, data_type="users")
        assert result["body"] == "hello"

    def test_unknown_data_type_falls_back_to_duck_typing(self):
        record = {"id": 1, "user_id": 101, "submitted_at": "2026-03-01T00:00:00Z", "body": "hello"}
        result = anonymize_response_data(record, data_type="general")
        assert result["body"].startswith("[CONTENT_REDACTED")

    def test_data_type_detection_is_segment_aware(self):
        assert _determine_data_type("/courses/1/assignments/2/submissions") == "submissions"
        assert _determine_data_type("/courses/1/assignments/2/submissions?include[]=user") == "submissions"
        assert _determine_data_type("/courses/1/pages/submissions") == "general"
        assert _determine_data_type("/courses/1/pages/users") == "general"
        assert _determine_data_type("/courses/1/assignments") == "assignments"


class TestFailClosed:
    """An unrecognized shape on a sensitive endpoint still gets scrubbed."""

    def test_unknown_shape_still_identity_scrubbed(self):
        payload = {
            "meta": {"page": 1},
            "records": [
                {
                    "wrapper_id": 9,
                    "person": {
                        "id": 101,
                        "sortable_name": "Doe, John",
                        "email": "jdoe2@illinois.edu",
                        "sis_user_id": "670001234",
                    },
                }
            ],
        }
        result = anonymize_response_data(payload, data_type="something_new")
        assert_no_pii(result)
        assert result["meta"]["page"] == 1

    def test_deeply_nested_identity_scrubbed(self):
        payload = {"a": {"b": {"c": [{"user": {"id": 101, "name": "Alice Example",
                                               "login_id": "jdoe2"}}]}}}
        result = anonymize_response_data(payload)
        assert_no_pii(result)


class TestIdempotence:

    @pytest.mark.parametrize("name", sorted(ALL_FIXTURES))
    @pytest.mark.parametrize("data_type", ["users", "submissions", "discussions", "general"])
    def test_double_application_is_stable(self, name, data_type):
        once = anonymize_response_data(ALL_FIXTURES[name](), data_type=data_type)
        twice = anonymize_response_data(once, data_type=data_type)
        assert twice == once

    def test_tool_layer_double_anonymization_is_stable(self):
        """Tool modules call anonymize_response_data() on data the client layer
        already anonymized. That double pass must be a no-op."""
        client_pass = anonymize_response_data(users_with_enrollments(), data_type="users")
        tool_pass = anonymize_response_data(client_pass, data_type="users")
        assert tool_pass == client_pass
        assert_no_pii(tool_pass)


# ---------------------------------------------------------------------------
# Self-submission carve-out
# ---------------------------------------------------------------------------

class TestSelfSubmissionEndpoint:

    @pytest.mark.parametrize("endpoint", [
        "/courses/123/assignments/456/submissions/self",
        "/courses/123/assignments/456/submissions/self?include[]=submission_comments",
        "/sections/45/assignments/456/submissions/self",
    ])
    def test_self_submission_not_anonymized(self, endpoint):
        assert _should_anonymize_endpoint(endpoint) is False

    @pytest.mark.parametrize("endpoint", [
        "/courses/123/assignments/456/submissions/123",
        "/courses/123/assignments/456/submissions",
        "/courses/123/assignments/456/submissions/selfie",
        "/courses/123/assignments/456/submissions/self_review",
        "/courses/123/students/submissions",
    ])
    def test_other_submission_endpoints_still_anonymized(self, endpoint):
        assert _should_anonymize_endpoint(endpoint) is True

    def test_self_carveout_does_not_disable_other_sensitive_segments(self):
        # A path that also touches /users must still anonymize.
        assert _should_anonymize_endpoint(
            "/courses/123/users/9/assignments/456/submissions/self"
        ) is True

    def test_self_submission_content_preserved_end_to_end(self):
        """The gate is the only thing standing between a student and their own
        submitted text — assert the anonymizer would otherwise redact it."""
        submission = {
            "id": 7004,
            "user_id": 101,
            "submitted_at": "2026-03-01T12:00:00Z",
            "body": "My own essay text",
            "url": "https://example.com/my-work",
        }
        assert _should_anonymize_endpoint(
            "/courses/1/assignments/2/submissions/self"
        ) is False
        redacted = anonymize_response_data(submission, data_type="submissions")
        assert redacted["body"].startswith("[CONTENT_REDACTED")


class TestUserOnlyNullFields:
    """time_zone/locale are personal on user records, institutional elsewhere
    (codex review P2: the old anonymize_user_data nulled both on users)."""

    def test_user_time_zone_and_locale_nulled(self):
        user = {
            "id": 101,
            "name": "Jane Doe",
            "sortable_name": "Doe, Jane",
            "time_zone": "America/Chicago",
            "locale": "en",
        }
        result = anonymize_response_data(user, data_type="users")
        assert result["time_zone"] is None
        assert result["locale"] is None

    def test_course_time_zone_preserved(self):
        course = {
            "id": 12,
            "name": "BADM 350 Fall 2026",
            "course_code": "BADM350",
            "time_zone": "America/Chicago",
        }
        result = anonymize_response_data(course, data_type="general")
        assert result["time_zone"] == "America/Chicago"
        assert result["name"] == "BADM 350 Fall 2026"


class TestAvatarSuffixMatching:
    """Live replay found avatar URLs surviving under variant key names
    (assessor_avatar_url, avatar_path) not covered by the explicit list."""

    @pytest.mark.parametrize("key", [
        "avatar_url", "avatar_image_url", "assessor_avatar_url", "avatar_path",
    ])
    def test_avatar_variant_nulled(self, key):
        record = {"id": 101, "user_id": 101, key: "https://canvas/avatars/101"}
        result = anonymize_response_data(record, data_type="submissions")
        assert result[key] is None

    def test_non_avatar_url_preserved(self):
        record = {"id": 5, "html_url": "https://canvas/courses/1/users/101"}
        result = anonymize_response_data(record, data_type="general")
        assert result["html_url"] == "https://canvas/courses/1/users/101"
