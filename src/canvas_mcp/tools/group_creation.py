"""Caller-owned course group creation; no adoption or membership reassignment."""

import asyncio
import csv
import io
import json
import secrets
import time
from dataclasses import dataclass, field
from typing import Any

from fastmcp import FastMCP
from mcp.types import ToolAnnotations

from ..core.cache import resolve_numeric_course_id
from ..core.client import fetch_all_paginated_results, make_canvas_request
from ..core.tool_results import FULL_CONTENT_TOOL_META
from ..core.untrusted_content import (
    contains_fence_markers,
    fence_untrusted,
    fence_untrusted_inline,
)
from ..core.validation import coerce_canvas_id, validate_params
from ..core.write_confirmation import ConfirmationGuard
from ..core.write_outcome import RequestFailure, WriteOutcome

_GUARD = ConfirmationGuard(nothing_done="Nothing was changed by this call.")
_WORK_LOCK = asyncio.Lock()
_PERMISSIONS = ["manage_groups_add", "manage_groups_manage", "read_roster"]
_RUN_TTL = 24 * 60 * 60
_MAX_RUNS = 128


@dataclass(frozen=True)
class GroupPlan:
    name: str
    description: str
    users: tuple[str, ...]


@dataclass
class GroupRun:
    owner: str
    course: str
    name: str
    plan: tuple[GroupPlan, ...]
    expires: float = field(default_factory=lambda: time.monotonic() + _RUN_TTL)
    category: str | None = None
    groups: dict[str, str] = field(default_factory=dict)
    members: dict[str, str] = field(default_factory=dict)
    revision: int = 0
    uncertain_creation: bool = False
    failure: str | None = None
    last_operation: dict[str, Any] | None = None


_RUNS: dict[str, GroupRun] = {}


def _error(message: str, token: str | None = None, **details: Any) -> dict[str, Any]:
    if token:
        # A refused confirm cannot later be replayed against reverted state.
        _GUARD.reserve(token)
    return {"error": message, **details}


def _text(value: str, limit: int, *, allow_empty: bool = False) -> str:
    text = value.strip()
    if (
        (not text and not allow_empty)
        or len(text) > limit
        or contains_fence_markers(text)
        or any(not c.isprintable() and c not in "\n\t" for c in text)
    ):
        raise ValueError(
            "Names/descriptions must be bounded plain text without content-fence markers or control characters."
        )
    return text


def _parse_csv(value: str) -> tuple[GroupPlan, ...]:
    if len(value) > 250000:
        raise ValueError("CSV exceeds 250,000 characters.")
    reader = csv.DictReader(io.StringIO(value), strict=True)
    if reader.fieldnames is None or sorted(reader.fieldnames) != [
        "canvas_user_id",
        "description",
        "group_name",
    ]:
        raise ValueError(
            "CSV must contain exactly group_name,description,canvas_user_id columns."
        )
    groups: dict[str, tuple[str, list[str]]] = {}
    seen: set[str] = set()
    aliases: dict[str, str] = {}
    for row in reader:
        if None in row or any(v is None for v in row.values()):
            raise ValueError("Every CSV row must have exactly three fields.")
        name = _text(row["group_name"], 100)
        description = _text(row["description"], 1000, allow_empty=True)
        uid = _id(row["canvas_user_id"])
        if uid is None:
            raise ValueError(
                "Every canvas_user_id must be a numeric Canvas ID; names and emails are not matched."
            )
        if uid in seen:
            raise ValueError(
                f"Duplicate or conflicting input rows for Canvas user ID {uid}."
            )
        if name.casefold() in aliases and aliases[name.casefold()] != name:
            raise ValueError("Group names that differ only in case are ambiguous.")
        aliases[name.casefold()] = name
        if name in groups and groups[name][0] != description:
            raise ValueError("Rows for the same group must have the same description.")
        groups.setdefault(name, (description, []))[1].append(uid)
        seen.add(uid)
        if len(seen) > 200 or len(groups) > 50:
            raise ValueError(
                "At most 200 students and 50 groups are supported per run."
            )
    if not groups:
        raise ValueError("CSV must contain at least one student row.")
    return tuple(
        GroupPlan(name, desc, tuple(users)) for name, (desc, users) in groups.items()
    )


def _id(value: Any) -> str | None:
    return coerce_canvas_id(value) if isinstance(value, (str, int)) else None


def _identity(record: Any, course: str, *, category: str | None = None) -> bool:
    return (
        isinstance(record, dict)
        and "error" not in record
        and _id(record.get("id")) is not None
        and record.get("context_type") == "Course"
        and _id(record.get("course_id")) == course
        and (
            record.get("non_collaborative") is None
            or record.get("non_collaborative") is False
        )
        and (category is None or _id(record.get("group_category_id")) == category)
    )


async def _list(
    endpoint: str, params: dict[str, Any] | None = None
) -> list[dict[str, Any]]:
    result = await fetch_all_paginated_results(
        endpoint, {"per_page": 100, **(params or {})}
    )
    if not isinstance(result, list) or any(not isinstance(r, dict) for r in result):
        raise ValueError(
            "Canvas list could not be read completely. Nothing further was written."
        )
    return result


async def _inspect(run: GroupRun) -> dict[str, Any]:
    """Re-read authorization, ownership and ALL memberships before writing."""
    permissions = await make_canvas_request(
        "get",
        f"/courses/{run.course}/permissions",
        params={"permissions[]": _PERMISSIONS},
    )
    if (
        not isinstance(permissions, dict)
        or "error" in permissions
        or any(
            not (permissions.get(p) is True or permissions.get(p) == "true")
            for p in _PERMISSIONS
        )
    ):
        raise ValueError(
            "Explicit Canvas manage_groups_add, manage_groups_manage and read_roster permissions are required."
        )
    course = await make_canvas_request("get", f"/courses/{run.course}")
    if (
        not isinstance(course, dict)
        or "error" in course
        or _id(course.get("id")) != run.course
    ):
        raise ValueError("Canvas course identity could not be verified.")
    enrollments = await _list(
        f"/courses/{run.course}/enrollments",
        {"type[]": ["StudentEnrollment"], "state[]": ["active"]},
    )
    enrolled = {
        _id(r.get("user_id"))
        for r in enrollments
        if r.get("type") == "StudentEnrollment"
        and r.get("enrollment_state") == "active"
    }
    missing = sorted({uid for group in run.plan for uid in group.users} - enrolled)
    if missing:
        raise ValueError(
            "These Canvas user IDs lack a visible active student enrollment: "
            + ", ".join(missing)
        )
    if run.category is None:
        categories = await _list(f"/courses/{run.course}/group_categories")
        if any(
            not isinstance(r.get("name"), str) or _id(r.get("id")) is None
            for r in categories
        ):
            raise ValueError(
                "Malformed group-set listing; cannot check for duplicate names."
            )
        if any(r["name"].strip().casefold() == run.name.casefold() for r in categories):
            raise ValueError(
                "A group set with that name already exists. Existing group sets are never adopted or duplicated."
            )
        return {
            "course_code": str(course.get("course_code") or run.course)[:200],
            "categories": sorted((str(r["id"]), r["name"]) for r in categories),
            "memberships": {},
            "conflicts": [],
        }
    category = await make_canvas_request("get", f"/group_categories/{run.category}")
    if (
        not _identity(category, run.course)
        or str(category["id"]) != run.category
        or category.get("name") != run.name
        or category.get("self_signup") is not None
    ):
        raise ValueError(
            "Recorded group set changed or its course ownership cannot be verified."
        )
    groups = await _list(f"/group_categories/{run.category}/groups")
    if any(not _identity(g, run.course, category=run.category) for g in groups):
        raise ValueError(
            "Group ownership or complete category contents cannot be verified."
        )
    by_id = {str(g["id"]): g for g in groups}
    if len(by_id) != len(groups):
        raise ValueError("Duplicate group IDs in Canvas response.")
    for group in run.plan:
        gid = run.groups.get(group.name)
        if gid:
            fresh = await make_canvas_request("get", f"/groups/{gid}")
            if (
                gid not in by_id
                or not _identity(fresh, run.course, category=run.category)
                or str(fresh["id"]) != gid
                or fresh.get("name") != group.name
                or (fresh.get("description") or "") != group.description
                or fresh.get("is_public") is not False
            ):
                raise ValueError(
                    "A recorded group changed, is missing, or no longer belongs to this course/group set."
                )
        elif any(
            str(g.get("name", "")).strip().casefold() == group.name.casefold()
            for g in groups
        ):
            raise ValueError(
                "An unrecorded group has a planned name; it will not be adopted or duplicated."
            )
    desired = {uid: run.groups.get(g.name) for g in run.plan for uid in g.users}
    memberships: dict[str, list[tuple[str, str]]] = {}
    conflicts = []
    for gid in sorted(by_id):
        members = await _list(f"/groups/{gid}/memberships")
        pairs = []
        for member in members:
            uid = _id(member.get("user_id"))
            state = member.get("workflow_state")
            if (
                uid is None
                or _id(member.get("group_id")) != gid
                or state not in ("accepted", "invited", "requested")
            ):
                raise ValueError(
                    "Malformed membership data; conflict checking cannot be completed."
                )
            pairs.append((uid, state))
            if uid in desired and (desired[uid] != gid or state != "accepted"):
                conflicts.append(
                    {
                        "user_id": uid,
                        "current_group_id": gid,
                        "requested_group_id": desired[uid],
                        "current_state": state,
                    }
                )
        memberships[gid] = sorted(pairs)
    for uid, status in run.members.items():
        if (
            not conflicts
            and status == "confirmed"
            and (uid, "accepted") not in memberships.get(desired[uid] or "", [])
        ):
            raise ValueError(
                "A previously confirmed membership changed; it will not be silently restored."
            )
    return {
        "course_code": str(course.get("course_code") or run.course)[:200],
        "category": run.category,
        "groups": sorted(by_id),
        "memberships": memberships,
        "conflicts": conflicts,
    }


def _report(run_id: str, run: GroupRun, status: str) -> dict[str, Any]:
    return {
        "status": status,
        "run_id": run_id,
        "group_set_id": run.category,
        "group_set_name": fence_untrusted_inline(run.name, "group set name"),
        "groups": [
            {
                "name": fence_untrusted_inline(g.name, "group name"),
                "description": fence_untrusted(g.description, "group description"),
                "group_id": run.groups.get(g.name),
                "members": [
                    {"user_id": uid, "status": run.members.get(uid, "pending")}
                    for uid in g.users
                ],
            }
            for g in run.plan
        ],
        "failure": run.failure,
        "last_operation": run.last_operation,
        "resume": {
            "tool": "resume_course_group_creation",
            "run_id": run_id,
            "fresh_confirmation_required": True,
        },
        "note": "Only this run's recorded created IDs are used. Existing assignments are never intentionally moved. Runs expire after 24 hours and do not survive server restart. Inspect uncertain creations manually; do not repeat creation blindly.",
    }


def _fingerprint(
    action: str, run: GroupRun, snapshot: dict[str, Any], run_id: str = ""
) -> str:
    plan = [[g.name, g.description, g.users] for g in run.plan]
    return _GUARD.fingerprint(
        action,
        run_id,
        run.course,
        run.name,
        json.dumps(plan),
        str(run.revision),
        json.dumps(snapshot, sort_keys=True),
    )


def _preview(
    action: str, run: GroupRun, snapshot: dict[str, Any], run_id: str = ""
) -> dict[str, Any]:
    result = _report(run_id, run, "preview")
    for group, displayed in zip(run.plan, result["groups"], strict=True):
        gid = run.groups.get(group.name)
        displayed["action"] = "use_recorded_group" if gid else "create_group"
        for member in displayed["members"]:
            member["action"] = (
                "skip_verified"
                if (member["user_id"], "accepted")
                in snapshot["memberships"].get(gid or "", [])
                else "add_membership"
            )
    result.update(
        course=snapshot["course_code"],
        confirmation_token=_GUARD.issue(_fingerprint(action, run, snapshot, run_id)),
        instruction="Nothing was written. Show every planned group and Canvas user ID to the user; only after explicit approval call the same tool with identical arguments and this single-use token (expires in five minutes).",
    )
    return result


async def _dispatch(
    run: GroupRun, endpoint: str, data: dict[str, str], *, creation: bool
) -> Any:
    # Set uncertainty BEFORE awaiting dispatch, including cancellation. A known
    # negative response may clear it; a timeout/unknown response never does.
    if creation:
        run.uncertain_creation = True
    run.last_operation = {
        "endpoint": endpoint,
        "status": "uncertain",
        "user_id": data.get("user_id"),
    }
    if "name" in data:
        run.last_operation["name"] = fence_untrusted_inline(
            data["name"], "created object name"
        )
    response = await make_canvas_request(
        "post", endpoint, data=data, use_form_data=True
    )
    if isinstance(response, dict) and "error" not in response:
        return response
    rejected = isinstance(response, RequestFailure) and response.outcome in (
        WriteOutcome.NOT_DISPATCHED,
        WriteOutcome.REJECTED,
    )
    if creation and rejected:
        run.uncertain_creation = False
    if rejected:
        run.last_operation["status"] = "failed"
    run.failure = (
        "Canvas rejected the operation."
        if rejected
        else "Operation outcome is uncertain; inspect Canvas before retrying."
    )
    raise ValueError(run.failure)


async def _execute(run_id: str, run: GroupRun) -> dict[str, Any]:
    run.failure = None
    try:
        if run.category is None:
            before = await _inspect(run)
            category = await _dispatch(
                run,
                f"/courses/{run.course}/group_categories",
                {"name": run.name, "non_collaborative": "false"},
                creation=True,
            )
            if (
                not _identity(category, run.course)
                or category.get("name") != run.name
                or _id(category.get("id")) in {cid for cid, _ in before["categories"]}
            ):
                raise ValueError(
                    "Group-set creation is uncertain: response identity/payload did not match."
                )
            run.category = _id(category["id"])
            assert run.category is not None
            run.uncertain_creation = False
            await _inspect(run)
            assert run.last_operation is not None
            run.last_operation["status"] = "confirmed"
        # Revalidate the entire run before each write, not just the selected
        # student's target. A conflict anywhere stops the remaining batch.
        for group in run.plan:
            if group.name in run.groups:
                continue
            snapshot = await _inspect(run)
            if snapshot["conflicts"]:
                return _error(
                    "Conflicting memberships; nothing further was written.",
                    **_report(run_id, run, "partial_failure"),
                    conflicts=snapshot["conflicts"],
                )
            created = await _dispatch(
                run,
                f"/group_categories/{run.category}/groups",
                {"name": group.name, "description": group.description},
                creation=True,
            )
            if (
                not _identity(created, run.course, category=run.category)
                or created.get("name") != group.name
                or (created.get("description") or "") != group.description
            ):
                raise ValueError(
                    "Group creation is uncertain: response identity/payload did not match."
                )
            gid = _id(created["id"])
            assert gid is not None
            if gid in snapshot["groups"]:
                raise ValueError(
                    "Group creation is uncertain: Canvas returned a pre-existing ID; it will not be adopted."
                )
            run.groups[group.name] = gid
            run.uncertain_creation = False
            await _inspect(run)  # Independently read every created object back.
            assert run.last_operation is not None
            run.last_operation["status"] = "confirmed"
        for group in run.plan:
            gid = run.groups[group.name]
            for uid in group.users:
                snapshot = await _inspect(run)
                if snapshot["conflicts"]:
                    return _error(
                        "Conflicting memberships; nothing further was written.",
                        **_report(run_id, run, "partial_failure"),
                        conflicts=snapshot["conflicts"],
                    )
                if (uid, "accepted") in snapshot["memberships"].get(gid or "", []):
                    run.members[uid] = "confirmed"
                    continue
                run.members[uid] = "uncertain"
                response = await _dispatch(
                    run, f"/groups/{gid}/memberships", {"user_id": uid}, creation=False
                )
                after = await make_canvas_request("get", f"/groups/{gid}/users/{uid}")
                if any(
                    not isinstance(record, dict)
                    or "error" in record
                    or _id(record.get("group_id")) != gid
                    or _id(record.get("user_id")) != uid
                    or record.get("workflow_state") != "accepted"
                    for record in (response, after)
                ):
                    raise ValueError(
                        "Membership outcome is uncertain: accepted membership did not read back."
                    )
                run.members[uid] = "confirmed"
                assert run.last_operation is not None
                run.last_operation["status"] = "confirmed"
        if run.last_operation:
            assert run.last_operation is not None
            run.last_operation["status"] = "confirmed"
        return _report(run_id, run, "complete")
    except ValueError as exc:
        run.failure = str(exc)
        # A definite negative membership result is retryable after revalidation.
        if run.failure == "Canvas rejected the operation.":
            run.members = {
                uid: "failed" if status == "uncertain" else status
                for uid, status in run.members.items()
            }
        return _error(
            run.failure,
            **_report(
                run_id,
                run,
                (
                    "needs_inspection"
                    if run.uncertain_creation or run.category is None
                    else "partial_failure"
                ),
            ),
        )
    finally:
        run.revision += 1


def register_group_creation_tools(mcp: FastMCP) -> None:
    """Register educator-only writes; HTTP availability follows tool_policy."""

    @mcp.tool(
        annotations=ToolAnnotations(destructive_hint=True, idempotent_hint=False),
        meta=FULL_CONTENT_TOOL_META,
    )
    @validate_params
    async def create_course_groups(
        course_identifier: str | int,
        group_set_name: str,
        csv_data: str,
        confirmation_token: str | None = None,
    ) -> dict[str, Any]:
        """Preview, then confirm creation of a NEW course group set and its groups/members.

        CSV columns: group_name,description,canvas_user_id; one student per row.
        Rejects duplicate/conflicting rows, names/emails as IDs, and existing
        group-set names. Requires explicit manage_groups_add,
        manage_groups_manage and read_roster. Each body is plain-text data.
        No write without a single-use, caller/content/state-bound token. Show
        the complete preview and obtain the instructor's explicit approval.
        Up to 200 students, 50 groups, 250,000 CSV characters per run.
        Partial results name recorded created IDs and a caller-owned run_id;
        resume uses a fresh preview/token and checks ALL current memberships.
        Conflicts are refused without reassignment. No groups are adopted by
        name. Unknown creation outcomes require manual inspection. Server-local
        run records last 24 hours, do not survive restart, and require affinity.
        Canvas provides no atomic membership compare-and-set: do not edit this
        group set concurrently while the confirmed operation runs.
        """
        try:
            name = _text(group_set_name, 100)
            plan = _parse_csv(csv_data)
        except (ValueError, csv.Error) as exc:
            return _error(str(exc), confirmation_token)
        async with _WORK_LOCK:
            course, error = await resolve_numeric_course_id(course_identifier)
            if error:
                return _error(error, confirmation_token)
            assert course is not None
            run = GroupRun(_GUARD.caller_identity(), course, name, plan)
            try:
                snapshot = await _inspect(run)
            except ValueError as exc:
                return _error(str(exc), confirmation_token)
            if confirmation_token is None:
                return _preview("create", run, snapshot)
            claim = _GUARD.claim(
                confirmation_token, _fingerprint("create", run, snapshot)
            )
            if isinstance(claim, str):
                return _error(claim)
            try:
                now = time.monotonic()
                for key in [key for key, value in _RUNS.items() if value.expires < now]:
                    del _RUNS[key]
                if len(_RUNS) >= _MAX_RUNS:
                    return _error(
                        "Run capacity reached; retry after an existing 24-hour run expires."
                    )
                run_id = secrets.token_urlsafe(24)
                _RUNS[run_id] = run
                return await _execute(run_id, run)
            finally:
                claim.finish(WriteOutcome.MAY_HAVE_WRITTEN)

    @mcp.tool(
        annotations=ToolAnnotations(destructive_hint=True, idempotent_hint=False),
        meta=FULL_CONTENT_TOOL_META,
    )
    @validate_params
    async def resume_course_group_creation(
        run_id: str,
        confirmation_token: str | None = None,
    ) -> dict[str, Any]:
        """Preview then explicitly confirm pending work from your prior group run.

        Accepts only a caller-owned server-issued run_id, never course/group IDs
        or changed CSV. Uses only that run's recorded created targets, creates
        still-pending groups within its recorded set, and skips verified accepted
        memberships. Revalidates all memberships, ownership and permissions;
        shows every conflict and refuses the entire remaining batch on conflict.
        Requires a fresh preview and single-use token; initial tokens never work.
        Unknown category/group creation IDs cannot be recovered automatically.
        Run records expire after 24 hours or server restart. No deletion, moving
        students, automatic rollback or adoption of pre-existing objects.
        """
        async with _WORK_LOCK:
            run = _RUNS.get(run_id)
            if (
                run is None
                or run.expires < time.monotonic()
                or run.owner != _GUARD.caller_identity()
            ):
                return _error(
                    "Unknown, expired or unavailable run for this caller. Existing IDs cannot be supplied or adopted.",
                    confirmation_token,
                )
            if run.category is None or run.uncertain_creation:
                return _error(
                    "Creation outcome is uncertain or no created group-set ID was recorded. Inspect Canvas manually; no automatic resume or adoption is possible.",
                    confirmation_token,
                    **_report(run_id, run, "needs_inspection"),
                )
            try:
                snapshot = await _inspect(run)
            except ValueError as exc:
                return _error(
                    str(exc),
                    confirmation_token,
                    **_report(run_id, run, "partial_failure"),
                )
            if snapshot["conflicts"]:
                return _error(
                    "Conflicting memberships; nothing was written. Resolve outside this tool, then preview again.",
                    confirmation_token,
                    **_report(run_id, run, "partial_failure"),
                    conflicts=snapshot["conflicts"],
                )
            if confirmation_token is None:
                return _preview("resume", run, snapshot, run_id)
            claim = _GUARD.claim(
                confirmation_token, _fingerprint("resume", run, snapshot, run_id)
            )
            if isinstance(claim, str):
                return _error(claim)
            try:
                return await _execute(run_id, run)
            finally:
                claim.finish(WriteOutcome.MAY_HAVE_WRITTEN)
