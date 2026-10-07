"""Student group tools: the caller's own Canvas groups, members and files.

Everything here is read-only and scoped to groups the caller BELONGS to.

A group's discussions and announcements are not read here. The shared
discussion tools take a ``group_id`` (``list_discussion_topics``,
``get_discussion_with_replies`` and the other discussion readers), and
``list_my_groups`` prints the course ID and group ID those calls need.

Why membership is checked here rather than left to Canvas
---------------------------------------------------------
Canvas can authorize group reads more widely than membership: course-level
group permissions, self-signup categories (whose rosters students see in
order to pick a group) and public community groups may let a token read a
group it is not in. A 401 from Canvas is therefore not a membership oracle,
and relying on it would let an agent browse other teams' rosters and files
whenever an institution's settings happen to allow it. Before any group-scoped
request, every tool re-reads ``/users/self/groups`` (the caller's own active
groups) and refuses a group that is not on it. That costs one extra request
per call and fails closed: if the membership list cannot be read, nothing else
is requested.

Privacy
-----------------------------
- ``/groups/{id}/users`` is a roster of classmates. It stays at the client
  layer's ``full`` anonymization tier (``core/client.py``, the ``users``
  segment rule), exactly like every other roster endpoint: with
  ``ENABLE_DATA_ANONYMIZATION`` on, names are pseudonymized and IDs kept. A
  student who wants real names can turn anonymization off for their own
  server. Independently of that setting, ``get_group_members`` prints only the
  member's ID and name — never an email, login ID or SIS ID — because the
  output is built from an explicit field allowlist.
- A group description is not a free-text field at the client layer (elsewhere
  ``description`` is instructor content), so ``list_my_groups`` applies
  ``scrub_free_text`` to it when anonymization is on.
- ``/users/self/groups`` lands in the ``full`` tier through its ``users``
  segment. Group records carry ``avatar_url``, which used to make the scrubber
  mistake a group for a person and rename it ``Student_<hash>``;
  ``group_category_id`` is now a non-person marker in ``core/anonymization.py``.

All Canvas-authored text (group names and descriptions, file names, member
names) is fenced at the output boundary (issue 239): group members write most
of it.
"""

from __future__ import annotations

import html
import re
from typing import Any

from fastmcp import FastMCP
from mcp.types import ToolAnnotations

from ..core.anonymization import scrub_free_text
from ..core.cache import get_course_code, resolve_numeric_course_id
from ..core.client import fetch_all_paginated_results
from ..core.config import get_config
from ..core.dates import format_date
from ..core.file_validation import format_file_size
from ..core.untrusted_content import fence_untrusted, fence_untrusted_inline
from ..core.validation import coerce_canvas_id, validate_params

_INVALID_GROUP_ID = (
    "Error: group_id must be a numeric Canvas group ID. "
    "Use list_my_groups to find it."
)

_VALID_FILE_SORTS = frozenset(
    {"name", "size", "created_at", "updated_at", "content_type"}
)

# make_canvas_request starts an HTTP failure with this prefix, then appends the
# response body. Anchored so a status-looking string inside that body (or inside
# another kind of failure text) can never be mistaken for the real status.
_HTTP_STATUS = re.compile(r"HTTP error: (\d{3})(?!\d)")
_TAG = re.compile(r"<[^>]+>")
# A bare MIME type (type/subtype). Group files are uploaded by classmates and
# Canvas's upload preflight takes a client-supplied content_type, so anything
# that is not a plain MIME token is not printed: ASCII only (``\w`` would admit
# Unicode), no whitespace, a registered top-level type, and a hard length cap.
_MIME_TOP_LEVEL = (
    "application|audio|chemical|font|haptics|image|message|model|multipart|text|video"
)
_MIME_TYPE = re.compile(
    rf"(?:{_MIME_TOP_LEVEL})/[A-Za-z0-9][A-Za-z0-9.+-]*", re.IGNORECASE
)
_MAX_MIME_LENGTH = 100


def _safe_content_type(raw: object) -> str:
    """The content type if it is a plain, short MIME token, else a placeholder."""
    if (
        isinstance(raw, str)
        and len(raw) <= _MAX_MIME_LENGTH
        and _MIME_TYPE.fullmatch(raw)
    ):
        return raw
    return "unknown type"


def _scrub(text: str) -> str:
    """Redact emails/phones/SSNs when data anonymization is on.

    Covers group-member-authored text the client-layer tier does not scrub:
    group descriptions (``description`` is not a free-text field there,
    because elsewhere it is instructor content).
    """
    if get_config().enable_data_anonymization:
        return str(scrub_free_text(text))
    return text


def _http_status(error: object) -> int | None:
    """The HTTP status embedded in a make_canvas_request error, if any."""
    match = _HTTP_STATUS.match(str(error))
    return int(match.group(1)) if match else None


def _is_error(response: Any) -> bool:
    return isinstance(response, dict) and "error" in response


def _plain_text(markup: object) -> str:
    """Strip HTML tags and decode entities for display. Never sent back to Canvas."""
    if not isinstance(markup, str) or not markup:
        return ""
    return html.unescape(_TAG.sub("", markup)).strip()


_MAX_ERROR_DETAIL = 200


def _failure_reason(error: object) -> str:
    """A short, safe reason for a failed Canvas request.

    ``make_canvas_request`` embeds the response body in its error string
    (``HTTP error: 500, Text: ...``). That body is not ours to trust, and a
    proxy or gateway page can carry text aimed at the model, so only the HTTP
    status is surfaced for an HTTP failure. Any other failure text (a timeout,
    a connection error) is truncated and fenced as untrusted.
    """
    status = _http_status(error)
    if status is not None:
        return f"HTTP {status}"
    detail = str(error).strip()[:_MAX_ERROR_DETAIL] or "no detail"
    return fence_untrusted_inline(detail, "Canvas error")


def _access_error(action: str, group_id: str, error: object) -> str:
    """A clear message for a failed group-scoped read."""
    status = _http_status(error)
    if status in (401, 403):
        return (
            f"Error: Canvas did not allow you to {action} for group {group_id} "
            f"(HTTP {status}). The group may have this feature turned off, or "
            "your instructor may have restricted it."
        )
    if status == 404:
        return f"Error: Canvas could not find that resource in group {group_id} (HTTP 404)."
    return f"Error: could not {action} for group {group_id}: {_failure_reason(error)}"


async def _fetch_my_groups(params: dict[str, Any] | None = None) -> list[dict] | dict:
    """GET /users/self/groups — the caller's active groups, all pages."""
    query: dict[str, Any] = {"per_page": 100}
    if params:
        query.update(params)
    groups = await fetch_all_paginated_results("/users/self/groups", query)
    if _is_error(groups):
        return {"error": str(groups.get("error"))}
    if not isinstance(groups, list):
        return {"error": "Unexpected response from Canvas for /users/self/groups"}
    return [g for g in groups if isinstance(g, dict)]


async def _require_membership(raw_group_id: str | int) -> tuple[str, dict | None, str | None]:
    """Validate a group ID and confirm the caller belongs to that group.

    Returns ``(group_id, group, error)``; exactly one of ``group`` / ``error``
    is set. The ID is validated BEFORE any request, and the membership list is
    read fresh on every call so a student who left a group loses access
    immediately. Fails closed when the list cannot be read.
    """
    group_id = coerce_canvas_id(raw_group_id)
    if group_id is None:
        return "", None, _INVALID_GROUP_ID

    groups = await _fetch_my_groups()
    if isinstance(groups, dict):
        return group_id, None, (
            "Error: could not confirm your membership in group "
            f"{group_id}, so nothing was read: {_failure_reason(groups.get('error'))}"
        )

    for group in groups:
        if str(group.get("id")) == group_id:
            return group_id, group, None

    return group_id, None, (
        f"Error: you are not a member of group {group_id}. These tools only "
        "read groups you belong to; use list_my_groups to see them."
    )


async def _group_label(group: dict) -> str:
    """Fenced group name plus its course code (or parent context name)."""
    name = fence_untrusted_inline(group.get("name") or "Unnamed group", "group name")
    course_id = group.get("course_id")
    if group.get("context_type") == "Course" and course_id:
        course_display = await get_course_code(course_id) or course_id
        return f"{name} in {course_display}"
    context_name = group.get("context_name")
    if context_name:
        return f"{name} in {fence_untrusted_inline(context_name, 'group context name')}"
    return name


def register_student_group_tools(mcp: FastMCP) -> None:
    """Register the read-only student group tools."""

    @mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
    @validate_params
    async def list_my_groups(course_identifier: str | int | None = None) -> str:
        """List the Canvas groups you belong to (project teams, study groups).

        Shows each group's name, ID, course and course ID, group category ID
        and member count. Use the group ID with get_group_members and
        list_group_files.

        To read a group's discussions or announcements, use the shared
        discussion tools with the course ID and group ID printed here:
        list_discussion_topics(course_identifier, group_id=...,
        include_announcements=True) lists them, then
        get_discussion_with_replies(course_identifier, topic_id,
        include_replies=True, group_id=...) reads one with its replies.

        Args:
            course_identifier: Only show your groups in this course
                (course code or Canvas ID). Default: groups in every course.
        """
        params: dict[str, Any] = {}
        course_id: str | None = None
        if course_identifier is not None:
            if not str(course_identifier).strip():
                # A filter that was given but is unusable must not quietly
                # widen the answer to every course.
                return (
                    "Error: course_identifier is blank. Leave it out to list "
                    "your groups in every course, or give a course code or "
                    "numeric Canvas course ID."
                )
            # The filter below compares numeric IDs, so an unresolved code or
            # SIS ID would silently match nothing; fail loudly instead.
            course_id, course_error = await resolve_numeric_course_id(course_identifier)
            if course_id is None:
                return f"Error: {course_error}"
            # Documented filter on /users/self/groups. Canvas has no course
            # filter on this endpoint, so the course match is done below.
            params["context_type"] = "Course"

        groups = await _fetch_my_groups(params)
        if isinstance(groups, dict):
            return f"Error fetching your groups: {_failure_reason(groups.get('error'))}"

        if course_id is not None:
            groups = [g for g in groups if str(g.get("course_id")) == course_id]

        if not groups:
            if course_id is not None:
                course_display = await get_course_code(course_id) or course_identifier
                return f"You are not in any groups in {course_display}."
            return "You are not in any Canvas groups."

        lines = [f"Your groups ({len(groups)}):", ""]
        has_course_group = False
        for group in groups:
            lines.append(f"Group: {await _group_label(group)}")
            lines.append(f"  ID: {group.get('id')}")
            if group.get("context_type") == "Course" and group.get("course_id"):
                has_course_group = True
                lines.append(f"  Course ID: {group.get('course_id')}")
            category_id = group.get("group_category_id")
            if category_id is not None:
                lines.append(f"  Group category ID: {category_id}")
            members = group.get("members_count")
            lines.append(
                f"  Members: {members if members is not None else 'unknown'}"
            )
            description = _scrub(_plain_text(group.get("description")))
            if description:
                lines.append("  Description:")
                lines.append(fence_untrusted(description, "group description"))
            lines.append("")
        if has_course_group:
            lines.append(
                "To read a group's discussions or announcements: "
                "list_discussion_topics(course_identifier=<Course ID>, "
                "group_id=<ID>, include_announcements=True), then "
                "get_discussion_with_replies(course_identifier=<Course ID>, "
                "topic_id=<topic ID>, include_replies=True, group_id=<ID>)."
            )
        return "\n".join(lines).rstrip()

    @mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
    @validate_params
    async def get_group_members(group_id: str | int) -> str:
        """List the members of one of your groups (names and Canvas user IDs).

        Only works for groups you belong to. Never shows email addresses. When
        the server's data anonymization is on (ENABLE_DATA_ANONYMIZATION),
        classmates' names appear as stable pseudonyms; IDs are real.

        Args:
            group_id: Canvas group ID from list_my_groups
        """
        group_id, group, error = await _require_membership(group_id)
        if error or group is None:
            return error or _INVALID_GROUP_ID

        # exclude_inactive defaults to false: without it, members whose course
        # enrollment was deactivated or dropped are listed as current members.
        members = await fetch_all_paginated_results(
            f"/groups/{group_id}/users", {"per_page": 100, "exclude_inactive": True}
        )
        if _is_error(members):
            return _access_error("list members", group_id, members.get("error"))
        # Count only what is printed, so the header never promises more members
        # than the list shows.
        members = [m for m in members if isinstance(m, dict)] if isinstance(members, list) else []
        if not members:
            return f"No members are listed for group {group_id}."

        lines = [f"Members of {await _group_label(group)} ({len(members)}):", ""]
        for member in members:
            # Explicit allowlist: id and display name only. Email, login_id
            # and SIS identifiers are never printed, whatever Canvas returns
            # and whether or not anonymization is enabled.
            name = member.get("name") or member.get("short_name") or "Unnamed user"
            lines.append(
                f"  - {fence_untrusted_inline(name, 'user name')} (ID: {member.get('id')})"
            )
        if get_config().enable_data_anonymization:
            lines.append("")
            lines.append(
                "Note: data anonymization is on, so classmates' names are pseudonyms."
            )
        return "\n".join(lines)

    @mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
    @validate_params
    async def list_group_files(
        group_id: str | int,
        search_term: str | None = None,
        sort: str = "updated_at",
        order: str = "desc",
    ) -> str:
        """List the files stored in one of your groups.

        Args:
            group_id: Canvas group ID from list_my_groups
            search_term: Only files whose name contains this text (2+ characters)
            sort: name, size, created_at, updated_at or content_type (default: updated_at)
            order: "asc" or "desc" (default: desc)
        """
        if sort not in _VALID_FILE_SORTS:
            return (
                f"Error: invalid sort '{sort}'. Use one of: "
                f"{', '.join(sorted(_VALID_FILE_SORTS))}."
            )
        if order not in ("asc", "desc"):
            return f"Error: invalid order '{order}'. Use 'asc' or 'desc'."
        search_term = (search_term or "").strip() or None
        if search_term is not None and len(search_term) < 2:
            # Canvas rejects shorter search terms with a 400.
            return "Error: search_term must be at least 2 characters."

        group_id, group, error = await _require_membership(group_id)
        if error or group is None:
            return error or _INVALID_GROUP_ID

        params: dict[str, Any] = {"per_page": 100, "sort": sort, "order": order}
        if search_term:
            params["search_term"] = search_term

        files = await fetch_all_paginated_results(f"/groups/{group_id}/files", params)
        if _is_error(files):
            return _access_error("list files", group_id, files.get("error"))
        files = [f for f in files if isinstance(f, dict)] if isinstance(files, list) else []
        if not files:
            if search_term:
                return f"No files in group {group_id} match that search."
            return f"No files in group {group_id}."

        lines = [f"Files in {await _group_label(group)}:", ""]
        for item in files:
            name = item.get("display_name") or item.get("filename") or "unknown"
            size = format_file_size(item.get("size") or 0)
            content_type = _safe_content_type(item.get("content-type"))
            updated = format_date(item.get("updated_at"))
            lines.append(
                f"  ID: {item.get('id')} | {fence_untrusted_inline(name, 'file name')} "
                f"({size}, {content_type}, updated {updated})"
            )
        lines.append("")
        lines.append(f"Total: {len(files)} file(s)")
        return "\n".join(lines)
