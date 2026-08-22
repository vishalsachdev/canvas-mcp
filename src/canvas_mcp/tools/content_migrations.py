"""Educator tools for starting and checking Canvas content migrations."""

from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import urlsplit

from fastmcp import FastMCP
from mcp.types import ToolAnnotations

from ..core.cache import get_course_id
from ..core.client import fetch_all_paginated_results, make_canvas_request
from ..core.dates import parse_date
from ..core.untrusted_content import fence_untrusted
from ..core.validation import coerce_canvas_id, validate_params
from ..core.write_confirmation import ConfirmationGuard, unconfirmed_write_warning

_CONTENT_MIGRATION_GUARD = ConfirmationGuard()
_MIGRATION_TYPE = "course_copy_importer"

# Selective imports intentionally stay out of v1. Canvas's two-phase selective
# workflow needs live measurement before this server can expose it safely.
_SELECTIVE_IMPORT = "false"

_OCCUPANCY_ENDPOINTS = {
    "assignments": "assignments",
    "pages": "pages",
    "modules": "modules",
    "discussions": "discussion_topics",
    "files": "files",
}


async def _resolve_course(
    course_identifier: str | int, label: str
) -> tuple[str | None, dict[str, Any] | None, str | None]:
    """Resolve and verify one course, returning its canonical numeric ID."""
    try:
        resolved = await get_course_id(course_identifier)
        response = await make_canvas_request("get", f"/courses/{resolved}")
    except Exception as exc:
        return None, None, f"Could not resolve the {label} course: {exc}"

    if not isinstance(response, dict):
        return None, None, f"Could not resolve the {label} course: invalid response."
    if "error" in response:
        return (
            None,
            response,
            f"Could not resolve the {label} course: {response.get('error')}",
        )

    canonical_id = coerce_canvas_id(response.get("id", ""))
    if canonical_id is None:
        return (
            None,
            response,
            f"The {label} course response did not contain a numeric Canvas ID.",
        )
    return canonical_id, response, None


def _normalise_date_options(
    old_start_date: str | None,
    old_end_date: str | None,
    new_start_date: str | None,
    new_end_date: str | None,
) -> tuple[dict[str, str], str | None]:
    """Validate the optional all-or-none date group and normalize its values."""
    raw_dates = {
        "old_start_date": old_start_date,
        "old_end_date": old_end_date,
        "new_start_date": new_start_date,
        "new_end_date": new_end_date,
    }
    provided = [value is not None for value in raw_dates.values()]
    if any(provided) and not all(provided):
        return {}, "Provide either none or all four date-shift fields."
    if not any(provided):
        return {}, None

    parsed = {name: parse_date(value) for name, value in raw_dates.items()}
    invalid = [name for name, value in parsed.items() if value is None]
    if invalid:
        return {}, (
            "Each date-shift field must be a valid date. Invalid field(s): "
            + ", ".join(invalid)
            + "."
        )

    old_start = parsed["old_start_date"]
    old_end = parsed["old_end_date"]
    new_start = parsed["new_start_date"]
    new_end = parsed["new_end_date"]
    if old_start is None or old_end is None or new_start is None or new_end is None:
        return {}, "Each date-shift field must be a valid date."
    if old_start >= old_end:
        return {}, "old_start_date must be before old_end_date."
    if new_start >= new_end:
        return {}, "new_start_date must be before new_end_date."

    return {
        "shift_dates": "true",
        "old_start_date": old_start.isoformat(),
        "old_end_date": old_end.isoformat(),
        "new_start_date": new_start.isoformat(),
        "new_end_date": new_end.isoformat(),
    }, None


async def _target_occupancy(target_course_id: str) -> dict[str, Any]:
    """Count target-course objects that are readable through list endpoints."""
    counts: dict[str, Any] = {}
    unavailable: list[str] = []
    total = 0

    for label, endpoint_suffix in _OCCUPANCY_ENDPOINTS.items():
        try:
            response = await fetch_all_paginated_results(
                f"/courses/{target_course_id}/{endpoint_suffix}",
                {"per_page": 100},
            )
        except Exception:
            response = None

        if isinstance(response, list):
            count = len(response)
            counts[label] = count
            total += count
        else:
            counts[label] = None
            unavailable.append(label)

    counts["total_items"] = total
    counts["unavailable"] = unavailable
    return counts


def _occupancy_warning(occupancy: dict[str, Any]) -> str | None:
    warnings: list[str] = []
    total = occupancy.get("total_items", 0)
    if isinstance(total, int) and total > 0:
        warnings.append(
            f"Target course already contains {total} items; a course copy adds "
            "to it and may create duplicates. These counts show occupancy, "
            "not a content-level diff of what may collide."
        )
    unavailable = occupancy.get("unavailable", [])
    if isinstance(unavailable, list) and unavailable:
        warnings.append(
            "Some target contents could not be read, so the occupancy total is "
            "partial: "
            + ", ".join(str(item) for item in unavailable)
            + "."
        )
    return " ".join(warnings) or None


def _migration_fingerprint(
    source_course_id: str,
    target_course_id: str,
    date_options: dict[str, str],
) -> str:
    canonical_dates = json.dumps(
        date_options,
        sort_keys=True,
        separators=(",", ":"),
    )
    return _CONTENT_MIGRATION_GUARD.fingerprint(
        source_course_id,
        target_course_id,
        _MIGRATION_TYPE,
        _SELECTIVE_IMPORT,
        canonical_dates,
    )


def _next_status_action(course_id: str, migration_id: str) -> dict[str, Any]:
    return {
        "tool": "get_content_migration_status",
        "arguments": {
            "course_identifier": course_id,
            "migration_id": migration_id,
        },
    }


def _unconfirmed_start_error(
    source_course_id: str,
    target_course_id: str,
    detail: object,
) -> dict[str, Any]:
    warning = unconfirmed_write_warning(
        "whether Canvas created the content migration record",
        {
            "Source course ID": source_course_id,
            "Target course ID": target_course_id,
            "Detail": detail,
        },
        (
            "Check the target course's migration history before trying again; "
            "a retry could queue a duplicate migration."
        ),
    )
    return {
        "error": warning,
        "migration_start_unconfirmed": True,
    }


def _progress_id_from_url(progress_url: object) -> str | None:
    if not isinstance(progress_url, str) or not progress_url.strip():
        return None
    try:
        path = urlsplit(progress_url).path.rstrip("/")
    except ValueError:
        return None
    match = re.search(r"(?:^|/)progress/([0-9]+)$", path)
    return match.group(1) if match else None


def _progress_snapshot(progress: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": progress.get("id"),
        "workflow_state": progress.get("workflow_state"),
        "completion": progress.get("completion"),
        "message": progress.get("message"),
    }


def _fence_migration_issues(issues: list[Any]) -> list[Any]:
    fenced: list[Any] = []
    for issue in issues:
        if not isinstance(issue, dict):
            fenced.append(issue)
            continue
        item = dict(issue)
        for field, source in (
            ("description", "content migration issue description"),
            ("site_admin_error", "content migration issue administrator detail"),
        ):
            value = item.get(field)
            if isinstance(value, str) and value:
                item[field] = fence_untrusted(value, source)
        fenced.append(item)
    return fenced


def register_content_migration_tools(mcp: FastMCP) -> None:
    """Register educator-only content migration tools."""

    @mcp.tool(
        annotations=ToolAnnotations(destructiveHint=True, idempotentHint=False)
    )
    @validate_params
    async def create_content_migration(
        target_course_identifier: str | int,
        source_course_identifier: str | int,
        old_start_date: str | None = None,
        old_end_date: str | None = None,
        new_start_date: str | None = None,
        new_end_date: str | None = None,
        confirmation_token: str | None = None,
    ) -> dict[str, Any]:
        """Preview or confirm a full course-copy migration request.

        The first call returns a target-occupancy preview and a short-lived
        token. A second call with the token and identical arguments requests
        the migration. Date shifting accepts either all four date fields or
        none.
        """
        target_id, _target, target_error = await _resolve_course(
            target_course_identifier, "target"
        )
        source_id, _source, source_error = await _resolve_course(
            source_course_identifier, "source"
        )
        if target_error:
            return {"error": target_error}
        if source_error:
            return {"error": source_error}
        if target_id is None or source_id is None:
            return {"error": "Could not resolve both courses to numeric Canvas IDs."}
        if target_id == source_id:
            return {
                "error": "Source and target resolve to the same course; choose two different courses."
            }

        date_options, date_error = _normalise_date_options(
            old_start_date,
            old_end_date,
            new_start_date,
            new_end_date,
        )
        if date_error:
            return {"error": date_error}

        fingerprint = _migration_fingerprint(source_id, target_id, date_options)
        if not confirmation_token:
            occupancy = await _target_occupancy(target_id)
            result: dict[str, Any] = {
                "preview": True,
                "migration_requested": False,
                "source_course_id": source_id,
                "target_course_id": target_id,
                "migration_type": _MIGRATION_TYPE,
                "selective_import": False,
                "date_shift_options": date_options or None,
                "target_current_contents": occupancy,
                "confirmation_token": _CONTENT_MIGRATION_GUARD.issue(fingerprint),
                "instructions": (
                    "Show this preview to the educator. To request the course "
                    "copy, call create_content_migration again with this "
                    "confirmation_token and identical arguments. The token is "
                    "single-use and expires shortly."
                ),
            }
            warning = _occupancy_warning(occupancy)
            if warning:
                result["warning"] = warning
            return result

        token_error = _CONTENT_MIGRATION_GUARD.check(
            confirmation_token, fingerprint
        )
        if token_error:
            _CONTENT_MIGRATION_GUARD.reserve(confirmation_token)
            return {"error": token_error, "migration_requested": False}
        if not _CONTENT_MIGRATION_GUARD.reserve(confirmation_token):
            return {
                "error": (
                    "❌ That confirmation was already used. Run the preview "
                    "again before requesting another migration."
                ),
                "migration_requested": False,
            }

        form: dict[str, str] = {
            "migration_type": _MIGRATION_TYPE,
            "settings[source_course_id]": source_id,
            "selective_import": _SELECTIVE_IMPORT,
        }
        for key, value in date_options.items():
            form[f"date_shift_options[{key}]"] = value

        try:
            response = await make_canvas_request(
                "post",
                f"/courses/{target_id}/content_migrations",
                data=form,
                use_form_data=True,
            )
        except Exception as exc:
            return _unconfirmed_start_error(source_id, target_id, exc)

        if not isinstance(response, dict):
            return _unconfirmed_start_error(
                source_id, target_id, "Canvas returned an invalid response."
            )
        if "error" in response:
            return _unconfirmed_start_error(
                source_id, target_id, response.get("error")
            )

        migration_id = coerce_canvas_id(response.get("id", ""))
        if migration_id is None:
            return _unconfirmed_start_error(
                source_id,
                target_id,
                "Canvas did not return a numeric migration ID.",
            )

        return {
            "migration_created": True,
            "migration_id": migration_id,
            "canvas_workflow_state": response.get("workflow_state"),
            "progress_url": response.get("progress_url"),
            "migration_issues_url": response.get("migration_issues_url"),
            "next_action": _next_status_action(target_id, migration_id),
        }

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
    @validate_params
    async def get_content_migration_status(
        course_identifier: str | int,
        migration_id: str | int,
    ) -> dict[str, Any]:
        """Read one content migration and its current progress snapshot.

        Each call reads progress once. Call again only when ``poll_again`` is
        true. Terminal results include migration issues when Canvas makes them
        available.
        """
        canonical_migration_id = coerce_canvas_id(migration_id)
        if canonical_migration_id is None:
            return {"error": "migration_id must be a numeric Canvas ID."}

        course_id, _course, course_error = await _resolve_course(
            course_identifier, "course"
        )
        if course_error:
            return {"error": course_error}
        if course_id is None:
            return {"error": "Could not resolve the course to a numeric Canvas ID."}

        migration_endpoint = (
            f"/courses/{course_id}/content_migrations/{canonical_migration_id}"
        )
        try:
            migration = await make_canvas_request("get", migration_endpoint)
        except Exception as exc:
            return {"error": f"Could not read the content migration: {exc}"}
        if not isinstance(migration, dict):
            return {"error": "Could not read the content migration: invalid response."}
        if "error" in migration:
            return {
                "error": f"Could not read the content migration: {migration.get('error')}"
            }

        progress_id = _progress_id_from_url(migration.get("progress_url"))
        if progress_id is None:
            return {
                "error": (
                    "The content migration response did not include a "
                    "progress_url ending in a numeric progress ID."
                )
            }

        try:
            progress = await make_canvas_request("get", f"/progress/{progress_id}")
        except Exception as exc:
            return {"error": f"Could not read content migration progress: {exc}"}
        if not isinstance(progress, dict):
            return {"error": "Could not read content migration progress: invalid response."}
        if "error" in progress:
            return {
                "error": f"Could not read content migration progress: {progress.get('error')}"
            }

        snapshot = _progress_snapshot(progress)
        progress_message = snapshot.get("message")
        if isinstance(progress_message, str) and progress_message:
            snapshot["message"] = fence_untrusted(
                progress_message, "content migration progress message"
            )
        raw_state = progress.get("workflow_state")
        state = raw_state.strip().lower() if isinstance(raw_state, str) else None
        base: dict[str, Any] = {
            "course_id": course_id,
            "migration_id": canonical_migration_id,
            "progress": snapshot,
        }

        if state in {"queued", "running"}:
            return {
                **base,
                "status": state,
                "terminal": False,
                "poll_again": True,
                "next_action": _next_status_action(
                    course_id, canonical_migration_id
                ),
            }

        if state not in {"completed", "failed"}:
            return {
                **base,
                "status": "unknown",
                "terminal": False,
                "poll_again": False,
                "error": (
                    "Canvas returned a missing or unknown content migration "
                    "progress state; completion cannot be determined."
                ),
            }

        issues_endpoint = f"{migration_endpoint}/migration_issues"
        try:
            issues_response = await fetch_all_paginated_results(issues_endpoint)
        except Exception as exc:
            issues_response = {"error": str(exc)}

        if not isinstance(issues_response, list):
            detail = (
                issues_response.get("error")
                if isinstance(issues_response, dict)
                else "invalid response"
            )
            return {
                **base,
                "status": state,
                "terminal": True,
                "poll_again": False,
                "issues_checked": False,
                "error": (
                    "The migration reached a terminal progress state, but its "
                    f"issues could not be read: {detail}"
                ),
            }

        issues = _fence_migration_issues(issues_response)
        terminal = {
            **base,
            "terminal": True,
            "poll_again": False,
            "issues_checked": True,
            "issues": issues,
        }
        if state == "failed":
            return {
                **terminal,
                "status": "failed",
                "requires_review": True,
                "error": (
                    "Canvas reports that the content migration failed. Review "
                    "the progress snapshot and migration issues."
                ),
            }
        if issues:
            return {
                **terminal,
                "status": "completed_with_issues",
                "requires_review": True,
                "warning": (
                    f"The content migration completed with {len(issues)} issue(s); "
                    "review them before treating the copied course as ready."
                ),
            }
        return {
            **terminal,
            "status": "completed",
            "requires_review": False,
        }
