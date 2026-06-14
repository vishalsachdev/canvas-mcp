"""Enrollment-check capability: is a specific NetID enrolled in a course?

This answers a *roster-membership question about an externally-supplied subject*
(a NetID provided by the caller), which is structurally different from every other
tool here — those answer about the authenticated caller. The answer is minimized by
construction: a boolean plus a little non-sensitive metadata. The roster itself —
names, the full membership list, grades — is NEVER returned or logged.

FERPA note (deliberate raw-PII read): to match the caller's NetID against the
roster we must read the un-anonymized ``login_id`` / ``sis_user_id``. So this module
fetches with ``skip_anonymization=True`` ON PURPOSE and emits only the boolean +
minimal metadata below. Justified because we answer about a *single, externally
known* subject, not by exposing the class.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .audit import log_data_access
from .cache import get_course_id
from .client import make_canvas_request

# NetID guard: alphanumerics plus a few separators, bounded length, before the
# value ever reaches a Canvas query string.
_NETID_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")

# Caller-facing role -> Canvas enrollment ``type`` filter. "any" omits the filter.
_ROLE_TO_TYPE = {
    "student": "StudentEnrollment",
    "teacher": "TeacherEnrollment",
    "ta": "TaEnrollment",
    "observer": "ObserverEnrollment",
    "designer": "DesignerEnrollment",
}


@dataclass(frozen=True)
class EnrollmentResult:
    """Minimal, data-minimizing answer to "is net_id enrolled in course?"."""

    enrolled: bool
    course_id: str
    # minimal, non-sensitive metadata only — NEVER the roster:
    enrollment_state: str | None = None  # "active" | "invited" | "completed" | None
    role: str | None = None              # "StudentEnrollment" | "TeacherEnrollment" | ...
    matched_on: str | None = None        # "login_id" | "sis_user_id" (audit/debug)


def _match_enrollment(
    enrollments: list[dict],
    net_id: str,
    active_only: bool,
) -> tuple[dict, str] | None:
    """Find the first enrollment whose user matches net_id. Pure (testable).

    Matches case-insensitively against ``user.login_id`` first, then
    ``user.sis_user_id``. Returns ``(enrollment, matched_on)`` or ``None``. Never
    accumulates or returns the roster.
    """
    needle = net_id.strip().lower()
    for enrollment in enrollments:
        if active_only and enrollment.get("enrollment_state") != "active":
            continue
        user = enrollment.get("user") or {}
        login_id = (user.get("login_id") or "").strip().lower()
        if login_id and needle == login_id:
            return enrollment, "login_id"
        sis_user_id = (user.get("sis_user_id") or "").strip().lower()
        if sis_user_id and needle == sis_user_id:
            return enrollment, "sis_user_id"
    return None


async def _fetch_enrollments_raw(course_id: str, params: dict) -> list[dict] | dict:
    """Paginate /courses/:id/enrollments with anonymization explicitly OFF.

    We must read raw ``login_id`` / ``sis_user_id`` to match the NetID, so this
    bypasses ``fetch_all_paginated_results`` (which re-anonymizes the final set).
    Only the boolean result leaves the caller — never this raw roster. Returns the
    accumulated list, or a ``{"error": ...}`` dict if Canvas rejects the request.
    """
    results: list[dict] = []
    page = 1
    while True:
        resp = await make_canvas_request(
            "get",
            f"/courses/{course_id}/enrollments",
            params={**params, "page": page, "per_page": 100},
            skip_anonymization=True,
        )
        if isinstance(resp, dict) and "error" in resp:
            return resp
        if not resp or not isinstance(resp, list):
            break
        results.extend(resp)
        if len(resp) < 100:
            break
        page += 1
    return results


async def check_enrollment(
    course_identifier: str | int,
    net_id: str,
    *,
    role: str = "student",
    active_only: bool = True,
) -> EnrollmentResult:
    """Is ``net_id`` enrolled (as ``role``) in ``course_identifier``?

    Uses the presented (teacher-scoped) Canvas token. Returns a minimal
    ``EnrollmentResult`` — boolean plus non-sensitive metadata, never the roster.

    Raises:
        ValueError: invalid net_id / role, or the course can't be resolved.
        RuntimeError: Canvas rejected the roster read (e.g. a student-scoped token
            yields a clean 403 rather than a partial answer).
    """
    if not _NETID_RE.match(net_id or ""):
        raise ValueError(
            "net_id must be 1-64 chars of letters, digits, '.', '_' or '-'"
        )
    role_key = (role or "student").strip().lower()
    if role_key not in _ROLE_TO_TYPE and role_key != "any":
        raise ValueError(
            f"role must be one of {sorted(_ROLE_TO_TYPE)} or 'any'"
        )

    course_id = await get_course_id(course_identifier)
    if not course_id:
        raise ValueError(f"Could not resolve course '{course_identifier}'")

    params: dict = {"include[]": ["user"]}
    if active_only:
        params["state[]"] = ["active"]
    if role_key != "any":
        params["type[]"] = [_ROLE_TO_TYPE[role_key]]

    enrollments = await _fetch_enrollments_raw(course_id, params)
    if isinstance(enrollments, dict) and "error" in enrollments:
        log_data_access("GET", f"/courses/{course_id}/enrollments", "error",
                        error=str(enrollments.get("error")))
        raise RuntimeError(str(enrollments.get("error")))

    match = _match_enrollment(enrollments, net_id, active_only)
    log_data_access("GET", f"/courses/{course_id}/enrollments", "success")

    if match is None:
        return EnrollmentResult(enrolled=False, course_id=course_id)
    enrollment, matched_on = match
    return EnrollmentResult(
        enrolled=True,
        course_id=course_id,
        enrollment_state=enrollment.get("enrollment_state"),
        role=enrollment.get("type"),
        matched_on=matched_on,
    )
