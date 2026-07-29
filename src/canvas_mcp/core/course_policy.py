"""Per-course instructor policy for student write tools (#170).

Faculty need agency over whether AI agents may write in *their* course, separate
from whatever the campus operator has enabled server-wide. Canvas has no native
concept of "agent access", so the policy is expressed as a Canvas-native
artifact that the instructor controls.

Choosing the carrier is the whole security question here, because the policy is
read using the *student's own token*. The artifact must therefore be one the
student cannot author or alter:

* **Syllabus (default).** ``syllabus_body`` is editable only by instructors and
  admins under every standard Canvas role, and readable by enrolled students.
  That makes instructor authorship structural rather than assumed.
* **Page (opt-in).** A course Page is friendlier, but Canvas Pages carry an
  ``editing_roles`` setting that can be ``students``, ``members`` or ``public``,
  and in many courses a student may create a page before any instructor does.
  Reading such a page through the student's own token proves nothing about who
  wrote it. So when this mode is selected the reader **refuses to trust** any
  page whose ``editing_roles`` is not restricted to teachers.

Layering holds strictly: ``STUDENT_WRITE_TOOLS`` is the campus-wide operator
ceiling. A course policy may only further restrict within it, never expand it,
because a course-level artifact is the wrong trust level for widening a
campus-wide permission.

Failure posture: only a definitively read, well-formed artifact can yield
"allow". Malformed content, permission failures, transient errors and
untrusted-provenance artifacts all deny.
"""

from __future__ import annotations

import html
import re
import time
from typing import Any, NamedTuple

from .client import make_canvas_request
from .config import get_config
from .logging import log_warning

_KEY_AGENT_WRITES = "agent_writes"
_KEY_ALLOW_TOOLS = "allow_tools"
_KEY_NOTE = "note"

_TAG_RE = re.compile(r"<[^>]+>")
_KV_RE = re.compile(r"^\s*([a-z_]+)\s*:\s*(.*?)\s*$", re.IGNORECASE)

# Editing roles that keep a Page out of student hands. Canvas returns a
# comma-separated string; anything mentioning students/members/public means the
# artifact is not trustworthy as an instructor statement.
_UNTRUSTED_EDIT_ROLES = ("student", "member", "public")


class CoursePolicy(NamedTuple):
    """Resolved write policy for a single course.

    Attributes:
        allow_writes: Whether agent writes are permitted in this course.
        allow_tools: Optional further narrowing to named tools. ``None`` means
            "every tool the operator has enabled".
        note: Instructor-authored message surfaced on refusal, so a block is
            informative rather than opaque.
        source: Where the decision came from, for diagnostics and tests.
    """

    allow_writes: bool
    allow_tools: frozenset[str] | None
    note: str
    source: str


# course_id -> (expires_at_monotonic, policy)
_policy_cache: dict[str, tuple[float, CoursePolicy]] = {}


def reset_policy_cache() -> None:
    """Discard cached course policies (tests, and immediate policy re-read)."""
    _policy_cache.clear()


def _is_not_found(error_message: str) -> bool:
    """Distinguish "no policy artifact" from "the read failed".

    ``make_canvas_request`` flattens HTTP failures into ``{"error": "HTTP error:
    404"}``, so status is only available as text. The distinction is
    load-bearing: a 404 means the artifact is absent and the configured default
    posture applies, while any other failure means the policy is *unknown* and
    must deny. Collapsing the two would let a Canvas outage grant writes
    everywhere the default is permissive.
    """
    return "404" in error_message


def _strip_html(body: str) -> str:
    """Reduce Canvas rich text to plain lines.

    Instructors type policy into Canvas's WYSIWYG editor, which wraps content in
    markup, so the parser sees through tags rather than demanding clean source.
    """
    text = re.sub(r"<\s*br\s*/?\s*>", "\n", body, flags=re.IGNORECASE)
    text = re.sub(r"</\s*(p|div|li|h[1-6])\s*>", "\n", text, flags=re.IGNORECASE)
    text = _TAG_RE.sub("", text)
    return html.unescape(text)


def parse_policy_body(body: str) -> CoursePolicy:
    """Parse policy text into a :class:`CoursePolicy`.

    Format is ``key: value`` lines, so an instructor can express "no agents
    writing in my course" in one line without knowing YAML or JSON::

        agent_writes: deny

    Text that does not yield a valid ``agent_writes`` value denies. Failing
    closed on malformed policy is the only defensible posture: the alternative
    is a typo silently granting write access.

    Note the marker must be *present* to be meaningful. A syllabus with no
    ``agent_writes`` line is treated as "no policy stated" by the caller, not as
    a malformed policy.
    """
    values: dict[str, str] = {}
    for line in _strip_html(body).splitlines():
        match = _KV_RE.match(line)
        if match:
            key = match.group(1).lower()
            if key in (_KEY_AGENT_WRITES, _KEY_ALLOW_TOOLS, _KEY_NOTE):
                values.setdefault(key, match.group(2).strip())

    note = values.get(_KEY_NOTE, "")
    raw_writes = values.get(_KEY_AGENT_WRITES, "").lower()

    if raw_writes == "allow":
        raw_tools = values.get(_KEY_ALLOW_TOOLS, "")
        tools = frozenset(
            name.strip() for name in raw_tools.replace(",", " ").split() if name.strip()
        )
        return CoursePolicy(True, tools or None, note, "course_artifact")

    if raw_writes == "deny":
        return CoursePolicy(False, None, note, "course_artifact")

    return CoursePolicy(
        allow_writes=False,
        allow_tools=None,
        note=note or (
            "The course's agent policy could not be interpreted. Ask your "
            "instructor to check it."
        ),
        source="course_artifact_malformed",
    )


def _has_policy_marker(text: str) -> bool:
    """Whether text actually states a policy, vs. merely being a syllabus."""
    return bool(re.search(rf"\b{_KEY_AGENT_WRITES}\s*:", _strip_html(text), re.IGNORECASE))


async def _read_policy_text(course_id: str) -> tuple[str | None, str]:
    """Fetch the raw policy text for a course.

    Returns ``(text, status)`` where status is one of ``ok`` (text found),
    ``absent`` (no artifact, apply default), ``error`` (undetermined, deny) or
    ``untrusted`` (artifact exists but its provenance cannot be trusted, deny).
    """
    config = get_config()

    if config.course_agent_policy_source == "page":
        response = await make_canvas_request(
            "get", f"/courses/{course_id}/pages/{config.course_agent_policy_page}"
        )
        if isinstance(response, dict) and "error" in response:
            message = str(response["error"])
            return None, "absent" if _is_not_found(message) else "error"

        # Provenance guard. A page a student could edit is not an instructor
        # statement, regardless of what it says.
        editing_roles = str(response.get("editing_roles") or "").lower()
        if any(role in editing_roles for role in _UNTRUSTED_EDIT_ROLES):
            log_warning(
                "Ignoring course agent policy page: it is not teacher-only",
                course_id=course_id,
                editing_roles=editing_roles,
            )
            return None, "untrusted"

        return str(response.get("body") or ""), "ok"

    # Default: the syllabus, which students cannot edit.
    response = await make_canvas_request(
        "get", f"/courses/{course_id}", params={"include[]": ["syllabus_body"]}
    )
    if isinstance(response, dict) and "error" in response:
        message = str(response["error"])
        return None, "absent" if _is_not_found(message) else "error"

    body = str(response.get("syllabus_body") or "")
    if not _has_policy_marker(body):
        return None, "absent"
    return body, "ok"


def _default_policy() -> CoursePolicy:
    """Posture for a course that states no policy at all."""
    allows = get_config().course_agent_policy_default == "allow"
    return CoursePolicy(
        allow_writes=allows,
        allow_tools=None,
        note="" if allows else (
            "This course has not opted in to agent-assisted writes. Ask your "
            "instructor if you think it should."
        ),
        source="default",
    )


async def get_course_policy(course_id: str | int) -> CoursePolicy:
    """Resolve the effective write policy for one course, with a TTL cache.

    Grants are cached far more briefly than denials. A stale grant is a
    revocation window on an action that consumes a student's limited attempts,
    so it is deliberately short; a stale denial is merely inconvenient.
    """
    config = get_config()
    key = str(course_id)

    cached = _policy_cache.get(key)
    if cached and cached[0] > time.monotonic():
        return cached[1]

    text, status = await _read_policy_text(key)

    if status == "ok" and text is not None:
        policy = parse_policy_body(text)
    elif status == "absent":
        policy = _default_policy()
    elif status == "untrusted":
        policy = CoursePolicy(
            allow_writes=False,
            allow_tools=None,
            note=(
                "This course's agent policy is stored somewhere students can "
                "edit, so it is not being trusted. Ask your instructor to move "
                "it somewhere only teachers can change."
            ),
            source="untrusted_artifact",
        )
    else:
        log_warning(
            "Could not read course agent policy; denying student write",
            course_id=key,
        )
        policy = CoursePolicy(
            allow_writes=False,
            allow_tools=None,
            note=(
                "The course's agent policy could not be checked right now, so "
                "nothing was submitted. Try again shortly."
            ),
            source="read_error",
        )

    ttl = (
        config.course_agent_policy_allow_ttl
        if policy.allow_writes
        else config.course_agent_policy_deny_ttl
    )
    _policy_cache[key] = (time.monotonic() + ttl, policy)
    return policy


async def check_student_write_allowed(
    course_id: str | int, tool_name: str
) -> tuple[bool, str]:
    """Authorize one student write in one course.

    Returns ``(allowed, reason)``; ``reason`` is empty when allowed.

    The operator ceiling is checked first, so a course artifact can never widen
    it. Callers must re-invoke this immediately before the write itself, not
    only during a preview, so a policy change between the two takes effect.
    """
    config = get_config()

    if tool_name not in config.student_write_tools:
        return False, (
            f"'{tool_name}' is not enabled on this server. Student write tools "
            "are off unless an administrator adds them to STUDENT_WRITE_TOOLS."
        )

    if not config.course_agent_policy_enabled:
        return True, ""

    policy = await get_course_policy(course_id)

    if not policy.allow_writes:
        reason = "Agent writes are not permitted in this course."
        return False, f"{reason} {policy.note}".strip()

    if policy.allow_tools is not None and tool_name not in policy.allow_tools:
        reason = f"This course permits agent writes but not '{tool_name}'."
        return False, f"{reason} {policy.note}".strip()

    return True, ""


def assert_no_identity_override(data: dict[str, Any]) -> None:
    """Guard the outbound field set of a student write.

    The submit endpoint (``POST /courses/:id/assignments/:id/submissions``) is
    the one student write path that is *not* structurally self-scoped: Canvas
    accepts ``submission[user_id]`` there to submit on another user's behalf
    when the token carries grading permission. Since a real person can hold
    mixed student and TA enrollments, the tool profile alone does not guarantee
    the token lacks that permission.

    So the guarantee is enforced on the wire instead: no student write may ever
    carry an identity override. Raising here is deliberate. This is a
    programming error, not a user error, and it must never be swallowed into a
    partial success.
    """
    forbidden = {
        "as_user_id",
        "submission[user_id]",
        "user_id",
        "submission[group_id]",
        "group_id",
        "student_id",
    }
    present = forbidden.intersection(data)
    if present:
        raise ValueError(
            "Student write attempted with identity-override field(s): "
            f"{', '.join(sorted(present))}"
        )
