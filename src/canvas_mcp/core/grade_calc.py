"""Pure reproduction of Canvas's course-grade arithmetic (no I/O).

The student grade tools (``tools/student_grades.py``) fetch a course's
assignment groups with the caller's own submissions and hand them to this
module. Keeping the arithmetic here, free of HTTP and formatting, lets the
tests pin it against hand-checked examples.

What is reproduced, following Canvas's client-side grade calculator
(``ui/shared/grading/AssignmentGroupGradeCalculator.ts`` and
``CourseGradeCalculator.ts`` in canvas-lms):

- An assignment counts only when it is published, graded (not
  ``not_graded``) and not ``omit_from_final_grade``. Excused submissions are
  removed before anything else.
- The **current** grade uses graded work only: a submission with no score, or
  one in ``pending_review``, is left out. The **final** grade counts every
  remaining assignment, an ungraded one as 0.
- Drop rules (``drop_lowest``, ``drop_highest``, ``never_drop``) apply per
  group to whatever survived the step above. Canvas does not drop the lowest
  *percentages*: it keeps the subset whose combined score/possible ratio is
  best (worst, for ``drop_highest``), solved as a fractional optimization.
  Canvas bisects on the ratio; this module uses Dinkelbach's iteration, which
  reaches the same optimum exactly. Exact ties can resolve to a different but
  equally scored subset.
- Weighted groups: groups with zero points possible are left out, the rest
  contribute ``score / possible * weight``, and the sum is rescaled to 100 only
  when the counted weights total less than 100 (weights above 100 act as extra
  credit). No counted weight means no grade.
- Unweighted: total score over total points possible.

- An unposted submission (no ``posted_at``) is ignored, as Canvas's
  student-visible calculation ignores it: no score and no excusal, so it
  counts like ungraded work.
- Course scores are rounded the way Ruby rounds (``canvas_round``) before a
  letter is assigned, and points-based schemes round in points first.

Not reproduced: grading-period weighting, final grade overrides, and anything
a student cannot see (unposted scores, assignments not assigned to them).
Callers must say so.
"""

import math
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

# Canvas's built-in scheme (GradingStandard.default_grading_standard), used
# when a course has no scheme of its own or the caller cannot read it.
CANVAS_DEFAULT_SCHEME: tuple[tuple[str, float], ...] = (
    ("A", 0.94),
    ("A-", 0.90),
    ("B+", 0.87),
    ("B", 0.84),
    ("B-", 0.80),
    ("C+", 0.77),
    ("C", 0.74),
    ("C-", 0.70),
    ("D+", 0.67),
    ("D", 0.64),
    ("D-", 0.61),
    ("F", 0.0),
)

# Canvas stores course scores rounded to two decimals and assigns the letter
# from that rounded score, so letter_for_percent rounds first (the way Ruby
# rounds, see canvas_round). Targets are deliberately stricter: the requirement
# is computed so the UNROUNDED grade reaches the target, which can ask for 0.01
# points more than strictly needed but never tells a student a score is enough
# when it is not.
SCORE_DECIMALS = 2
_RATIO_EPSILON = 1e-12
# Grid step for the target search when the grade is not monotone in the score
# on remaining work (a group that drops both lowest and highest).
_NON_MONOTONE_GRID_STEP = 0.5


def _c_round(value: float) -> float:
    """C ``round()``: half away from zero."""
    magnitude = abs(value)
    floor = math.floor(magnitude)
    rounded = floor + 1.0 if magnitude - floor >= 0.5 else float(floor)
    return math.copysign(rounded, value)


def canvas_round(value: float, digits: int = SCORE_DECIMALS) -> float:
    """Round like Ruby's ``Float#round(digits)``, which Canvas uses for scores.

    Ruby rounds half up on the decimal value (``round_half_up`` in float.c),
    so 60.995 becomes 61.0 even though the binary double sits a hair below
    60.995 and Python's correctly rounded ``round()`` gives 60.99. At a letter
    cutoff that difference changes the letter.
    """
    if not math.isfinite(value):
        return value
    scale = 10.0**digits
    rounded = _c_round(value * scale)
    if value > 0:
        if (rounded + 0.5) / scale <= value:
            rounded += 1
    elif value < 0:
        if (rounded - 0.5) / scale >= value:
            rounded -= 1
    return rounded / scale


@dataclass(frozen=True)
class GradedItem:
    """One assignment as the grade calculation sees it."""

    assignment_id: str
    group_id: str
    points_possible: float
    score: float | None = None
    excused: bool = False
    pending_review: bool = False
    counts_toward_grade: bool = True

    @property
    def is_graded(self) -> bool:
        """Has a visible score that Canvas's current grade would use."""
        return self.score is not None and not self.pending_review


@dataclass(frozen=True)
class GroupRules:
    """An assignment group's weight and drop rules."""

    group_id: str
    weight: float = 0.0
    drop_lowest: int = 0
    drop_highest: int = 0
    never_drop: frozenset[str] = frozenset()


@dataclass(frozen=True)
class GroupGrade:
    """Result for one assignment group."""

    group_id: str
    weight: float
    score: float
    possible: float
    kept: tuple[str, ...]
    dropped: tuple[str, ...]

    @property
    def percent(self) -> float | None:
        if self.possible > 0:
            return self.score / self.possible * 100
        return None


@dataclass(frozen=True)
class CourseGrade:
    """Result for the whole course."""

    percent: float | None
    weighted: bool
    groups: tuple[GroupGrade, ...]
    # Weighted: total weight of the groups that counted. Unweighted: unused.
    counted_weight: float = 0.0


@dataclass(frozen=True)
class _Entry:
    assignment_id: str
    score: float
    total: float
    order: int


def _ratio(entries: Iterable[_Entry], extra_score: float, extra_total: float) -> float | None:
    entries = list(entries)
    total = sum(e.total for e in entries) + extra_total
    if total <= 0:
        return None
    return (sum(e.score for e in entries) + extra_score) / total


def _keep_by_ratio(
    candidates: Sequence[_Entry],
    cant_drop: Sequence[_Entry],
    keep_count: int,
    maximize: bool,
) -> list[_Entry]:
    """Keep ``keep_count`` candidates with the best (or worst) combined ratio.

    The never-drop entries are part of the ratio but are never candidates.
    Dinkelbach's method: rank by ``score - q * total`` for the current ratio q,
    keep the top ``keep_count``, recompute q from that set, and repeat until q
    stops moving. Each step improves q monotonically, and there are finitely
    many subsets, so it terminates at the optimum.
    """
    keep_count = max(1, keep_count)
    if len(candidates) <= keep_count:
        return list(candidates)

    cant_score = sum(e.score for e in cant_drop)
    cant_total = sum(e.total for e in cant_drop)

    def choose(q: float) -> list[_Entry]:
        # sorted() is stable with reverse=True too, so equal values keep
        # assignment order, matching Canvas's stable sort.
        ranked = sorted(candidates, key=lambda e: e.score - q * e.total, reverse=maximize)
        return ranked[:keep_count]

    start = _ratio(candidates, cant_score, cant_total)
    chosen = choose(start if start is not None else 0.0)
    q = _ratio(chosen, cant_score, cant_total)
    # A chosen set with no points possible (only zero-point extra credit, and
    # no never-drop points) has no ratio; Canvas keeps it as is too.
    for _ in range(1000):
        if q is None:
            break
        nxt = choose(q)
        new_q = _ratio(nxt, cant_score, cant_total)
        if new_q is None:
            chosen = nxt
            break
        improved = new_q > q + _RATIO_EPSILON if maximize else new_q < q - _RATIO_EPSILON
        if not improved:
            break
        chosen, q = nxt, new_q
    return sorted(chosen, key=lambda e: e.order)


def _assignment_sort_key(assignment_id: str) -> tuple[int, str]:
    # Numeric IDs compare numerically without mixing int and str in a key.
    return (len(assignment_id), assignment_id) if assignment_id.isdigit() else (1 << 30, assignment_id)


def drop_assignments(
    entries: Sequence[_Entry],
    drop_lowest: int = 0,
    drop_highest: int = 0,
    never_drop: frozenset[str] = frozenset(),
) -> tuple[list[_Entry], list[_Entry]]:
    """Apply a group's drop rules. Returns (kept, dropped), kept in input order.

    Clamping follows Canvas: at least one droppable entry is always kept, and
    ``drop_highest`` is ignored when it and ``drop_lowest`` together would
    leave nothing.
    """
    drop_lowest = max(0, int(drop_lowest or 0))
    drop_highest = max(0, int(drop_highest or 0))
    if not (drop_lowest or drop_highest):
        return list(entries), []

    cant = [e for e in entries if e.assignment_id in never_drop]
    droppable = [e for e in entries if e.assignment_id not in never_drop]
    if not droppable:
        return list(entries), []

    n = len(droppable)
    drop_lowest = min(drop_lowest, n - 1)
    if drop_lowest + drop_highest >= n:
        drop_highest = 0
    keep_highest = n - drop_lowest
    keep_lowest = keep_highest - drop_highest

    if any(e.total > 0 for e in droppable):
        kept_high = _keep_by_ratio(droppable, cant, keep_highest, maximize=True)
        kept = _keep_by_ratio(kept_high, cant, keep_lowest, maximize=False)
    else:
        # Nothing has points possible: plain score order, ID as tie-break.
        ordered = sorted(droppable, key=lambda e: (e.score, _assignment_sort_key(e.assignment_id)))
        kept = ordered[len(ordered) - keep_highest:][:keep_lowest]

    kept_orders = {e.order for e in kept}
    kept_all = sorted([*kept, *cant], key=lambda e: e.order)
    dropped = [e for e in droppable if e.order not in kept_orders]
    return kept_all, dropped


def calculate_group(
    rules: GroupRules, items: Sequence[GradedItem], include_ungraded: bool
) -> GroupGrade:
    """Score one group: filter, drop, then sum."""
    entries: list[_Entry] = []
    for order, item in enumerate(items):
        if item.group_id != rules.group_id or not item.counts_toward_grade or item.excused:
            continue
        if not include_ungraded and not item.is_graded:
            continue
        score = item.score if item.score is not None else 0.0
        entries.append(_Entry(item.assignment_id, score, max(item.points_possible, 0.0), order))

    kept, dropped = drop_assignments(
        entries, rules.drop_lowest, rules.drop_highest, rules.never_drop
    )
    return GroupGrade(
        group_id=rules.group_id,
        weight=rules.weight or 0.0,
        score=sum(e.score for e in kept),
        possible=sum(e.total for e in kept),
        kept=tuple(e.assignment_id for e in kept),
        dropped=tuple(e.assignment_id for e in dropped),
    )


def calculate_course(
    groups: Sequence[GroupRules],
    items: Sequence[GradedItem],
    weighted: bool,
    include_ungraded: bool = False,
) -> CourseGrade:
    """Course percentage the way Canvas computes it (unrounded)."""
    group_grades = tuple(calculate_group(g, items, include_ungraded) for g in groups)

    if weighted:
        relevant = [g for g in group_grades if g.possible > 0]
        full_weight = sum(g.weight for g in relevant)
        if full_weight == 0:
            return CourseGrade(None, True, group_grades, 0.0)
        total = sum(g.score / g.possible * g.weight for g in relevant)
        if full_weight < 100:
            total = total * 100 / full_weight
        return CourseGrade(total, True, group_grades, full_weight)

    score = sum(g.score for g in group_grades)
    possible = sum(g.possible for g in group_grades)
    percent = score / possible * 100 if possible > 0 else None
    return CourseGrade(percent, False, group_grades)


def apply_hypothetical_scores(
    items: Sequence[GradedItem], scores: Mapping[str, float]
) -> list[GradedItem]:
    """Replace scores as if graded (the student's what-if)."""
    return [
        replace(item, score=float(scores[item.assignment_id]), excused=False, pending_review=False)
        if item.assignment_id in scores
        else item
        for item in items
    ]


def remaining_items(items: Sequence[GradedItem]) -> list[GradedItem]:
    """Counted, non-excused, still-ungraded assignments worth points."""
    return [
        item
        for item in items
        if item.counts_toward_grade
        and not item.excused
        and not item.is_graded
        and item.points_possible > 0
    ]


def project_uniform(
    groups: Sequence[GroupRules],
    items: Sequence[GradedItem],
    weighted: bool,
    percent_on_remaining: float,
) -> CourseGrade:
    """Course grade if every remaining assignment scored the same percent."""
    remaining = {item.assignment_id for item in remaining_items(items)}
    fraction = percent_on_remaining / 100
    filled = [
        replace(item, score=fraction * item.points_possible, pending_review=False)
        if item.assignment_id in remaining
        else item
        for item in items
    ]
    return calculate_course(groups, filled, weighted, include_ungraded=False)


@dataclass(frozen=True)
class TargetResult:
    """Uniform percent needed on remaining work to reach a target."""

    target_percent: float
    remaining_ids: tuple[str, ...]
    remaining_points: float
    # Lowest uniform percent (0.01 resolution) that reaches the target, or
    # None when the search finds no solution. With non_monotone=True this
    # is indeterminate: a narrow passing interval may have been missed.
    required_percent: float | None
    projected_at_zero: float | None
    projected_at_full: float | None
    # True when a group with remaining work drops both its lowest and highest
    # scores. The grade is then not monotone in the score on remaining work
    # (a higher uniform score can give a LOWER grade), so the search scans a
    # grid and the answer is the lowest value found, not a proven minimum.
    non_monotone: bool = False

    @property
    def already_secured(self) -> bool:
        return self.required_percent == 0.0

    @property
    def needs_extra_credit(self) -> bool:
        return self.required_percent is not None and self.required_percent > 100


def _meets(percent: float | None, target: float) -> bool:
    return percent is not None and percent >= target - 1e-9


def required_uniform_percent(
    groups: Sequence[GroupRules],
    items: Sequence[GradedItem],
    weighted: bool,
    target_percent: float,
    max_percent: float = 200.0,
) -> TargetResult:
    """Lowest uniform percent on all remaining work that reaches the target.

    With no drops, or only drop_lowest or only drop_highest in a group, the
    course grade rises with the score on remaining work (drop rules can make
    it step rather than slide), so the threshold is found by bisection and
    then checked directly. A group that drops both lowest and highest breaks
    that: Canvas keeps the best subset and then the worst of those, and a
    higher score can change which items survive and lower the grade. Then a
    grid is scanned first and the first grid point that meets the target is
    refined. Whatever is returned has passed a direct projection; when no
    such value is found the answer is None.
    """
    remaining = remaining_items(items)
    remaining_ids = tuple(item.assignment_id for item in remaining)
    remaining_points = sum(item.points_possible for item in remaining)
    remaining_groups = {item.group_id for item in remaining}
    non_monotone = any(
        g.drop_lowest > 0 and g.drop_highest > 0 and g.group_id in remaining_groups
        for g in groups
    )

    def grade_at(p: float) -> float | None:
        return project_uniform(groups, items, weighted, p).percent

    at_zero = grade_at(0.0)
    at_full = grade_at(100.0)

    def result(required: float | None) -> TargetResult:
        return TargetResult(
            target_percent=target_percent,
            remaining_ids=remaining_ids,
            remaining_points=remaining_points,
            required_percent=required,
            projected_at_zero=at_zero,
            projected_at_full=at_full,
            non_monotone=non_monotone,
        )

    if not remaining:
        return result(0.0 if _meets(at_zero, target_percent) else None)
    if _meets(at_zero, target_percent):
        return result(0.0)

    if non_monotone:
        return result(_scan_non_monotone(grade_at, target_percent, max_percent))

    if _meets(at_full, target_percent):
        low, high = 0.0, 100.0
    elif _meets(grade_at(max_percent), target_percent):
        low, high = 100.0, max_percent
    else:
        return result(None)

    for _ in range(60):
        mid = (low + high) / 2
        if _meets(grade_at(mid), target_percent):
            high = mid
        else:
            low = mid
    # Round UP to the reporting resolution, then make sure that value works.
    required = math.ceil(high * 100 - 1e-9) / 100
    while not _meets(grade_at(required), target_percent) and required < max_percent:
        required = round(required + 0.01, 2)
    return result(required if _meets(grade_at(required), target_percent) else None)


def _scan_non_monotone(
    grade_at: Callable[[float], float | None], target_percent: float, max_percent: float
) -> float | None:
    """First grid point that meets the target, refined at 0.01 resolution.

    Only used when the grade is not monotone, where bisection cannot be
    trusted. The refinement walks the 0.01 steps between the last failing
    grid point and the first passing one, so the value returned always meets
    the target. A narrower window that meets the target between two failing
    grid points can be missed; callers say the answer is approximate.
    """
    steps = math.ceil(max_percent / _NON_MONOTONE_GRID_STEP)
    previous = 0.0
    for i in range(1, steps + 1):
        point = min(round(i * _NON_MONOTONE_GRID_STEP, 2), max_percent)
        if _meets(grade_at(point), target_percent):
            for j in range(1, round((point - previous) * 100)):
                candidate = round(previous + j / 100, 2)
                if _meets(grade_at(candidate), target_percent):
                    return candidate
            return point
        previous = point
    return None


# --------------------------------------------------------------------------
# Letter grades
# --------------------------------------------------------------------------


def parse_grading_scheme(
    data: Any, scaling_factor: float | None = None
) -> tuple[tuple[str, float], ...] | None:
    """Normalize a Canvas grading scheme to ((name, lower_bound_fraction), ...).

    Accepts the course API's ``grading_scheme`` (``[["A", 0.94], ...]``) and the
    grading standards API's (``[{"name": "A", "value": 0.94}, ...]``). A points
    based scheme whose bounds are given in points is converted with its
    ``scaling_factor``. Returns None for anything that does not look like a
    scheme, so the caller falls back to Canvas's default.
    """
    if not isinstance(data, list) or not data:
        return None
    entries: list[tuple[str, float]] = []
    for row in data:
        if isinstance(row, Mapping):
            name, value = row.get("name"), row.get("value")
        elif isinstance(row, (list, tuple)) and len(row) == 2:
            name, value = row
        else:
            return None
        if not isinstance(name, str) or not name.strip():
            return None
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None
        if not math.isfinite(value) or value < 0:
            return None
        entries.append((name, float(value)))
    if scaling_factor and scaling_factor > 1 and any(v > 1 for _, v in entries):
        entries = [(n, v / scaling_factor) for n, v in entries]
    if any(v > 1.0 + 1e-9 for _, v in entries):
        return None
    entries.sort(key=lambda e: e[1], reverse=True)
    return tuple(entries)


def _ruby_decimal(value: float) -> Decimal:
    # Float#to_d: the shortest decimal that round-trips, which repr() gives.
    return Decimal(repr(float(value)))


def _scale_points_based(score: float, scaling_factor: float) -> float:
    """Canvas's ``GradingStandard#scale_score`` and the ``round(2)`` after it.

    A points-based scheme (for example a 4-point GPA scale) turns the score
    into points rounded to two decimals and assigns the letter from that:
    89.9% on a 4-point scale is 3.596, rounded to 3.60, which is 90%.
    """
    if scaling_factor == 100 or scaling_factor <= 0:
        return score
    factor = _ruby_decimal(scaling_factor)
    two_places = Decimal("0.01")
    try:
        scaled = (_ruby_decimal(score) / (Decimal(100) / factor)).quantize(
            two_places, rounding=ROUND_HALF_UP
        )
        back = (scaled / factor * 100).quantize(two_places, rounding=ROUND_HALF_UP)
    except (InvalidOperation, ZeroDivisionError):
        return score
    return float(back)


def letter_for_percent(
    percent: float | None,
    scheme: Sequence[tuple[str, float]],
    points_based: bool = False,
    scaling_factor: float | None = None,
) -> str | None:
    """Letter for a course percentage: the highest bound it reaches.

    Follows Canvas (``GradingStandard#score_to_grade``): the course score is
    stored rounded to two decimals with Ruby's rounding, a negative score
    counts as 0, and a points-based scheme compares the score after turning
    it into points and back with two-decimal rounding.
    """
    if percent is None or not scheme:
        return None
    score = max(canvas_round(percent), 0.0)
    if points_based and scaling_factor is not None and math.isfinite(scaling_factor):
        score = _scale_points_based(score, scaling_factor)
    for name, lower in scheme:
        if score >= round(lower * 100, 6) - 1e-9:
            return name
    return scheme[-1][0]


def same_scheme(
    first: Sequence[tuple[str, float]] | None, second: Sequence[tuple[str, float]] | None
) -> bool:
    """Whether two parsed schemes have the same letters and cutoffs."""
    if first is None or second is None or len(first) != len(second):
        return False
    return all(
        a_name == b_name and abs(a_value - b_value) < 1e-9
        for (a_name, a_value), (b_name, b_value) in zip(first, second, strict=True)
    )


def find_letter(
    letter: str, scheme: Sequence[tuple[str, float]]
) -> tuple[str, float] | None:
    """(scheme name, lower-bound percent) for ``letter``: exact match first,
    then a unique case-insensitive one. None when the scheme has no such letter."""
    wanted = letter.strip()
    for name, lower in scheme:
        if name == wanted:
            return name, round(lower * 100, 6)
    folded = [(name, lower) for name, lower in scheme if name.strip().casefold() == wanted.casefold()]
    if len(folded) == 1:
        return folded[0][0], round(folded[0][1] * 100, 6)
    return None


# --------------------------------------------------------------------------
# Canvas JSON -> model
# --------------------------------------------------------------------------


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def own_submission(assignment: Mapping[str, Any]) -> Mapping[str, Any] | None:
    """The caller's submission embedded by ``include[]=submission``.

    Canvas embeds one object for a student. Anything else (absent, null, or a
    list, which Canvas sends for observer tokens and which would describe the
    observed students, not the caller) is not the caller's own submission.
    """
    submission = assignment.get("submission")
    return submission if isinstance(submission, Mapping) else None


def is_unposted(submission: Mapping[str, Any] | None) -> bool:
    """Whether Canvas's student-visible grade ignores this submission.

    Canvas's posted grade calculation (``GradeCalculator#ignore_submission?``)
    drops every submission without a ``posted_at``, and with it the excused
    flag, so the assignment counts like one never graded. Only applied when
    Canvas sent the ``posted_at`` key.
    """
    return (
        submission is not None
        and "posted_at" in submission
        and not submission.get("posted_at")
    )


def grade_not_posted(submission: Mapping[str, Any] | None) -> bool:
    """Whether the instructor graded or excused this but has not posted it.

    A graded or excused submission with no ``posted_at`` is hidden: Canvas
    strips the score (not the ``excused`` flag) from a student's view. Without
    a ``posted_at`` key (an older payload) the only sign left is a graded
    submission whose score was withheld.
    """
    if submission is None:
        return False
    state = submission.get("workflow_state")
    if "posted_at" in submission:
        return is_unposted(submission) and (
            bool(submission.get("excused")) or state == "graded"
        )
    return (
        state == "graded"
        and _number(submission.get("score")) is None
        and not submission.get("excused")
    )


def assignment_counts(assignment: Mapping[str, Any]) -> bool:
    """Whether Canvas counts this assignment toward the course grade."""
    if assignment.get("omit_from_final_grade"):
        return False
    if assignment.get("grading_type") == "not_graded":
        return False
    if "not_graded" in (assignment.get("submission_types") or []):
        return False
    if assignment.get("workflow_state") == "unpublished" or assignment.get("published") is False:
        return False
    return True


def submission_statuses(
    assignment: Mapping[str, Any], submission: Mapping[str, Any] | None
) -> list[str]:
    """Plain-language status labels for one of the caller's assignments."""
    labels: list[str] = []
    if assignment.get("omit_from_final_grade"):
        labels.append("not counted toward final grade")
    if assignment.get("grading_type") == "not_graded" or "not_graded" in (
        assignment.get("submission_types") or []
    ):
        labels.append("not graded")
    if submission is None:
        labels.append("no submission record visible")
        return labels

    state = submission.get("workflow_state")
    score = _number(submission.get("score"))
    if grade_not_posted(submission):
        # Canvas withholds the score, and does not apply an excusal to the
        # grade, until the instructor posts it.
        labels.append("grade not posted yet (hidden from you)")
    elif submission.get("excused"):
        labels.append("excused")
    elif state == "pending_review":
        labels.append("pending review (needs manual grading)")
    elif score is not None:
        labels.append("graded")
    elif submission.get("missing"):
        labels.append("missing")
    elif submission.get("submitted_at"):
        labels.append("submitted, not graded yet")
    else:
        labels.append("unsubmitted")

    if score is not None and submission.get("missing"):
        labels.append("marked missing")
    if submission.get("late"):
        labels.append("late")
    deducted = _number(submission.get("points_deducted"))
    if deducted:
        labels.append(f"late penalty -{deducted:g} pts")
    return labels


class MalformedGradeData(ValueError):
    """Canvas sent assignment-group data the grade model cannot trust.

    Raised instead of skipping the offending entry: a grade computed from a
    silently shortened list of groups, assignments or rules would look
    authoritative and be wrong.
    """


def canvas_id(value: Any) -> str | None:
    """A Canvas object ID as its normalized digit string, else None."""
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        return None
    text = str(value).strip()
    return text if text.isascii() and text.isdigit() else None


def _checked_number(
    value: Any, label: str, *, minimum: float | None = None
) -> float | None:
    """A numeric field Canvas may leave null, but must not send as anything else.

    None stays None (the field is absent). Any other value that is not a finite
    number, or is below ``minimum``, is malformed: defaulting it to 0 would let
    a wrong grade look authoritative.
    """
    if value is None:
        return None
    number = _number(value)
    if number is None:
        raise MalformedGradeData(f"{label} is not a number: {value!r}")
    if minimum is not None and number < minimum:
        raise MalformedGradeData(f"{label} is below {minimum:g}: {value!r}")
    return number


def _drop_count(rules: Mapping[str, Any], key: str, group_id: str) -> int:
    value = rules.get(key)
    if value is None:
        return 0
    number = _number(value)
    if number is None or number < 0 or number != int(number):
        raise MalformedGradeData(
            f"assignment group {group_id} has an unreadable {key} rule: {value!r}"
        )
    return int(number)


def _check_boolean_fields(payload: Mapping[str, Any], fields: Sequence[str], label: str) -> None:
    """Reject malformed flags instead of treating text such as 'false' as true."""
    for field in fields:
        if field in payload and not isinstance(payload[field], bool):
            raise MalformedGradeData(f"{label} {field} is not a boolean: {payload[field]!r}")


def build_grade_model(
    groups_json: Sequence[Mapping[str, Any]],
) -> tuple[list[GroupRules], list[GradedItem]]:
    """Turn ``/assignment_groups?include[]=assignments&include[]=submission``
    into the calculation model. IDs become strings.

    Raises ``MalformedGradeData`` when the payload is not the shape Canvas
    documents: a group or assignment that is not an object or has no numeric
    ID, assignments that are not a list, unreadable drop rules, or a
    submission that is not the caller's single object. Numeric fields that are
    present but not numeric (a null stays allowed), a ``never_drop`` entry that
    is not an assignment ID, and a group or assignment ID that appears twice
    are rejected the same way.
    """
    groups: list[GroupRules] = []
    items: list[GradedItem] = []
    seen_groups: set[str] = set()
    seen_assignments: set[str] = set()
    for group in groups_json:
        if not isinstance(group, Mapping):
            raise MalformedGradeData("an assignment group entry is not an object")
        group_id = canvas_id(group.get("id"))
        if group_id is None:
            raise MalformedGradeData(
                f"an assignment group has no numeric ID (got {group.get('id')!r})"
            )
        if group_id in seen_groups:
            raise MalformedGradeData(f"assignment group {group_id} appears more than once")
        seen_groups.add(group_id)
        rules = group.get("rules")
        if rules is None:
            rules = {}
        if not isinstance(rules, Mapping):
            raise MalformedGradeData(f"assignment group {group_id} has unreadable drop rules")
        never_drop = rules.get("never_drop")
        if never_drop is None:
            never_drop = []
        if not isinstance(never_drop, list):
            raise MalformedGradeData(
                f"assignment group {group_id} has an unreadable never_drop rule"
            )
        never_drop_ids: set[str] = set()
        for entry in never_drop:
            entry_id = canvas_id(entry)
            if entry_id is None:
                raise MalformedGradeData(
                    f"assignment group {group_id} has a never_drop entry that is not "
                    f"an assignment ID: {entry!r}"
                )
            never_drop_ids.add(entry_id)
        weight = _checked_number(
            group.get("group_weight"), f"assignment group {group_id} group_weight", minimum=0.0
        )
        groups.append(
            GroupRules(
                group_id=group_id,
                weight=weight or 0.0,
                drop_lowest=_drop_count(rules, "drop_lowest", group_id),
                drop_highest=_drop_count(rules, "drop_highest", group_id),
                never_drop=frozenset(never_drop_ids),
            )
        )
        assignments = group.get("assignments")
        if not isinstance(assignments, list):
            raise MalformedGradeData(f"assignment group {group_id} did not list its assignments")
        for assignment in assignments:
            if not isinstance(assignment, Mapping):
                raise MalformedGradeData(
                    f"an assignment entry in group {group_id} is not an object"
                )
            assignment_id = canvas_id(assignment.get("id"))
            if assignment_id is None:
                raise MalformedGradeData(
                    f"an assignment in group {group_id} has no numeric ID "
                    f"(got {assignment.get('id')!r})"
                )
            if assignment_id in seen_assignments:
                raise MalformedGradeData(f"assignment {assignment_id} appears more than once")
            seen_assignments.add(assignment_id)
            _check_boolean_fields(
                assignment, ("published", "omit_from_final_grade"), f"assignment {assignment_id}"
            )
            points_possible = _checked_number(
                assignment.get("points_possible"),
                f"assignment {assignment_id} points_possible",
                minimum=0.0,
            )
            raw_submission = assignment.get("submission")
            if raw_submission is not None and not isinstance(raw_submission, Mapping):
                raise MalformedGradeData(
                    f"assignment {assignment_id} came back with submissions as a list or "
                    "other non-object, which Canvas does for observer tokens; this tool "
                    "reports only your own submissions"
                )
            submission = own_submission(assignment)
            if submission is not None:
                _check_boolean_fields(
                    submission, ("excused", "missing", "late"), f"assignment {assignment_id} submission"
                )
            # Canvas's student-visible grade treats an unposted submission as
            # never graded: no score and no excusal.
            unposted = is_unposted(submission)
            raw_score = (
                _checked_number(submission.get("score"), f"assignment {assignment_id} score")
                if submission
                else None
            )
            score = None if unposted else raw_score
            items.append(
                GradedItem(
                    assignment_id=assignment_id,
                    group_id=group_id,
                    points_possible=points_possible or 0.0,
                    score=score,
                    excused=bool(submission and submission.get("excused")) and not unposted,
                    pending_review=bool(
                        submission and submission.get("workflow_state") == "pending_review"
                    ),
                    counts_toward_grade=assignment_counts(assignment),
                )
            )
    return groups, items
