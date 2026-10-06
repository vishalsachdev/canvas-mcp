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

_CONTEXT_CODE = re.compile(r"^course_(\d+)$")
# Grade-shaped tokens shown as-is: letter grades ("A-"), numbers and
# percentages ("92.5", "85%"), and Canvas's fixed pass/fail and excused words.
# Letter-grade text comes from instructor-named grading-scheme entries, so
# anything else is rendered through the inline fence.
_PLAIN_GRADE = re.compile(
    r"^(?:[A-F][+-]?|\d{1,4}(?:\.\d{1,2})?%?|complete|incomplete|pass|fail|EX)$",
    re.IGNORECASE,
)
_HTTP_STATUS = re.compile(r"^HTTP error: (\d{3})\b")

#: Statuses for which a failed multi-course /announcements request is retried
#: one course at a time. Canvas is not known to produce these per course: the
#: endpoint has no per-course authorization and silently omits courses the
#: caller cannot read (``api_find_all`` filters rather than raising), so this
#: fallback is defensive. Server errors, 429 after the client's own retries,
#: and transport failures concern the whole request and are never fanned out.
_PER_COURSE_RETRY_STATUSES = frozenset({400, 401, 403, 404})
_PLAIN_CATEGORY = re.compile(r"^[A-Za-z &/\-]{1,40}$")

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
    if _PLAIN_GRADE.match(text):
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


async def _fetch_active_courses() -> list[dict] | str:
    """The caller's active-enrollment courses, or an error string."""
    courses = await fetch_all_paginated_results(
        "/courses", params={"enrollment_state": "active", "per_page": 100}
    )
    if isinstance(courses, dict) and "error" in courses:
        return f"Error fetching your courses: {courses['error']}"
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
    request-wide and later chunks are not fanned out.
    """
    found: list[dict] = []
    course_failures: list[tuple[str, str]] = []
    request_failures: list[tuple[list[str], str]] = []
    request_wide = False

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
        if status not in _PER_COURSE_RETRY_STATUSES or request_wide:
            request_failures.append((chunk, result))
            continue
        if len(chunk) == 1:
            course_failures.append((chunk[0], result))
            continue
        singles = [(code, await fetch([code])) for code in chunk]
        if all(isinstance(r, str) and _http_status(r) == status for _, r in singles):
            request_wide = True
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
    posted = format_date(announcement.get("posted_at") or announcement.get("created_at"))
    unread = " [UNREAD]" if announcement.get("read_state") == "unread" else ""

    lines = [
        f"• {course_display} | Posted {posted}{unread}",
        f"  Title: {fence_untrusted_inline(title, 'announcement title')}",
        f"  Author: {fence_untrusted_inline(author_name, 'announcement author')}",
    ]
    ref = f"  ID: {announcement.get('id')}"
    if announcement.get("html_url"):
        ref += f" | Link: {announcement['html_url']}"
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
        key=lambda m: parse_date(str(m.get("created_at") or ""))
        or datetime.min.replace(tzinfo=UTC),
    )
    return ordered[-1].get("message")


def _stream_item_sort_key(item: dict) -> datetime:
    return (
        parse_date(item.get("updated_at") or item.get("created_at"))
        or datetime.min.replace(tzinfo=UTC)
    )


async def _format_stream_item(
    item: dict, codes: dict[str, str], preview_chars: int
) -> str:
    item_type = item.get("type") or "Unknown"
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
    when = format_date(item.get("updated_at") or item.get("created_at"))
    unread = " [UNREAD]" if item.get("read_state") is False else ""
    lines = [f"• {where} | {item_type} | {when}{unread}"]

    if item_type == "Submission":
        raw_assignment = item.get("assignment")
        assignment: dict[str, Any] = raw_assignment if isinstance(raw_assignment, dict) else {}
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
                key=lambda c: parse_date(c.get("created_at")) or datetime.min.replace(tzinfo=UTC),
            )
            author = latest.get("author_name") or "Unknown commenter"
            lines.append(
                f"  Comments: {len(comments)} (latest by "
                f"{fence_untrusted_inline(author, 'comment author')}, "
                f"{format_date(latest.get('created_at'))})"
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
        if item_type == "Conversation" and item.get("participant_count") is not None:
            lines.append(f"  Participants: {item.get('participant_count')}")
        if item_type == "Message" and item.get("notification_category"):
            category = str(item["notification_category"])
            # Canvas-defined ("Due Date", "Grading"); fenced if it is ever not.
            if not _PLAIN_CATEGORY.match(category):
                category = fence_untrusted_inline(category, "notification category")
            lines.append(f"  Category: {category}")
        if item_type in ("DiscussionTopic", "Announcement"):
            replies = item.get("total_root_discussion_entries")
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

    if item.get("html_url"):
        lines.append(f"  Link: {item['html_url']}")
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

        filtered = course_identifier is not None and bool(str(course_identifier).strip())
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

        failed_count = len(course_failures) + sum(len(chunk) for chunk, _ in request_failures)
        if failed_count and failed_count >= len(course_ids) and not announcements:
            details = [err for _, err in request_failures] + [
                f"{code}: {err}" for code, err in course_failures
            ]
            detail = "; ".join(list(dict.fromkeys(details))[:5])
            return f"Error fetching announcements: {detail}"

        # A course listed in two chunks or retried must not show twice.
        unique: dict[str, dict] = {}
        for announcement in announcements:
            key = f"{announcement.get('context_code')}:{announcement.get('id')}"
            unique.setdefault(key, announcement)
        ordered = sorted(
            unique.values(),
            key=lambda a: parse_date(a.get("posted_at") or a.get("created_at"))
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
            errors = "; ".join(list(dict.fromkeys(err for _, err in request_failures))[:3])
            failure_note += (
                f"\n⚠️  Canvas returned an error for the announcements of {missed} of "
                f"{len(course_ids)} courses ({errors}); results may be incomplete.\n"
            )
        if course_failures:
            failed = []
            for code, err in course_failures:
                match = _CONTEXT_CODE.match(code)
                label = await _course_label(match.group(1), codes) if match else code
                failed.append(f"  • {label}: {err}\n")
            failure_note += (
                "\n⚠️  Could not read announcements for:\n" + "".join(failed)
                + "Those courses may have announcements not shown here.\n"
            )

        if not ordered:
            return (
                f"No announcements in {scope} from {window_text}." + failure_note
            )

        lines = [
            f"Announcements across {scope} ({window_text}), newest first: "
            f"{len(ordered)} found\n"
        ]
        for announcement in ordered[:limit]:
            match = _CONTEXT_CODE.match(str(announcement.get("context_code") or ""))
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
            return f"Error fetching your activity stream: {items['error']}"
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
                detail = summary.get("error") if isinstance(summary, dict) else summary
                output.append(f"⚠️  Activity summary unavailable: {detail}\n")

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
