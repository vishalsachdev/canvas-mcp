"""Student calendar and planner tools.

Read side: the Canvas calendar (``/calendar_events``) and the student's own
planner notes (``/planner_notes``). Assignment *due dates with submission
status* are already covered by ``get_my_upcoming_assignments`` (Planner items),
so these tools add what that one cannot show: real calendar events (lectures,
exams, office hours, personal events) and the student's own to-do notes.

Write side (each tool off unless the operator lists it in
``STUDENT_WRITE_TOOLS``, like every student write tool):

* planner notes: create, update, delete
* planner overrides: mark a planner item complete (or not)
* personal calendar events: create, delete

Four properties are load-bearing:

1. **Self-scoped by construction.** Personal calendar writes always target the
   caller's own ``user_<id>`` calendar, with that id read from ``/users/self``;
   no tool accepts a context code or a user id. Update and delete first read the
   object and refuse unless it belongs to the caller (a planner note's
   ``user_id``, a calendar event's ``context_code``).
2. **Course policy where a course is involved.** A planner note linked to a
   course, or a planner item that is course content, goes through
   ``check_student_write_allowed`` for that course, re-checked immediately
   before the write. A calendar event's course is read from
   ``effective_context_code`` as well as ``context_code`` (section events and
   appointment reservations name the course only there) and from the owning
   group; an event that cannot be tied to a course is refused. Marking course
   content complete also needs ``mark_module_item_done`` permitted, because
   Canvas syncs the planner override to the item's "Mark as done" module
   requirement (and reverses it on unmark).
3. **Preview, then confirm, for anything that removes or replaces.** Delete and
   update take the shared single-use ``ConfirmationGuard`` token, bound to the
   caller and to the exact state the preview showed, so a note edited between
   preview and confirm stops matching.
4. **Appointment reservations are out of scope.** A reservation lives on the
   student's own calendar, but deleting it cancels a booking with an
   instructor, which is an action toward another person. It is refused.

Privacy: ``/calendar_events``, ``/planner_notes`` and ``/planner/overrides``
fall in the client's "none" anonymization tier (no users/submissions/
enrollments segment). Calendar events can still carry other people in
``user`` and ``child_events`` (appointment-slot sign-ups when the instructor
made them visible), so the read tools render an explicit field projection and
never those two fields; list requests also send ``excludes[]=child_events``.
"""

from __future__ import annotations

import datetime as dt
import re
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastmcp import FastMCP
from mcp.types import ToolAnnotations

from ..core.cache import get_course_code, resolve_numeric_course_id
from ..core.client import fetch_all_paginated_results, make_canvas_request
from ..core.config import get_config
from ..core.course_policy import (
    assert_no_identity_override,
    check_student_write_allowed,
)
from ..core.dates import format_date, output_timezone, parse_date
from ..core.tool_results import FULL_CONTENT_TOOL_META
from ..core.untrusted_content import (
    FENCE_LEAK_ERROR,
    contains_fence_markers,
    fence_untrusted,
    fence_untrusted_inline,
    format_canvas_error,
)
from ..core.validation import coerce_canvas_id, validate_params
from ..core.write_confirmation import (
    ConfirmationGuard,
    preview_with_token,
    redeem_confirmation,
    unconfirmed_write_warning,
)
from .courses import strip_html_tags

# Canvas documents context_codes[] on GET /calendar_events as "Limited to 10
# context codes, additional ones are ignored". Ignored silently, so a student
# with eleven courses would lose a calendar without any error; chunk instead.
CALENDAR_CONTEXT_CODES_PER_REQUEST = 10

_DEFAULT_WINDOW_DAYS = 14
_MAX_WINDOW_DAYS = 366

_EVENT_TYPES = {"event": ("event",), "assignment": ("assignment",),
                "all": ("event", "assignment")}

# POST /planner_notes linked_object_type values, per the Planner API docs.
_LINKABLE_TYPES = ("announcement", "assignment", "discussion_topic", "wiki_page", "quiz")

# Planner item types mark_planner_item_complete accepts, mapped to the
# course-scoped endpoint that proves the object exists in the named course and
# is visible to the caller. planner_note and calendar_event are verified through
# their own endpoints instead. Other documented plannable types
# (assessment_request, sub_assignment, peer_review_sub_assignment) have no
# endpoint a student can use to tie them to a course, so they are refused rather
# than marked without a course-policy check.
_COURSE_PLANNABLES = {
    "assignment": ("assignments", "name"),
    "quiz": ("quizzes", "title"),
    "discussion_topic": ("discussion_topics", "title"),
    "announcement": ("discussion_topics", "title"),
    "wiki_page": ("pages", "title"),
}
_SELF_PLANNABLES = ("planner_note", "calendar_event")
_PLANNABLE_TYPES = tuple(_COURSE_PLANNABLES) + _SELF_PLANNABLES

_DATE_ONLY = re.compile(r"^\d{4}-\d{2}-\d{2}$")
# Calendar date, then a time with at least hours and minutes; the rest
# (seconds, fraction, offset or Z) is left to datetime.fromisoformat.
_ISO_DATETIME = re.compile(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}")
_COURSE_CONTEXT = re.compile(r"^course_(\d+)$")
_SECTION_CONTEXT = re.compile(r"^course_section_\d+$")
_GROUP_CONTEXT = re.compile(r"^group_(\d+)$")
_USER_CONTEXT = re.compile(r"^user_(\d+)$")
_ACCOUNT_CONTEXT = re.compile(r"^account_\d+$")

_UPDATE_NOTE_GUARD = ConfirmationGuard(nothing_done="The note was not changed.")
_DELETE_NOTE_GUARD = ConfirmationGuard(nothing_done="Nothing was deleted.")
_DELETE_EVENT_GUARD = ConfirmationGuard(nothing_done="Nothing was deleted.")

_INVALID_ID = "Error: {name} must be a numeric Canvas ID."


def reset_pending_confirmations() -> None:
    """Discard confirmation state (used by tests)."""
    _UPDATE_NOTE_GUARD.reset()
    _DELETE_NOTE_GUARD.reset()
    _DELETE_EVENT_GUARD.reset()


def _is_error(response: Any) -> bool:
    return isinstance(response, dict) and "error" in response


def _error_detail(response: Any) -> str:
    if isinstance(response, dict):
        return format_canvas_error(response.get("error", response))
    return "unexpected response from Canvas"


# --- Dates -------------------------------------------------------------------


def _now() -> dt.datetime:
    """The current instant (a seam for tests)."""
    return dt.datetime.now(dt.UTC)


def _local_zone() -> dt.tzinfo | None:
    """The operator's configured ``TIMEZONE``, or None when it is not known.

    ``TIMEZONE`` defaults to UTC, and an unknown zone name also falls back to
    UTC, so plain UTC here means "the student's zone is not known", not "the
    student is in UTC".
    """
    zone = output_timezone()
    return None if zone is dt.UTC else zone


def _to_canvas_date(value: str, name: str) -> tuple[str | None, dt.datetime | None, str | None]:
    """Validate one caller-supplied date for a Canvas query or body.

    Returns ``(wire_value, comparable_datetime, error)``. A bare
    ``YYYY-MM-DD`` passes through unchanged, because Canvas documents that form
    and resolves it in the user's own Canvas time zone; converting it to UTC
    midnight here would shift the day for anyone west of Greenwich. Anything
    else must be an ISO 8601 date-time and goes out as ISO 8601 UTC.

    A date-time without an offset is never assumed to be UTC: it is read in
    the configured ``TIMEZONE`` when one is set, and refused otherwise, since
    guessing would put a 2pm event at 7am for a student in California.
    """
    text = value.strip()
    if _DATE_ONLY.match(text):
        try:
            day = dt.date.fromisoformat(text)
        except ValueError:
            return None, None, f"Error: {name} '{value}' is not a real date."
        return text, dt.datetime(day.year, day.month, day.day, tzinfo=dt.UTC), None
    parsed: dt.datetime | None = None
    if _ISO_DATETIME.match(text):
        try:
            parsed = dt.datetime.fromisoformat(text)
        except ValueError:
            parsed = None
    if parsed is None:
        return None, None, (
            f"Error: {name} '{value}' is not a recognised date. Use YYYY-MM-DD "
            "or an ISO 8601 date-time with an offset, such as "
            "2026-10-05T14:00:00-07:00 or 2026-10-05T21:00:00Z."
        )
    if parsed.tzinfo is None:
        zone = _local_zone()
        if zone is None:
            return None, None, (
                f"Error: {name} '{value}' has no time zone, and none is configured "
                "on this server. Add an offset (for example "
                "2026-10-05T14:00:00-07:00) or use a plain YYYY-MM-DD date."
            )
        parsed = parsed.replace(tzinfo=zone)
    utc = parsed.astimezone(dt.UTC)
    return utc.strftime("%Y-%m-%dT%H:%M:%SZ"), utc, None


def _upper_bound(wire: str, lower: dt.datetime) -> dt.datetime:
    """Canvas reads a date-only end as the end of that day."""
    return lower + dt.timedelta(days=1) if _DATE_ONLY.match(wire) else lower


def _resolve_window(
    start_date: str | None, end_date: str | None, days: int
) -> tuple[str, str, str | None]:
    """Turn optional start/end plus a look-ahead into a Canvas date window.

    Canvas's own defaults are unhelpful here: ``/calendar_events`` defaults
    ``end_date`` to ``start_date``, i.e. a single day, so the window is always
    made explicit.

    The default start is *today* as a date-only value, not the current
    instant. Canvas stores an all-day event at local midnight and a date-only
    planner note's ``todo_date`` at local midnight too, so a window that opens
    "now" would silently drop both for today. A date-only bound lets Canvas
    apply ``beginning_of_day`` (and ``end_of_day`` for the end) in the
    student's own Canvas zone. When the server has no ``TIMEZONE`` configured,
    "today" is not known, so the window opens a day early rather than risk
    starting tomorrow for anyone west of UTC.
    """
    if days < 1 or days > _MAX_WINDOW_DAYS:
        return "", "", f"Error: days must be between 1 and {_MAX_WINDOW_DAYS}."

    zone = _local_zone()
    today = _now().astimezone(zone).date() if zone else _now().date()

    if start_date:
        start_wire, start_dt, error = _to_canvas_date(start_date, "start_date")
        if error:
            return "", "", error
        assert start_wire is not None and start_dt is not None
        span_start = start_dt
    else:
        first_day = today if zone else today - dt.timedelta(days=1)
        start_wire = first_day.isoformat()
        start_dt = dt.datetime(first_day.year, first_day.month, first_day.day, tzinfo=dt.UTC)
        # The slack day is a safety margin, not part of the requested span.
        span_start = dt.datetime(today.year, today.month, today.day, tzinfo=dt.UTC)

    if end_date:
        end_wire, end_dt, error = _to_canvas_date(end_date, "end_date")
        if error:
            return "", "", error
        assert end_wire is not None and end_dt is not None
        end_upper = _upper_bound(end_wire, end_dt)
    elif _DATE_ONLY.match(start_wire):
        # Inclusive date-only end: `days` whole days counted from the anchor.
        anchor = span_start.date()
        last_day = anchor + dt.timedelta(days=days - 1)
        end_wire = last_day.isoformat()
        end_upper = dt.datetime(
            last_day.year, last_day.month, last_day.day, tzinfo=dt.UTC
        ) + dt.timedelta(days=1)
    else:
        end_upper = start_dt + dt.timedelta(days=days)
        end_wire = end_upper.strftime("%Y-%m-%dT%H:%M:%SZ")

    if end_upper < start_dt:
        return "", "", "Error: end_date is before start_date."
    if end_upper - span_start > dt.timedelta(days=_MAX_WINDOW_DAYS):
        return "", "", (
            f"Error: the date window is longer than {_MAX_WINDOW_DAYS} days. "
            "Ask for a shorter range."
        )
    return str(start_wire), str(end_wire), None


# --- Identity and course resolution -----------------------------------------


async def _my_user_profile() -> tuple[dict | None, str | None]:
    """The caller's profile with a validated numeric id, or an error."""
    me = await make_canvas_request("get", "/users/self")
    if not isinstance(me, dict) or _is_error(me):
        return None, f"Error identifying current user: {_error_detail(me)}"
    user_id = coerce_canvas_id(me.get("id", ""))
    if user_id is None:
        return None, "Error identifying current user: Canvas returned no user id."
    return me, None


async def _my_user_id() -> tuple[str | None, str | None]:
    """The caller's numeric Canvas user id, or an error message."""
    me, error = await _my_user_profile()
    if me is None:
        return None, error
    return coerce_canvas_id(me["id"]), None


def _planner_date_matches(returned: Any, requested: str, canvas_zone: Any) -> bool:
    """Confirm an instant, or a date-only request in the caller's Canvas zone."""
    if not isinstance(returned, str):
        return False
    try:
        if _DATE_ONLY.fullmatch(returned):
            return _DATE_ONLY.fullmatch(requested) is not None and dt.date.fromisoformat(returned) == dt.date.fromisoformat(requested)
        actual = dt.datetime.fromisoformat(returned)
        if actual.tzinfo is None:
            return False
        if _DATE_ONLY.fullmatch(requested):
            if not isinstance(canvas_zone, str):
                return False
            return actual.astimezone(ZoneInfo(canvas_zone)).date() == dt.date.fromisoformat(requested)
        return actual == dt.datetime.fromisoformat(requested)
    except (ValueError, ZoneInfoNotFoundError):
        return False


async def _resolve_numeric_course_id(
    course_identifier: str | int,
) -> tuple[str | None, str | None]:
    """Resolve a course code/name/SIS id/Canvas id to a numeric id.

    Planner notes take ``course_id`` as an integer, and course policy and
    context codes are keyed by it. ``resolve_numeric_course_id`` never puts an
    unvalidated identifier in a request path, so a crafted value such as
    ``101/assignments/4242`` cannot reach a sub-resource and have its ``id``
    mistaken for a course id.
    """
    course_id, error = await resolve_numeric_course_id(course_identifier)
    if course_id is None:
        return None, f"Error: {error or f'Could not find course {course_identifier}'}"
    return course_id, None


async def _course_policy_error(course_ids: set[str], tool_name: str, verb: str) -> str | None:
    """Check every course a write touches; the first refusal wins."""
    for course_id in sorted(course_ids):
        allowed, reason = await check_student_write_allowed(course_id, tool_name)
        if not allowed:
            return f"❌ {verb} blocked. {reason}"
    return None


async def _course_display(course_id: Any) -> str:
    if course_id in (None, ""):
        return "Personal (no course)"
    code = await get_course_code(course_id)
    return code or f"course {course_id}"


def _course_of_context(context_code: Any) -> str | None:
    match = _COURSE_CONTEXT.match(str(context_code or ""))
    return str(match.group(1)) if match else None


async def _calendar_event_courses(
    event: dict, my_id: str
) -> tuple[set[str], str | None]:
    """Every course whose policy governs a calendar event, or a refusal.

    The course is not always in ``context_code``. Canvas documents that a
    section-level event carries ``course_section_<id>`` there and the course
    in ``effective_context_code`` (which may list several calendars, comma
    separated), and a student's appointment reservation sits in
    ``user_<me>`` with the course again only in ``effective_context_code``.
    A group event names only ``group_<id>``; the group's own record says
    which course, if any, owns it. Anything that cannot be tied to a course
    is refused rather than written without a policy check.
    """
    codes = [
        code.strip()
        for code in str(event.get("effective_context_code") or "").split(",")
        if code.strip()
    ]
    context = str(event.get("context_code") or "").strip()
    if context:
        codes.append(context)
    if not codes:
        # An event that names no calendar at all proves nothing about its
        # course; passing it would skip the policy check entirely.
        return set(), (
            "❌ This calendar event does not say which calendar it belongs to, so "
            "the course policy cannot be checked."
        )

    courses: set[str] = set()
    sections = False
    for code in codes:
        if (course := _course_of_context(code)) is not None:
            courses.add(course)
        elif _SECTION_CONTEXT.match(code):
            sections = True
        elif match := _GROUP_CONTEXT.match(code):
            group_id = coerce_canvas_id(match.group(1))
            group = await make_canvas_request("get", f"/groups/{group_id}")
            if not isinstance(group, dict) or _is_error(group):
                return set(), (
                    f"❌ Could not tell which course owns group {group_id}, so the "
                    f"course policy cannot be checked: {_error_detail(group)}"
                )
            context_type = group.get("context_type")
            if context_type == "Course":
                group_course = coerce_canvas_id(group.get("course_id") or "")
                if group_course is None:
                    return set(), (
                        f"❌ Could not tell which course owns group {group_id}, so "
                        "the course policy cannot be checked."
                    )
                courses.add(group_course)
            elif context_type != "Account":
                # Only a group Canvas says belongs to the institution is exempt;
                # a missing or unknown owner is not read as "no course".
                return set(), (
                    f"❌ Could not tell which course owns group {group_id}, so the "
                    "course policy cannot be checked."
                )
        elif match := _USER_CONTEXT.match(code):
            if match.group(1) != my_id:
                return set(), "❌ This calendar event is on someone else's calendar."
        elif _ACCOUNT_CONTEXT.match(code):
            continue  # institution calendar: no course policy applies
        else:
            return set(), (
                f"❌ This calendar event belongs to '{code}', which cannot be tied "
                "to a course, so the course policy cannot be checked."
            )
    if sections and not courses:
        return set(), (
            "❌ This is a section event and Canvas did not say which course it "
            "belongs to, so the course policy cannot be checked."
        )
    return courses, None


def _note_course(note: dict) -> tuple[str | None, str | None]:
    """The course a planner note is filed under, or a refusal.

    A note with no course is personal. A note that names a course which is not
    a usable id is not personal: it is refused so the course policy is never
    skipped by reading an unparseable id as "no course".
    """
    raw = note.get("course_id")
    if raw is None or raw == "":
        return None, None
    course = coerce_canvas_id(raw)
    if course is None:
        return None, (
            f"❌ Planner note {note.get('id')} names a course Canvas did not "
            "identify, so the course policy cannot be checked."
        )
    return course, None


def _has_fence_markers(*values: str | None) -> bool:
    return any(contains_fence_markers(value or "") for value in values)


# --- Formatting ----------------------------------------------------------------


def _event_when(event: dict) -> str:
    if event.get("all_day"):
        day = event.get("all_day_date") or format_date(event.get("start_at"))
        return f"All day {day}"
    start = event.get("start_at")
    end = event.get("end_at")
    if start and end and end != start:
        return f"{format_date(start)} to {format_date(end)}"
    return format_date(start)


def _event_calendar_label(event: dict, labels: dict[str, str]) -> str:
    for key in ("effective_context_code", "context_code"):
        code = event.get(key)
        if code and code in labels:
            return labels[code]
    name = event.get("context_name")
    if name:
        return fence_untrusted_inline(name, "calendar name")
    return str(event.get("context_code") or "unknown calendar")


def _is_assignment_event(event: dict) -> bool:
    return bool(event.get("assignment")) or str(event.get("id", "")).startswith("assignment_")


def _format_event(
    event: dict, labels: dict[str, str], my_context: str | None, include_description: bool
) -> str:
    kind = "Assignment due" if _is_assignment_event(event) else "Event"
    lines = [
        f"• [{kind}] {fence_untrusted_inline(event.get('title') or 'Untitled', 'event title')}",
        f"  When: {_event_when(event)}",
        f"  Calendar: {_event_calendar_label(event, labels)}",
    ]
    if event.get("location_name"):
        lines.append(
            f"  Location: {fence_untrusted_inline(event['location_name'], 'event location')}"
        )
    assignment = event.get("assignment")
    if isinstance(assignment, dict) and assignment.get("id") is not None:
        lines.append(f"  Assignment ID: {assignment['id']}")
    else:
        personal = (
            " (your personal event)"
            if my_context and event.get("context_code") == my_context
            and not event.get("appointment_group_id") and not event.get("parent_event_id")
            else ""
        )
        lines.append(f"  Event ID: {event.get('id')}{personal}")
    if include_description and event.get("description"):
        text = strip_html_tags(str(event["description"])).strip()
        if text:
            lines.append(f"  Description:\n{fence_untrusted(text, 'calendar event description')}")
    return "\n".join(lines)


async def _format_note(note: dict) -> str:
    lines = [
        f"• {fence_untrusted_inline(note.get('title') or 'Untitled', 'planner note title')}",
        f"  To-do date: {format_date(note.get('todo_date'))}",
        f"  Course: {await _course_display(note.get('course_id'))}",
        f"  Note ID: {note.get('id')}",
    ]
    if note.get("linked_object_type"):
        lines.append(
            f"  Linked to: {note['linked_object_type']} {note.get('linked_object_id')}"
        )
    if note.get("description"):
        lines.append(f"  Details:\n{fence_untrusted(note['description'], 'planner note details')}")
    return "\n".join(lines)


def _normalize_plannable_type(value: Any) -> str:
    """Compare Canvas type names across their API and model spellings.

    The API takes ``discussion_topic``; a serializer may echo the model name
    ``DiscussionTopic`` or a namespaced ``Quizzes::Quiz``. Fold all of them to
    one key so an existing override is never missed.
    """
    text = str(value or "").split("::")[-1]
    return text.replace("_", "").lower()


def _find_override(
    overrides: list[Any], plannable_type: str, stored_ids: set[str], validated: str
) -> dict | None:
    """The caller's existing override for this item, if Canvas holds one.

    Canvas rewrites ``(plannable_type, plannable_id)`` before saving
    (PlannerOverride#link_to_submittable / #link_to_parent_topic): an
    assignment that is a classic quiz, graded discussion or page is stored as
    that quiz/topic/page, and a group discussion's child topic as its root
    topic. The override JSON keeps the associated ``assignment_id``, so an
    assignment is matched on that too; otherwise a second call would miss the
    stored override and POST a duplicate that Canvas rejects (400).
    """
    wanted = _normalize_plannable_type(plannable_type)
    exact: list[dict] = []
    rewritten: list[dict] = []
    for override in overrides:
        if not isinstance(override, dict):
            continue
        if (
            _normalize_plannable_type(override.get("plannable_type")) == wanted
            and str(override.get("plannable_id")) in stored_ids
        ):
            exact.append(override)
        elif plannable_type == "assignment" and str(override.get("assignment_id")) == validated:
            rewritten.append(override)
    found = exact or rewritten
    return found[0] if found else None


# --- Fetching ----------------------------------------------------------------


def _chunks(codes: list[str]) -> list[list[str]]:
    step = CALENDAR_CONTEXT_CODES_PER_REQUEST
    return [codes[offset:offset + step] for offset in range(0, len(codes), step)]


async def _fetch_events(
    context_sets: list[list[str]],
    types: tuple[str, ...],
    start: str,
    end: str,
    include_descriptions: bool,
) -> tuple[list[dict], list[str], int]:
    """Fetch calendar events, 10 context codes per request.

    Each set in ``context_sets`` is chunked on its own, so codes from
    different sets never share a request. Canvas rejects a whole request (401)
    when any one of its codes is outside the caller's visible contexts, so a
    group Canvas will not accept must not take the personal and course
    calendars down with it.

    Returns ``(events, failures, successful_requests)``.
    """
    events: list[dict] = []
    failures: list[str] = []
    succeeded = 0
    seen: set[str] = set()
    for event_type in types:
        for codes in context_sets:
            for chunk in _chunks(codes):
                params: dict[str, Any] = {
                    "type": event_type,
                    "start_date": start,
                    "end_date": end,
                    "context_codes[]": chunk,
                    "per_page": 100,
                    # child_events carries appointment-slot reservations,
                    # i.e. classmates' identities; never fetch them.
                    "excludes[]": (
                        ["child_events"] if include_descriptions
                        else ["description", "child_events"]
                    ),
                }
                result = await fetch_all_paginated_results("/calendar_events", params=params)
                if _is_error(result) or not isinstance(result, list):
                    failures.append(
                        f"{event_type} entries for {', '.join(chunk)}: {_error_detail(result)}"
                    )
                    continue
                succeeded += 1
                for event in result:
                    if not isinstance(event, dict):
                        continue
                    key = str(event.get("id"))
                    if key in seen:
                        continue
                    seen.add(key)
                    events.append(event)
    return events, failures, succeeded


def _event_sort_key(event: dict) -> dt.datetime:
    parsed = parse_date(event.get("start_at")) if event.get("start_at") else None
    return parsed or dt.datetime.max.replace(tzinfo=dt.UTC)


async def _fetch_my_note(note_id: str, my_id: str) -> tuple[dict | None, str | None]:
    """Read a planner note and prove it belongs to the caller."""
    note = await make_canvas_request("get", f"/planner_notes/{note_id}")
    if not isinstance(note, dict) or _is_error(note):
        return None, f"Error fetching planner note {note_id}: {_error_detail(note)}"
    owner = note.get("user_id")
    if owner is None or str(owner) != my_id:
        return None, (
            f"❌ Planner note {note_id} could not be verified as yours, so it was "
            "not changed."
        )
    if note.get("workflow_state") == "deleted":
        return None, f"❌ Planner note {note_id} is already deleted."
    return note, None


async def _fetch_my_personal_event(event_id: str, my_id: str) -> tuple[dict | None, str | None]:
    """Read a calendar event and prove it is on the caller's personal calendar."""
    event = await make_canvas_request("get", f"/calendar_events/{event_id}")
    if not isinstance(event, dict) or _is_error(event):
        return None, f"Error fetching calendar event {event_id}: {_error_detail(event)}"
    mine = f"user_{my_id}"
    effective = event.get("effective_context_code")
    if event.get("context_code") != mine or (effective and effective != mine):
        return None, (
            f"❌ Calendar event {event_id} is not on your personal calendar, so it "
            "cannot be changed here. Only events you created on your own calendar "
            "can be deleted."
        )
    if event.get("appointment_group_id") or event.get("parent_event_id"):
        return None, (
            f"❌ Calendar event {event_id} is an appointment reservation. Deleting "
            "it would cancel your booking with the instructor, so it is not done "
            "here. Cancel it in Canvas if you mean to."
        )
    if event.get("workflow_state") == "deleted":
        return None, f"❌ Calendar event {event_id} is already deleted."
    return event, None


def register_student_calendar_tools(mcp: FastMCP) -> None:
    """Register calendar/planner tools.

    The read tools are always registered for the student profile. Each write
    tool registers only when the operator names it in ``STUDENT_WRITE_TOOLS``.
    """
    enabled = get_config().student_write_tools

    @mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
    @validate_params
    async def list_calendar_events(
        start_date: str | None = None,
        end_date: str | None = None,
        days: int = _DEFAULT_WINDOW_DAYS,
        course_identifier: str | int | None = None,
        event_type: str = "all",
        include_descriptions: bool = False,
    ) -> str:
        """List your Canvas calendar: course events, personal events, group
        events and assignment due dates, in date order.

        Covers every active course, your personal calendar and your groups
        unless course_identifier narrows it. For submission status of upcoming
        assignments use get_my_upcoming_assignments instead.

        Args:
            start_date: Window start, YYYY-MM-DD or ISO 8601 with an offset
                (default: today)
            end_date: Window end, inclusive (default: start + days); the
                window may span at most 366 days
            days: Look-ahead when end_date is omitted (default 14, max 366)
            course_identifier: Only this course's calendar (code or Canvas ID)
            event_type: "event", "assignment", or "all" (default)
            include_descriptions: Include event descriptions (longer output)
        """
        types = _EVENT_TYPES.get(event_type)
        if types is None:
            return "Error: event_type must be 'event', 'assignment', or 'all'."
        start, end, window_error = _resolve_window(start_date, end_date, days)
        if window_error:
            return window_error

        my_id, me_error = await _my_user_id()
        if me_error:
            return me_error
        my_context = f"user_{my_id}"

        labels: dict[str, str] = {my_context: "Personal calendar"}
        notes: list[str] = []
        group_contexts: list[str] = []
        if course_identifier is not None:
            course_id, course_error = await _resolve_numeric_course_id(course_identifier)
            if course_error:
                return course_error
            assert course_id is not None
            contexts = [f"course_{course_id}"]
            labels[contexts[0]] = await _course_display(course_id)
        else:
            courses = await fetch_all_paginated_results(
                "/courses", params={"enrollment_state": "active", "per_page": 100}
            )
            if _is_error(courses) or not isinstance(courses, list):
                return f"Error fetching your courses: {_error_detail(courses)}"
            contexts = [my_context]
            active_courses: set[str] = set()
            for course in courses:
                course_id = coerce_canvas_id(course.get("id", "")) if isinstance(course, dict) else None
                if course_id is None:
                    continue
                code = f"course_{course_id}"
                contexts.append(code)
                active_courses.add(course_id)
                labels[code] = str(course.get("course_code") or course.get("name") or code)

            groups = await fetch_all_paginated_results(
                "/users/self/groups", params={"per_page": 100}
            )
            if _is_error(groups) or not isinstance(groups, list):
                notes.append(
                    f"⚠️  Could not list your groups, so group calendars were not "
                    f"checked: {_error_detail(groups)}"
                )
            else:
                for group in groups:
                    group_id = coerce_canvas_id(group.get("id", "")) if isinstance(group, dict) else None
                    if group_id is None:
                        continue
                    # /users/self/groups also lists groups from concluded
                    # courses, which the calendar refuses (401 for the whole
                    # request). Only groups of an active course, or groups
                    # outside any course, are asked for.
                    if (
                        group.get("context_type") == "Course"
                        and str(group.get("course_id")) not in active_courses
                    ):
                        continue
                    code = f"group_{group_id}"
                    group_contexts.append(code)
                    labels[code] = (
                        f"Group {fence_untrusted_inline(group.get('name') or group_id, 'group name')}"
                    )

        events, failures, succeeded = await _fetch_events(
            [contexts, group_contexts], types, start, end, include_descriptions
        )
        if failures and not succeeded:
            return (
                "Error fetching calendar events; nothing could be confirmed:\n"
                + "\n".join(f"  • {failure}" for failure in failures)
            )
        for failure in failures:
            notes.append(f"⚠️  Could not fetch {failure}. Some entries may be missing.")

        header = f"Calendar from {start} to {end}"
        if not events:
            return "\n".join([f"{header}: nothing scheduled.", *notes])

        events.sort(key=_event_sort_key)
        lines = [f"{header} ({len(events)} entries):\n"]
        lines.extend(
            _format_event(event, labels, my_context, include_descriptions) + "\n"
            for event in events
        )
        lines.extend(notes)
        return "\n".join(lines)

    @mcp.tool(
        annotations=ToolAnnotations(read_only_hint=True), meta=FULL_CONTENT_TOOL_META
    )
    @validate_params
    async def get_calendar_event(event_id: str | int) -> str:
        """Get one calendar event in full, including its description.

        Args:
            event_id: Numeric calendar event ID (from list_calendar_events). For
                an assignment due date, use get_assignment_details instead.
        """
        validated = coerce_canvas_id(event_id)
        if validated is None:
            return (
                _INVALID_ID.format(name="event_id")
                + " Assignment entries (assignment_<id>) are assignments, not "
                "calendar events: use get_assignment_details."
            )

        event = await make_canvas_request("get", f"/calendar_events/{validated}")
        if not isinstance(event, dict) or _is_error(event):
            return f"Error fetching calendar event {validated}: {_error_detail(event)}"

        my_id, _ = await _my_user_id()
        my_context = f"user_{my_id}" if my_id else None
        labels: dict[str, str] = {}
        if my_context:
            labels[my_context] = "Personal calendar"
        course_id = _course_of_context(event.get("effective_context_code")) or _course_of_context(
            event.get("context_code")
        )
        if course_id:
            labels[f"course_{course_id}"] = await _course_display(course_id)

        lines = [_format_event(event, labels, my_context, include_description=True)]
        if event.get("location_address"):
            lines.append(
                f"  Address: {fence_untrusted_inline(event['location_address'], 'event address')}"
            )
        if event.get("series_uuid"):
            lines.append("  Part of a repeating series.")
        if event.get("appointment_group_id"):
            lines.append("  Appointment-group slot or reservation.")
        if event.get("html_url"):
            lines.append(f"  Open in Canvas: {event['html_url']}")
        return "\n".join(lines)

    @mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
    @validate_params
    async def list_planner_notes(
        start_date: str | None = None,
        end_date: str | None = None,
        days: int = _DEFAULT_WINDOW_DAYS,
        course_identifier: str | int | None = None,
    ) -> str:
        """List your own planner notes (personal to-do items) in a date window.

        Args:
            start_date: Window start, YYYY-MM-DD or ISO 8601 with an offset
                (default: today)
            end_date: Window end, inclusive (default: start + days); the
                window may span at most 366 days
            days: Look-ahead when end_date is omitted (default 14, max 366)
            course_identifier: Only notes linked to this course
        """
        start, end, window_error = _resolve_window(start_date, end_date, days)
        if window_error:
            return window_error

        params: dict[str, Any] = {"start_date": start, "end_date": end, "per_page": 100}
        course_id: str | None = None
        if course_identifier is not None:
            course_id, course_error = await _resolve_numeric_course_id(course_identifier)
            if course_error:
                return course_error
            params["context_codes[]"] = [f"course_{course_id}"]

        notes = await fetch_all_paginated_results("/planner_notes", params=params)
        if _is_error(notes) or not isinstance(notes, list):
            return f"Error fetching planner notes: {_error_detail(notes)}"

        notes = [
            note for note in notes
            if isinstance(note, dict) and note.get("workflow_state") != "deleted"
            # Backstop for the context filter, which the docs do not promise
            # is exclusive.
            and (course_id is None or str(note.get("course_id")) == course_id)
        ]
        if not notes:
            return f"No planner notes from {start} to {end}."

        notes.sort(key=lambda n: parse_date(n.get("todo_date")) or dt.datetime.max.replace(tzinfo=dt.UTC))
        lines = [f"Planner notes from {start} to {end} ({len(notes)}):\n"]
        for note in notes:
            lines.append(await _format_note(note) + "\n")
        return "\n".join(lines)

    if "create_planner_note" in enabled:

        @mcp.tool(annotations=ToolAnnotations(destructive_hint=False, idempotent_hint=False))
        @validate_params
        async def create_planner_note(
            title: str,
            todo_date: str,
            details: str | None = None,
            course_identifier: str | int | None = None,
            linked_object_type: str | None = None,
            linked_object_id: str | int | None = None,
        ) -> str:
            """Add a note to YOUR OWN Canvas planner (a personal to-do item).

            Args:
                title: Note title
                todo_date: Day it shows on, YYYY-MM-DD (or ISO 8601 with an offset)
                details: Optional note text
                course_identifier: Optional course to file it under
                linked_object_type: Optional: announcement, assignment,
                    discussion_topic, wiki_page or quiz (needs a course)
                linked_object_id: ID of that object, in the same course
            """
            if not title.strip():
                return "Error: title cannot be empty."
            if _has_fence_markers(title, details):
                return FENCE_LEAK_ERROR
            date_wire, _, date_error = _to_canvas_date(todo_date, "todo_date")
            if date_error:
                return date_error

            data: dict[str, Any] = {"title": title, "todo_date": date_wire}
            if details:
                data["details"] = details

            if (linked_object_type is None) != (linked_object_id is None):
                return "Error: linked_object_type and linked_object_id go together."
            if linked_object_type is not None and linked_object_id is not None:
                if linked_object_type not in _LINKABLE_TYPES:
                    return (
                        "Error: linked_object_type must be one of "
                        f"{', '.join(_LINKABLE_TYPES)}."
                    )
                if course_identifier is None:
                    return "Error: a linked object needs course_identifier (its course)."
                linked_id = coerce_canvas_id(linked_object_id)
                if linked_id is None:
                    return _INVALID_ID.format(name="linked_object_id")
                data["linked_object_type"] = linked_object_type
                data["linked_object_id"] = linked_id

            course_id: str | None = None
            if course_identifier is not None:
                course_id, course_error = await _resolve_numeric_course_id(course_identifier)
                if course_error:
                    return course_error
                assert course_id is not None
                data["course_id"] = course_id
                # Checked here, immediately before the single write call.
                policy_error = await _course_policy_error(
                    {course_id}, "create_planner_note", "Planner note"
                )
                if policy_error:
                    return policy_error

            assert_no_identity_override(data)
            created = await make_canvas_request(
                "post", "/planner_notes", data=data, use_form_data=True
            )
            if _is_error(created):
                return f"❌ Could not create the planner note: {_error_detail(created)}"
            if not isinstance(created, dict) or created.get("id") is None:
                return unconfirmed_write_warning(
                    "the planner note was created",
                    {"Title": title, "To-do date": date_wire},
                    "Canvas returned no note. Check your planner before retrying, "
                    "or the note may be duplicated.",
                )
            return "✅ Planner note created.\n" + await _format_note(created)

    if "update_planner_note" in enabled:

        @mcp.tool(annotations=ToolAnnotations(destructive_hint=True, idempotent_hint=True))
        @validate_params
        async def update_planner_note(
            note_id: str | int,
            title: str | None = None,
            details: str | None = None,
            todo_date: str | None = None,
            course_identifier: str | int | None = None,
            confirmation_token: str | None = None,
        ) -> str:
            """Change one of YOUR OWN planner notes. Two-step.

            Call without confirmation_token to preview the change and get a
            token; show the preview to the student, then call again with the
            token and identical arguments. The old text is not kept by Canvas.

            Args:
                note_id: Planner note ID (from list_planner_notes)
                title: New title
                details: New note text (replaces the old text)
                todo_date: New day, YYYY-MM-DD (or ISO 8601 with an offset)
                course_identifier: File the note under this course instead
                confirmation_token: Token from the preview call; omit to preview
            """
            validated = coerce_canvas_id(note_id)
            if validated is None:
                return _INVALID_ID.format(name="note_id")
            if title is None and details is None and todo_date is None and course_identifier is None:
                return "Error: nothing to change. Pass title, details, todo_date or course_identifier."
            if title is not None and not title.strip():
                return "Error: title cannot be empty."
            if _has_fence_markers(title, details):
                return FENCE_LEAK_ERROR

            data: dict[str, Any] = {}
            if title is not None:
                data["title"] = title
            if details is not None:
                data["details"] = details
            if todo_date is not None:
                date_wire, _, date_error = _to_canvas_date(todo_date, "todo_date")
                if date_error:
                    return date_error
                data["todo_date"] = date_wire

            me, me_error = await _my_user_profile()
            if me_error:
                return me_error
            assert me is not None
            my_id = coerce_canvas_id(me["id"])
            assert my_id is not None
            note, note_error = await _fetch_my_note(validated, my_id)
            if note_error:
                return note_error
            assert note is not None

            courses: set[str] = set()
            current_course, course_refusal = _note_course(note)
            if course_refusal:
                return course_refusal
            if current_course:
                courses.add(current_course)
            if course_identifier is not None:
                if note.get("linked_object_type"):
                    return (
                        "Error: this note is linked to a course item, and Canvas "
                        "does not allow moving such a note to another course."
                    )
                new_course, course_error = await _resolve_numeric_course_id(course_identifier)
                if course_error:
                    return course_error
                assert new_course is not None
                data["course_id"] = new_course
                courses.add(new_course)

            policy_error = await _course_policy_error(courses, "update_planner_note", "Update")
            if policy_error:
                return policy_error

            # Bound to the caller, the proposed fields and everything the
            # preview shows of the current note, so an edit in between voids it.
            fingerprint = _UPDATE_NOTE_GUARD.fingerprint(
                "update_planner_note", validated,
                *(f"{key}={data[key]}" for key in sorted(data)),
                str(note.get("title")), str(note.get("description")),
                str(note.get("todo_date")), str(note.get("course_id")),
            )

            if not confirmation_token:
                preview = [
                    f"Would update planner note {validated}.",
                    f"  Current title: {fence_untrusted_inline(note.get('title') or '', 'planner note title')}",
                    f"  Current to-do date: {format_date(note.get('todo_date'))}",
                    f"  Current course: {await _course_display(note.get('course_id'))}",
                ]
                if note.get("description"):
                    preview.append(
                        "  Current details:\n"
                        + fence_untrusted(note["description"], "planner note details")
                    )
                preview.append("\n  Changes:")
                if "title" in data:
                    preview.append(f"  New title: {fence_untrusted_inline(title, 'proposed title')}")
                if "todo_date" in data:
                    preview.append(f"  New to-do date: {data['todo_date']}")
                if "course_id" in data:
                    preview.append(f"  New course: {await _course_display(data['course_id'])}")
                if "details" in data:
                    preview.append(
                        "  New details (replace the old text entirely):\n"
                        + fence_untrusted(details, "proposed note details")
                    )
                return preview_with_token(
                    _UPDATE_NOTE_GUARD, fingerprint, "update_planner_note",
                    "\n".join(preview), action="update the note",
                )

            error = redeem_confirmation(_UPDATE_NOTE_GUARD, confirmation_token, fingerprint)
            if error:
                return error

            # Re-checked at the moment of the write, not only at preview time.
            policy_error = await _course_policy_error(courses, "update_planner_note", "Update")
            if policy_error:
                return policy_error

            assert_no_identity_override(data)
            updated = await make_canvas_request(
                "put", f"/planner_notes/{validated}", data=data, use_form_data=True
            )
            if _is_error(updated):
                return f"❌ Could not update planner note {validated}: {_error_detail(updated)}"
            landed = isinstance(updated, dict) and (
                "title" not in data or updated.get("title") == data["title"]
            ) and ("details" not in data or updated.get("description") == data["details"]) and (
                "course_id" not in data or str(updated.get("course_id")) == data["course_id"]
            ) and (
                "todo_date" not in data or _planner_date_matches(
                    updated.get("todo_date"), data["todo_date"], me.get("time_zone")
                )
            )
            if not landed:
                return unconfirmed_write_warning(
                    "the planner note was updated",
                    {"Note ID": validated},
                    "Canvas accepted the request but did not return the new "
                    "content. Check the note with list_planner_notes.",
                )
            return "✅ Planner note updated.\n" + await _format_note(updated)

    if "delete_planner_note" in enabled:

        @mcp.tool(annotations=ToolAnnotations(destructive_hint=True, idempotent_hint=True))
        @validate_params
        async def delete_planner_note(
            note_id: str | int,
            confirmation_token: str | None = None,
        ) -> str:
            """Delete one of YOUR OWN planner notes. Two-step.

            Call without confirmation_token to preview and get a token; call
            again with the token to delete.

            Args:
                note_id: Planner note ID (from list_planner_notes)
                confirmation_token: Token from the preview call; omit to preview
            """
            validated = coerce_canvas_id(note_id)
            if validated is None:
                return _INVALID_ID.format(name="note_id")

            my_id, me_error = await _my_user_id()
            if me_error:
                return me_error
            assert my_id is not None
            note, note_error = await _fetch_my_note(validated, my_id)
            if note_error:
                return note_error
            assert note is not None

            course, course_refusal = _note_course(note)
            if course_refusal:
                return course_refusal
            courses = {course} if course else set()
            policy_error = await _course_policy_error(courses, "delete_planner_note", "Delete")
            if policy_error:
                return policy_error

            fingerprint = _DELETE_NOTE_GUARD.fingerprint(
                "delete_planner_note", validated,
                str(note.get("title")), str(note.get("description")),
                str(note.get("todo_date")), str(note.get("course_id")),
            )
            if not confirmation_token:
                return preview_with_token(
                    _DELETE_NOTE_GUARD, fingerprint, "delete_planner_note",
                    "Would delete this planner note:\n" + await _format_note(note),
                )

            error = redeem_confirmation(_DELETE_NOTE_GUARD, confirmation_token, fingerprint)
            if error:
                return error
            policy_error = await _course_policy_error(courses, "delete_planner_note", "Delete")
            if policy_error:
                return policy_error

            deleted = await make_canvas_request("delete", f"/planner_notes/{validated}")
            if _is_error(deleted):
                return f"❌ Could not delete planner note {validated}: {_error_detail(deleted)}"
            return f"✅ Planner note {validated} deleted."

    if "mark_planner_item_complete" in enabled:

        # Destructive: complete=False removes a completion, and Canvas also
        # un-completes the item's "Mark as done" module requirement, which
        # can re-lock later modules. See internal/architecture.md.
        @mcp.tool(annotations=ToolAnnotations(destructive_hint=True, idempotent_hint=True))
        @validate_params
        async def mark_planner_item_complete(
            plannable_type: str,
            plannable_id: str | int,
            course_identifier: str | int | None = None,
            complete: bool = True,
        ) -> str:
            """Tick (or untick) an item in YOUR OWN Canvas planner.

            Does not submit anything. For course content (assignment, quiz,
            discussion, announcement, page) Canvas also syncs the item's
            module progress: ticking it satisfies a "Mark as done" module
            requirement, and unticking it reverses that, which can re-lock
            later modules. Course content therefore also needs
            mark_module_item_done to be permitted in that course.

            Args:
                plannable_type: assignment, quiz, discussion_topic, announcement,
                    wiki_page, planner_note or calendar_event
                plannable_id: The item's Canvas ID
                course_identifier: The item's course (required for course
                    content; not needed for planner_note or calendar_event)
                complete: True to mark complete (default), False to unmark
            """
            if plannable_type not in _PLANNABLE_TYPES:
                return (
                    "Error: plannable_type must be one of "
                    f"{', '.join(_PLANNABLE_TYPES)}."
                )
            validated = coerce_canvas_id(plannable_id)
            if validated is None:
                return _INVALID_ID.format(name="plannable_id")

            courses: set[str] = set()
            # Course content is a ContextModuleItem; Canvas's override
            # create/update run sync_module_requirement_done on it.
            module_courses: set[str] = set()
            # Ids Canvas may have stored this item's override under.
            stored_ids = {validated}
            if plannable_type == "planner_note":
                my_id, me_error = await _my_user_id()
                if me_error:
                    return me_error
                assert my_id is not None
                target, target_error = await _fetch_my_note(validated, my_id)
                if target_error:
                    return target_error
                assert target is not None
                label = target.get("title")
                course, course_refusal = _note_course(target)
                if course_refusal:
                    return course_refusal
                if course:
                    courses.add(course)
            elif plannable_type == "calendar_event":
                my_id, me_error = await _my_user_id()
                if me_error:
                    return me_error
                assert my_id is not None
                target = await make_canvas_request("get", f"/calendar_events/{validated}")
                if not isinstance(target, dict) or _is_error(target):
                    return f"Error fetching calendar event {validated}: {_error_detail(target)}"
                event_courses, event_error = await _calendar_event_courses(target, my_id)
                if event_error:
                    return event_error
                label = target.get("title")
                courses |= event_courses
            else:
                if course_identifier is None:
                    return (
                        f"Error: course_identifier is required for a {plannable_type}."
                    )
                course_id, course_error = await _resolve_numeric_course_id(course_identifier)
                if course_error:
                    return course_error
                assert course_id is not None
                segment, title_key = _COURSE_PLANNABLES[plannable_type]
                target = await make_canvas_request(
                    "get", f"/courses/{course_id}/{segment}/{validated}"
                )
                if not isinstance(target, dict) or _is_error(target):
                    return (
                        f"Error: could not find {plannable_type} {validated} in that "
                        f"course: {_error_detail(target)}"
                    )
                label = target.get(title_key)
                courses.add(course_id)
                module_courses.add(course_id)
                # PlannerOverride#link_to_parent_topic stores a group
                # discussion's child topic under its root topic.
                root = coerce_canvas_id(target.get("root_topic_id") or "")
                if plannable_type in ("discussion_topic", "announcement") and root:
                    stored_ids.add(root)

            policy_error = await _course_policy_error(
                courses, "mark_planner_item_complete", "Update"
            )
            if policy_error:
                return policy_error
            module_error = await _course_policy_error(
                module_courses, "mark_module_item_done", "Update"
            )
            if module_error:
                return (
                    f"{module_error}\nMarking course content complete in the planner "
                    "also completes (or, when unmarking, reverses) its 'Mark as done' "
                    "module requirement, so mark_module_item_done must be permitted too."
                )

            overrides = await fetch_all_paginated_results(
                "/planner/overrides", params={"per_page": 100}
            )
            if _is_error(overrides) or not isinstance(overrides, list):
                return (
                    "❌ Could not read your existing planner overrides, so nothing "
                    f"was changed: {_error_detail(overrides)}"
                )
            existing = _find_override(overrides, plannable_type, stored_ids, validated)

            shown = fence_untrusted_inline(label or f"{plannable_type} {validated}", "planner item title")
            state = "complete" if complete else "not complete"
            if existing is not None and bool(existing.get("marked_complete")) == complete:
                return f"✅ {shown} is already marked {state} in your planner."

            flag = "true" if complete else "false"
            override_id = (
                coerce_canvas_id(existing.get("id", "")) if existing is not None else None
            )
            # Pagination may outlast a policy grant. Recheck both permissions
            # after reading the overrides, immediately before the mutation.
            policy_error = await _course_policy_error(
                courses, "mark_planner_item_complete", "Update"
            )
            if policy_error:
                return policy_error
            module_error = await _course_policy_error(
                module_courses, "mark_module_item_done", "Update"
            )
            if module_error:
                return module_error

            if override_id is not None:
                assert existing is not None
                # Canvas's update sets dismissed from the request
                # unconditionally, so the current value is sent back or a
                # dismissed item would reappear in the student's list.
                response = await make_canvas_request(
                    "put", f"/planner/overrides/{override_id}",
                    data={
                        "marked_complete": flag,
                        "dismissed": "true" if existing.get("dismissed") else "false",
                    },
                    use_form_data=True,
                )
            else:
                body = {
                    "plannable_type": plannable_type,
                    "plannable_id": validated,
                    "marked_complete": flag,
                }
                assert_no_identity_override(body)
                response = await make_canvas_request(
                    "post", "/planner/overrides", data=body, use_form_data=True
                )
                if _is_error(response):
                    # GET /planner/overrides lists only active overrides, but
                    # a deleted one still counts for Canvas's uniqueness check.
                    return (
                        f"❌ Could not update your planner: {_error_detail(response)}\n"
                        "If Canvas reports the item as already taken, it holds a "
                        "planner record for this item that the API does not list "
                        "(for example a removed one). Tick it in the Canvas planner "
                        "instead."
                    )
            if _is_error(response):
                return f"❌ Could not update your planner: {_error_detail(response)}"
            if not isinstance(response, dict) or bool(response.get("marked_complete")) != complete:
                return unconfirmed_write_warning(
                    f"the item was marked {state}",
                    {"Item": shown, "Type": plannable_type},
                    "Canvas accepted the request but did not report the new "
                    "state. Check your planner in Canvas.",
                )
            return f"✅ {shown} marked {state} in your planner."

    if "create_personal_calendar_event" in enabled:

        @mcp.tool(annotations=ToolAnnotations(destructive_hint=False, idempotent_hint=False))
        @validate_params
        async def create_personal_calendar_event(
            title: str,
            start_at: str,
            end_at: str | None = None,
            description: str | None = None,
            location_name: str | None = None,
            all_day: bool = False,
        ) -> str:
            """Add an event to YOUR OWN personal Canvas calendar.

            Always goes on your personal calendar, never a course or group
            calendar, so nobody else is notified.

            Args:
                title: Event title
                start_at: Start, ISO 8601 date-time with an offset such as
                    2026-10-06T15:00:00-07:00 (or YYYY-MM-DD with all_day)
                end_at: Optional end, same format
                description: Optional description
                location_name: Optional location
                all_day: True for an all-day event
            """
            if not title.strip():
                return "Error: title cannot be empty."
            if _has_fence_markers(title, description, location_name):
                return FENCE_LEAK_ERROR
            start_wire, start_dt, start_error = _to_canvas_date(start_at, "start_at")
            if start_error:
                return start_error
            data: dict[str, Any] = {
                "calendar_event[title]": title,
                "calendar_event[start_at]": start_wire,
            }
            if end_at:
                end_wire, end_dt, end_error = _to_canvas_date(end_at, "end_at")
                if end_error:
                    return end_error
                assert start_dt is not None and end_dt is not None
                if end_dt < start_dt:
                    return "Error: end_at is before start_at."
                data["calendar_event[end_at]"] = end_wire
            if description:
                data["calendar_event[description]"] = description
            if location_name:
                data["calendar_event[location_name]"] = location_name
            if all_day:
                data["calendar_event[all_day]"] = "true"

            my_id, me_error = await _my_user_id()
            if me_error:
                return me_error
            my_context = f"user_{my_id}"
            # The context comes only from /users/self, never from the caller.
            data["calendar_event[context_code]"] = my_context

            assert_no_identity_override(data)
            created = await make_canvas_request(
                "post", "/calendar_events", data=data, use_form_data=True
            )
            if _is_error(created):
                return f"❌ Could not create the event: {_error_detail(created)}"
            if not isinstance(created, dict) or created.get("id") is None:
                return unconfirmed_write_warning(
                    "the event was created",
                    {"Title": title, "Start": start_wire},
                    "Canvas returned no event. Check your calendar before "
                    "retrying, or the event may be duplicated.",
                )
            if created.get("context_code") != my_context:
                # A response that does not name the calendar is not proof it
                # landed on the personal one.
                return unconfirmed_write_warning(
                    "the event landed on your personal calendar",
                    {"Event ID": created.get("id"), "Calendar": created.get("context_code")},
                    "Check this event in Canvas.",
                )
            return "✅ Event added to your personal calendar.\n" + _format_event(
                created, {my_context: "Personal calendar"}, my_context, include_description=False
            )

    if "delete_personal_calendar_event" in enabled:

        @mcp.tool(annotations=ToolAnnotations(destructive_hint=True, idempotent_hint=True))
        @validate_params
        async def delete_personal_calendar_event(
            event_id: str | int,
            confirmation_token: str | None = None,
        ) -> str:
            """Delete an event from YOUR OWN personal calendar. Two-step.

            Course, group and appointment events are refused. Call without
            confirmation_token to preview and get a token; call again with it
            to delete. For a repeating event only this occurrence is deleted.

            Args:
                event_id: Calendar event ID (from list_calendar_events)
                confirmation_token: Token from the preview call; omit to preview
            """
            validated = coerce_canvas_id(event_id)
            if validated is None:
                return _INVALID_ID.format(name="event_id")

            my_id, me_error = await _my_user_id()
            if me_error:
                return me_error
            assert my_id is not None
            event, event_error = await _fetch_my_personal_event(validated, my_id)
            if event_error:
                return event_error
            assert event is not None

            in_series = bool(event.get("series_uuid"))
            fingerprint = _DELETE_EVENT_GUARD.fingerprint(
                "delete_personal_calendar_event", validated,
                str(event.get("title")), str(event.get("start_at")),
                str(event.get("end_at")), str(event.get("context_code")),
                str(event.get("series_uuid")),
            )
            if not confirmation_token:
                my_context = f"user_{my_id}"
                preview = "Would delete this event from your personal calendar:\n" + _format_event(
                    event, {my_context: "Personal calendar"}, my_context, include_description=False
                )
                if in_series:
                    preview += "\n  Repeating event: only this occurrence is deleted."
                return preview_with_token(
                    _DELETE_EVENT_GUARD, fingerprint, "delete_personal_calendar_event", preview
                )

            error = redeem_confirmation(_DELETE_EVENT_GUARD, confirmation_token, fingerprint)
            if error:
                return error

            deleted = await make_canvas_request(
                "delete", f"/calendar_events/{validated}",
                params={"which": "one"} if in_series else None,
            )
            if _is_error(deleted):
                return f"❌ Could not delete event {validated}: {_error_detail(deleted)}"
            return f"✅ Event {validated} deleted from your personal calendar."
