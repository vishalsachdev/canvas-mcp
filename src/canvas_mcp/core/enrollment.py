"""Enrollment-check capability: is a specific login ID enrolled in a course?

The identifier is whatever the institution puts in Canvas ``login_id`` — a NetID
at UIUC, a uniqname at UMich, an email-style login elsewhere. The matcher treats
``zqian`` and ``zqian@umich.edu`` as the same person (issue #199).

This answers a *roster-membership question about an externally-supplied subject*
(a login ID provided by the caller), which is structurally different from every other
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
from typing import cast

from .audit import log_data_access
from .cache import get_course_id
from .client import make_canvas_request

# Identifier guard: alphanumerics plus a few separators, bounded length, before
# the value ever reaches a Canvas query string. ``@`` is permitted because many
# Canvas instances provision logins from email addresses, so the identifier a
# caller naturally supplies IS an email (issue #199); rejecting it outright
# failed before a single Canvas call was made.
#
# The bound is 254 — the RFC 5321 maximum for an email address — not the old 64,
# which was a NetID-era assumption that would now reject the very email-style
# logins this tool documents as supported. Canvas does not constrain login_id to
# short campus IDs: a live roster read turned up a 40-character login_id. This is
# an injection guard, not a validity check; Canvas remains the authority on
# whether an identifier exists.
_NETID_RE = re.compile(r"^[A-Za-z0-9._@+-]{1,254}$")

# Caller-facing role -> Canvas enrollment ``type`` filter. "any" omits the filter.
_ROLE_TO_TYPE = {
    "student": "StudentEnrollment",
    "teacher": "TeacherEnrollment",
    "ta": "TaEnrollment",
    "observer": "ObserverEnrollment",
    "designer": "DesignerEnrollment",
}


class EnrollmentCheckUnavailable(RuntimeError):
    """Canvas answered the roster read but withheld the identifier fields.

    **Permission-blindness is not absence.** Canvas gates ``user.login_id`` and
    ``user.sis_user_id`` on roster-admin rights. A token without those rights
    (e.g. a student-scoped token) still gets ``HTTP 200`` plus the full roster —
    only every ``user`` object comes back reduced to
    ``{created_at, id, name, short_name, sortable_name}``. There is no error to
    catch, so the NetID match simply never succeeds and a naive implementation
    reports a confident, wrong ``NO``.

    Raised instead, so the caller can say "indeterminate" rather than "no".
    """


class AmbiguousIdentifier(ValueError):
    """The supplied identifier matched more than one person on the roster.

    Only reachable through the email-local-part fallback (issue #199): a bare
    ``jdoe`` cannot be told apart from ``jdoe@a.edu`` and ``jdoe@b.edu`` when
    both are enrolled. Choosing one would make an access-gating answer depend on
    roster ordering, so the caller is asked for a fully-qualified identifier
    instead. Distinct from ``EnrollmentCheckUnavailable``, which is about
    permission, not ambiguity.
    """


@dataclass(frozen=True)
class EnrollmentResult:
    """Minimal, data-minimizing answer to "is net_id enrolled in course?"."""

    enrolled: bool
    course_id: str
    # minimal, non-sensitive metadata only — NEVER the roster:
    enrollment_state: str | None = None  # "active" | "invited" | "completed" | None
    role: str | None = None              # "StudentEnrollment" | "TeacherEnrollment" | ...
    matched_on: str | None = None        # "login_id" | "sis_user_id" (audit/debug)
    # Every enrollment type the subject holds in this course. Populated even
    # when ``enrolled`` is False, so a role-scoped NO can say what the subject
    # actually IS instead of implying they are absent (issue #199). Empty for a
    # genuine stranger — which is what distinguishes the two cases.
    roles_held: tuple[str, ...] = ()


_ID_FIELDS = ("login_id", "sis_user_id")


def _local_part(value: str) -> str:
    """The part of an email-style identifier before the ``@``, else the value."""
    return value.split("@", 1)[0] if "@" in value else value


def _norm(value: object) -> str:
    return (value or "").strip().lower() if isinstance(value, str) else ""


class _UnverifiableDomain(Exception):
    """Internal signal: a qualified needle met a bare roster id it may not be.

    Never escapes ``_match_enrollment``, which converts it into a caller-facing
    ``AmbiguousIdentifier`` once it knows no exact match exists anywhere.
    """


def _local_part_field(user: dict, needle: str, needle_local: str) -> str | None:
    """Which identifier field of ``user`` matches ``needle`` by email local part.

    Returns the field name, or ``None`` when this user is not a local-part
    candidate. Evaluated per USER rather than per field, because a user's own
    identifiers constrain each other: if the roster says this person is
    ``jdoe@other.edu``, a query for ``jdoe@school.edu`` is asking about somebody
    else, and their bare ``sis_user_id`` of ``jdoe`` must not become a side door
    back to a confident YES.
    """
    stored = {field: _norm(user.get(field)) for field in _ID_FIELDS}
    stored = {field: value for field, value in stored.items() if value}
    if not stored:
        return None

    if "@" in needle:
        # A domain-qualified identifier on this user is positive evidence about
        # who they are. If they carry one and it isn't the needle, they are a
        # different person — pass 1 already gave any exact match its chance.
        if any("@" in value for value in stored.values()):
            return None
        # Every identifier is bare, so nothing on the roster can confirm which
        # domain this person belongs to: 'jdoe@attacker.example' has exactly as
        # much claim on a stored 'jdoe' as 'jdoe@illinois.edu' does. Matching
        # would let an unverified domain authorize an identity, so this is
        # reported as unresolvable rather than answered either way.
        if any(_local_part(value) == needle_local for value in stored.values()):
            raise _UnverifiableDomain
        return None

    for field in _ID_FIELDS:
        value = stored.get(field)
        if value and _local_part(value) == needle_local:
            return field
    return None


def _match_enrollment(
    enrollments: list[dict],
    net_id: str,
    active_only: bool,
) -> tuple[dict, str, bool] | None:
    """Find the first enrollment whose user matches net_id. Pure (testable).

    Returns ``(enrollment, matched_on, was_exact)`` or ``None``. ``was_exact``
    matters to the caller's visibility guard: an exact match is self-proving,
    while a local-part match is only sound if no OTHER person shares the local
    part — which a roster row with stripped identifiers could refute.

    Matches case-insensitively against ``user.login_id`` first, then
    ``user.sis_user_id``. Returns ``(enrollment, matched_on)`` or ``None``. Never
    accumulates or returns the roster.

    Two passes, and the order matters (issue #199). Canvas does not define what
    ``login_id`` contains: measured live, UIUC stores the bare NetID
    (``vishal``), while instances that provision logins from email store the
    full address (``uniqname@umich.edu``). Matching only on exact equality made
    the second shape unmatchable, so a subject who was plainly on the roster
    came back as a confident "not enrolled".

    Pass 1 is exact equality. Pass 2 compares email local parts, but only where
    that comparison is actually meaningful, because this tool is documented as
    an external access gate and a false positive is an authorization defect:

    * A domain-qualified needle is only compared against users who carry NO
      qualified identifier of their own. Two fully-qualified addresses that
      differ — ``jdoe@school.edu`` vs. ``jdoe@other.edu`` — are different
      people, and that verdict holds for the whole user, so a bare secondary
      ``sis_user_id`` cannot smuggle the match back in (see
      ``_local_part_field``).
    * The fallback must identify exactly ONE person. A bare ``jdoe`` against a
      roster holding ``jdoe@a.edu`` and ``jdoe@b.edu`` is genuinely ambiguous;
      returning the first would make the answer a function of roster order.
      That raises ``AmbiguousIdentifier`` rather than guessing. Several
      enrollments belonging to the *same* user are not ambiguous.

    Exact equality is exhausted across the WHOLE roster first, so an
    unambiguous exact hit is never spoiled by local-part noise elsewhere.

    Raises:
        AmbiguousIdentifier: the local-part fallback matched more than one person.
    """
    needle = _norm(net_id)
    if not needle:
        return None
    needle_local = _local_part(needle)

    candidates = [
        (enrollment, enrollment.get("user") or {})
        for enrollment in enrollments
        if not (active_only and enrollment.get("enrollment_state") != "active")
    ]

    # Pass 1 — exact equality, the only unconditionally safe comparison.
    for enrollment, user in candidates:
        for field in _ID_FIELDS:
            stored = _norm(user.get(field))
            if stored and stored == needle:
                return enrollment, field, True

    # Pass 2 — local-part fallback, collected in full so ambiguity is visible.
    hits: list[tuple[dict, str]] = []
    seen_users: set = set()
    unverifiable_domain = False
    for enrollment, user in candidates:
        try:
            local_field = _local_part_field(user, needle, needle_local)
        except _UnverifiableDomain:
            unverifiable_domain = True
            continue
        if local_field is not None:
            user_id = user.get("id")
            # Fall back to identity of the row itself when Canvas gives no id,
            # so a missing id cannot silently collapse two people into one.
            key = ("id", user_id) if user_id is not None else ("row", id(enrollment))
            if key not in seen_users:
                seen_users.add(key)
                hits.append((enrollment, local_field))

    if len(hits) > 1:
        raise AmbiguousIdentifier(
            f"'{net_id}' matches {len(hits)} different people on this roster by "
            "email local part alone. Supply the full login ID (including the "
            "domain, if the institution uses email-style logins)."
        )
    if hits:
        enrollment, field = hits[0]
        return enrollment, field, False
    if unverifiable_domain:
        raise AmbiguousIdentifier(
            f"This course stores bare login IDs, so nothing on the roster can "
            f"confirm that '{net_id}' is the person holding "
            f"'{needle_local}' — any domain would match equally. Re-run with "
            f"just '{needle_local}'."
        )
    return None


def _enrollments_for_user(
    enrollments: list[dict],
    user_id: object,
    active_only: bool,
) -> list[dict]:
    """Every enrollment belonging to one user — the subject's full role set.

    A person can hold several enrollments in one course (Teacher + Designer is
    common). Returning only the first would make a role-scoped answer arbitrary.
    """
    if user_id is None:
        return []
    return [
        enrollment
        for enrollment in enrollments
        if (enrollment.get("user") or {}).get("id") == user_id
        and not (active_only and enrollment.get("enrollment_state") != "active")
    ]


def _exposes_identifier(user: dict) -> bool:
    """Whether this roster user actually carries a matchable identifier.

    Requires a non-empty value, not merely the key: Canvas may return the key
    with ``null`` for a user whose pseudonym the caller cannot see, which is
    just as unmatchable as omitting it.
    """
    return bool(
        (user.get("login_id") or "").strip()
        or (user.get("sis_user_id") or "").strip()
    )


def _identifiers_visible(enrollments: list[dict]) -> bool:
    """Whether EVERY user in the roster exposes login_id or sis_user_id.

    ``all``, not ``any``, and that distinction is the whole point of the guard.
    With ``any``, a roster mixing visible and hidden identifiers passes as soon
    as one unrelated row is readable. If the NetID being asked about happens to
    be one of the hidden rows, matching fails and we return a confident "not
    enrolled" again, recreating the exact false negative this guard exists to
    prevent.

    A negative answer is only trustworthy when every candidate row *could* have
    matched. Canvas strips these fields per-permission rather than per-row, so
    in practice this rarely differs; where it does differ, indeterminate is the
    correct answer.
    """
    return all(
        _exposes_identifier(enrollment.get("user") or {})
        for enrollment in enrollments
    )


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
        AmbiguousIdentifier: the identifier matched several people by email
            local part alone (a ValueError subclass — catch it first).
        EnrollmentCheckUnavailable: Canvas returned a roster but withheld the
            identifier fields on every user, so no answer can be trusted.
            Permission-blindness is not absence — see the exception's docstring.
        RuntimeError: Canvas rejected the roster read outright.
    """
    if not _NETID_RE.match(net_id or ""):
        raise ValueError(
            "net_id must be a campus login ID (NetID, uniqname, or email-style "
            "Canvas login) of 1-254 chars: letters, digits, '.', '_', '@', '+' "
            "or '-'. It is not a display name."
        )
    role_key = (role or "student").strip().lower()
    if role_key not in _ROLE_TO_TYPE and role_key != "any":
        raise ValueError(
            f"role must be one of {sorted(_ROLE_TO_TYPE)} or 'any'"
        )

    course_id = await get_course_id(course_identifier)
    if not course_id:
        raise ValueError(f"Could not resolve course '{course_identifier}'")

    # Deliberately NO ``type[]`` filter (issue #199). Pushing the role filter to
    # Canvas hides every other enrollment the subject holds, so asking about a
    # teacher with the default role="student" produced a bare "no ... enrollment"
    # that reads as "not in this course". Fetching the whole roster costs one
    # request either way and lets a role-scoped NO name the real role.
    params: dict = {"include[]": ["user"]}
    if active_only:
        params["state[]"] = ["active"]

    raw = await _fetch_enrollments_raw(course_id, params)
    if isinstance(raw, dict) and "error" in raw:
        log_data_access("GET", f"/courses/{course_id}/enrollments", "error",
                        error=str(raw.get("error")))
        raise RuntimeError(str(raw.get("error")))
    # _fetch_enrollments_raw returns a list in every non-error case.
    enrollments = cast("list[dict]", raw)

    match = _match_enrollment(enrollments, net_id, active_only)

    # Match first, and only question visibility when the answer would be NO.
    #
    # A positive match is trustworthy however much of the rest of the roster is
    # hidden: we found the person. A NEGATIVE is a claim about rows we may not
    # have been able to read, so it is only trustworthy when EVERY row exposed a
    # matchable identifier. Otherwise the requested NetID may be sitting in a
    # row whose identifiers Canvas stripped, and "no" would be the exact false
    # negative this guard exists to prevent.
    #
    # An EMPTY roster is a real, trustworthy "nobody is enrolled".
    #
    # Scoped to the requested role. Since the ``type[]`` filter moved off the
    # Canvas request, the roster now carries every role, and an unrelated hidden
    # row — an observer, say — would otherwise make a *student* lookup
    # indeterminate even though that row could never have satisfied it. Only
    # rows that could have answered the question get a vote; role="any" means
    # every row could.
    wanted = None if role_key == "any" else _ROLE_TO_TYPE[role_key]
    answerable = (
        enrollments
        if wanted is None
        else [e for e in enrollments if e.get("type") == wanted]
    )
    # An EXACT match is self-proving and may skip the guard: the identifier IS
    # that person, however much of the roster is hidden. A local-part match is
    # not — it holds only if nobody ELSE shares the local part, and a stripped
    # row could be exactly that person. So a fallback positive needs the same
    # visibility proof a negative does.
    #
    # The two cases need different scopes. A NEGATIVE may look only at rows of
    # the requested role: any student row belonging to the subject would itself
    # be in that subset, so a hidden one still trips the guard. A FALLBACK
    # POSITIVE is threatened by something else — a second person sharing the
    # local part — and that person's role has no bearing on whether we picked
    # the right human, so it must see the whole roster.
    needs_visibility_proof = match is None or not match[2]
    scope = answerable if match is None else enrollments
    if needs_visibility_proof and scope and not _identifiers_visible(scope):
        log_data_access("GET", f"/courses/{course_id}/enrollments", "indeterminate")
        detail = (
            "so a 'not enrolled' answer cannot be trusted."
            if match is None
            else (
                f"and '{net_id}' was matched only by email local part, so it "
                "cannot be proven that no other person on this roster shares it."
            )
        )
        raise EnrollmentCheckUnavailable(
            "Canvas withheld login_id and sis_user_id on at least one user in "
            f"this roster, {detail}"
        )

    log_data_access("GET", f"/courses/{course_id}/enrollments", "success")

    if match is None:
        return EnrollmentResult(enrolled=False, course_id=course_id)

    matched_enrollment, matched_on, _was_exact = match
    subject_id = (matched_enrollment.get("user") or {}).get("id")
    subject = _enrollments_for_user(enrollments, subject_id, active_only) or [
        matched_enrollment
    ]
    # dict.fromkeys preserves roster order while de-duplicating.
    role_values = (e.get("type") for e in subject)
    roles_held = tuple(
        dict.fromkeys(r for r in role_values if isinstance(r, str) and r)
    )

    # Role is now evaluated here rather than by Canvas, so pick the enrollment
    # that satisfies the requested role; "any" takes the first.
    enrollment = (
        subject[0]
        if wanted is None
        else next((e for e in subject if e.get("type") == wanted), None)
    )

    if enrollment is None:
        # On the roster, but not in the requested role. A NO — with the roles
        # they DO hold, so it cannot be misread as "not in this course".
        return EnrollmentResult(
            enrolled=False, course_id=course_id, roles_held=roles_held
        )

    return EnrollmentResult(
        enrolled=True,
        course_id=course_id,
        enrollment_state=enrollment.get("enrollment_state"),
        role=enrollment.get("type"),
        matched_on=matched_on,
        roles_held=roles_held,
    )
