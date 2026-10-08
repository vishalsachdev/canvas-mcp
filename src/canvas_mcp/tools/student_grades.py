"""Student grade insight: your assignment scores and a what-if grade calculator.

Both tools are read-only and answer only about the caller. They read

- ``GET /courses/:id`` for ``apply_assignment_group_weights``, the
  ``restrict_quantitative_data`` flag (both tools refuse such a course) and,
  with ``include[]=total_scores``, Canvas's own current/final score for the
  caller's student enrollment; and
- ``GET /courses/:id/assignment_groups?include[]=assignments&include[]=submission``
  for group weights, drop rules, assignments, and the caller's own
  submission on each.

Neither path carries a ``users``/``submissions``/``enrollments`` route
segment, so the client applies no anonymization tier to them: the embedded
submission is the caller's own (``include[]=submission`` returns the current
user's submission), and no roster is requested.

Both tools fail closed: data that is not the documented shape, a restricted
course, or a letter target without a known scheme is refused, not guessed.

The arithmetic lives in ``core/grade_calc.py``. This module fetches, picks a
letter scheme, and formats. Group names, assignment names, grading standard
titles and custom letter names are instructor-authored, so they are fenced at
the output boundary.
"""

import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from fastmcp import FastMCP
from mcp.types import ToolAnnotations

from ..core import grade_calc as gc
from ..core.cache import resolve_numeric_course_id
from ..core.client import fetch_all_paginated_results, make_canvas_request
from ..core.dates import format_date, parse_date
from ..core.tool_results import FULL_CONTENT_TOOL_META
from ..core.untrusted_content import fence_untrusted_inline
from ..core.validation import coerce_canvas_id, validate_params

GROUP_INCLUDES = ["assignments", "submission"]
# grading_scheme is emitted by canvas-lms (lib/api/v1/course.rb) but is not in
# the published include[] list; Canvas ignores includes it does not know, and
# the grading standards API is the fallback.
COURSE_INCLUDES = [
    "total_scores",
    "current_grading_period_scores",
    "grading_scheme",
    "restrict_quantitative_data",
]
# Both tools read the restriction flag so they can refuse before computing.
SCORES_COURSE_INCLUDES = ["restrict_quantitative_data"]
_RESTRICTED_MESSAGE = (
    "Error: this course restricts quantitative grade data for students, so Canvas "
    "withholds the points and scores this tool needs. It will not estimate them or "
    "show numbers the course hides; check Canvas for your grade."
)
_UNKNOWN_RESTRICTION_MESSAGE = (
    "Error: Canvas did not say whether this course restricts quantitative grade data "
    "for students, so this tool cannot tell whether the scores it needs are withheld. "
    "It will not guess; check Canvas for your grade."
)
MAX_HYPOTHETICAL_SCORES = 500
# Upper bound on one what-if score, in points. Far above any real assignment
# (extra credit included) and small enough that sums of 500 of them stay
# finite and the drop-rule ranking never sees inf or NaN.
MAX_HYPOTHETICAL_POINTS = 1e6
MAX_TARGET_PERCENT = 200.0
# Canvas stores course scores to two decimals.
DISAGREEMENT_TOLERANCE = 0.01
_MAX_LISTED_REMAINING = 15

_DEFAULT_LETTERS = frozenset(name for name, _ in gc.CANVAS_DEFAULT_SCHEME)


@dataclass
class _CourseData:
    course_id: str
    course: dict[str, Any]
    groups_json: list[dict[str, Any]]
    # The validated calculation model built from groups_json.
    groups: list[gc.GroupRules]
    items: list[gc.GradedItem]
    display: str


def _fmt(value: float | None, decimals: int = 2) -> str:
    """Compact number: 18, 18.5, 87.53."""
    if value is None:
        return "n/a"
    text = f"{value:.{decimals}f}".rstrip("0").rstrip(".")
    return "0" if text in ("-0", "") else text


def _pct(value: float | None) -> str:
    # Rounded the way Canvas rounds stored scores, so 60.995 shows as 61.00
    # (Python's formatting would print the binary value's 60.99).
    return "n/a" if value is None else f"{gc.canvas_round(value):.2f}%"


def _letter_label(name: str | None) -> str:
    """Canvas default letters print as-is; anything else is instructor text."""
    if name is None:
        return "n/a"
    if name in _DEFAULT_LETTERS:
        return name
    return fence_untrusted_inline(name, "grading scheme letter")


def _with_letter(percent: float | None, scheme: "_Scheme") -> str:
    if percent is None:
        return "n/a (no graded work counts yet)"
    return f"{_pct(percent)} ({_letter_label(scheme.letter(percent))})"


def _student_enrollment(course: dict[str, Any]) -> dict[str, Any] | None:
    for enrollment in course.get("enrollments") or []:
        if not isinstance(enrollment, dict):
            continue
        if enrollment.get("type") in ("student", "StudentEnrollment") or (
            enrollment.get("role") == "StudentEnrollment"
        ):
            return enrollment
    return None


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


async def _load_course(
    course_identifier: str | int, course_includes: list[str] | None
) -> _CourseData | str:
    """Fetch the course and its assignment groups, or return an error string."""
    course_id, course_error = await resolve_numeric_course_id(course_identifier)
    if course_id is None:
        return f"Error: {course_error}"

    params = {"include[]": course_includes} if course_includes else None
    course = await make_canvas_request("get", f"/courses/{course_id}", params=params)
    if not isinstance(course, dict) or "error" in course:
        detail = course.get("error") if isinstance(course, dict) else course
        return f"Error fetching course {course_id}: {fence_untrusted_inline(str(detail)[:200], 'Canvas error')}"
    # Fail closed: with quantitative data restricted, Canvas nulls the numbers
    # the arithmetic needs (and the course chose not to show them). Only an
    # explicit false proves the course is unrestricted; an absent, null or
    # otherwise unreadable flag is an unknown state and is refused too.
    restricted = course.get("restrict_quantitative_data")
    if restricted is not False:
        return _RESTRICTED_MESSAGE if restricted else _UNKNOWN_RESTRICTION_MESSAGE

    groups = await fetch_all_paginated_results(
        f"/courses/{course_id}/assignment_groups",
        params={"include[]": GROUP_INCLUDES, "per_page": 100},
    )
    if isinstance(groups, dict) and "error" in groups:
        return f"Error fetching assignment groups: {fence_untrusted_inline(str(groups['error'])[:200], 'Canvas error')}"
    if not isinstance(groups, list):
        return "Error fetching assignment groups: unexpected response from Canvas."

    # Never drop an entry that does not parse: a grade built from a shortened
    # list would look authoritative and be wrong.
    try:
        model_groups, model_items = gc.build_grade_model(groups)
    except gc.MalformedGradeData as exc:
        return (
            "Error: Canvas returned assignment data this tool cannot trust "
            f"({fence_untrusted_inline(str(exc), 'malformed grade data')}). "
            "Nothing was computed."
        )

    display = course.get("course_code") or course.get("name") or course_id
    return _CourseData(
        course_id=course_id,
        course=course,
        groups_json=groups,
        groups=model_groups,
        items=model_items,
        display=str(display),
    )


@dataclass(frozen=True)
class _Scheme:
    """The letter scheme in use, how Canvas applies it, and where it came from."""

    entries: tuple[tuple[str, float], ...]
    source: str
    points_based: bool = False
    scaling_factor: float | None = None
    # True when the letters are a stand-in (Canvas's default scheme used because
    # the course's real scheme is unknown or unreadable). Such a scheme is fine
    # for context but must not decide a target letter.
    is_guess: bool = False

    def letter(self, percent: float | None) -> str | None:
        return gc.letter_for_percent(
            percent, self.entries, self.points_based, self.scaling_factor
        )


def _scheme_from(
    payload: dict[str, Any], scheme_key: str, points_based_key: str, source: str
) -> _Scheme | None:
    """Parse a scheme plus its points-based settings from a Canvas payload."""
    scaling = _number(payload.get("scaling_factor"))
    entries = gc.parse_grading_scheme(payload.get(scheme_key), scaling)
    if entries is None:
        return None
    return _Scheme(entries, source, payload.get(points_based_key) is True, scaling)


async def _resolve_letter_scheme(course_id: str, course: dict[str, Any]) -> _Scheme:
    """Pick the letter scheme Canvas would use and say where it came from.

    With ``include[]=grading_scheme`` Canvas returns the scheme it actually
    applies (``Course#grading_standard_or_default``): the course's own
    standard, else the account chain's (institution) default, else Canvas's
    built-in scheme. That answer is used whenever it parses, whatever
    ``grading_standard_id`` says; the id only decides how the source is
    described. The grading standards API is a fallback for a payload without
    the scheme.
    """
    standard_id = course.get("grading_standard_id")
    no_standard = standard_id in (None, "")
    from_include = _scheme_from(course, "grading_scheme", "points_based_grading_scheme", "")

    if from_include is not None:
        guess = False
        if "grading_standard_id" not in course:
            source = (
                "the scheme Canvas returned for this course (Canvas did not say whether the "
                "course has letter grades enabled)."
            )
        elif no_standard:
            enrollment = _student_enrollment(course)
            shows_letter = bool(enrollment and enrollment.get("computed_current_grade"))
            if gc.same_scheme(from_include.entries, gc.CANVAS_DEFAULT_SCHEME) and not shows_letter:
                source = (
                    "Canvas default scheme. This course has no grading scheme enabled and "
                    "Canvas returned no institution default, so Canvas may show you no letter "
                    "grade; letters here are for reference only."
                )
                guess = True
            else:
                source = (
                    "the course or institution default scheme, as returned by Canvas (the "
                    "course sets no scheme of its own, so Canvas uses the institution's)."
                )
        elif str(standard_id) == "0":
            source = "Canvas default scheme (the scheme this course uses)."
        else:
            source = "the course's own grading scheme (from the course record)."
        return _Scheme(
            from_include.entries,
            source,
            from_include.points_based,
            from_include.scaling_factor,
            is_guess=guess,
        )

    if no_standard:
        return _Scheme(gc.CANVAS_DEFAULT_SCHEME, (
            "Canvas default scheme. Canvas returned no scheme and the course itself has no "
            "grading scheme enabled; Canvas may apply an institution default or show you no "
            "letter grade, so letters here are for reference only."
        ), is_guess=True)
    if str(standard_id) == "0":
        return _Scheme(gc.CANVAS_DEFAULT_SCHEME, "Canvas default scheme (the scheme this course uses).")

    safe_id = (
        coerce_canvas_id(standard_id)
        if isinstance(standard_id, (str, int)) and not isinstance(standard_id, bool)
        else None
    )
    if safe_id is not None:
        standard = await make_canvas_request(
            "get", f"/courses/{course_id}/grading_standards/{safe_id}"
        )
        if isinstance(standard, dict) and "error" not in standard:
            title = standard.get("title") or f"#{safe_id}"
            parsed = _scheme_from(
                standard, "grading_scheme", "points_based",
                "the course's grading standard "
                f"{fence_untrusted_inline(title, 'grading standard title')} "
                "(from the grading standards API).",
            )
            if parsed is not None:
                return parsed
    which = f"grading standard {safe_id}" if safe_id is not None else "an unrecognised grading standard id"
    return _Scheme(gc.CANVAS_DEFAULT_SCHEME, (
        f"Canvas default scheme as a FALLBACK: the course uses {which}, "
        "which could not be read with your token (it is probably defined at the "
        "institution level). Letters here may differ from what Canvas shows you."
    ), is_guess=True)


def _score_text(assignment: Mapping[str, Any], submission: Mapping[str, Any] | None) -> str:
    points = _number(assignment.get("points_possible")) or 0.0
    if gc.grade_not_posted(submission):
        return f"-/{_fmt(points)}"
    score = _number(submission.get("score")) if submission else None
    if submission and submission.get("excused"):
        return "excused"
    if score is None:
        return f"-/{_fmt(points)}"
    if points > 0:
        return f"{_fmt(score)}/{_fmt(points)} ({score / points * 100:.1f}%)"
    return f"{_fmt(score)} pts (0 points possible: extra credit)"


def _due_text(due: Any) -> str:
    """A due date Canvas sent, only when it parses; raw text is never echoed."""
    if not due:
        return "no due date"
    if not isinstance(due, str) or parse_date(due) is None:
        return "an unreadable due date"
    return format_date(due)


def _rules_text(group: dict[str, Any]) -> str:
    raw_rules = group.get("rules")
    rules: dict[str, Any] = raw_rules if isinstance(raw_rules, dict) else {}
    parts = []
    drop_lowest = int(_number(rules.get("drop_lowest")) or 0)
    drop_highest = int(_number(rules.get("drop_highest")) or 0)
    if drop_lowest:
        parts.append(f"drop lowest {drop_lowest}")
    if drop_highest:
        parts.append(f"drop highest {drop_highest}")
    never = rules.get("never_drop") or []
    if never and parts:
        parts.append(f"never drop {len(never)} assignment(s)")
    return "; ".join(parts)


def _render_scores_report(data: _CourseData) -> str:
    """Group-by-group listing of the caller's scores. Fences Canvas text."""
    weighted = data.course.get("apply_assignment_group_weights") is True
    lines = [f"Assignment scores for {data.display}"]
    if "apply_assignment_group_weights" not in data.course:
        weighting = "Grade weighting: not reported by Canvas, so group weights are not shown as applied"
    elif weighted:
        weighting = "Grade weighting: by assignment group (weights below)"
    else:
        weighting = (
            "Grade weighting: none, the course grade is total points earned / total points possible"
        )
    lines.append(weighting)
    lines.append(
        "Only assignments Canvas shows you are listed; unposted grades show as "
        "'grade not posted yet'."
    )

    counts: dict[str, int] = {}
    if not data.groups_json:
        lines.append("\nNo assignment groups are visible in this course.")
        return "\n".join(lines)

    weights = {rules.group_id: rules.weight for rules in data.groups}
    for group in data.groups_json:
        header = f"\n== {fence_untrusted_inline(group.get('name') or 'Unnamed group', 'assignment group name')}"
        if weighted:
            weight = weights.get(gc.canvas_id(group.get("id")) or "", 0.0)
            header += f" | weight {_fmt(weight)}%"
        rules = _rules_text(group)
        if rules:
            header += f" | {rules}"
        lines.append(header)

        assignments = [a for a in group.get("assignments") or [] if isinstance(a, dict)]
        if not assignments:
            lines.append("  (no assignments visible)")
            continue
        for assignment in assignments:
            submission = gc.own_submission(assignment)
            statuses = gc.submission_statuses(assignment, submission)
            for status in statuses:
                if status.startswith("late penalty"):
                    continue
                key = status.split(" (")[0]
                counts[key] = counts.get(key, 0) + 1
            name = fence_untrusted_inline(assignment.get("name") or "Unnamed assignment", "assignment name")
            due_text = _due_text(assignment.get("due_at"))
            lines.append(
                f"  - {name} (ID {gc.canvas_id(assignment.get('id'))}): {_score_text(assignment, submission)}"
                f" | {', '.join(statuses)} | due {due_text}"
            )

    if counts:
        summary = ", ".join(f"{count} {label}" for label, count in sorted(counts.items()))
        lines.append(f"\nSummary: {summary}")
    return "\n".join(lines)


_REMAINING_NOTES = {
    "missing": "missing",
    "grade not posted yet (hidden from you)": "graded, not posted yet",
    "pending review (needs manual grading)": "pending review",
    "submitted, not graded yet": "submitted",
}


def _remaining_label(name: str, assignment: dict[str, Any] | None) -> str:
    """Fenced name plus a status note for work that is not simply 'to do'."""
    label = fence_untrusted_inline(name, "assignment name")
    if assignment is None:
        return label
    statuses = gc.submission_statuses(assignment, gc.own_submission(assignment))
    notes = [_REMAINING_NOTES[s] for s in statuses if s in _REMAINING_NOTES]
    return f"{label} [{', '.join(notes)}]" if notes else label


def _group_lines(
    grade: gc.CourseGrade,
    group_names: dict[str, str],
    assignment_names: dict[str, str],
) -> list[str]:
    lines = []
    for group in grade.groups:
        name = fence_untrusted_inline(group_names.get(group.group_id, "Unnamed group"), "assignment group name")
        weight = f" (weight {_fmt(group.weight)}%)" if grade.weighted else ""
        if group.possible > 0:
            body = f"{_fmt(group.score)}/{_fmt(group.possible)} = {_pct(group.percent)}"
        elif group.score > 0:
            body = f"{_fmt(group.score)} pts with 0 possible (extra credit only)"
        else:
            body = "no graded work yet"
        if grade.weighted and group.possible <= 0:
            body += ", not counted"
        lines.append(f"  - {name}{weight}: {body}")
        if group.dropped:
            dropped = ", ".join(
                fence_untrusted_inline(assignment_names.get(a, f"assignment {a}"), "assignment name")
                for a in group.dropped
            )
            lines.append(f"      dropped by group rules: {dropped}")
    return lines


def _render_grade_scenarios(
    data: _CourseData,
    scheme: _Scheme,
    hypothetical: dict[str, float],
    target: float | None,
    target_note: str,
) -> str:
    """Compute and format the report. Fences Canvas text."""
    course = data.course
    weighted = course.get("apply_assignment_group_weights") is True
    groups, items = data.groups, data.items
    group_names = {
        group_id: str(g.get("name") or "Unnamed group")
        for g in data.groups_json
        if (group_id := gc.canvas_id(g.get("id"))) is not None
    }
    assignments: dict[str, dict[str, Any]] = {
        assignment_id: a
        for g in data.groups_json
        for a in g.get("assignments") or []
        if isinstance(a, dict) and (assignment_id := gc.canvas_id(a.get("id"))) is not None
    }
    names = {aid: str(a.get("name") or f"assignment {aid}") for aid, a in assignments.items()}

    current = gc.calculate_course(groups, items, weighted, include_ungraded=False)
    final = gc.calculate_course(groups, items, weighted, include_ungraded=True)

    enrollment = _student_enrollment(course)
    canvas_current = _number(enrollment.get("computed_current_score")) if enrollment else None
    canvas_final = _number(enrollment.get("computed_final_score")) if enrollment else None
    canvas_letter = enrollment.get("computed_current_grade") if enrollment else None

    lines = [f"Grade calculation for {data.display}"]
    if weighted:
        lines.append(
            "Method: weighted assignment groups. Groups with no graded work are left out "
            "and, if the counted weights total under 100%, Canvas rescales them to 100%."
        )
    else:
        lines.append("Method: total points (assignment groups are not weighted).")
    if "apply_assignment_group_weights" not in course:
        lines.append(
            "Note: Canvas did not say whether groups are weighted; assumed unweighted."
        )

    # A final grade override replaces both of Canvas's student-visible scores
    # with the override score, so Canvas reports the same current and final
    # score even though the calculated ones differ.
    override_suspected = (
        canvas_current is not None
        and canvas_final is not None
        and abs(canvas_current - canvas_final) <= DISAGREEMENT_TOLERANCE / 2
        and current.percent is not None
        and final.percent is not None
        and abs(gc.canvas_round(current.percent) - gc.canvas_round(final.percent))
        > DISAGREEMENT_TOLERANCE
        and _disagrees(current.percent, canvas_current)
    )

    disagreements: list[str] = []
    lines.append("\nCurrent grade (graded work only)")
    lines.append(f"  Computed here: {_with_letter(current.percent, scheme)}")
    if canvas_current is not None:
        letter = f" ({_letter_label(canvas_letter)})" if canvas_letter else ""
        lines.append(f"  Canvas reports: {_pct(canvas_current)}{letter}")
        if _disagrees(current.percent, canvas_current):
            gap = (
                f"by {abs(gc.canvas_round(current.percent) - canvas_current):.2f} points"
                if current.percent is not None
                else "(this tool found no graded work that counts)"
            )
            lines.append(f"  WARNING: the computed current grade DISAGREES with Canvas {gap}.")
            if override_suspected:
                lines.append(
                    "  This looks like a final grade override entered by your instructor: "
                    "Canvas reports the same score as current and final, which is what it "
                    "does when an override replaces the calculated grade."
                )
            disagreements.append("current")
        else:
            lines.append("  Agreement: the computed grade matches Canvas.")
            ours = scheme.letter(current.percent)
            if canvas_letter and ours is not None and str(canvas_letter) != ours:
                lines.append(
                    f"  Note: Canvas shows the letter {_letter_label(str(canvas_letter))} but the "
                    f"scheme used here gives {_letter_label(ours)}. Canvas's letter reflects the "
                    "course's real scheme; treat the letters below as approximate."
                )
    else:
        lines.append("  Canvas reports: not available (see caveats)")

    lines.append("\nFinal grade if every ungraded assignment scored 0")
    lines.append(f"  Computed here: {_with_letter(final.percent, scheme)}")
    if canvas_final is not None:
        lines.append(f"  Canvas reports: {_pct(canvas_final)}")
        if _disagrees(final.percent, canvas_final):
            note = " (see the override note above)" if override_suspected else ""
            lines.append(f"  WARNING: the computed final grade DISAGREES with Canvas{note}.")
            disagreements.append("final")

    lines.append("\nGroups (current grade)")
    lines.extend(_group_lines(current, group_names, names))

    scenario_items = items
    if hypothetical:
        scenario_items = gc.apply_hypothetical_scores(items, hypothetical)
        what_if = gc.calculate_course(groups, scenario_items, weighted, include_ungraded=False)
        by_id = {item.assignment_id: item for item in items}
        lines.append("\nWhat-if scores applied")
        for aid, value in hypothetical.items():
            item = by_id[aid]
            if item.excused:
                was = "was excused"
            elif item.score is not None and not item.pending_review:
                was = f"was {_fmt(item.score)}"
            else:
                was = "was ungraded"
            note = ""
            if not item.counts_toward_grade:
                note = " (this assignment does not count toward the grade, so it changes nothing)"
            elif item.points_possible > 0 and value > item.points_possible:
                note = " (above points possible: counts as extra credit)"
            lines.append(
                f"  - {fence_untrusted_inline(names.get(aid, aid), 'assignment name')} (ID {aid}): "
                f"{_fmt(value)}/{_fmt(item.points_possible)}, {was}{note}"
            )
        lines.append(f"  What-if current grade: {_with_letter(what_if.percent, scheme)}")
        lines.extend(_group_lines(what_if, group_names, names))

    if target is not None:
        result = gc.required_uniform_percent(
            groups, scenario_items, weighted, target, max_percent=MAX_TARGET_PERCENT
        )
        lines.append(f"\nTarget: {_pct(target)}{target_note}")
        if hypothetical:
            lines.append("  (computed on top of the what-if scores above)")
        if override_suspected:
            lines.append(
                "  (this projects the calculated grade; while an instructor override is in "
                "place, Canvas shows the override instead)"
            )
        if result.remaining_ids:
            listed = ", ".join(
                _remaining_label(names.get(a, a), assignments.get(a))
                for a in result.remaining_ids[:_MAX_LISTED_REMAINING]
            )
            more = len(result.remaining_ids) - _MAX_LISTED_REMAINING
            if more > 0:
                listed += f", and {more} more"
            lines.append(
                f"  Counted assignments with no visible score yet: {len(result.remaining_ids)} "
                f"({_fmt(result.remaining_points)} points): {listed}"
            )
            if result.already_secured:
                lines.append(
                    "  Already secured: even 0% on all remaining work projects to "
                    f"{_with_letter(result.projected_at_zero, scheme)}."
                )
            elif result.required_percent is None:
                if result.non_monotone:
                    lines.append(
                        "  Indeterminate: the approximate search found no uniform score that "
                        "meets the target; narrower passing intervals may have been missed."
                    )
                else:
                    lines.append(
                        "  Not reachable: 100% on every remaining assignment projects to "
                        f"{_with_letter(result.projected_at_full, scheme)}."
                    )
            elif result.needs_extra_credit:
                lines.append(
                    f"  {'Found an extra-credit solution' if result.non_monotone else 'Reachable only with extra credit'}: you would need {result.required_percent:.2f}% "
                    "on every remaining assignment."
                )
            else:
                lines.append(
                    f"  {'One checked solution is' if result.non_monotone else 'You need at least'} {result.required_percent:.2f}% on every remaining "
                    "assignment (the same percentage on each)."
                )
            lines.append(
                f"  Projection: 0% on remaining gives {_with_letter(result.projected_at_zero, scheme)}; "
                f"100% gives {_with_letter(result.projected_at_full, scheme)}."
            )
            if result.non_monotone:
                lines.append(
                    "  Approximate: a group drops both its lowest and highest scores, so a higher "
                    "score on remaining work can LOWER the grade (it changes which scores are "
                    "dropped). The figure above was searched on a 0.5% grid and checked; a "
                    "different mix of scores may do better."
                )
        else:
            status = "met" if result.required_percent == 0.0 else "not met"
            lines.append(
                "  No ungraded assignments that count remain, so the grade cannot change "
                f"through remaining work: {_with_letter(result.projected_at_zero, scheme)}, target {status}."
            )

    lines.append(f"\nLetter scheme: {scheme.source}")
    lines.append("\nCaveats")
    lines.extend(f"  - {c}" for c in _caveats(data, groups, items, current, enrollment, disagreements, target))
    return "\n".join(lines)


def _disagrees(computed: float | None, canvas: float) -> bool:
    """Whether a computed percent, rounded as Canvas rounds, differs from Canvas's."""
    return computed is None or abs(gc.canvas_round(computed) - canvas) > DISAGREEMENT_TOLERANCE


def _caveats(
    data: _CourseData,
    groups: list[gc.GroupRules],
    items: list[gc.GradedItem],
    current: gc.CourseGrade,
    enrollment: dict[str, Any] | None,
    disagreements: list[str],
    target: float | None,
) -> list[str]:
    course = data.course
    caveats = [
        "Only assignments Canvas shows you right now are included. The instructor can "
        "still add assignments or change weights, drop rules, or scores.",
    ]
    hidden = 0
    no_record = 0
    for group in data.groups_json:
        for assignment in group.get("assignments") or []:
            submission = gc.own_submission(assignment)
            if submission is None:
                no_record += 1
            elif gc.grade_not_posted(submission):
                hidden += 1
    if no_record:
        caveats.append(
            f"{no_record} assignment(s) came back with no submission record of yours. They "
            "count as ungraded here, and a target treats them as still to be scored."
        )
    if hidden:
        caveats.append(
            f"{hidden} assignment(s) are graded or excused but not posted. Canvas hides those "
            "results from students, so they count as ungraded here (a target treats them as "
            "still to be scored, and an unposted excusal is not applied yet) and Canvas's own "
            "score leaves them out too."
        )
    pending = sum(1 for item in items if item.pending_review and not item.excused)
    if pending:
        caveats.append(
            f"{pending} submission(s) are pending review (for example quiz questions that need "
            "manual grading). Like Canvas, the current grade leaves them out until graded."
        )
    if any(g.drop_lowest or g.drop_highest for g in groups):
        caveats.append(
            "Drop rules use Canvas's method (keep the set with the best overall ratio, not "
            "simply the lowest percentage). In an exact tie the assignment shown as dropped "
            "may differ from Canvas's choice."
        )
    if current.weighted and current.percent is not None and current.counted_weight < 100:
        caveats.append(
            f"Only {_fmt(current.counted_weight)}% of the group weight has graded work so far; "
            "the current grade is rescaled from that and can move sharply as other groups "
            "get graded."
        )
    if course.get("hide_final_grades"):
        caveats.append(
            "The instructor hides course totals from students, so Canvas gives no total "
            "to compare with; the computed figure is an estimate the course does not show."
        )
    elif enrollment is None:
        caveats.append(
            "No student enrollment with scores came back for you in this course, so "
            "there is no Canvas total to compare with."
        )
    elif _number(enrollment.get("computed_current_score")) is None:
        caveats.append(
            "Canvas sent no current score for you (it sends none while nothing is graded "
            "yet), so the computed grade could not be checked against Canvas."
        )
    if enrollment and enrollment.get("has_grading_periods"):
        period = enrollment.get("current_grading_period_title")
        period_score = _number(enrollment.get("current_period_computed_current_score"))
        detail = ""
        if period_score is not None:
            title = fence_untrusted_inline(period, "grading period title") if period else "current period"
            detail = f" Canvas's current-period score ({title}) is {_pct(period_score)}."
        caveats.append(
            "This course uses grading periods. Canvas may weight periods or report one "
            "period only; this tool does not reproduce grading-period weighting and covers "
            f"every assignment returned for the course.{detail}"
        )
    if disagreements:
        caveats.append(
            "Where the computed grade disagrees with Canvas, trust Canvas. Usual causes: "
            "a final grade override entered by your instructor (Canvas then reports the "
            "override, not the calculated score), grading periods, assignments assigned only "
            "to some students, scores you cannot see yet, or a recent change Canvas has not "
            "recalculated."
        )
    if target is not None:
        caveats.append(
            "The target assumes the same percentage on every remaining assignment that "
            "exists now. Future late penalties and assignments not yet created are not predicted."
        )
    return caveats


def _parse_hypotheticals(raw: object) -> tuple[dict[str, float], str | None]:
    # ``raw`` is typed loosely on purpose: direct callers bypass FastMCP's
    # schema validation, so the isinstance check below is a real guard. Only
    # None and an empty object mean "no what-ifs"; any other falsy value (0, "",
    # [], False) is a malformed request, not something to ignore silently.
    if raw is None:
        return {}, None
    if not isinstance(raw, dict):
        return {}, "Error: hypothetical_scores must be an object of {assignment_id: score}."
    if len(raw) > MAX_HYPOTHETICAL_SCORES:
        return {}, f"Error: at most {MAX_HYPOTHETICAL_SCORES} hypothetical scores are allowed."
    parsed: dict[str, float] = {}
    for key, value in raw.items():
        assignment_id = coerce_canvas_id(key)
        if assignment_id is None:
            return {}, f"Error: hypothetical_scores key {key!r} is not a Canvas assignment ID (digits only)."
        score = _number(value)
        if score is None or score < 0 or score > MAX_HYPOTHETICAL_POINTS:
            return {}, (
                f"Error: hypothetical score for assignment {assignment_id} must be a "
                f"non-negative number of points, at most {MAX_HYPOTHETICAL_POINTS:g}."
            )
        parsed[assignment_id] = score
    return parsed, None


def register_student_grade_tools(mcp: FastMCP) -> None:
    """Register the student grade insight tools (read-only)."""

    # The report lists every assignment in the course, so the client is told it
    # may return a large result rather than shortening it.
    @mcp.tool(
        annotations=ToolAnnotations(read_only_hint=True), meta=FULL_CONTENT_TOOL_META
    )
    @validate_params
    async def get_my_assignment_scores(course_identifier: str | int) -> str:
        """List your score on every assignment in a course, grouped by assignment group.

        Shows each group's weight (when the course weights groups) and drop
        rules, then each assignment's score / points possible and status:
        graded, missing, late, excused, unsubmitted, submitted but ungraded,
        pending review, grade not posted yet, or not counted toward the final
        grade. Uses a student token's own submissions; it does not compute a
        course total (use calculate_grade_scenarios for that).

        Args:
            course_identifier: Course code or Canvas ID
        """
        data = await _load_course(course_identifier, SCORES_COURSE_INCLUDES)
        if isinstance(data, str):
            return data
        return _render_scores_report(data)

    @mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
    @validate_params
    async def calculate_grade_scenarios(
        course_identifier: str | int,
        hypothetical_scores: dict[str, float] | None = None,
        target_percent: float | None = None,
        target_letter: str | None = None,
    ) -> str:
        """Recompute your course grade, try what-if scores, and find what you need on remaining work.

        Reproduces Canvas's grade arithmetic (weighted or total-points groups,
        drop lowest/highest and never-drop rules, excused and omitted
        assignments, ungraded work excluded, groups with nothing graded left
        out) and shows it next to Canvas's own current score, flagging any
        disagreement. Optionally applies what-if scores, and reports the single
        percentage you would need on every remaining ungraded assignment to
        reach a target. Letters use the course's grading scheme when your token
        can read it, else Canvas's default scheme; the output says which.
        Nothing is changed in Canvas.

        Args:
            course_identifier: Course code or Canvas ID
            hypothetical_scores: Optional what-if points by assignment ID, e.g.
                {"12345": 18, "12346": 9.5}. Points, not percentages.
            target_percent: Optional target course percentage (0-200)
            target_letter: Optional target letter, e.g. "A-" (from the scheme in
                use). Give target_percent or target_letter, not both.
        """
        if target_percent is not None and target_letter is not None:
            return "Error: give target_percent or target_letter, not both."
        if target_percent is not None and (
            not math.isfinite(target_percent) or not 0 <= target_percent <= MAX_TARGET_PERCENT
        ):
            return f"Error: target_percent must be between 0 and {MAX_TARGET_PERCENT:g}."
        if target_letter is not None and not (0 < len(target_letter.strip()) <= 40):
            return "Error: target_letter must be a short letter grade such as 'B+'."

        hypothetical, error = _parse_hypotheticals(hypothetical_scores)
        if error:
            return error

        data = await _load_course(course_identifier, COURSE_INCLUDES)
        if isinstance(data, str):
            return data

        known = {item.assignment_id for item in data.items}
        unknown = sorted(set(hypothetical) - known, key=lambda a: (len(a), a))
        if unknown:
            return (
                "Error: hypothetical_scores names assignment IDs not found in this course: "
                f"{', '.join(unknown)}. Use get_my_assignment_scores to see valid IDs."
            )

        scheme = await _resolve_letter_scheme(data.course_id, data.course)

        target: float | None = target_percent
        target_note = ""
        if target_letter is not None:
            # Fail closed: a stand-in scheme could name the wrong cutoff for the
            # letter, so a letter target is refused rather than guessed.
            if scheme.is_guess:
                return (
                    "Error: cannot resolve target_letter because the course's real letter "
                    f"scheme is unknown. {scheme.source} Use target_percent instead."
                )
            found = gc.find_letter(target_letter, scheme.entries)
            if found is None:
                available = ", ".join(_letter_label(name) for name, _ in scheme.entries)
                return (
                    f"Error: the letter scheme in use has no letter {target_letter.strip()!r}. "
                    f"Available: {available}. Scheme: {scheme.source}"
                )
            letter_name, target = found
            target_note = f" (lower bound of {_letter_label(letter_name)})"

        return _render_grade_scenarios(data, scheme, hypothetical, target, target_note)
