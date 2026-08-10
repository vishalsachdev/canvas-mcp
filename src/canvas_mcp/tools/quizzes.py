"""Quiz-related MCP tools for Canvas API (Classic Quizzes).

These tools cover the student-facing quiz lifecycle:

    list_quizzes -> get_quiz_details -> start_quiz_attempt
        -> answer_quiz_questions -> submit_quiz_attempt

IMPORTANT — Classic Quizzes only
--------------------------------
The tools here target Canvas **Classic Quizzes** (the ``/api/v1/courses/:id/quizzes``
REST API). Canvas **New Quizzes** (the ``quiz_lti`` engine) does not expose a public
REST API for listing questions or recording answers; those quizzes surface as
assignments (see ``list_assignments``) and cannot be taken through these tools.

Taking a quiz is a multi-step workflow because Canvas requires you to *start an
attempt* first — that call returns a ``validation_token`` plus the questions with
their answer choices, which you then need to record answers and turn the quiz in.
"""

import json
from typing import Any

from fastmcp import FastMCP
from mcp.types import ToolAnnotations

from ..core.cache import get_course_code, get_course_id
from ..core.client import fetch_all_paginated_results, make_canvas_request
from ..core.dates import format_date
from ..core.untrusted_content import fence_untrusted, fence_untrusted_inline
from ..core.validation import validate_params
from ..core.write_confirmation import ConfirmationGuard
from .courses import strip_html_tags

_START_ATTEMPT_GUARD = ConfirmationGuard(ttl_seconds=300)
_SUBMIT_ATTEMPT_GUARD = ConfirmationGuard(ttl_seconds=300)

# Question types and the `answer` value they expect (summarised from the Canvas
# "Question Answer Formats" appendix). Surfaced to callers in tool docstrings and
# in the started-attempt output so an agent can build correctly-typed answers.
ANSWER_FORMAT_HELP = (
    "multiple_choice_question / true_false_question: answer id (int); "
    "multiple_answers_question: array of answer ids, e.g. [3, 6]; "
    "short_answer_question (fill-in-the-blank): string; "
    "essay_question: string (may contain HTML); "
    "numerical_question / calculated_question: number (or numeric string); "
    'fill_in_multiple_blanks_question: object {blank_name: "text"}; '
    "multiple_dropdowns_question: object {blank_name: answer_id}; "
    'matching_question: array of {"answer_id": id, "match_id": id}.'
)


def _truncate(text: str, limit: int) -> str:
    """Strip whitespace and append an ellipsis marker when over ``limit`` chars."""
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "… [truncated]"


def _format_submission_question(question: dict[str, Any]) -> str:
    """Render one in-progress quiz-submission question (with its answer choices)."""
    qid = question.get("id")
    qtype = question.get("question_type", "unknown")
    qname = question.get("question_name", "")
    qtext = _truncate(strip_html_tags(question.get("question_text", "") or ""), 600)

    lines = [f"  Question ID: {qid}", f"  Type: {qtype}"]
    if qname:
        lines.append("  Name: " + fence_untrusted_inline(qname, "quiz question name"))
    lines.append(
        "  Text:\n" + fence_untrusted(qtext or "(no text)", "quiz question text")
    )

    # Answer choices — present for choice-type questions (permissions-dependent).
    # Each may carry a blank_id for fill-in-multiple-blanks / multiple-dropdowns.
    answers = question.get("answers")
    if isinstance(answers, list) and answers:
        lines.append("  Answer choices:")
        for ans in answers:
            aid = ans.get("id")
            atext = _truncate(
                strip_html_tags(str(ans.get("text") or ans.get("html") or "")), 200
            )
            blank = ans.get("blank_id")
            blank_part = f" [blank: {blank}]" if blank else ""
            lines.append(
                f"    - id={aid}{blank_part}: "
                + fence_untrusted_inline(atext, "quiz answer choice")
            )

    # Matching questions also expose the set of match options to pair against.
    matches = question.get("matches")
    if isinstance(matches, list) and matches:
        lines.append("  Match options:")
        for match in matches:
            mid = match.get("match_id")
            mtext = _truncate(strip_html_tags(str(match.get("text") or "")), 200)
            lines.append(
                f"    - match_id={mid}: "
                + fence_untrusted_inline(mtext, "quiz match option")
            )

    current = question.get("answer")
    if current not in (None, "", [], {}):
        lines.append(f"  Current answer: {current}")

    return "\n".join(lines)


def reset_quiz_confirmations() -> None:
    """Reset quiz confirmation state for deterministic tests."""
    _START_ATTEMPT_GUARD.reset()
    _SUBMIT_ATTEMPT_GUARD.reset()


def _first_submission(response: Any) -> dict[str, Any] | None:
    """Extract the current user's first quiz submission from Canvas output."""
    if not isinstance(response, dict):
        return None
    submissions = response.get("quiz_submissions") or []
    return submissions[0] if submissions and isinstance(submissions[0], dict) else None


async def _fetch_quiz_state(
    course_id: str | int,
    quiz_id: str | int,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None, str | None]:
    """Load settings and current attempt state before issuing a confirmation."""
    quiz = await make_canvas_request("get", f"/courses/{course_id}/quizzes/{quiz_id}")
    if not isinstance(quiz, dict) or "error" in quiz:
        error = (
            quiz.get("error", "unexpected response") if isinstance(quiz, dict) else quiz
        )
        return None, None, f"Error fetching quiz details: {error}"

    response = await make_canvas_request(
        "get",
        f"/courses/{course_id}/quizzes/{quiz_id}/submission",
        skip_anonymization=True,
    )
    if isinstance(response, dict) and "error" in response:
        return None, None, f"Error fetching current quiz attempt: {response['error']}"
    return quiz, _first_submission(response), None


def _quiz_state_payload(quiz: dict[str, Any], submission: dict[str, Any] | None) -> str:
    """Serialize only state whose drift must invalidate a confirmation."""
    quiz_state = {
        key: quiz.get(key)
        for key in (
            "id",
            "allowed_attempts",
            "time_limit",
            "due_at",
            "unlock_at",
            "lock_at",
            "locked_for_user",
            "published",
        )
    }
    submission_state = (
        {
            key: submission.get(key)
            for key in ("id", "attempt", "workflow_state", "end_at")
        }
        if submission
        else None
    )
    return json.dumps(
        {"quiz": quiz_state, "submission": submission_state},
        sort_keys=True,
        default=str,
    )


def _question_state_payload(response: Any) -> str:
    """Serialize current answers so edits invalidate a submit confirmation."""
    questions = (
        response.get("quiz_submission_questions", [])
        if isinstance(response, dict)
        else response
    )
    if not isinstance(questions, list):
        questions = []
    state = [
        {
            "id": question.get("id"),
            "answer": question.get("answer"),
            "flagged": question.get("flagged", False),
        }
        for question in questions
        if isinstance(question, dict)
    ]
    return json.dumps(state, sort_keys=True, default=str)


def _burn_on_confirmation_error(
    guard: ConfirmationGuard,
    token: str,
    fingerprint: str,
) -> str | None:
    """Validate a token and burn genuine mismatches to prevent revert replay."""
    error = guard.check(token, fingerprint)
    if error:
        guard.reserve(token)
    return error


async def _fetch_submission_questions(quiz_submission_id: str | int) -> Any:
    """GET the questions for an in-progress quiz submission (the current user's)."""
    return await make_canvas_request(
        "get",
        f"/quiz_submissions/{quiz_submission_id}/questions",
        skip_anonymization=True,
    )


async def _render_started_attempt(submission: dict[str, Any], header: str) -> str:
    """Format a started/resumed attempt: the tokens to keep plus its questions."""
    sub_id = submission.get("id")
    attempt = submission.get("attempt")
    token = submission.get("validation_token", "")
    end_at = submission.get("end_at")
    if not isinstance(sub_id, (str, int)):
        return "Error loading quiz attempt: Canvas returned no quiz_submission_id."

    lines = [
        f"{header} (quiz {submission.get('quiz_id')}):",
        "",
        "⚠️  Save these — required by answer_quiz_questions and submit_quiz_attempt:",
        f"  quiz_submission_id: {sub_id}",
        f"  attempt: {attempt}",
        f"  validation_token: {token}",
        f"  workflow_state: {submission.get('workflow_state', 'untaken')}",
    ]
    if end_at:
        lines.append(f"  attempt due (end_at): {format_date(end_at)}")

    questions = await _fetch_submission_questions(sub_id)
    lines.append("")
    if isinstance(questions, dict) and "error" in questions:
        lines.append(f"(Could not load questions: {questions['error']})")
        return "\n".join(lines)

    qlist = (
        questions.get("quiz_submission_questions")
        if isinstance(questions, dict)
        else questions
    )
    if not qlist:
        lines.append("No questions were returned for this attempt.")
        return "\n".join(lines)

    lines.append(f"Questions ({len(qlist)}):")
    lines.append("")
    for question in qlist:
        lines.append(_format_submission_question(question))
        lines.append("")

    lines.append(f"Answer value formats — {ANSWER_FORMAT_HELP}")
    lines.append(
        "Next: call answer_quiz_questions with the IDs/tokens above, then "
        "submit_quiz_attempt to turn the quiz in."
    )
    return "\n".join(lines)


def _normalize_answers(
    answers_json: str,
) -> tuple[list[dict[str, Any]] | None, str | None]:
    """Parse the flexible ``answers`` input into Canvas's ``quiz_questions`` array.

    Accepts either form (as a JSON string):
      - an object mapping question id -> answer value:
            {"4": 5, "5": "Paris"}
      - an array of per-question objects:
            [{"id": 4, "answer": 5}, {"id": 5, "answer": "Paris", "flagged": true}]

    Returns ``(quiz_questions, None)`` on success, or ``(None, error_message)``.
    """
    try:
        parsed = json.loads(answers_json)
    except (json.JSONDecodeError, TypeError) as exc:
        return None, (
            f"Invalid answers JSON: {exc}. Provide a JSON object "
            '{"<question_id>": <answer>} or an array of {"id", "answer"}.'
        )

    quiz_questions: list[dict[str, Any]] = []

    if isinstance(parsed, dict):
        for qid, answer in parsed.items():
            quiz_questions.append({"id": str(qid), "answer": answer})
    elif isinstance(parsed, list):
        for entry in parsed:
            if not isinstance(entry, dict):
                return (
                    None,
                    "Each answers array item must be an object with 'id' and 'answer'.",
                )
            qid = entry.get("id", entry.get("question_id"))
            if qid is None:
                return (
                    None,
                    "Each answers array item must include an 'id' (question ID).",
                )
            if "answer" not in entry:
                return None, f"Answer for question {qid} is missing an 'answer' field."
            item: dict[str, Any] = {"id": str(qid), "answer": entry["answer"]}
            if "flagged" in entry:
                item["flagged"] = entry["flagged"]
            quiz_questions.append(item)
    else:
        return None, "answers must be a JSON object or array."

    if not quiz_questions:
        return None, "No answers provided."
    return quiz_questions, None


def register_shared_quiz_tools(mcp: FastMCP) -> None:
    """Register quiz tools available to all roles (read-only browse/inspect)."""

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
    @validate_params
    async def list_quizzes(
        course_identifier: str | int,
        search_term: str | None = None,
    ) -> str:
        """List Classic Quizzes available in a course.

        Args:
            course_identifier: Course code or Canvas ID
            search_term: Optional partial quiz title to filter by

        Note: Only Classic Quizzes appear here. "New Quizzes" show up as
        assignments (use list_assignments) and cannot be taken via these tools.
        """
        course_id = await get_course_id(course_identifier)

        params: dict[str, Any] = {"per_page": 100}
        if search_term:
            params["search_term"] = search_term

        quizzes = await fetch_all_paginated_results(
            f"/courses/{course_id}/quizzes", params
        )

        if isinstance(quizzes, dict) and "error" in quizzes:
            return f"Error fetching quizzes: {quizzes['error']}"

        if not quizzes:
            return f"No quizzes found for course {course_identifier}."

        course_display = await get_course_code(course_id) or course_identifier
        lines = [f"Quizzes for Course {course_display}:\n"]

        for quiz in quizzes:
            qid = quiz.get("id")
            title = fence_untrusted_inline(
                quiz.get("title", "Untitled quiz"), "quiz title"
            )
            qtype = quiz.get("quiz_type", "unknown")
            points = quiz.get("points_possible")
            qcount = quiz.get("question_count")
            due = format_date(quiz.get("due_at"))

            status = ["published" if quiz.get("published") else "unpublished"]
            if quiz.get("locked_for_user"):
                status.append("🔒 locked")

            lines.append(
                f"ID: {qid}\n"
                f"Title: {title}\n"
                f"Type: {qtype}\n"
                f"Questions: {qcount if qcount is not None else 'N/A'}\n"
                f"Points: {points if points is not None else 'N/A'}\n"
                f"Due: {due}\n"
                f"Status: {', '.join(status)}\n"
            )

        return "\n".join(lines)

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
    @validate_params
    async def get_quiz_details(
        course_identifier: str | int,
        quiz_id: str | int,
    ) -> str:
        """Get detailed settings for a single Classic Quiz.

        Args:
            course_identifier: Course code or Canvas ID
            quiz_id: Canvas quiz ID (from list_quizzes)
        """
        course_id = await get_course_id(course_identifier)

        quiz = await make_canvas_request(
            "get", f"/courses/{course_id}/quizzes/{quiz_id}"
        )

        if isinstance(quiz, dict) and "error" in quiz:
            return f"Error fetching quiz details: {quiz['error']}"

        description = _truncate(strip_html_tags(quiz.get("description") or ""), 1000)
        fenced_title = fence_untrusted_inline(quiz.get("title", "N/A"), "quiz title")

        allowed = quiz.get("allowed_attempts")
        if allowed == -1:
            allowed_display = "Unlimited"
        elif allowed is None:
            allowed_display = "N/A"
        else:
            allowed_display = str(allowed)

        time_limit = quiz.get("time_limit")
        time_display = f"{time_limit} minutes" if time_limit else "No time limit"

        qtypes = quiz.get("question_types") or []

        details = [
            f"Title: {fenced_title}",
            f"Quiz ID: {quiz.get('id', quiz_id)}",
            f"Type: {quiz.get('quiz_type', 'N/A')}",
            f"Points Possible: {quiz.get('points_possible', 'N/A')}",
            f"Question Count: {quiz.get('question_count', 'N/A')}",
            f"Question Types: {', '.join(qtypes) if qtypes else 'N/A'}",
            f"Allowed Attempts: {allowed_display}",
            f"Time Limit: {time_display}",
            f"Scoring Policy: {quiz.get('scoring_policy', 'N/A')}",
            f"One Question at a Time: {quiz.get('one_question_at_a_time', False)}",
            f"Can't Go Back: {quiz.get('cant_go_back', False)}",
            f"Shuffle Answers: {quiz.get('shuffle_answers', False)}",
            f"Due Date: {format_date(quiz.get('due_at'))}",
            f"Unlock At: {format_date(quiz.get('unlock_at'))}",
            f"Lock At: {format_date(quiz.get('lock_at'))}",
            f"Published: {quiz.get('published', False)}",
            f"Access Code Required: {bool(quiz.get('access_code') or quiz.get('has_access_code'))}",
            f"Locked For You: {quiz.get('locked_for_user', False)}",
        ]
        if quiz.get("locked_for_user") and quiz.get("lock_explanation"):
            details.append(
                "Lock Explanation:\n"
                + fence_untrusted(
                    strip_html_tags(quiz["lock_explanation"]),
                    "quiz lock explanation",
                )
            )
        details.append(
            "\nDescription:\n"
            + fence_untrusted(description or "N/A", "quiz description")
        )

        course_display = await get_course_code(course_id) or course_identifier
        return (
            f"Quiz Details for {fenced_title} in course {course_display}:\n\n"
            + "\n".join(details)
        )


def register_student_quiz_tools(mcp: FastMCP) -> None:
    """Register tools for taking a Classic Quiz (start, answer, submit).

    All three act on the *authenticated user's own* quiz attempts.
    """

    @mcp.tool(annotations=ToolAnnotations(destructiveHint=True, idempotentHint=False))
    @validate_params
    async def start_quiz_attempt(
        course_identifier: str | int,
        quiz_id: str | int,
        access_code: str | None = None,
        confirmation_token: str | None = None,
    ) -> str:
        """Preview, then start or resume a Classic Quiz attempt.

        The first call creates nothing. It returns the quiz timing, attempt
        state, and a short-lived confirmation token. Show that preview to the
        student, then call again with the token and identical arguments. The
        confirmed call creates a quiz submission (a "take" session) and returns the
        ``quiz_submission_id``, ``attempt`` number, and ``validation_token`` —
        you MUST pass all three to ``answer_quiz_questions`` and
        ``submit_quiz_attempt``. It also lists each question with its ID, type,
        and (for choice questions) the available answer choices and their IDs.

        Starting an attempt consumes one of the quiz's allowed attempts. It does
        NOT turn anything in — answers are recorded separately and the attempt is
        only submitted when you call ``submit_quiz_attempt``. If an attempt is
        already in progress, this resumes it instead of starting a new one.

        Args:
            course_identifier: Course code or Canvas ID
            quiz_id: Canvas quiz ID (from list_quizzes)
            access_code: Access code, if the quiz requires one
            confirmation_token: Token from the preview; omit to preview
        """
        course_id = await get_course_id(course_identifier)

        quiz, existing_submission, state_error = await _fetch_quiz_state(
            course_id, quiz_id
        )
        if state_error or quiz is None:
            return state_error or "Error fetching quiz state"

        fingerprint = _START_ATTEMPT_GUARD.fingerprint(
            str(course_id),
            str(quiz_id),
            access_code or "",
            _quiz_state_payload(quiz, existing_submission),
        )
        title = fence_untrusted_inline(quiz.get("title", "N/A"), "quiz title")
        resumable_states = {"untaken", "pending", "in_progress"}
        is_resumable = bool(
            existing_submission
            and existing_submission.get("workflow_state") in resumable_states
        )
        action = (
            "Resume the existing attempt" if is_resumable else "Start a new attempt"
        )
        current_attempt = (
            existing_submission.get("attempt") if existing_submission else 0
        )
        workflow = (
            existing_submission.get("workflow_state")
            if existing_submission
            else "not started"
        )
        allowed_attempts = quiz.get("allowed_attempts")
        allowed_display = "Unlimited" if allowed_attempts == -1 else allowed_attempts

        if not confirmation_token:
            token = _START_ATTEMPT_GUARD.issue(fingerprint)
            return (
                "Quiz attempt preview — nothing started:\n\n"
                f"Quiz: {title}\n"
                f"Action: {action}\n"
                f"Current workflow state: {workflow}\n"
                f"Current attempt number: {current_attempt}\n"
                f"Allowed attempts: {allowed_display if allowed_display is not None else 'N/A'}\n"
                f"Time limit: {quiz.get('time_limit') or 'No time limit'}"
                f"{' minutes' if quiz.get('time_limit') else ''}\n"
                f"Due: {format_date(quiz.get('due_at'))}\n"
                f"Locks: {format_date(quiz.get('lock_at'))}\n"
                f"Access code supplied: {access_code is not None}\n\n"
                f"confirmation_token: {token}\n\n"
                "Show this preview to the student. To proceed, call "
                "start_quiz_attempt again with this confirmation_token and "
                "identical arguments. The token is single-use and expires "
                "in five minutes."
            )

        token_error = _burn_on_confirmation_error(
            _START_ATTEMPT_GUARD, confirmation_token, fingerprint
        )
        if token_error:
            return f"{token_error} Nothing was started."
        if not _START_ATTEMPT_GUARD.reserve(confirmation_token):
            return (
                "❌ That confirmation was already used. Nothing was started. "
                "Run the preview again."
            )

        data: dict[str, Any] = {}
        if access_code is not None:
            data["access_code"] = access_code

        result = await make_canvas_request(
            "post",
            f"/courses/{course_id}/quizzes/{quiz_id}/submissions",
            data=data,
            skip_anonymization=True,
        )

        if isinstance(result, dict) and "error" in result:
            error = str(result["error"])
            # 409 Conflict: a submission already exists for this user/quiz. Resume
            # the in-progress attempt (its validation_token is returned for the
            # current user) instead of failing.
            if "409" in error or "Conflict" in error:
                existing = await make_canvas_request(
                    "get",
                    f"/courses/{course_id}/quizzes/{quiz_id}/submission",
                    skip_anonymization=True,
                )
                if isinstance(existing, dict) and "error" not in existing:
                    subs = existing.get("quiz_submissions") or []
                    if subs and subs[0].get("validation_token"):
                        return await _render_started_attempt(
                            subs[0], header="Resumed in-progress quiz attempt"
                        )
            return f"Error starting quiz attempt: {error}"

        submissions = (
            result.get("quiz_submissions") if isinstance(result, dict) else None
        )
        if not submissions:
            return f"Error starting quiz attempt: unexpected response: {result}"

        return await _render_started_attempt(
            submissions[0], header="Started quiz attempt"
        )

    @mcp.tool(annotations=ToolAnnotations(destructiveHint=True, idempotentHint=True))
    @validate_params
    async def answer_quiz_questions(
        quiz_submission_id: str | int,
        attempt: int,
        validation_token: str,
        answers: str,
        access_code: str | None = None,
    ) -> str:
        """Record answers for an in-progress quiz attempt (does NOT submit it).

        Answers are saved against the open attempt and may be updated by calling
        this again. Nothing is turned in until you call ``submit_quiz_attempt``.

        Args:
            quiz_submission_id: From start_quiz_attempt
            attempt: The attempt number from start_quiz_attempt (must be the latest)
            validation_token: The token from start_quiz_attempt
            answers: A JSON string — either an object mapping question id to
                answer value, e.g. ``{"4": 5, "5": "Paris"}``, or an array of
                ``{"id": <question_id>, "answer": <value>}`` objects. The answer
                VALUE format depends on the question type:
                multiple_choice_question / true_false_question -> answer id (int);
                multiple_answers_question -> array of answer ids [3, 6];
                short_answer_question -> string; essay_question -> string;
                numerical_question / calculated_question -> number;
                fill_in_multiple_blanks_question -> {"blank_name": "text"};
                multiple_dropdowns_question -> {"blank_name": answer_id};
                matching_question -> [{"answer_id": id, "match_id": id}].
            access_code: Access code, if the quiz requires one
        """
        quiz_questions, error = _normalize_answers(answers)
        if error:
            return f"Error: {error}"

        body: dict[str, Any] = {
            "attempt": attempt,
            "validation_token": validation_token,
            "quiz_questions": quiz_questions,
        }
        if access_code is not None:
            body["access_code"] = access_code

        result = await make_canvas_request(
            "post",
            f"/quiz_submissions/{quiz_submission_id}/questions",
            data=body,
            skip_anonymization=True,
        )

        if isinstance(result, dict) and "error" in result:
            return f"Error recording answers: {result['error']}"

        qlist = (
            result.get("quiz_submission_questions")
            if isinstance(result, dict)
            else result
        )
        if not qlist:
            return (
                "Answers sent, but Canvas returned no confirmation questions. "
                "Re-fetch the attempt to verify they were recorded."
            )

        lines = [
            f"Recorded answers for {len(qlist)} question(s) (attempt {attempt}):",
            "",
        ]
        for question in qlist:
            qid = question.get("id")
            flag = " [flagged]" if question.get("flagged") else ""
            lines.append(f"  Q{qid}{flag}: answer = {question.get('answer')}")
        lines.append("")
        lines.append("Not yet submitted. Call submit_quiz_attempt to turn the quiz in.")
        return "\n".join(lines)

    @mcp.tool(annotations=ToolAnnotations(destructiveHint=True, idempotentHint=False))
    @validate_params
    async def submit_quiz_attempt(
        course_identifier: str | int,
        quiz_id: str | int,
        quiz_submission_id: str | int,
        attempt: int,
        validation_token: str,
        access_code: str | None = None,
        confirmation_token: str | None = None,
    ) -> str:
        """Preview, then irreversibly submit an in-progress quiz attempt.

        The first call fetches and displays the current answers but submits
        nothing. Show the preview to the student, then call again with the
        returned confirmation token and identical arguments. The token is
        invalidated if the attempt or any saved answer changes.

        Args:
            course_identifier: Course code or Canvas ID
            quiz_id: Canvas quiz ID
            quiz_submission_id: From start_quiz_attempt
            attempt: The attempt number from start_quiz_attempt (must be the latest)
            validation_token: The token from start_quiz_attempt
            access_code: Access code, if the quiz requires one
            confirmation_token: Token from the preview; omit to preview
        """
        course_id = await get_course_id(course_identifier)

        quiz, existing_submission, state_error = await _fetch_quiz_state(
            course_id, quiz_id
        )
        if state_error or quiz is None:
            return state_error or "Error fetching quiz state"
        if existing_submission is None:
            return "Error: Canvas returned no current quiz attempt. Nothing submitted."
        if str(existing_submission.get("id")) != str(quiz_submission_id):
            return "Error: quiz_submission_id does not match the current attempt. Nothing submitted."
        if str(existing_submission.get("attempt") or 0) != str(attempt):
            return "Error: attempt does not match the current Canvas attempt. Nothing submitted."

        questions = await _fetch_submission_questions(quiz_submission_id)
        if isinstance(questions, dict) and "error" in questions:
            return f"Error fetching current quiz answers: {questions['error']}"

        fingerprint = _SUBMIT_ATTEMPT_GUARD.fingerprint(
            str(course_id),
            str(quiz_id),
            str(quiz_submission_id),
            str(attempt),
            validation_token,
            access_code or "",
            _quiz_state_payload(quiz, existing_submission),
            _question_state_payload(questions),
        )

        if not confirmation_token:
            qlist = (
                questions.get("quiz_submission_questions", [])
                if isinstance(questions, dict)
                else questions
            )
            rendered_questions = "\n\n".join(
                _format_submission_question(question)
                for question in qlist or []
                if isinstance(question, dict)
            )
            title = fence_untrusted_inline(quiz.get("title", "N/A"), "quiz title")
            token = _SUBMIT_ATTEMPT_GUARD.issue(fingerprint)
            return (
                "Quiz submission preview — nothing submitted:\n\n"
                f"Quiz: {title}\n"
                f"Attempt: {attempt}\n"
                f"Workflow state: {existing_submission.get('workflow_state', 'unknown')}\n"
                f"Questions and saved answers:\n{rendered_questions or '(none returned)'}\n\n"
                f"confirmation_token: {token}\n\n"
                "Show this preview to the student. To irreversibly turn in "
                "the attempt, call submit_quiz_attempt again with this "
                "confirmation_token and identical arguments. The token is "
                "single-use and expires in five minutes."
            )

        token_error = _burn_on_confirmation_error(
            _SUBMIT_ATTEMPT_GUARD, confirmation_token, fingerprint
        )
        if token_error:
            return f"{token_error} Nothing was submitted."
        if not _SUBMIT_ATTEMPT_GUARD.reserve(confirmation_token):
            return (
                "❌ That confirmation was already used. Nothing was submitted. "
                "Run the preview again."
            )

        body: dict[str, Any] = {
            "attempt": attempt,
            "validation_token": validation_token,
        }
        if access_code is not None:
            body["access_code"] = access_code

        result = await make_canvas_request(
            "post",
            f"/courses/{course_id}/quizzes/{quiz_id}/submissions/{quiz_submission_id}/complete",
            data=body,
            skip_anonymization=True,
        )

        if isinstance(result, dict) and "error" in result:
            return f"Error submitting quiz attempt: {result['error']}"

        submissions = (
            result.get("quiz_submissions") if isinstance(result, dict) else None
        )
        if not submissions:
            return (
                f"Quiz submitted, but Canvas returned an unexpected response: {result}"
            )

        sub = submissions[0]
        state = sub.get("workflow_state", "complete")
        lines = [
            f"✅ Quiz submitted (attempt {sub.get('attempt', attempt)}).",
            f"  Workflow state: {state}",
        ]
        if sub.get("score") is not None:
            lines.append(f"  Score: {sub.get('score')}")
        if sub.get("kept_score") is not None:
            lines.append(f"  Kept score: {sub.get('kept_score')}")
        if state == "pending_review":
            lines.append(
                "  Note: some questions need manual grading; the final score "
                "will appear once the instructor reviews them."
            )
        return "\n".join(lines)
