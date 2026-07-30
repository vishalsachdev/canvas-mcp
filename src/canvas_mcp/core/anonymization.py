"""
Data anonymization utilities for Canvas MCP server.

This module provides functions to anonymize student data before sending
to AI systems, ensuring FERPA compliance and student privacy protection.
"""

import hashlib
import re
from typing import Any

# Global anonymization mapping cache
_anonymization_cache: dict[str, str] = {}

# --------------------------------------------------------------------------
# Field policy for the recursive identity scrubber (issue #166)
# --------------------------------------------------------------------------

#: Person-name fields that are unambiguous: whenever one of these keys is
#: present it holds a human's name/handle, never a file or object label.
STRICT_IDENTITY_FIELDS = frozenset({
    'short_name',
    'sortable_name',
    'user_name',
    'author_name',
    'assessor_name',
    'grader_name',
    'email',
    'primary_email',
    'unconfirmed_email',
    'contact_info',
    'login_id',
})

#: Keys whose pseudonym must be rendered as an email address rather than a bare
#: ``Student_<hash>``. Canvas returns the caller's address under several names
#: (``/users/self/profile`` alone can carry ``primary_email``,
#: ``unconfirmed_email`` and ``contact_info``), and a downstream consumer that
#: parses these as addresses would choke on a bare pseudonym.
EMAIL_SHAPED_FIELDS = frozenset({
    'email',
    'primary_email',
    'unconfirmed_email',
    'contact_info',
})

#: Name fields that are ambiguous — Canvas uses them for courses, groups,
#: modules, pages and file attachments as well as for people. These are only
#: rewritten when the containing dict carries a corroborating user signal
#: (see ``USER_SIGNAL_FIELDS`` / ``USER_CONTAINER_KEYS`` / user-ish id keys).
#:
#: ``full_name`` is deliberately ambiguous rather than strict: it is exactly the
#: field the ``free_text`` endpoint tier preserves (a conversation participant's
#: name in the caller's own inbox), while on a user profile the same key is PII
#: and gets pseudonymised. ``unique_id`` is ambiguous because Canvas reuses it
#: on non-person objects (LTI tools, outcome imports) as an opaque key.
AMBIGUOUS_IDENTITY_FIELDS = frozenset({
    'name',
    'display_name',
    'full_name',
    'unique_id',
})

#: All identity fields, for callers that just want the union.
IDENTITY_FIELDS = STRICT_IDENTITY_FIELDS | AMBIGUOUS_IDENTITY_FIELDS

#: Fields that carry direct identifiers / imagery and are nulled outright.
#: ``pronouns`` and ``pronunciation`` live here rather than in IDENTITY_FIELDS:
#: replacing a pronoun set or a name-pronunciation guide with a
#: ``Student_<hash>`` pseudonym would be nonsense, and a pronunciation string
#: reconstructs the name it describes. Dropping the value is correct.
NULL_FIELDS = frozenset({
    'sis_user_id',
    'integration_id',
    'sis_login_id',
    'avatar_url',
    'avatar_image_url',
    'bio',
    'pronouns',
    'pronunciation',
})

#: Profile fields nulled only on records that look like a person. Courses and
#: terms also carry ``time_zone`` (and could carry ``locale``), where the value
#: is institutional, not personal — nulling it there would be over-reach.
#: ``address`` is container-scoped for the same reason: on a
#: ``communication_channels[]`` entry it is the student's email or phone, while
#: on a calendar event or an account it is a street address of a building.
USER_ONLY_NULL_FIELDS = frozenset({
    'time_zone',
    'locale',
    'address',
})


def _is_avatar_field(key_lower: str) -> bool:
    """Whether a key names an avatar image reference in any Canvas variant.

    Canvas scatters avatar URLs under many names (``avatar_url``,
    ``avatar_image_url``, ``assessor_avatar_url``, ``avatar_path``); suffix
    matching catches the variants an explicit list would miss.
    """
    return 'avatar' in key_lower and (
        key_lower.endswith('url') or key_lower.endswith('path')
    )

#: Keys searched, in order, for the id that a record's identity fields are
#: keyed to. ``id`` is only used when the record itself looks like a user
#: (otherwise it is an enrollment/comment/submission id and keying to it would
#: mis-attribute the pseudonym).
USER_ID_KEYS = ('user_id', 'author_id', 'assessor_id', 'grader_id')

#: Presence of any of these keys corroborates "this dict describes a person".
USER_SIGNAL_FIELDS = frozenset({
    'sortable_name',
    'short_name',
    'login_id',
    'email',
    'sis_user_id',
    'sis_login_id',
    'avatar_url',
    'avatar_image_url',
    'enrollments',
})

#: Keys that positively identify a record as NOT a person. Course objects also
#: carry an ``enrollments`` list, which would otherwise corroborate them as a
#: user and get the course title rewritten as a student pseudonym.
NON_USER_MARKER_FIELDS = frozenset({
    'course_code',
    'sis_course_id',
    'enrollment_term_id',
})

#: Dict keys whose *value* is by convention a user record. Children reached
#: through one of these inherit user context, so their ambiguous name fields and
#: user-only null fields apply without needing their own corroborating signal.
#: ``communication_channels`` / ``pseudonyms`` are the ``/users/self/profile``
#: sub-objects that hold the caller's addresses and login handles.
USER_CONTAINER_KEYS = frozenset({
    'user',
    'author',
    'assessor',
    'grader',
    'editor',
    'submitter',
    'participant',
    'student',
    'observed_user',
    'communication_channels',
    'pseudonyms',
})

#: Free-text fields that get PII regex scrubbing wherever they are found.
#: ``last_message`` / ``last_authored_message`` are the conversation-list
#: previews: Canvas inlines the first ~255 characters of the message body there,
#: so they carry exactly the addresses and phone numbers ``body`` does.
FREE_TEXT_FIELDS = frozenset({
    'message',
    'comment',
    'comments',
    'body',
    'last_message',
    'last_authored_message',
})

#: data_type values the router knows about. An explicit value outside this set
#: (e.g. the legacy "test_endpoint" / "general") falls back to duck-typing;
#: an explicit value *inside* it suppresses duck-typing entirely.
KNOWN_DATA_TYPES = frozenset({'users', 'discussions', 'submissions', 'assignments'})

_EMAIL_RE = re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b')
_PHONE_RE = re.compile(r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b')
_SSN_RE = re.compile(r'\b\d{3}-\d{2}-\d{4}\b')


def scrub_free_text(value: Any) -> Any:
    """Redact emails, phone numbers and SSNs from a free-text string."""
    if not isinstance(value, str) or not value:
        return value
    value = _SSN_RE.sub('[SSN_REDACTED]', value)
    value = _EMAIL_RE.sub('[EMAIL_REDACTED]', value)
    value = _PHONE_RE.sub('[PHONE_REDACTED]', value)
    return value


def generate_anonymous_id(real_id: str | int, prefix: str = "Student") -> str:
    """Generate a consistent anonymous ID for a given real ID.

    Args:
        real_id: The real Canvas user ID or identifier
        prefix: Prefix for the anonymous ID (default: "Student")

    Returns:
        Consistent anonymous identifier
    """
    real_id_str = str(real_id)

    # Check cache first
    if real_id_str in _anonymization_cache:
        return _anonymization_cache[real_id_str]

    # Generate consistent hash-based ID
    hash_object = hashlib.sha256(real_id_str.encode())
    hash_hex = hash_object.hexdigest()

    # Use first 8 characters for readability
    anonymous_id = f"{prefix}_{hash_hex[:8]}"

    # Cache the mapping
    _anonymization_cache[real_id_str] = anonymous_id

    return anonymous_id


def _looks_like_user_record(record: dict[str, Any], user_context: bool) -> bool:
    """Whether `record` describes a person (vs. a course/group/file/module).

    Corroboration is required before rewriting the ambiguous `name` /
    `display_name` keys, so that non-user objects keep their labels.
    """
    if any(field in record for field in NON_USER_MARKER_FIELDS):
        return False
    if user_context:
        return True
    if any(field in record for field in USER_SIGNAL_FIELDS):
        return True
    return any(record.get(key) not in (None, '') for key in USER_ID_KEYS)


def _record_identity_id(record: dict[str, Any], user_context: bool) -> Any:
    """The id the record's identity fields should be pseudonymised against."""
    for key in USER_ID_KEYS:
        value = record.get(key)
        if value not in (None, ''):
            return value
    if _looks_like_user_record(record, user_context):
        own_id = record.get('id')
        if own_id not in (None, ''):
            return own_id
    return None


def scrub_identity(
    node: Any,
    inherited_id: Any = None,
    user_context: bool = False,
    *,
    scrub_text: bool = True,
    scrub_display_names: bool = True,
) -> Any:
    """Recursively remove personal identity from an arbitrary Canvas payload.

    This is the *baseline* protection applied to every response the endpoint
    gate marks as sensitive. It walks lists and dicts uniformly, so identity
    fields nested at any depth (``enrollments[].sis_user_id``,
    ``submission_comments[].author.display_name``,
    ``full_rubric_assessment.assessor_name``) are scrubbed rather than passed
    through by a top-level-only typed handler (issue #166).

    Invariants:
    - It NEVER adds a key that was not already present (no fabricated
      email/login_id/sortable_name on records that never had them).
    - Identity fields are keyed to the nearest enclosing user id, so the same
      student maps to the same pseudonym across a response.
    - It is idempotent: scrubbed output is a fixed point.

    Args:
        node: Any JSON-ish value (dict, list or primitive).
        inherited_id: Id of the nearest enclosing user-ish record, used when a
            nested dict carries a name but no id of its own.
        user_context: True when the node was reached through a key that is by
            convention a user record (``user``, ``author``, ``assessor``, ...).
        scrub_text: When False, leave :data:`FREE_TEXT_FIELDS` (``body``,
            ``message``, ``comment``, the conversation previews) untouched. Used
            by the ``identity`` endpoint tier, where the free text is
            instructor-authored course content and redacting it is a functional
            regression, not a privacy win.
        scrub_display_names: When False, leave :data:`AMBIGUOUS_IDENTITY_FIELDS`
            and bare-string user containers untouched. Used by the ``free_text``
            endpoint tier, where the names belong to the caller's own
            correspondents and pseudonymising them destroys the answer to "who
            emailed me?". :data:`STRICT_IDENTITY_FIELDS` and
            :data:`NULL_FIELDS` still always apply.

    Returns:
        A scrubbed copy of `node`.
    """
    if isinstance(node, list):
        return [
            scrub_identity(
                item,
                inherited_id,
                user_context,
                scrub_text=scrub_text,
                scrub_display_names=scrub_display_names,
            )
            for item in node
        ]

    if not isinstance(node, dict):
        return node

    looks_user = _looks_like_user_record(node, user_context)
    identity_id = _record_identity_id(node, user_context)
    if identity_id in (None, ''):
        identity_id = inherited_id

    anonymous_id = generate_anonymous_id(identity_id) if identity_id not in (None, '') else None

    scrubbed: dict[str, Any] = {}
    for key, value in node.items():
        key_lower = key.lower() if isinstance(key, str) else key

        if (
            key_lower in NULL_FIELDS
            or (isinstance(key_lower, str) and _is_avatar_field(key_lower))
            or (key_lower in USER_ONLY_NULL_FIELDS and looks_user)
        ):
            scrubbed[key] = None
            continue

        if key_lower in STRICT_IDENTITY_FIELDS or (
            scrub_display_names and key_lower in AMBIGUOUS_IDENTITY_FIELDS and looks_user
        ):
            scrubbed[key] = _pseudonymise_field(key_lower, value, anonymous_id)
            continue

        # Canvas sometimes returns a bare name string where a user object is
        # expected (e.g. "author": "Bob Smith") — that is an identity value.
        if scrub_display_names and key_lower in USER_CONTAINER_KEYS and isinstance(value, str):
            scrubbed[key] = _pseudonymise_field('name', value, anonymous_id)
            continue

        if scrub_text and key_lower in FREE_TEXT_FIELDS and isinstance(value, str):
            scrubbed[key] = scrub_free_text(value)
            continue

        scrubbed[key] = scrub_identity(
            value,
            inherited_id=identity_id,
            user_context=(key_lower in USER_CONTAINER_KEYS),
            scrub_text=scrub_text,
            scrub_display_names=scrub_display_names,
        )

    return scrubbed


def _pseudonymise_field(key_lower: str, value: Any, anonymous_id: str | None) -> Any:
    """Replace one identity field's value, preserving None/empty as-is."""
    if value is None or value == '':
        return value
    if anonymous_id is None:
        return "[REDACTED]"
    if key_lower in EMAIL_SHAPED_FIELDS:
        return f"{anonymous_id.lower()}@example.edu"
    if key_lower == 'login_id':
        return anonymous_id.lower()
    return anonymous_id


def anonymize_user_data(user_data: Any) -> Any:
    """Anonymize a single user (or user-wrapping) record.

    Thin wrapper over :func:`scrub_identity` kept for API compatibility. The
    record is treated as user context, so a bare `name` on it is rewritten.
    """
    if not isinstance(user_data, dict):
        return user_data
    return scrub_identity(user_data, user_context=True)


def anonymize_discussion_entry(entry_data: Any) -> Any:
    """Anonymize a discussion entry (or the /view wrapper dict).

    Thin wrapper over :func:`scrub_identity`; nested replies, ``view``,
    ``new_entries`` and ``participants`` are handled by the uniform recursion.
    """
    if not isinstance(entry_data, dict):
        return entry_data
    return scrub_identity(entry_data)


def _redact_submission_content(submission: dict[str, Any]) -> dict[str, Any]:
    """Redact submitted content (body/url/attachments) on a submission record."""
    user_id = submission.get('user_id')
    if not user_id:
        return submission

    anonymous_id = generate_anonymous_id(user_id)
    redacted = submission.copy()
    for field in ('body', 'url', 'attachments'):
        if field in redacted and redacted[field]:
            if isinstance(redacted[field], str):
                redacted[field] = f"[CONTENT_REDACTED_FOR_{anonymous_id}]"
            else:
                redacted[field] = "[CONTENT_REDACTED]"
    return redacted


def anonymize_submission_data(submission_data: Any) -> Any:
    """Anonymize submission data (identity scrub + submitted-content redaction)."""
    if not isinstance(submission_data, dict):
        return submission_data
    return _redact_submission_content(scrub_identity(submission_data))


def _truncate_long_description(assignment: dict[str, Any]) -> dict[str, Any]:
    """Truncate very long assignment descriptions that may embed student info."""
    description = assignment.get('description')
    if isinstance(description, str) and len(description) > 1000:
        truncated = assignment.copy()
        truncated['description'] = "[LONG_DESCRIPTION_REDACTED_FOR_PRIVACY]"
        return truncated
    return assignment


def anonymize_assignment_data(assignment_data: Any) -> Any:
    """Anonymize assignment data (keep assignment details, drop student info)."""
    if not isinstance(assignment_data, dict):
        return assignment_data
    return _truncate_long_description(scrub_identity(assignment_data))


def _resolve_record_type(record: dict[str, Any], data_type: str) -> str:
    """Resolve which typed refinement applies to `record`.

    An explicit, known `data_type` always wins — duck-typing is only consulted
    when the caller did not state a type. This stops e.g. an assignment record
    that happens to carry a `message` key from being treated as a discussion
    entry, or a course record's `name` from being rewritten as a student's.
    """
    if data_type in KNOWN_DATA_TYPES:
        return data_type
    if 'submitted_at' in record:
        return 'submissions'
    if 'due_at' in record:
        return 'assignments'
    if 'message' in record:
        return 'discussions'
    return 'general'


def _apply_type_refinements(data: Any, data_type: str) -> Any:
    """Apply the record-level refinements layered on top of the identity scrub."""
    if isinstance(data, list):
        return [_apply_type_refinements(item, data_type) for item in data]
    if not isinstance(data, dict):
        return data

    resolved = _resolve_record_type(data, data_type)
    if resolved == 'submissions':
        return _redact_submission_content(data)
    if resolved == 'assignments':
        return _truncate_long_description(data)
    return data


def anonymize_response_data(data: Any, data_type: str = "general") -> Any:
    """Main function to anonymize Canvas API response data.

    Two passes, in order:

    1. :func:`scrub_identity` — the recursive baseline. Runs on every payload
       regardless of shape or `data_type`, so unknown/nested shapes still get
       identity protection (fail-closed).
    2. Typed refinements — submitted-content redaction for submissions and
       long-description truncation for assignments, applied per record.

    Args:
        data: The data to anonymize (can be dict, list, or other types)
        data_type: Type of data being anonymized for specific handling. Values
            outside :data:`KNOWN_DATA_TYPES` fall back to duck-typing.

    Returns:
        Anonymized data structure
    """
    return _apply_type_refinements(scrub_identity(data), data_type)


def create_anonymization_summary(original_count: int, anonymized_count: int, data_type: str) -> str:
    """Create a summary of the anonymization process.

    Args:
        original_count: Number of records before anonymization
        anonymized_count: Number of records after anonymization
        data_type: Type of data that was anonymized

    Returns:
        Summary string for logging/reporting
    """
    return (
        f"Anonymization Summary - {data_type.title()}:\n"
        f"  Original records: {original_count}\n"
        f"  Anonymized records: {anonymized_count}\n"
        f"  Privacy protection: ENABLED\n"
        f"  Unique anonymous IDs generated: {len(_anonymization_cache)}"
    )


def get_anonymization_stats() -> dict[str, Any]:
    """Get statistics about the current anonymization session.

    Returns:
        Dictionary with anonymization statistics
    """
    return {
        "total_anonymized_ids": len(_anonymization_cache),
        "sample_mappings": {
            f"real_id_{i}": anon_id
            for i, anon_id in enumerate(list(_anonymization_cache.values())[:3])
        },
        "privacy_status": "PROTECTED"
    }


def clear_anonymization_cache() -> None:
    """Clear the anonymization cache (use when switching courses/contexts)."""
    global _anonymization_cache
    _anonymization_cache.clear()
