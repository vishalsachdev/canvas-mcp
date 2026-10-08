"""Student "what's new" feed: cross-course announcements and activity.

Two read-only tools that answer "what happened in my classes lately?" without
the caller having to walk their courses one at a time:

- ``list_my_announcements`` reads ``GET /api/v1/announcements``, the one Canvas
  endpoint that returns announcements for several courses in a single query
  (``context_codes[]``). The per-course ``list_announcements`` tool is left as
  it is; this one is deliberately cross-course.
- ``get_my_activity_stream`` reads ``GET /api/v1/users/self/activity_stream``
  and its ``/summary`` twin, the feed behind the Canvas dashboard's "Recent
  Activity" view, and groups it by kind (announcements, discussions, inbox
  conversations, grades and submission comments, notifications).

Neither endpoint changes read state, and neither tool writes anything.

Everything Canvas users wrote — titles, bodies, author names, comments — is
fenced at the output boundary (issue 239). Privacy tiers: ``/announcements``
has no sensitive path segment and stays at ``ANONYMIZE_NONE``, the same
treatment as the ``/discussion_topics`` listings it mirrors (instructor-authored
course content). ``/users/self/activity_stream`` carries a ``users`` route
segment and is NOT on the exact self-only allowlist, so it gets the full
anonymization tier when anonymization is enabled; that is correct for a feed
that embeds other people's discussion posts, messages and comments.
"""

import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Any, Literal

from fastmcp import FastMCP
from mcp.types import ToolAnnotations

from ..core.cache import (
    SIS_COURSE_PREFIX,
    get_course_code,
    match_course,
    resolve_numeric_course_id,
)
from ..core.client import fetch_all_paginated_results
from ..core.dates import _output_tz, format_date, parse_date
from ..core.untrusted_content import fence_untrusted, fence_untrusted_inline
from ..core.validation import coerce_canvas_id, validate_params
from .courses import strip_html_tags

#: Default look-back window for ``list_my_announcements``. Matches Canvas's own
#: default ``start_date`` for ``/announcements`` ("Defaults to 14 days ago").
DEFAULT_ANNOUNCEMENT_DAYS = 14

#: Course context codes sent per ``/announcements`` request. Canvas documents no
#: limit, but every code lengthens the query string and a student can carry
#: dozens of "active" enrollments, so requests are split into bounded chunks.
CONTEXT_CODE_CHUNK_SIZE = 10

MAX_LIMIT = 200
MAX_PREVIEW_CHARS = 2000

_CONTEXT_CODE = re.compile(r"course_(\d+)")
# Grade-shaped tokens shown as-is: letter grades ("A-"), numbers and
# percentages ("92.5", "85%"), and Canvas's fixed pass/fail and excused words.
# Letter-grade text comes from instructor-named grading-scheme entries, so
# anything else is rendered through the inline fence.
_PLAIN_GRADE = re.compile(
    r"(?:[A-F][+-]?|\d{1,4}(?:\.\d{1,2})?%?|complete|incomplete|pass|fail|EX)",
    re.IGNORECASE,
)
_HTTP_STATUS = re.compile(r"^HTTP error: (\d{3})\b")

#: Statuses for which a failed multi-course /announcements request is retried
#: one course at a time. A multi-course permission failure can hide readable
#: courses in the same chunk, so each failed chunk gets its own fallback.
#: Server errors, 429 after the client's own retries,
#: and transport failures concern the whole request and are never fanned out.
_PER_COURSE_RETRY_STATUSES = frozenset({400, 401, 403, 404})

#: Notification categories Canvas defines for its notification preferences.
#: Anything outside this set goes through the inline fence, so free text placed
#: in the field cannot pass as a plain label.
_KNOWN_CATEGORIES = frozenset(
    {
        "Account Notification",
        "Added To Conversation",
        "Administrative",
        "Alert",
        "All Submissions",
        "Announcement",
        "Announcement Created By You",
        "Appointment Availability",
        "Appointment Cancellations",
        "Appointment Signups",
        "Blueprint Sync",
        "Calendar",
        "Content Link Error",
        "Conversation Message",
        "Course Activities",
        "Course Content",
        "Discussion",
        "DiscussionEntry",
        "Due Date",
        "Files",
        "Grading",
        "Invitation",
        "Late Grading",
        "Membership Update",
        "Migration",
        "Other",
        "Recording Ready",
        "Registration",
        "ReportedReply",
        "Student Content",
        "Summaries",
    }
)

#: Activity-stream item ``type`` -> display category, in display order.
_STREAM_CATEGORIES: list[tuple[str, tuple[str, ...]]] = [
    ("Announcements", ("Announcement",)),
    ("Discussions", ("DiscussionTopic", "DiscussionEntry")),
    ("Inbox conversations", ("Conversation",)),
    ("Grades & submission comments", ("Submission",)),
    ("Notifications", ("Message",)),
    ("Peer review requests", ("AssessmentRequest",)),
]
_OTHER_CATEGORY = "Other activity"

_TYPE_FILTERS: dict[str, tuple[str, ...]] = {
    "announcements": ("Announcement",),
    "discussions": ("DiscussionTopic", "DiscussionEntry"),
    "conversations": ("Conversation",),
    "submissions": ("Submission",),
    "notifications": ("Message",),
}

ActivityType = Literal[
    "all", "announcements", "discussions", "conversations", "submissions", "notifications"
]


def _stamp(value: Any) -> datetime | None:
    """A Canvas timestamp as a datetime; None for anything that is not one."""
    return parse_date(value) if isinstance(value, str) else None


def _when(value: Any) -> str:
    """A Canvas timestamp for display.

    ``format_date`` hands back a string it cannot parse unchanged, which would
    put an arbitrary Canvas-supplied value in the output unfenced, so anything
    that is not a timestamp is reported as unknown instead.
    """
    return format_date(value) if _stamp(value) is not None else "unknown date"


_PLAIN_URL = re.compile(r"https?://\S+")


def _link(value: Any) -> str | None:
    """A Canvas link for display: as-is when it is one plain URL, else fenced."""
    if not isinstance(value, str) or not value:
        return None
    if _PLAIN_URL.fullmatch(value):
        return value
    return fence_untrusted_inline(value, "link")


def _count_label(value: Any) -> int | None:
    """A Canvas count as an int, or None when it is anything else."""
    return value if isinstance(value, int) and not isinstance(value, bool) else None


#: Every ``type`` Canvas gives an activity stream item that is printed as it is.
#: Collaborations and web conferences have no category of their own and are
#: listed as other activity.
_KNOWN_STREAM_TYPES = frozenset(
    {t for _, types in _STREAM_CATEGORIES for t in types} | {"Collaboration", "WebConference"}
)


def _category_for(item_type: Any) -> str:
    for label, types in _STREAM_CATEGORIES:
        if item_type in types:
            return label
    return _OTHER_CATEGORY


def _to_canvas_timestamp(dt: datetime) -> str:
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass(frozen=True)
class _Bound:
    """One end of the announcement window.

    ``param`` is what Canvas receives, ``display`` what the caller is shown,
    and ``instant`` is used only for the local start <= end check.
    """

    param: str
    display: str
    instant: datetime
    day: date | None = None


def _day_bound(day: date, *, end: bool) -> _Bound:
    # Sent as YYYY-MM-DD so Canvas applies beginning_of_day / end_of_day in the
    # user's Canvas profile time zone (announcements_api_controller#get_dates),
    # the same day boundaries the Canvas UI uses. The local ordering check uses
    # the configured TIMEZONE as the closest available stand-in.
    edge = datetime.combine(day, time.max if end else time.min, tzinfo=_output_tz())
    text = day.isoformat()
    return _Bound(text, text, edge, day)


def _instant_bound(moment: datetime) -> _Bound:
    stamp = _to_canvas_timestamp(moment)
    return _Bound(stamp, format_date(stamp), moment)


def _parse_bound(raw: str, name: str, *, end: bool) -> _Bound | str:
    parsed = parse_date(raw)
    if parsed is None:
        return (
            f"Error: could not parse {name} '{raw}'. Use YYYY-MM-DD, "
            "MM/DD/YYYY or ISO 8601 (YYYY-MM-DDTHH:MM:SSZ)."
        )
    text = raw.strip()
    # Every format parse_date accepts with a time of day contains ':'.
    if "T" not in text.upper() and ":" not in text:
        return _day_bound(parsed.date(), end=end)
    return _instant_bound(parsed)


def _resolve_window(
    start_date: str | None, end_date: str | None
) -> tuple[_Bound, _Bound] | str:
    """Resolve the optional window bounds, or return an error string.

    Date-only values (YYYY-MM-DD or MM/DD/YYYY) are sent to Canvas as dates so
    Canvas covers the whole day in the user's own time zone; timestamps are
    sent as UTC. Without a start_date the window starts 14 days before its end.
    """
    if end_date:
        end = _parse_bound(end_date, "end_date", end=True)
        if isinstance(end, str):
            return end
    else:
        end = _instant_bound(datetime.now(UTC))

    if start_date:
        start = _parse_bound(start_date, "start_date", end=False)
        if isinstance(start, str):
            return start
    elif end.day is not None:
        start = _day_bound(end.day - timedelta(days=DEFAULT_ANNOUNCEMENT_DAYS), end=False)
    else:
        start = _instant_bound(end.instant - timedelta(days=DEFAULT_ANNOUNCEMENT_DAYS))

    if start.instant > end.instant:
        return "Error: start_date must be on or before end_date."
    return start, end


def _preview(text: Any, max_chars: int) -> str:
    """Plain-text preview of Canvas rich text, cut at ``max_chars``."""
    if not isinstance(text, str) or not text:
        return ""
    plain = strip_html_tags(text)
    if len(plain) > max_chars:
        return plain[: max(max_chars - 3, 0)].rstrip() + "..."
    return plain


def _preview_was_cut(text: Any, max_chars: int) -> bool:
    """True when ``_preview`` had to shorten ``text``."""
    return isinstance(text, str) and len(strip_html_tags(text)) > max_chars


#: Where the full text of a shortened feed preview lives, by item type.
_FULL_TEXT_TOOL = {
    "Announcement": "get_discussion_topic_details",
    "DiscussionTopic": "get_discussion_topic_details",
    "Conversation": "get_conversation_details",
    "Submission": "get_my_submission",
}


def _cut_note(tool: str | None) -> str:
    if tool:
        return f"  (Preview shortened; {tool} reads the full text.)"
    return "  (Preview shortened; the link opens the full text in Canvas.)"


def _as_count(value: Any) -> int:
    try:
        return max(int(value or 0), 0)
    except (TypeError, ValueError):
        return 0


def _grade_label(value: Any) -> str:
    text = str(value)
    if _PLAIN_GRADE.fullmatch(text):
        return text
    return fence_untrusted_inline(text, "grade text")


def _number_label(value: Any) -> str:
    """Canvas sends scores as floats (18.0); show them as 18, 18.5, 17.25."""
    if isinstance(value, bool) or not isinstance(value, int | float):
        return _grade_label(value)
    text = f"{float(value):.2f}".rstrip("0").rstrip(".")
    return text or "0"


def _same_number(a: Any, b: Any) -> bool:
    try:
        return float(a) == float(b)
    except (TypeError, ValueError):
        return False


def _http_status(error: str) -> int | None:
    match = _HTTP_STATUS.match(error)
    return int(match.group(1)) if match else None


def _failure_reason(error: object) -> str:
    """Show HTTP status only; fence and bound other untrusted failure details."""
    text = str(error)
    status = _http_status(text)
    if status is not None:
        return f"HTTP {status}"
    return fence_untrusted_inline(text.strip()[:200] or "no detail", "Canvas error")


async def _fetch_active_courses() -> list[dict] | str:
    """The caller's active-enrollment courses, or an error string."""
    courses = await fetch_all_paginated_results(
        "/courses", params={"enrollment_state": "active", "per_page": 100}
    )
    if isinstance(courses, dict) and "error" in courses:
        return f"Error fetching your courses: {_failure_reason(courses['error'])}"
    if not isinstance(courses, list):
        return "Error fetching your courses: unexpected response from Canvas."
    return [c for c in courses if isinstance(c, dict)]


async def _course_label(
    course_id: Any, codes: dict[str, str], *, lookup: bool = True
) -> str:
    """Course code for display, never an unvalidated value in a request path.

    Every result, including the ``course <id>`` fallback after a failed
    lookup, is written back into ``codes`` so each course is looked up at
    most once per call. With ``lookup=False`` no request is made at all.
    """
    numeric = coerce_canvas_id(course_id) if course_id is not None else None
    if numeric is None:
        return "Unknown course"
    if numeric in codes:
        return codes[numeric]
    label = f"course {numeric}"
    if lookup:
        code = await get_course_code(numeric)
        # get_course_code returns the bare ID when it cannot find a code.
        if code and str(code) != numeric:
            label = str(code)
    codes[numeric] = label
    return label


def _canvas_id(value: Any) -> str | None:
    """A Canvas object ID as digits, or None when the value is not one."""
    if value is None or isinstance(value, bool):
        return None
    return coerce_canvas_id(value)


def _chunks(items: list[str], size: int) -> list[list[str]]:
    return [items[i:i + size] for i in range(0, len(items), size)]


async def _fetch_announcements(
    context_codes: list[str], window_params: dict[str, Any]
) -> tuple[list[dict], list[tuple[str, str]], list[tuple[list[str], str]]]:
    """Fetch announcements for ``context_codes`` in bounded chunks.

    Returns ``(announcements, course_failures, request_failures)``:
    ``course_failures`` holds ``(context_code, error)`` for a course that
    failed on its own, and ``request_failures`` holds ``(chunk, error)`` for a
    request that failed as a whole, which is not blamed on any one course.

    Only a chunk that fails with a status in ``_PER_COURSE_RETRY_STATUSES`` is
    retried course by course (defensive; see that constant). If every
    single-course retry repeats the chunk's status, the failure is treated as
    request-wide for that chunk only; later chunks retry independently.
    """
    found: list[dict] = []
    course_failures: list[tuple[str, str]] = []
    request_failures: list[tuple[list[str], str]] = []

    async def fetch(codes: list[str]) -> list[dict] | str:
        result = await fetch_all_paginated_results(
            "/announcements",
            params={"context_codes[]": codes, **window_params, "per_page": 100},
        )
        if isinstance(result, dict) and "error" in result:
            return str(result["error"])
        if not isinstance(result, list):
            return "unexpected response from Canvas"
        return [a for a in result if isinstance(a, dict)]

    for chunk in _chunks(context_codes, CONTEXT_CODE_CHUNK_SIZE):
        result = await fetch(chunk)
        if not isinstance(result, str):
            found.extend(result)
            continue
        status = _http_status(result)
        if status not in _PER_COURSE_RETRY_STATUSES:
            request_failures.append((chunk, result))
            continue
        if len(chunk) == 1:
            course_failures.append((chunk[0], result))
            continue
        singles = [(code, await fetch([code])) for code in chunk]
        if all(isinstance(r, str) and _http_status(r) == status for _, r in singles):
            request_failures.append((chunk, result))
            continue
        for code, single in singles:
            if isinstance(single, str):
                course_failures.append((code, single))
            else:
                found.extend(single)
    return found, course_failures, request_failures


def _format_announcement(
    announcement: dict, course_display: str, preview_chars: int
) -> str:
    author = announcement.get("author") or {}
    author_name = (
        (author.get("display_name") if isinstance(author, dict) else None)
        or announcement.get("user_name")
        or "Unknown author"
    )
    title = announcement.get("title") or "Untitled announcement"
    posted = _when(announcement.get("posted_at") or announcement.get("created_at"))
    unread = " [UNREAD]" if announcement.get("read_state") == "unread" else ""

    lines = [
        f"• {course_display} | Posted {posted}{unread}",
        f"  Title: {fence_untrusted_inline(title, 'announcement title')}",
        f"  Author: {fence_untrusted_inline(author_name, 'announcement author')}",
    ]
    announcement_id = _canvas_id(announcement.get("id"))
    ref = f"  ID: {announcement_id or 'unavailable'}"
    link = _link(announcement.get("html_url"))
    if link:
        ref += f" | Link: {link}"
    lines.append(ref)
    if preview_chars > 0:
        body = _preview(announcement.get("message"), preview_chars)
        if body:
            lines.append(fence_untrusted(body, "announcement body preview"))
            if _preview_was_cut(announcement.get("message"), preview_chars):
                lines.append(_cut_note(_FULL_TEXT_TOOL["Announcement"]))
    return "\n".join(lines) + "\n"


def _latest_conversation_message(item: dict) -> Any:
    """Text of the newest message in a Conversation stream item.

    Canvas sends ``message: null`` for conversations (a Conversation has no
    body) and puts the text in ``latest_messages[].message``, already limited
    to messages the viewer takes part in.
    """
    raw = item.get("latest_messages")
    messages = [m for m in raw if isinstance(m, dict)] if isinstance(raw, list) else []
    if not messages:
        return None
    ordered = sorted(
        messages,
        key=lambda m: _stamp(m.get("created_at")) or datetime.min.replace(tzinfo=UTC),
    )
    return ordered[-1].get("message")


def _stream_item_sort_key(item: dict) -> datetime:
    return (
        _stamp(item.get("updated_at") or item.get("created_at"))
        or datetime.min.replace(tzinfo=UTC)
    )


async def _format_stream_item(
    item: dict, codes: dict[str, str], preview_chars: int
) -> str:
    item_type = item.get("type") or "Unknown"
    # Only Canvas's own type names are printed as they are; anything else is
    # Canvas-supplied text and is fenced like any other.
    type_label = (
        item_type
        if item_type == "Unknown" or item_type in _KNOWN_STREAM_TYPES
        else fence_untrusted_inline(str(item_type), "activity item type")
    )
    if item.get("course_id") is not None:
        # Labelled from the caller's course list only: a per-item lookup would
        # cost a request (or two) per item for any course not in that list.
        where = await _course_label(item.get("course_id"), codes, lookup=False)
    elif item.get("group_id") is not None:
        # Defensive: with only_active_courses=true Canvas returns only items
        # whose context is an active course, so group items should not occur.
        group = coerce_canvas_id(item["group_id"])
        where = f"group {group}" if group else "a group"
    else:
        where = "no course"
    when = _when(item.get("updated_at") or item.get("created_at"))
    unread = " [UNREAD]" if item.get("read_state") is False else ""
    lines = [f"• {where} | {type_label} | {when}{unread}"]

    course_id = _canvas_id(item.get("course_id"))
    if course_id:
        lines.append(f"  Course ID: {course_id}")
    if item_type in ("DiscussionTopic", "Announcement"):
        topic_id = _canvas_id(item.get("discussion_topic_id"))
        if item_type == "Announcement" and topic_id is None:
            topic_id = _canvas_id(item.get("announcement_id"))
        if topic_id:
            lines.append(f"  Topic ID: {topic_id}")
    elif item_type == "Conversation":
        conversation_id = _canvas_id(item.get("conversation_id"))
        if conversation_id:
            lines.append(f"  Conversation ID: {conversation_id}")

    if item_type == "Submission":
        raw_assignment = item.get("assignment")
        assignment: dict[str, Any] = raw_assignment if isinstance(raw_assignment, dict) else {}
        assignment_id = _canvas_id(assignment.get("id"))
        if assignment_id:
            lines.append(f"  Assignment ID: {assignment_id}")
        name = assignment.get("name") or item.get("title") or "Unnamed assignment"
        lines.append(f"  Assignment: {fence_untrusted_inline(name, 'assignment name')}")
        score, grade = item.get("score"), item.get("grade")
        points = assignment.get("points_possible")
        if score is not None or grade is not None:
            parts = []
            if score is not None:
                parts.append(
                    f"{_number_label(score)}/{_number_label(points)}"
                    if points is not None
                    else _number_label(score)
                )
            if grade is not None and not _same_number(grade, score):
                parts.append(f"grade {_grade_label(grade)}")
            lines.append(f"  Grade: {', '.join(parts)}")
        comments = [
            c for c in (item.get("submission_comments") or []) if isinstance(c, dict)
        ]
        if comments:
            latest = max(
                comments,
                key=lambda c: _stamp(c.get("created_at")) or datetime.min.replace(tzinfo=UTC),
            )
            author = latest.get("author_name") or "Unknown commenter"
            lines.append(
                f"  Comments: {len(comments)} (latest by "
                f"{fence_untrusted_inline(author, 'comment author')}, "
                f"{_when(latest.get('created_at'))})"
            )
            if preview_chars > 0:
                text = _preview(latest.get("comment"), preview_chars)
                if text:
                    lines.append(fence_untrusted(text, "submission comment preview"))
                    if _preview_was_cut(latest.get("comment"), preview_chars):
                        lines.append(_cut_note(_FULL_TEXT_TOOL["Submission"]))
    else:
        title = item.get("title") or "(no title)"
        lines.append(f"  Title: {fence_untrusted_inline(title, 'activity item title')}")
        participants = _count_label(item.get("participant_count"))
        if item_type == "Conversation" and participants is not None:
            lines.append(f"  Participants: {participants}")
        if item_type == "Message" and item.get("notification_category"):
            category = str(item["notification_category"])
            # Canvas-defined ("Due Date", "Grading"); fenced if it is ever not.
            if category not in _KNOWN_CATEGORIES:
                category = fence_untrusted_inline(category, "notification category")
            lines.append(f"  Category: {category}")
        if item_type in ("DiscussionTopic", "Announcement"):
            replies = _count_label(item.get("total_root_discussion_entries"))
            if replies is not None:
                lines.append(f"  Replies: {replies}")
            if item.get("require_initial_post") and item.get("user_has_posted") is False:
                lines.append("  You must post before you can see replies.")
        if preview_chars > 0:
            source, label = item.get("message"), "activity item preview"
            if item_type == "Conversation":
                latest = _latest_conversation_message(item)
                if latest is not None:
                    source, label = latest, "latest conversation message preview"
            text = _preview(source, preview_chars)
            if text:
                lines.append(fence_untrusted(text, label))
                if _preview_was_cut(source, preview_chars):
                    lines.append(_cut_note(_FULL_TEXT_TOOL.get(item_type)))

    link = _link(item.get("html_url"))
    if link:
        lines.append(f"  Link: {link}")
    return "\n".join(lines) + "\n"


def register_student_feed_tools(mcp: FastMCP) -> None:
    """Register the cross-course announcement and activity feed tools."""

    @mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
    @validate_params
    async def list_my_announcements(
        course_identifier: str | int | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        limit: int = 50,
        preview_chars: int = 400,
    ) -> str:
        """List announcements across ALL your active courses in one call.

        Cross-course: one query covers every course you are actively enrolled
        in, newest first. For a single course's full announcement history use
        list_announcements instead. Default window: the last 14 days.

        Args:
            course_identifier: Optional course code or Canvas ID to show only
                that course.
            start_date: Earliest post date, YYYY-MM-DD, MM/DD/YYYY or ISO
                8601 (default: 14 days before end_date). A date-only value
                starts at midnight in your Canvas account's time zone.
            end_date: Latest post date, same formats (default: now). A
                date-only value includes that whole day in your Canvas
                account's time zone; ISO timestamps are exact.
            limit: Maximum announcements to show (1-200, default 50).
            preview_chars: Characters of body text to preview per
                announcement (0-2000, default 400; 0 shows titles only). A
                shortened preview says so; get_discussion_topic_details with
                the course and announcement ID reads the whole announcement.
        """
        if not 1 <= limit <= MAX_LIMIT:
            return f"Error: limit must be between 1 and {MAX_LIMIT}."
        if not 0 <= preview_chars <= MAX_PREVIEW_CHARS:
            return f"Error: preview_chars must be between 0 and {MAX_PREVIEW_CHARS}."

        window = _resolve_window(start_date, end_date)
        if isinstance(window, str):
            return window
        start, end = window

        courses = await _fetch_active_courses()
        if isinstance(courses, str):
            return courses

        codes: dict[str, str] = {}
        course_ids: list[str] = []
        for course in courses:
            raw_id = course.get("id")
            cid = coerce_canvas_id(raw_id) if raw_id is not None else None
            if cid is None or cid in codes:
                continue
            codes[cid] = course.get("course_code") or course.get("name") or f"course {cid}"
            course_ids.append(cid)

        # A blank filter is refused rather than read as "no filter": the caller
        # asked to narrow the list, and silently widening it to every course
        # would hide that the value was not understood.
        if course_identifier is not None and not str(course_identifier).strip():
            return (
                "Error: course_identifier is blank. Omit it to list every active "
                "course, or pass a course code or numeric Canvas ID."
            )
        filtered = course_identifier is not None
        unlisted_target = False
        if filtered:
            wanted = str(course_identifier).strip()
            # A numeric ID is used as given, even for a course that is no
            # longer active. A course code, name or SIS ID is matched only
            # against the caller's own active courses, with no request, so
            # nothing else becomes a context code. A SIS ID that is not among
            # them is asked of Canvas (a plain token only) and must still turn
            # out to be one of them.
            target = coerce_canvas_id(wanted)
            numeric_given = target is not None
            if target is None:
                target, error = match_course(wanted, courses)
                if target is None and error is None and wanted.startswith(SIS_COURSE_PREFIX):
                    target, error = await resolve_numeric_course_id(wanted)
                if error is not None:
                    return f"Error: {error}"
            if target is None or (not numeric_given and target not in codes):
                return (
                    f"Error: '{wanted}' is not one of your active courses. "
                    "Pass its numeric Canvas course ID instead."
                )
            course_ids = [target]
            # Canvas omits courses the caller cannot read instead of refusing
            # them, so for an ID outside the active list an empty answer is
            # ambiguous and is reported as such below.
            unlisted_target = target not in codes
        elif not course_ids:
            return "You have no active courses, so there are no announcements to show."

        window_params = {
            "start_date": start.param,
            "end_date": end.param,
            "active_only": True,
        }
        announcements, course_failures, request_failures = await _fetch_announcements(
            [f"course_{cid}" for cid in course_ids], window_params
        )

        # Only announcements of the courses that were asked for are shown. The
        # endpoint should never return others; if it does, they are counted and
        # reported, not displayed and not silently dropped.
        requested = {f"course_{cid}" for cid in course_ids}
        in_scope = [a for a in announcements if a.get("context_code") in requested]
        out_of_scope = len(announcements) - len(in_scope)

        failed_count = len(course_failures) + sum(len(chunk) for chunk, _ in request_failures)
        if failed_count and failed_count >= len(course_ids) and not in_scope:
            details = [_failure_reason(err) for _, err in request_failures] + [
                f"{code}: {_failure_reason(err)}" for code, err in course_failures
            ]
            detail = "; ".join(list(dict.fromkeys(details))[:5])
            return f"Error fetching announcements: {detail}"

        # A course listed in two chunks or retried must not show twice.
        # An announcement without an ID cannot be matched with another, so it
        # is kept rather than merged into one.
        unique: dict[str, dict] = {}
        for position, announcement in enumerate(in_scope):
            announcement_id = _canvas_id(announcement.get("id"))
            key = (
                f"{announcement.get('context_code')}:{announcement_id}"
                if announcement_id
                else f"unidentified:{position}"
            )
            unique.setdefault(key, announcement)
        ordered = sorted(
            unique.values(),
            key=lambda a: _stamp(a.get("posted_at") or a.get("created_at"))
            or datetime.min.replace(tzinfo=UTC),
            reverse=True,
        )

        window_text = f"{start.display} to {end.display}"
        scope = (
            await _course_label(course_ids[0], codes)
            if filtered
            else f"{len(course_ids)} active course{'s' if len(course_ids) != 1 else ''}"
        )

        failure_note = ""
        if request_failures:
            missed = sum(len(chunk) for chunk, _ in request_failures)
            errors = "; ".join(list(dict.fromkeys(_failure_reason(err) for _, err in request_failures))[:3])
            failure_note += (
                f"\n⚠️  Canvas returned an error for the announcements of {missed} of "
                f"{len(course_ids)} courses ({errors}); results may be incomplete.\n"
            )
        if course_failures:
            failed = []
            for code, err in course_failures:
                match = _CONTEXT_CODE.fullmatch(code)
                label = await _course_label(match.group(1), codes) if match else code
                failed.append(f"  • {label}: {_failure_reason(err)}\n")
            failure_note += (
                "\n⚠️  Could not read announcements for:\n" + "".join(failed)
                + "Those courses may have announcements not shown here.\n"
            )

        if out_of_scope:
            failure_note += (
                f"\n⚠️  Ignored {out_of_scope} announcement(s) Canvas returned for "
                "courses that were not asked for.\n"
            )

        if not ordered:
            access_note = ""
            if unlisted_target:
                access_note = (
                    f"\n⚠️  {scope} is not among your active courses (it may be "
                    "concluded), and Canvas leaves out courses you cannot read "
                    "instead of refusing them, so this may also mean you have no "
                    "access to it.\n"
                )
            return (
                f"No announcements in {scope} from {window_text}." + access_note + failure_note
            )

        lines = [
            f"Announcements across {scope} ({window_text}), newest first: "
            f"{len(ordered)} found\n"
        ]
        for announcement in ordered[:limit]:
            match = _CONTEXT_CODE.fullmatch(str(announcement.get("context_code") or ""))
            course_display = (
                await _course_label(match.group(1), codes) if match else "Unknown course"
            )
            lines.append(_format_announcement(announcement, course_display, preview_chars))
        if len(ordered) > limit:
            lines.append(
                f"... {len(ordered) - limit} more not shown. Narrow the date range, "
                "filter by course, or raise limit."
            )
        return "\n".join(lines) + failure_note

    @mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
    @validate_params
    async def get_my_activity_stream(
        item_type: ActivityType = "all",
        limit: int = 30,
        include_summary: bool = True,
        preview_chars: int = 300,
    ) -> str:
        """Your recent Canvas activity across all active courses, grouped by kind.

        The dashboard "Recent Activity" feed: announcements, discussions,
        inbox conversations, grades and submission comments, and
        notifications, newest first. Reading it does not mark anything read.
        Group activity and inbox messages not tied to a course are not
        included (Canvas limits this feed to your active courses).

        Args:
            item_type: Show only one kind: "announcements", "discussions",
                "conversations", "submissions" (grades and submission
                comments), "notifications", or "all" (default).
            limit: Maximum items to show (1-200, default 30).
            include_summary: Also show per-kind total and unread counts
                (default True).
            preview_chars: Characters of text to preview per item (0-2000,
                default 300; 0 shows titles only).
        """
        if not 1 <= limit <= MAX_LIMIT:
            return f"Error: limit must be between 1 and {MAX_LIMIT}."
        if not 0 <= preview_chars <= MAX_PREVIEW_CHARS:
            return f"Error: preview_chars must be between 0 and {MAX_PREVIEW_CHARS}."

        items = await fetch_all_paginated_results(
            "/users/self/activity_stream",
            params={"only_active_courses": True, "per_page": 100},
        )
        if isinstance(items, dict) and "error" in items:
            return f"Error fetching your activity stream: {_failure_reason(items['error'])}"
        if not isinstance(items, list):
            return "Error fetching your activity stream: unexpected response from Canvas."
        items = [i for i in items if isinstance(i, dict)]

        output: list[str] = []
        if include_summary:
            summary = await fetch_all_paginated_results(
                "/users/self/activity_stream/summary",
                params={"only_active_courses": True},
            )
            if isinstance(summary, list):
                totals: dict[str, list[int]] = {}
                for row in summary:
                    if not isinstance(row, dict):
                        continue
                    counts = totals.setdefault(_category_for(row.get("type")), [0, 0])
                    counts[0] += _as_count(row.get("count"))
                    counts[1] += _as_count(row.get("unread_count"))
                output.append("Activity summary (active courses):")
                order = [label for label, _ in _STREAM_CATEGORIES] + [_OTHER_CATEGORY]
                for label in order:
                    if label in totals:
                        total, unread = totals[label]
                        output.append(f"  {label}: {total} ({unread} unread)")
                if not totals:
                    output.append("  No recent activity.")
                output.append("")
            else:
                detail = (
                    summary["error"]
                    if isinstance(summary, dict) and "error" in summary
                    else "unexpected response from Canvas"
                )
                output.append(f"⚠️  Activity summary unavailable: {_failure_reason(detail)}\n")

        if item_type != "all":
            wanted = _TYPE_FILTERS[item_type]
            items = [i for i in items if i.get("type") in wanted]

        if not items:
            kind = "" if item_type == "all" else f" {item_type}"
            output.append(f"No recent{kind} activity in your active courses.")
            return "\n".join(output)

        items.sort(key=_stream_item_sort_key, reverse=True)
        shown = items[:limit]

        courses = await _fetch_active_courses()
        codes: dict[str, str] = {}
        if isinstance(courses, list):
            for course in courses:
                raw_id = course.get("id")
                cid = coerce_canvas_id(raw_id) if raw_id is not None else None
                if cid is not None:
                    codes[cid] = course.get("course_code") or course.get("name") or f"course {cid}"

        if isinstance(courses, str):
            # Only the labels degrade: say so instead of showing bare IDs unexplained.
            output.append(f"⚠️  {courses} Courses are shown by ID instead of code.\n")

        grouped: dict[str, list[dict]] = {}
        for item in shown:
            grouped.setdefault(_category_for(item.get("type")), []).append(item)

        output.append(
            f"Recent activity, newest first ({len(shown)} of {len(items)} items):"
        )
        order = [label for label, _ in _STREAM_CATEGORIES] + [_OTHER_CATEGORY]
        for label in order:
            group = grouped.get(label)
            if not group:
                continue
            output.append(f"\n## {label} ({len(group)})\n")
            for item in group:
                output.append(await _format_stream_item(item, codes, preview_chars))
        if len(items) > limit:
            output.append(
                f"... {len(items) - limit} older items not shown. Raise limit or "
                "filter with item_type."
            )
        return "\n".join(output)
