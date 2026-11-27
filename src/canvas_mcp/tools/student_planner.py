"""Read the caller's complete planner, including instructor-scheduled Pages.

The self-scoped /planner/items endpoint is already used by student_tools.
Render only workload fields, never nested identities or submission bodies.
"""
import datetime as dt
from typing import Any
from urllib.parse import urljoin, urlparse
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastmcp import FastMCP
from mcp.types import ToolAnnotations

from ..core.cache import get_course_code, resolve_numeric_course_id
from ..core.client import fetch_all_paginated_results, make_canvas_request
from ..core.config import get_config
from ..core.dates import format_date, parse_date
from ..core.untrusted_content import fence_untrusted_inline, format_canvas_error
from ..core.validation import validate_params
from .student_tools import _planner_submission_status


def _now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def _bound(value: str, zone: ZoneInfo, *, end: bool = False) -> dt.datetime:
    """Dates include the whole local day; timestamps are exact boundaries."""
    if len(value) == 10:
        day = dt.date.fromisoformat(value)
        if end:
            day += dt.timedelta(days=1)
        return dt.datetime.combine(day, dt.time(), zone)
    instant = dt.datetime.fromisoformat(value)
    if instant.tzinfo is None:
        raise ValueError('timestamps require an explicit UTC offset')
    return instant


def _is_complete(item: dict[str, Any]) -> bool:
    override = item.get('planner_override')
    submissions = item.get('submissions')
    return (
        isinstance(override, dict) and override.get('marked_complete') is True
    ) or (
        item.get('plannable', {}).get('workflow_state') == 'completed'
    ) or (
        isinstance(submissions, dict)
        and (submissions.get('submitted') is True or submissions.get('excused') is True
             or (submissions.get('graded') is True and not submissions.get('missing')))
    )


async def _format_planner_item(item: dict[str, Any], zone: ZoneInfo) -> str:
    plannable = item['plannable']
    kind = item.get('plannable_type', 'unknown')
    due = plannable.get('due_at')
    todo = plannable.get('todo_date') or plannable.get('student_todo_at')
    if due:
        label = 'Assignment deadline'
    elif kind == 'planner_note':
        label = 'Personal planner note'
    elif todo or kind in ('wiki_page', 'discussion_topic'):
        label = 'Scheduled course to-do'
    else:
        label = 'Scheduled planner item'
    course_id = item.get('course_id')
    course = await get_course_code(course_id) if course_id else None
    lines = [
        f"• {fence_untrusted_inline(plannable.get('title') or plannable.get('name') or 'Untitled', 'planner item title')}",
        f"  Kind: {label} ({fence_untrusted_inline(kind, 'planner item type')})",
        f"  Course: {fence_untrusted_inline(course or item.get('context_name') or 'Personal / other context', 'planner context')}",
        f"  Planner ID: {fence_untrusted_inline(item.get('plannable_id', plannable.get('id', 'unknown')), 'planner item ID')}",
    ]
    for name, value in (
        ('Due', due), ('To-do date', todo), ('Scheduled', item.get('plannable_date')),
    ):
        if value:
            parsed = parse_date(value)
            # This tool's account/caller zone may differ from operator TIMEZONE.
            display = parsed.astimezone(zone).isoformat() if parsed else format_date(value)
            lines.append(f"  {name}: {fence_untrusted_inline(display, 'planner date')}")
    override = item.get('planner_override')
    if isinstance(override, dict) and isinstance(override.get('marked_complete'), bool):
        completion = 'Marked complete' if override['marked_complete'] else 'Marked incomplete'
    elif plannable.get('workflow_state') == 'completed':
        completion = 'Completed'
    else:
        completion = 'No completion override recorded'
    lines.append(f'  Completion: {completion}')
    submissions = item.get('submissions')
    if submissions is False:
        lines.append('  Submission: No Canvas submission required (no associated assignment)')
    elif isinstance(submissions, dict):
        lines.append(f'  Submission: {_planner_submission_status(submissions)}')
    else:
        lines.append('  Submission: Status unavailable')
    raw_url = item.get('html_url')
    if isinstance(raw_url, str):
        url = urljoin(get_config().canvas_api_url, raw_url)
        if urlparse(url).scheme in ('http', 'https'):
            lines.append(f"  Open in Canvas: {fence_untrusted_inline(url, 'planner item URL')}")
    return '\n'.join(lines)


def register_student_planner_tools(mcp: FastMCP) -> None:
    """Register read-only complete daily planner coverage."""

    @mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
    @validate_params
    async def list_planner_items(
        start_date: str | None = None,
        end_date: str | None = None,
        days: int = 1,
        course_identifier: str | int | None = None,
        timezone: str | None = None,
        incomplete_only: bool = False,
    ) -> str:
        """What do I have to do today? Read the complete daily Canvas planner.

        Includes assignment deadlines AND instructor-created reading Pages and
        ungraded discussions with to-do dates, plus personal planner notes and
        other planner types. Each kind is labelled separately. Prefer this for
        daily workload; get_my_todo_items and upcoming assignments are narrower.
        All pages are fetched. This reads only your own planner and changes no
        completion or submission state.

        Args:
            start_date: YYYY-MM-DD or ISO timestamp with offset; default local
                midnight today, including items earlier today.
            end_date: Inclusive YYYY-MM-DD, or exclusive ISO timestamp with
                offset. Default: days whole local days from start.
            days: Days when end_date is omitted (default 1, max 366).
            course_identifier: Optional course code or Canvas ID.
            timezone: IANA zone, e.g. America/Los_Angeles. Defaults to your
                Canvas profile's time_zone. Handles daylight-saving transitions.
            incomplete_only: Exclude completed/submitted/excused items (default
                False shows everything with completion status).
        """
        if not 1 <= days <= 366:
            return 'Error: days must be between 1 and 366.'
        course_id = None
        if course_identifier is not None:
            course_id, error = await resolve_numeric_course_id(course_identifier)
            if error:
                return f'Error resolving course: {error}'
        if timezone is None:
            profile = await make_canvas_request('get', '/users/self/profile')
            if not isinstance(profile, dict) or 'error' in profile:
                detail = profile.get('error', 'invalid response') if isinstance(profile, dict) else 'invalid response'
                return f'Error reading your Canvas time zone: {format_canvas_error(detail)}. Supply timezone explicitly.'
            timezone = profile.get('time_zone')
        try:
            if not timezone:
                raise ValueError('Canvas did not provide a time zone; supply timezone explicitly')
            zone = ZoneInfo(timezone)
            start = _bound(start_date, zone) if start_date else dt.datetime.combine(
                _now().astimezone(zone).date(), dt.time(), zone,
            )
            end = _bound(end_date, zone, end=True) if end_date else (
                start.astimezone(zone) + dt.timedelta(days=days)
            )
            lower, upper = start.astimezone(dt.UTC), end.astimezone(dt.UTC)
            span = end.astimezone(zone).replace(tzinfo=None) - start.astimezone(zone).replace(tzinfo=None)
            if upper <= lower or span > dt.timedelta(days=366):
                raise ValueError('window must be positive and no longer than 366 local days')
        except (ValueError, OverflowError, ZoneInfoNotFoundError) as exc:
            return f'Error: invalid planner date window or time zone: {exc}'

        params: dict[str, Any] = {
            'start_date': lower.strftime('%Y-%m-%dT%H:%M:%SZ'),
            'end_date': upper.strftime('%Y-%m-%dT%H:%M:%SZ'), 'per_page': 100,
        }
        if course_id is not None:
            params['context_codes[]'] = [f'course_{course_id}']
        if incomplete_only:
            params['filter'] = 'incomplete_items'
        items = await fetch_all_paginated_results('/planner/items', params=params)
        if isinstance(items, dict) and 'error' in items:
            return f"Error fetching planner items: {format_canvas_error(items['error'])}"
        if not isinstance(items, list) or any(
            not isinstance(item, dict) or not isinstance(item.get('plannable'), dict)
            or not isinstance(item.get('plannable_type'), str)
            for item in items
        ):
            return 'Error fetching planner items: invalid response; workload coverage could not be confirmed.'

        selected: list[tuple[dt.datetime, dict[str, Any]]] = []
        seen: set[tuple[Any, ...]] = set()
        for item in items:
            if course_id is not None and str(item.get('course_id')) != course_id:
                continue
            if incomplete_only and _is_complete(item):
                continue
            plannable = item['plannable']
            when = item.get('plannable_date') or plannable.get('due_at') or plannable.get('todo_date') or plannable.get('student_todo_at')
            if any(value is not None and not isinstance(value, str) for value in (
                when, plannable.get('due_at'), plannable.get('todo_date'), plannable.get('student_todo_at'),
            )):
                return 'Error fetching planner items: invalid schedule date; workload coverage is incomplete.'
            parsed = parse_date(when)
            if parsed is None:
                return 'Error fetching planner items: an item has no valid schedule date; workload coverage is incomplete.'
            if not lower <= parsed < upper:
                continue
            key = (str(item.get('course_id')), item.get('plannable_type'),
                   str(item.get('plannable_id', plannable.get('id', len(selected)))), when)
            if key in seen:
                continue
            seen.add(key)
            selected.append((parsed, item))
        selected.sort(key=lambda pair: pair[0])
        header = f'Planner from {start.astimezone(zone).isoformat()} to {end.astimezone(zone).isoformat()} (end exclusive; {timezone})'
        if not selected:
            return f'No planner items: {header}.'
        lines = [f'{header} ({len(selected)} items):\n']
        for _, item in selected:
            lines.append(await _format_planner_item(item, zone) + '\n')
        return '\n'.join(lines)
