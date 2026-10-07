"""Read-only quiz awareness for students (issue #172, student slice).

Two tools answer "what quizzes do I have, when are they due, and how many
attempts do I have left?". Neither takes a quiz, starts an attempt, or reads a
question or answer: those are academic-integrity decisions this module
deliberately does not make, so no endpoint under ``.../questions``,
``.../quiz_submissions/:id/...`` or any POST/PUT is ever called.

Canvas has two quiz engines, and they surface differently to a student token:

- **Classic Quizzes** have their own API. ``GET /courses/:id/quizzes`` lists them
  (404 when the instructor has hidden the Quizzes page; only this list checks
  the tab), ``GET /courses/:id/quizzes/:id`` describes one, ``GET
  /courses/:id/quizzes/:id/submission`` returns the caller's live quiz record
  (including the ``settings_only`` record that holds extra attempts granted
  before a first attempt), and ``GET /courses/:id/quizzes/:id/submissions``
  can return attempt history but also trigger grading.
  The plural route is never called: it queues Canvas's job that grades
  overdue in-progress attempts for both students and graders
  (QuizSubmissionsApiController#index). Only the latest attempt is available.
- **New Quizzes** live in a separate LTI service. To Canvas they are assignments
  whose external tool is the Quizzes LTI tool, which the assignment serializer
  marks with ``is_quiz_lti_assignment: true`` (canvas-lms
  ``lib/api/v1/assignment.rb``, set only when ``assignment.quiz_lti?``). Their
  settings and per-attempt history are not exposed to students by any
  documented Canvas REST endpoint, and the tools say so instead of guessing.

``is_quiz_assignment`` is NOT a New Quizzes signal, whatever its docstring says:
the serializer sets it to ``assignment.quiz? && assignment.quiz.assignment?``,
i.e. a graded *Classic* quiz, and that was measured live on #172. Closed PR #191
used it to find New Quizzes and would have reported none.
"""

import re
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit

from fastmcp import FastMCP
from mcp.types import ToolAnnotations

from ..core.cache import get_course_code, resolve_numeric_course_id
from ..core.client import fetch_all_paginated_results, make_canvas_request
from ..core.dates import format_date, parse_date
from ..core.tool_results import FULL_CONTENT_TOOL_META
from ..core.untrusted_content import fence_untrusted, fence_untrusted_inline
from ..core.validation import coerce_canvas_id, validate_params

_QUIZ_TYPE_LABELS = {
    "assignment": "graded quiz",
    "practice_quiz": "practice quiz",
    "graded_survey": "graded survey",
    "survey": "ungraded survey",
}

_SCORING_POLICY_LABELS = {
    "keep_highest": "highest attempt counts",
    "keep_latest": "latest attempt counts",
    "keep_average": "average of attempts counts",
}


def _label(labels: dict[str, str], raw: Any, default: str) -> str:
    """Look up a Canvas enum value's label; unknown or non-string values get ``default``."""
    return labels.get(raw, default) if isinstance(raw, str) else default


def _quiz_type_label(raw: Any) -> str:
    """A quiz type's label; an unrecognised value is fenced, never echoed raw."""
    if isinstance(raw, str) and raw and raw not in _QUIZ_TYPE_LABELS:
        return fence_untrusted_inline(raw, "quiz type")
    return _label(_QUIZ_TYPE_LABELS, raw, "unknown type")


_PLAIN_NUMBER = re.compile(r"[0-9]+(?:\.[0-9]+)?")


def _plain(value: object) -> str:
    """Render a Canvas ID, count or limit that is expected to be a plain number.

    Numbers and digit strings pass through. Anything else (a field Canvas
    should never fill with text) is fenced inline instead of being echoed raw,
    so a free-text value in a numeric field cannot reach the model unmarked.
    """
    if value is None:
        return "unknown"
    if isinstance(value, int | float):
        return str(value)
    if isinstance(value, str) and _PLAIN_NUMBER.fullmatch(value):
        return value
    return fence_untrusted_inline(value, "unexpected value from Canvas")


def _whole_number(value: object) -> int | None:
    """A non-negative whole number from an int or a digit string; None for anything else.

    Used for attempt numbers and counts, which are compared and subtracted.
    Booleans, negative numbers, floats and free text are not accepted, so a
    malformed value is treated as unknown rather than as a number.
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value >= 0 else None
    if isinstance(value, str) and value.isascii() and value.isdigit():
        return int(value)
    return None


def _flag(value: object) -> bool:
    """A Canvas boolean that is really ``true``; the string "false" is not a yes."""
    return value is True


def _when(value: object) -> str:
    """Format a Canvas timestamp; one that does not parse is fenced, not echoed raw."""
    if isinstance(value, str) and parse_date(value) is not None:
        return format_date(value)
    return fence_untrusted_inline(value, "unparseable date from Canvas")


def _link(value: object) -> str | None:
    """A Canvas link safe to print on one line, or None to leave it out."""
    if isinstance(value, str) and re.fullmatch(r"https?://\S+", value):
        return value
    return None


# QuizSubmission states that represent a finished attempt. "untaken" is an
# attempt in progress; "settings_only" is a placeholder Canvas creates when an
# instructor grants extra attempts or time before the student starts; "preview"
# is a teacher preview. Neither of the last two is an attempt.
_FINISHED_STATES = ("complete", "pending_review")
_NON_ATTEMPT_STATES = ("settings_only", "preview")

_NEW_QUIZZES_NOTE = (
    "Note: this is a New Quiz. Its time limit, number of allowed attempts, "
    "question count and your per-attempt history are stored in the New "
    "Quizzes service, and Canvas's documented REST API does not expose them to "
    "students. Only the Canvas assignment record is shown; open the quiz in "
    "Canvas for the rest."
)

_HTTP_STATUS = re.compile(r"HTTP error: (\d{3})")


def _http_status(error: object) -> int | None:
    """The HTTP status carried by a client error string, if any."""
    match = _HTTP_STATUS.search(str(error))
    return int(match.group(1)) if match else None


def _explain_error(
    error: object,
    what: str,
    *,
    tab_hint: bool = False,
    unauthorized: str | None = None,
) -> str:
    """One sentence that tells a student what a Canvas refusal most likely means.

    Canvas answers an action the caller's role may not perform with 401 (not
    403), so a 401 is not necessarily a bad token; ``unauthorized`` replaces the
    generic 401 text where the cause is known. A hidden Quizzes page answers
    404 with "That page has been disabled for this course", but only the quiz
    LIST checks the tab (``QuizzesApiController#index`` calls ``tab_enabled?``;
    ``show`` and the quiz-submissions routes do not), so ``tab_hint`` is passed
    only for that request.
    """
    status = _http_status(error)
    if status == 401:
        hint = unauthorized or (
            f"Canvas refused to show {what} (401 Unauthorized). Either the token "
            "is invalid or expired, or your role in this course may not view it "
            "(for example it is unpublished or not assigned to you)."
        )
    elif status == 403:
        hint = f"Canvas refused to show {what} (403 Forbidden) for your role in this course."
    elif status == 404:
        hint = (
            f"Canvas could not find {what} (404). The course or item may not "
            "exist or be visible to you"
        )
        hint += (
            ", or the instructor has hidden the Quizzes page in this course."
            if tab_hint else "."
        )
    else:
        hint = f"Could not fetch {what}."
    return f"{hint} Details: {error}"


# Both quiz-submission routes require the quiz's :submit right, which Canvas
# withholds when the course has concluded for the student (no
# participate_as_student) or the student is excused from the quiz
# (Quizzes::Quiz set_policy). The quiz itself was just read with the same
# token, so a token problem is not the explanation.
_ATTEMPTS_UNAUTHORIZED = (
    "Canvas refused to show your quiz attempts (401 Unauthorized). Canvas only "
    "shows quiz attempts while you can still take the quiz; this happens when "
    "the course has concluded for you or you are excused from this quiz."
)

# Canvas permission names taken to put the quiz-submissions index on its grader
# branch (QuizSubmissionsApiController#index): grading a course's quizzes is
# governed by manage_grades, and viewing every student's grades by
# view_all_grades (canvas-lms controller source checked 2026-10-07). A student must have
# both explicitly denied, so a missing or unclear answer fails closed.
_GRADING_PERMISSIONS = ("manage_grades", "view_all_grades")

# Extra, stricter-only signal. Staff roles hold read_as_admin, so if any other
# permission were to select the grader branch for a staff caller, this still
# stops the call. It can only add a refusal: a student's answer is not
# required to include it.
_STAFF_PERMISSIONS = ("read_as_admin",)


def _grading_rights(response: object) -> bool | None:
    """Whether a /courses/:id/permissions answer grants grading rights.

    True if any grading or staff permission is granted, False if every grading
    permission is explicitly denied and no staff permission is granted, None
    when the answer is an error or incomplete (callers fail closed). Canvas
    renders booleans; its docs show "true"/"false" strings, so both are
    accepted.
    """
    if not isinstance(response, dict) or _is_error(response):
        return None
    names = _GRADING_PERMISSIONS + _STAFF_PERMISSIONS
    if any(response.get(name) is True or response.get(name) == "true" for name in names):
        return True
    graded = [response.get(name) for name in _GRADING_PERMISSIONS]
    if all(v is False or v == "false" for v in graded):
        return False
    return None


def _is_error(response: object) -> bool:
    return isinstance(response, dict) and "error" in response


# Submission types Canvas documents for assignments. Any other string is fenced
# when shown, and a non-string is dropped.
_KNOWN_SUBMISSION_TYPES = frozenset({
    "discussion_topic", "online_quiz", "on_paper", "none", "external_tool",
    "online_text_entry", "online_url", "online_upload", "media_recording",
    "student_annotation", "wiki_page",
})


def _submission_types(assignment: dict[str, Any]) -> list[str]:
    """The assignment's submission types as strings; anything but a list of strings is empty."""
    raw = assignment.get("submission_types")
    if not isinstance(raw, list):
        return []
    return [t for t in raw if isinstance(t, str)]


def _describe_submission_types(assignment: dict[str, Any]) -> str:
    """Submission types for a message: known names as-is, anything else fenced."""
    types = [
        t if t in _KNOWN_SUBMISSION_TYPES else fence_untrusted_inline(t, "submission type")
        for t in _submission_types(assignment)
    ]
    return ", ".join(types) or "none"


def _is_new_quiz(assignment: dict[str, Any]) -> bool:
    """Whether a Canvas assignment record is a New Quiz.

    Primary signal: ``is_quiz_lti_assignment`` (present, and true, only for
    Quizzes-LTI assignments). Fallback for serializers that omit it: an
    ``external_tool`` assignment launching an Instructure-hosted ``quiz-lti``
    host, which is where New Quizzes is served from. ``is_quiz_assignment`` is
    deliberately not consulted; see the module docstring.
    """
    if assignment.get("is_quiz_lti_assignment") is True:
        return True
    if "external_tool" not in _submission_types(assignment):
        return False
    tag = assignment.get("external_tool_tag_attributes") or {}
    url = tag.get("url") if isinstance(tag, dict) else None
    if not isinstance(url, str):
        return False
    host = (urlsplit(url).hostname or "").lower()
    return "quiz-lti" in host and host.endswith(".instructure.com")


def _is_classic_quiz_assignment(assignment: dict[str, Any]) -> bool:
    """A graded Classic quiz's assignment shell (carries its ``quiz_id``)."""
    return (
        "online_quiz" in _submission_types(assignment)
        and assignment.get("quiz_id") is not None
    )


def _due_sort_key(record: dict[str, Any]) -> tuple[int, datetime]:
    """Earliest due date first; undated items last."""
    raw = record.get("due_at")
    due = parse_date(raw) if isinstance(raw, str) else None
    if due is None:
        return (1, datetime.max.replace(tzinfo=UTC))
    return (0, due)


def _fmt_points(value: object) -> str:
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return _plain(value)


def _date_line(record: dict[str, Any]) -> str:
    due = _when(record["due_at"]) if record.get("due_at") else "no due date"
    parts = [f"Due: {due}"]
    if record.get("unlock_at"):
        parts.append(f"Opens: {_when(record['unlock_at'])}")
    if record.get("lock_at"):
        parts.append(f"Closes: {_when(record['lock_at'])}")
    return " | ".join(parts)


def _yes_no(value: object) -> str:
    if value is True:
        return "yes"
    if value is False:
        return "no"
    return "unknown"


def _attempts_allowed(value: object) -> str:
    if value is None:
        return "not reported"
    if isinstance(value, int) and value < 0:
        return "unlimited"
    return _plain(value)


def _lock_line(record: dict[str, Any]) -> str | None:
    """The 'locked for you' line, or None when Canvas did not say it is locked.

    ``lock_explanation`` is Canvas-generated but can embed a module name the
    instructor wrote, so it is fenced as an inline label.
    """
    if not record.get("locked_for_user"):
        return None
    explanation = record.get("lock_explanation")
    if explanation:
        return (
            "Locked for you: yes, "
            f"{fence_untrusted_inline(explanation, 'lock explanation')}"
        )
    return "Locked for you: yes"


def _describe_assignment_submission(
    submission: object, points_possible: object
) -> str:
    """The caller's own gradebook submission for a quiz's assignment shell."""
    if not isinstance(submission, dict) or not submission:
        return "no submission record returned"
    if _flag(submission.get("excused")):
        return "excused"
    parts = []
    if submission.get("submitted_at"):
        parts.append(f"submitted {_when(submission['submitted_at'])}")
    else:
        parts.append("not submitted")
    if submission.get("workflow_state") == "pending_review":
        parts.append("pending review")
    score = submission.get("score")
    if score is not None:
        total = f"/{_fmt_points(points_possible)}" if points_possible is not None else ""
        parts.append(f"score {_fmt_points(score)}{total}")
    if _flag(submission.get("late")):
        parts.append("late")
    if _flag(submission.get("missing")):
        parts.append("marked missing")
    return ", ".join(parts)


def _classic_quiz_block(
    quiz: dict[str, Any], assignment: dict[str, Any] | None
) -> list[str]:
    title = fence_untrusted_inline(quiz.get("title") or "Untitled quiz", "quiz title")
    quiz_type = _quiz_type_label(quiz.get("quiz_type"))
    head = f"  Quiz ID: {_plain(quiz.get('id'))} | Type: {quiz_type}"
    if quiz.get("published") is not None:
        head += f" | Published: {_yes_no(quiz.get('published'))}"
    time_limit = quiz.get("time_limit")
    details = [
        f"Time limit: {_plain(time_limit)} min" if time_limit else "Time limit: none",
        f"Attempts allowed: {_attempts_allowed(quiz.get('allowed_attempts'))}",
    ]
    if quiz.get("points_possible") is not None:
        details.append(f"Points: {_fmt_points(quiz['points_possible'])}")
    lines = [f"• {title}", head, f"  {_date_line(quiz)}", f"  {' | '.join(details)}"]
    lock = _lock_line(quiz)
    if lock:
        lines.append(f"  {lock}")
    if assignment is not None:
        lines.append(
            "  Your submission: "
            + _describe_assignment_submission(
                assignment.get("submission"), assignment.get("points_possible")
            )
        )
    return lines


def _new_quiz_block(assignment: dict[str, Any]) -> list[str]:
    name = fence_untrusted_inline(assignment.get("name") or "Untitled quiz", "quiz title")
    head = f"  Assignment ID: {_plain(assignment.get('id'))}"
    if assignment.get("points_possible") is not None:
        head += f" | Points: {_fmt_points(assignment['points_possible'])}"
    if assignment.get("published") is not None:
        head += f" | Published: {_yes_no(assignment.get('published'))}"
    lines = [f"• {name}", head, f"  {_date_line(assignment)}"]
    lock = _lock_line(assignment)
    if lock:
        lines.append(f"  {lock}")
    lines.append(
        "  Your submission: "
        + _describe_assignment_submission(
            assignment.get("submission"), assignment.get("points_possible")
        )
    )
    return lines


_UNREADABLE_ATTEMPTS = (
    "Canvas returned attempt data in a shape this tool could not read, so "
    "nothing is claimed about how many attempts you have used or have left."
)


def _quiz_submission_records(response: dict[str, Any]) -> list[dict[str, Any]] | None:
    """The ``quiz_submissions`` list of an attempts answer, or None when unreadable.

    Both attempt routes answer ``{"quiz_submissions": [...]}``. A missing key, a
    value that is not a list, or a list holding anything but objects is unknown
    state, not "no attempts", and the caller must not report usage from it.
    """
    records = response.get("quiz_submissions")
    if not isinstance(records, list) or not all(isinstance(r, dict) for r in records):
        return None
    return records


def _attempt_number(record: dict[str, Any]) -> int:
    """A record's attempt number, 0 when it has none; callers check readability first."""
    return _whole_number(record.get("attempt")) or 0


def _attempts_readable(records: list[dict[str, Any]]) -> bool:
    """Whether every record that stands for an attempt has a plain attempt number.

    ``settings_only`` and ``preview`` records are not attempts and may carry no
    number. Any other record must have a whole number of at least 1, otherwise
    the used/remaining arithmetic would be a guess.
    """
    for record in records:
        if record.get("workflow_state") in _NON_ATTEMPT_STATES:
            continue
        number = _whole_number(record.get("attempt"))
        if number is None or number < 1:
            return False
    return True


def _attempt_summary(
    history: list[dict[str, Any]],
    quiz: dict[str, Any],
    live: dict[str, Any] | None = None,
) -> list[str]:
    """Attempts used/remaining, kept score, in-progress state and history.

    Both inputs contain only the caller's current record from the singular
    route, including a ``settings_only`` record when extra attempts were
    granted before the first attempt. No prior history is requested: the
    plural submissions GET queues grading even for a student's own attempt.

    ``attempts_left`` is Canvas's own figure (``allowed_attempts - attempt +
    extra_attempts``, or -1 for unlimited) and is preferred over recomputing it,
    taken from the live record when there is one.
    """
    # The live record first, so it wins ties with its own history version.
    records = ([live] if live else []) + list(history)
    if not _attempts_readable(records):
        return [_UNREADABLE_ATTEMPTS]
    attempts = [s for s in records if s.get("workflow_state") not in _NON_ATTEMPT_STATES]
    latest = max(attempts, key=_attempt_number) if attempts else {}
    source = live if live else (max(records, key=_attempt_number) if records else {})
    used = _attempt_number(latest) if latest else 0
    allowed = quiz.get("allowed_attempts")

    in_progress: dict[int, dict[str, Any]] = {}
    for record in attempts:
        if record.get("workflow_state") == "untaken":
            in_progress.setdefault(_attempt_number(record), record)
    finished = sorted(
        (s for s in history if s.get("workflow_state") in _FINISHED_STATES),
        key=_attempt_number,
    )
    # Any attempt numbered above 1 means an earlier one was submitted, even
    # when Canvas does not list it.
    submitted_any = bool(finished) or any(
        s.get("workflow_state") in _FINISHED_STATES for s in attempts
    ) or any(n > 1 for n in in_progress)

    raw_left = source.get("attempts_left") if source else None
    raw_extra = source.get("extra_attempts") if source else None
    # Canvas uses -1 for "unlimited", so a left count may be negative; the
    # other counts are whole numbers or unknown (never echoed raw).
    left = raw_left if isinstance(raw_left, int) and not isinstance(raw_left, bool) else None
    extra = _whole_number(raw_extra)
    allowed_count = allowed if isinstance(allowed, int) and not isinstance(allowed, bool) else None
    if raw_left is None and allowed_count is not None and (raw_extra is None or extra is not None):
        left = -1 if allowed_count < 0 else max(0, allowed_count - used + (extra or 0))

    if left is not None and left < 0:
        usage = f"Attempts used: {used} (unlimited attempts allowed)"
    elif left is not None:
        usage = f"Attempts used: {used}, remaining: {left}"
        if allowed_count is not None and allowed_count >= 0:
            usage = f"Attempts used: {used} of {allowed_count}, remaining: {left}"
        if extra:
            usage += f" (includes {extra} extra granted by your instructor)"
    else:
        usage = f"Attempts used: {used} (remaining attempts not reported by Canvas)"
    if in_progress:
        usage += "; the attempt in progress counts as used"
    lines = [usage]

    points = quiz.get("points_possible")
    total = f"/{_fmt_points(points)}" if points is not None else ""
    kept = latest.get("kept_score") if latest else None
    if kept is not None:
        policy = _label(_SCORING_POLICY_LABELS, quiz.get("scoring_policy"), "")
        suffix = f" ({policy})" if policy else ""
        lines.append(f"Kept score: {_fmt_points(kept)}{total}{suffix}")
    elif submitted_any:
        lines.append("Kept score: not available (results may be hidden or not yet graded)")
    elif in_progress:
        lines.append("Kept score: none yet (no submitted attempt yet)")

    for number in sorted(in_progress):
        current = in_progress[number]
        line = f"In progress: attempt {number}"
        if current.get("started_at"):
            line += f", started {_when(current['started_at'])}"
        if current.get("end_at"):
            line += f", must be submitted by {_when(current['end_at'])}"
        if _flag(current.get("overdue_and_needs_submission")):
            line += " (past its end time; Canvas will submit it automatically)"
        lines.append(line)
    running = max(in_progress, default=0)
    if running > 1 and not any(_attempt_number(s) < running for s in finished):
        earlier = "attempt 1 is" if running == 2 else f"attempts 1 to {running - 1} are"
        lines.append(
            f"Your earlier {earlier} not listed by Canvas while an attempt is in "
            "progress; check again after submitting."
        )

    if finished:
        lines.append("History:")
        for record in finished:
            score = record.get("score")
            score_text = (
                f"score {_fmt_points(score)}{total}" if score is not None else "score not available"
            )
            entry = f"  • Attempt {_attempt_number(record)}: {score_text}"
            if record.get("workflow_state") == "pending_review":
                entry += ", pending review"
            if record.get("finished_at"):
                entry += f", finished {_when(record['finished_at'])}"
            spent = record.get("time_spent")
            if isinstance(spent, int | float):
                entry += (
                    f", time spent {round(spent / 60)} min"
                    if spent >= 60 else f", time spent {int(spent)} s"
                )
            lines.append(entry)
    elif not in_progress and not used:
        lines.append("You have not started this quiz.")
    return lines


def register_student_quiz_tools(mcp: FastMCP) -> None:
    """Register the read-only student quiz tools."""

    @mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
    @validate_params
    async def list_quizzes(course_identifier: str | int) -> str:
        """List the quizzes in one of YOUR courses: Classic and New Quizzes.

        Read-only. Shows due/open/close dates, time limit, allowed attempts,
        points and your submission state. It never opens a quiz, starts an
        attempt, or reads questions or answers.

        Classic quizzes are listed by quiz ID; New Quizzes by assignment ID
        (Canvas exposes them only as assignments). Use get_quiz_details for one
        quiz and your attempts.

        Args:
            course_identifier: Course code or Canvas ID
        """
        # Resolved before any request: a course that does not resolve is
        # reported as such, so the hidden-Quizzes-page hint below only ever
        # explains a real 404 from the quiz list.
        course_id, course_error = await resolve_numeric_course_id(course_identifier)
        if course_id is None:
            return f"Error: {course_error}"

        classic = await fetch_all_paginated_results(
            f"/courses/{course_id}/quizzes", {"per_page": 100}
        )
        assignments = await fetch_all_paginated_results(
            f"/courses/{course_id}/assignments",
            {"include[]": ["submission"], "per_page": 100},
        )

        classic_failed = _is_error(classic) or not isinstance(classic, list)
        assignments_failed = _is_error(assignments) or not isinstance(assignments, list)

        if classic_failed and assignments_failed:
            classic_err = classic.get("error") if isinstance(classic, dict) else classic
            assignment_err = (
                assignments.get("error") if isinstance(assignments, dict) else assignments
            )
            return (
                "Error: could not list quizzes for this course.\n"
                f"- Classic quizzes: {_explain_error(classic_err, 'the quiz list', tab_hint=True)}\n"
                f"- New Quizzes (assignments): {_explain_error(assignment_err, 'the assignment list')}"
            )

        assignment_list: list[dict[str, Any]] = (
            [a for a in assignments if isinstance(a, dict)] if not assignments_failed else []
        )
        by_quiz_id = {
            str(a["quiz_id"]): a for a in assignment_list if _is_classic_quiz_assignment(a)
        }
        new_quizzes = sorted(
            (a for a in assignment_list if _is_new_quiz(a)), key=_due_sort_key
        )

        course_display = await get_course_code(course_id) or course_identifier
        lines = [f"Quizzes for {course_display}:", ""]

        if not classic_failed:
            quizzes = sorted((q for q in classic if isinstance(q, dict)), key=_due_sort_key)
            lines.append(f"Classic Quizzes ({len(quizzes)}):")
            if not quizzes:
                lines.append("  none visible to you")
            for quiz in quizzes:
                lines.extend(_classic_quiz_block(quiz, by_quiz_id.get(str(quiz.get("id")))))
        else:
            classic_err = classic.get("error") if isinstance(classic, dict) else classic
            lines.append(
                "Classic Quizzes: "
                + _explain_error(classic_err, "the quiz list", tab_hint=True)
            )
            # A hidden Quizzes page does not hide graded quizzes from the
            # assignment list, so the student still sees their deadlines.
            shells = sorted(by_quiz_id.values(), key=_due_sort_key)
            if shells:
                lines.append(
                    f"Graded Classic quizzes found in the assignment list ({len(shells)}); "
                    "practice quizzes and ungraded surveys cannot be listed this way:"
                )
                for shell in shells:
                    name = fence_untrusted_inline(shell.get("name") or "Untitled quiz", "quiz title")
                    lines.append(f"• {name}")
                    lines.append(f"  Quiz ID: {_plain(shell.get('quiz_id'))} | "
                        f"Assignment ID: {_plain(shell.get('id'))}")
                    lines.append(f"  {_date_line(shell)}")
                    lines.append(
                        "  Your submission: "
                        + _describe_assignment_submission(
                            shell.get("submission"), shell.get("points_possible")
                        )
                    )

        lines.append("")
        if not assignments_failed:
            lines.append(f"New Quizzes ({len(new_quizzes)}):")
            if not new_quizzes:
                lines.append("  none visible to you")
            for assignment in new_quizzes:
                lines.extend(_new_quiz_block(assignment))
            if new_quizzes:
                lines.append(
                    "  (Time limits and allowed attempts for New Quizzes are not "
                    "available to students through the Canvas API.)"
                )
        else:
            assignment_err = (
                assignments.get("error") if isinstance(assignments, dict) else assignments
            )
            lines.append(
                "New Quizzes: unknown. "
                + _explain_error(assignment_err, "the assignment list")
            )

        lines.append("")
        lines.append(
            "For your attempts on one quiz, use get_quiz_details with quiz_id "
            "(Classic) or assignment_id (New Quizzes)."
        )
        return "\n".join(lines)

    @mcp.tool(
        annotations=ToolAnnotations(read_only_hint=True), meta=FULL_CONTENT_TOOL_META
    )
    @validate_params
    async def get_quiz_details(
        course_identifier: str | int,
        quiz_id: str | int | None = None,
        assignment_id: str | int | None = None,
    ) -> str:
        """Get one quiz's settings and YOUR OWN latest attempt (used, remaining, kept score).

        Read-only. It never starts an attempt and never reads questions or
        answers. Pass exactly one of quiz_id (a Classic quiz, as listed by
        list_quizzes) or assignment_id (a New Quiz, or the assignment of a
        graded Classic quiz). For New Quizzes Canvas does not expose settings
        or attempt history to students, and the result says so. With grading
        rights in the course, attempts are not requested at all.

        Args:
            course_identifier: Course code or Canvas ID
            quiz_id: Canvas Classic quiz ID
            assignment_id: Canvas assignment ID (New Quizzes)
        """
        if quiz_id is not None and assignment_id is None:
            which, raw_id = "quiz_id", quiz_id
        elif assignment_id is not None and quiz_id is None:
            which, raw_id = "assignment_id", assignment_id
        else:
            return (
                "Error: pass exactly one of quiz_id (Classic quiz) or "
                "assignment_id (New Quiz). list_quizzes shows which applies."
            )
        # IDs are interpolated into request paths, so anything but plain digits
        # is refused before a request is built.
        checked_id = coerce_canvas_id(raw_id)
        if checked_id is None:
            return f"Error: {which} must be a numeric Canvas ID. Use list_quizzes to find it."

        course_id, course_error = await resolve_numeric_course_id(course_identifier)
        if course_id is None:
            return f"Error: {course_error}"
        course_display = await get_course_code(course_id) or course_identifier

        assignment: dict[str, Any] | None = None
        if assignment_id is not None:
            response = await make_canvas_request(
                "get",
                f"/courses/{course_id}/assignments/{checked_id}",
                params={"include[]": ["submission"]},
            )
            if _is_error(response) or not isinstance(response, dict):
                detail = response.get("error") if isinstance(response, dict) else response
                return "Error: " + _explain_error(detail, f"assignment {checked_id}")
            assignment = response

            if _is_new_quiz(assignment):
                lines = [f"New Quiz in {course_display}:"]
                lines.extend(_new_quiz_block(assignment))
                description = assignment.get("description")
                if description:
                    lines.append("Description:")
                    lines.append(fence_untrusted(description, "quiz description"))
                own_submission = assignment.get("submission")
                attempt = own_submission.get("attempt") if isinstance(own_submission, dict) else None
                if attempt:
                    lines.append(
                        f"Canvas submission attempt number: {_plain(attempt)} (as recorded "
                        "in the Canvas gradebook; it may not match the New Quizzes "
                        "attempt count)"
                    )
                link = _link(assignment.get("html_url"))
                if link:
                    lines.append(f"Open in Canvas: {link}")
                lines.append("")
                lines.append(_NEW_QUIZZES_NOTE)
                return "\n".join(lines)

            if not _is_classic_quiz_assignment(assignment):
                types = _describe_submission_types(assignment)
                return (
                    f"Error: assignment {checked_id} is not a quiz (submission "
                    f"types: {types}). Use get_my_submission for ordinary assignments."
                )
            linked = coerce_canvas_id(assignment["quiz_id"])
            if linked is None:
                return f"Error: assignment {checked_id} names an invalid quiz ID."
            checked_id = linked

        quiz = await make_canvas_request("get", f"/courses/{course_id}/quizzes/{checked_id}")
        if _is_error(quiz) or not isinstance(quiz, dict):
            detail = quiz.get("error") if isinstance(quiz, dict) else quiz
            message = "Error: " + _explain_error(detail, f"quiz {checked_id}")
            if quiz_id is not None and _http_status(detail) == 404:
                message += (
                    "\nIf this is a New Quiz, pass its assignment_id instead "
                    "(list_quizzes shows it)."
                )
            return message

        quiz_type = _quiz_type_label(quiz.get("quiz_type"))
        lines = [
            f"Classic quiz in {course_display}: "
            f"{fence_untrusted_inline(quiz.get('title') or 'Untitled quiz', 'quiz title')}",
            f"Quiz ID: {_plain(quiz.get('id'))} | Type: {quiz_type}"
            + (
                f" | Assignment ID: {_plain(quiz['assignment_id'])}"
                if quiz.get("assignment_id") else ""
            ),
            _date_line(quiz),
        ]
        time_limit = quiz.get("time_limit")
        settings = [
            f"Time limit: {_plain(time_limit)} min" if time_limit else "Time limit: none",
            f"Attempts allowed: {_attempts_allowed(quiz.get('allowed_attempts'))}",
        ]
        if quiz.get("points_possible") is not None:
            settings.append(f"Points: {_fmt_points(quiz['points_possible'])}")
        if quiz.get("question_count") is not None:
            settings.append(f"Questions: {_plain(quiz['question_count'])}")
        lines.append(" | ".join(settings))
        if quiz.get("allowed_attempts") not in (None, 1) and quiz.get("scoring_policy"):
            lines.append(
                "Scoring: "
                + _label(
                    _SCORING_POLICY_LABELS,
                    quiz["scoring_policy"],
                    fence_untrusted_inline(quiz["scoring_policy"], "scoring policy"),
                )
            )
        if quiz.get("published") is not None:
            lines.append(f"Published: {_yes_no(quiz.get('published'))}")
        if quiz.get("has_access_code"):
            lines.append("Requires an access code from your instructor.")
        if quiz.get("require_lockdown_browser"):
            lines.append("Requires LockDown Browser.")
        if quiz.get("one_time_results"):
            lines.append("Results can be viewed only once after each attempt.")
        if quiz.get("hide_results") == "always":
            lines.append("Results are hidden from students.")
        elif quiz.get("hide_results") == "until_after_last_attempt":
            lines.append("Results are shown only after your last attempt.")
        lock = _lock_line(quiz)
        if lock:
            lines.append(lock)
        if assignment is not None:
            lines.append(
                "Your gradebook submission: "
                + _describe_assignment_submission(
                    assignment.get("submission"), assignment.get("points_possible")
                )
            )
        description = quiz.get("description")
        if description:
            lines.append("Description:")
            lines.append(fence_untrusted(description, "quiz description"))
        quiz_link = _link(quiz.get("html_url"))
        if quiz_link:
            lines.append(f"Open in Canvas: {quiz_link}")

        lines.append("")
        lines.append("Your attempts:")

        # Keep this student-only tool conservative for staff and ambiguous
        # permissions. The singular route is caller-scoped; the plural route
        # is never used because it queues grading even for student callers.
        permissions = await make_canvas_request(
            "get",
            f"/courses/{course_id}/permissions",
            params={"permissions[]": list(_GRADING_PERMISSIONS + _STAFF_PERMISSIONS)},
        )
        grader = _grading_rights(permissions)
        if grader is None:
            detail = permissions.get("error") if isinstance(permissions, dict) else permissions
            lines.append(
                "Could not confirm your role in this course, so your attempts "
                f"were not requested. Details: {detail}"
            )
            return "\n".join(lines)
        if grader:
            lines.append(
                "You have grading rights in this course; this tool only shows "
                "a student's own attempts, so none were requested."
            )
            return "\n".join(lines)

        me = await make_canvas_request("get", "/users/self")
        if not isinstance(me, dict) or _is_error(me) or me.get("id") is None:
            detail = me.get("error") if isinstance(me, dict) else me
            lines.append(f"Could not identify you to read your attempts: {detail}")
            return "\n".join(lines)
        my_id = str(me["id"])

        # The caller's live record in any state ("Get the quiz submission").
        # It is the only route that returns a settings_only record, which is
        # where extra attempts granted before a first attempt are stored.
        current = await make_canvas_request(
            "get", f"/courses/{course_id}/quizzes/{checked_id}/submission"
        )
        if _is_error(current) or not isinstance(current, dict):
            detail = current.get("error") if isinstance(current, dict) else current
            lines.append(
                _explain_error(
                    detail, "your quiz attempts", unauthorized=_ATTEMPTS_UNAUTHORIZED
                )
            )
            return "\n".join(lines)
        current_records = _quiz_submission_records(current)
        if current_records is None:
            lines.append(_UNREADABLE_ATTEMPTS)
            return "\n".join(lines)
        live = next(
            (r for r in current_records if str(r.get("user_id")) == my_id),
            None,
        )
        if current_records and live is None:
            # A live record that cannot be tied to the caller is unknown,
            # even when the separate history route would return no records.
            lines.append(_UNREADABLE_ATTEMPTS)
            return "\n".join(lines)

        # The plural submissions GET queues grading even for a student's own
        # overdue attempt. Read only the singular live record; prior attempts
        # cannot be fetched safely through that route.
        own = [live] if live is not None else []
        lines.extend(_attempt_summary(own, quiz, live))
        if len(current_records) > len(own):
            lines.append("Canvas also returned quiz submission records belonging to other users; they are not shown.")
        lines.append(
            "Only your current/latest attempt is shown. Earlier attempt history "
            "is unavailable here: Canvas's history endpoint can automatically "
            "submit and grade overdue attempts, so this read-only tool does not call it."
        )
        return "\n".join(lines)
