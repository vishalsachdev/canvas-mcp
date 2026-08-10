"""
Quiz Tools Unit Tests

Tests for the Canvas Classic Quiz tools:
- list_quizzes
- get_quiz_details
- start_quiz_attempt
- answer_quiz_questions
- submit_quiz_attempt

These tests mock the Canvas API so no real credentials/network are required.
"""

from unittest.mock import patch

import pytest

from canvas_mcp.core.credentials import (
    RequestCredentials,
    clear_request_credentials,
    set_request_credentials,
)
from canvas_mcp.tools.quizzes import (
    _normalize_answers,
    reset_quiz_confirmations,
)

# --- Mock data -------------------------------------------------------------

MOCK_QUIZZES = [
    {
        "id": 101,
        "title": "Hamlet Act 3 Quiz",
        "quiz_type": "assignment",
        "points_possible": 20,
        "question_count": 12,
        "due_at": "2026-02-01T23:59:00Z",
        "published": True,
        "locked_for_user": False,
    },
    {
        "id": 102,
        "title": "Practice Survey",
        "quiz_type": "survey",
        "points_possible": 0,
        "question_count": 5,
        "due_at": None,
        "published": False,
        "locked_for_user": True,
    },
]

MOCK_QUIZ_DETAIL = {
    "id": 101,
    "title": "Hamlet Act 3 Quiz",
    "quiz_type": "assignment",
    "description": "<p>This is a quiz on <b>Act 3</b> of Hamlet.</p>",
    "points_possible": 20,
    "question_count": 12,
    "question_types": ["multiple_choice_question", "essay_question"],
    "allowed_attempts": 3,
    "time_limit": 30,
    "scoring_policy": "keep_highest",
    "one_question_at_a_time": False,
    "cant_go_back": False,
    "shuffle_answers": True,
    "due_at": "2026-02-01T23:59:00Z",
    "unlock_at": None,
    "lock_at": None,
    "published": True,
    "access_code": None,
    "locked_for_user": False,
}

MOCK_SUBMISSION = {
    "id": 555,
    "quiz_id": 101,
    "user_id": 7,
    "attempt": 1,
    "validation_token": "VTOKEN123",
    "workflow_state": "untaken",
    "end_at": "2026-02-01T22:30:00Z",
}

MOCK_SUBMISSION_QUESTIONS = {
    "quiz_submission_questions": [
        {
            "id": 1,
            "question_type": "multiple_choice_question",
            "question_name": "Q1",
            "question_text": "<p>Pick the best answer.</p>",
            "answers": [{"id": 3, "text": "Option A"}, {"id": 6, "text": "Option B"}],
            "answer": None,
            "flagged": False,
        },
        {
            "id": 2,
            "question_type": "essay_question",
            "question_name": "Q2",
            "question_text": "Explain your reasoning.",
            "answers": None,
            "answer": None,
            "flagged": False,
        },
    ]
}


@pytest.fixture
def mock_quiz_api():
    """Mock the Canvas API helpers used by the quizzes module."""
    with (
        patch("canvas_mcp.tools.quizzes.get_course_id") as mock_get_id,
        patch("canvas_mcp.tools.quizzes.get_course_code") as mock_get_code,
        patch("canvas_mcp.tools.quizzes.fetch_all_paginated_results") as mock_fetch,
        patch("canvas_mcp.tools.quizzes.make_canvas_request") as mock_request,
    ):

        mock_get_id.return_value = "60366"
        mock_get_code.return_value = "badm_350_120251"

        yield {
            "get_course_id": mock_get_id,
            "get_course_code": mock_get_code,
            "fetch_all_paginated_results": mock_fetch,
            "make_canvas_request": mock_request,
        }


@pytest.fixture(autouse=True)
def reset_confirmation_state():
    reset_quiz_confirmations()
    yield
    reset_quiz_confirmations()


def _confirmation_token(preview: str) -> str:
    return preview.split("confirmation_token: ", 1)[1].splitlines()[0]


def _submission_response(submission=MOCK_SUBMISSION):
    return {"quiz_submissions": [submission] if submission else []}


def get_tool_function(tool_name: str):
    """Capture a registered quiz tool function by name."""
    from fastmcp import FastMCP

    from canvas_mcp.tools.quizzes import (
        register_shared_quiz_tools,
        register_student_quiz_tools,
    )

    mcp = FastMCP("test")
    captured: dict = {}

    original_tool = mcp.tool

    def capturing_tool(*args, **kwargs):
        decorator = original_tool(*args, **kwargs)

        def wrapper(fn):
            captured[fn.__name__] = fn
            return decorator(fn)

        return wrapper

    mcp.tool = capturing_tool
    register_shared_quiz_tools(mcp)
    register_student_quiz_tools(mcp)

    return captured.get(tool_name)


# --- list_quizzes ----------------------------------------------------------


class TestListQuizzes:
    @pytest.mark.asyncio
    async def test_list_quizzes_basic(self, mock_quiz_api):
        mock_quiz_api["fetch_all_paginated_results"].return_value = MOCK_QUIZZES

        list_quizzes = get_tool_function("list_quizzes")
        assert list_quizzes is not None

        result = await list_quizzes("badm_350_120251")

        mock_quiz_api["get_course_id"].assert_called_once_with("badm_350_120251")
        assert "Hamlet Act 3 Quiz" in result
        assert "quiz title" in result
        assert "UNTRUSTED CANVAS CONTENT" in result
        assert "Practice Survey" in result
        assert "101" in result
        assert "Points: 20" in result
        # Locked survey should be flagged
        assert "🔒" in result
        assert "unpublished" in result

    @pytest.mark.asyncio
    async def test_list_quizzes_empty(self, mock_quiz_api):
        mock_quiz_api["fetch_all_paginated_results"].return_value = []

        list_quizzes = get_tool_function("list_quizzes")
        result = await list_quizzes("empty_course")

        assert "No quizzes found" in result

    @pytest.mark.asyncio
    async def test_list_quizzes_error(self, mock_quiz_api):
        mock_quiz_api["fetch_all_paginated_results"].return_value = {
            "error": "Course not found"
        }

        list_quizzes = get_tool_function("list_quizzes")
        result = await list_quizzes("invalid_course")

        assert "Error" in result
        assert "Course not found" in result

    @pytest.mark.asyncio
    async def test_list_quizzes_search_term(self, mock_quiz_api):
        mock_quiz_api["fetch_all_paginated_results"].return_value = [MOCK_QUIZZES[0]]

        list_quizzes = get_tool_function("list_quizzes")
        await list_quizzes("60366", search_term="Hamlet")

        # search_term should be forwarded as a query param
        call_args = mock_quiz_api["fetch_all_paginated_results"].call_args
        params = call_args[0][1]
        assert params.get("search_term") == "Hamlet"


# --- get_quiz_details ------------------------------------------------------


class TestGetQuizDetails:
    @pytest.mark.asyncio
    async def test_get_quiz_details_success(self, mock_quiz_api):
        mock_quiz_api["make_canvas_request"].return_value = MOCK_QUIZ_DETAIL

        get_quiz_details = get_tool_function("get_quiz_details")
        result = await get_quiz_details("badm_350_120251", 101)

        assert "Hamlet Act 3 Quiz" in result
        assert "Allowed Attempts: 3" in result
        assert "Time Limit: 30 minutes" in result
        assert "keep_highest" in result
        # HTML stripped from description
        assert "Act 3" in result
        assert "<b>" not in result
        assert "quiz title" in result
        assert "quiz description" in result

    @pytest.mark.asyncio
    async def test_get_quiz_details_unlimited_attempts(self, mock_quiz_api):
        quiz = dict(MOCK_QUIZ_DETAIL, allowed_attempts=-1, time_limit=None)
        mock_quiz_api["make_canvas_request"].return_value = quiz

        get_quiz_details = get_tool_function("get_quiz_details")
        result = await get_quiz_details("60366", 101)

        assert "Allowed Attempts: Unlimited" in result
        assert "Time Limit: No time limit" in result

    @pytest.mark.asyncio
    async def test_get_quiz_details_error(self, mock_quiz_api):
        mock_quiz_api["make_canvas_request"].return_value = {"error": "Quiz not found"}

        get_quiz_details = get_tool_function("get_quiz_details")
        result = await get_quiz_details("60366", 999)

        assert "Error" in result
        assert "Quiz not found" in result


# --- start_quiz_attempt ----------------------------------------------------


class TestStartQuizAttempt:
    @pytest.mark.asyncio
    async def test_preview_starts_nothing(self, mock_quiz_api):
        mock_quiz_api["make_canvas_request"].side_effect = [
            MOCK_QUIZ_DETAIL,
            _submission_response(None),
        ]

        start_quiz_attempt = get_tool_function("start_quiz_attempt")
        preview = await start_quiz_attempt("60366", 101)

        assert "nothing started" in preview
        assert "confirmation_token:" in preview
        assert "UNTRUSTED CANVAS CONTENT" in preview
        assert all(
            call.args[0] == "get"
            for call in mock_quiz_api["make_canvas_request"].call_args_list
        )

    @pytest.mark.asyncio
    async def test_confirmed_start_attempt_success(self, mock_quiz_api):
        mock_quiz_api["make_canvas_request"].side_effect = [
            MOCK_QUIZ_DETAIL,
            _submission_response(None),
            MOCK_QUIZ_DETAIL,
            _submission_response(None),
            {"quiz_submissions": [MOCK_SUBMISSION]},
            MOCK_SUBMISSION_QUESTIONS,
        ]

        start_quiz_attempt = get_tool_function("start_quiz_attempt")
        preview = await start_quiz_attempt("60366", 101)
        result = await start_quiz_attempt(
            "60366", 101, confirmation_token=_confirmation_token(preview)
        )

        assert "Started quiz attempt" in result
        assert "VTOKEN123" in result
        assert "quiz_submission_id: 555" in result
        assert "attempt: 1" in result
        # Questions and their answer choices surfaced
        assert "Pick the best answer." in result
        assert "id=3" in result
        assert "multiple_choice_question" in result
        # Answer-format guidance present so the agent can build answers
        assert "matching_question" in result
        assert "UNTRUSTED CANVAS CONTENT" in result
        assert "quiz question name" in result
        assert "quiz question text" in result
        assert "quiz answer choice" in result

    @pytest.mark.asyncio
    async def test_start_attempt_resumes_on_conflict(self, mock_quiz_api):
        mock_quiz_api["make_canvas_request"].side_effect = [
            MOCK_QUIZ_DETAIL,
            _submission_response(MOCK_SUBMISSION),
            MOCK_QUIZ_DETAIL,
            _submission_response(MOCK_SUBMISSION),
            {"error": "HTTP error: 409, Details: {'message': 'already exists'}"},
            {"quiz_submissions": [MOCK_SUBMISSION]},
            MOCK_SUBMISSION_QUESTIONS,
        ]

        start_quiz_attempt = get_tool_function("start_quiz_attempt")
        preview = await start_quiz_attempt("60366", 101)
        result = await start_quiz_attempt(
            "60366", 101, confirmation_token=_confirmation_token(preview)
        )

        assert "Resumed in-progress quiz attempt" in result
        assert "VTOKEN123" in result
        assert "Pick the best answer." in result

        # The resume path must hit the singular /submission endpoint, NOT re-POST
        # to the plural /submissions create endpoint.
        calls = mock_quiz_api["make_canvas_request"].call_args_list
        assert calls[4].args[1].endswith("/submissions")
        assert calls[5].args[1].endswith("/submission")

    @pytest.mark.asyncio
    async def test_start_confirmation_rejected_after_state_change(self, mock_quiz_api):
        mock_quiz_api["make_canvas_request"].side_effect = [
            MOCK_QUIZ_DETAIL,
            _submission_response(None),
            MOCK_QUIZ_DETAIL,
            _submission_response(MOCK_SUBMISSION),
        ]

        start_quiz_attempt = get_tool_function("start_quiz_attempt")
        preview = await start_quiz_attempt("60366", 101)
        result = await start_quiz_attempt(
            "60366", 101, confirmation_token=_confirmation_token(preview)
        )

        assert "does not match" in result
        assert "Nothing was started" in result
        assert not any(
            call.args[0] == "post"
            for call in mock_quiz_api["make_canvas_request"].call_args_list
        )

    @pytest.mark.asyncio
    async def test_start_attempt_passes_access_code(self, mock_quiz_api):
        mock_quiz_api["make_canvas_request"].side_effect = [
            MOCK_QUIZ_DETAIL,
            _submission_response(None),
            MOCK_QUIZ_DETAIL,
            _submission_response(None),
            {"quiz_submissions": [MOCK_SUBMISSION]},
            MOCK_SUBMISSION_QUESTIONS,
        ]

        start_quiz_attempt = get_tool_function("start_quiz_attempt")
        preview = await start_quiz_attempt("60366", 101, access_code="secret")
        await start_quiz_attempt(
            "60366",
            101,
            access_code="secret",
            confirmation_token=_confirmation_token(preview),
        )

        post_call = mock_quiz_api["make_canvas_request"].call_args_list[4]
        assert post_call.kwargs["data"] == {"access_code": "secret"}
        assert "secret" not in preview

    @pytest.mark.asyncio
    async def test_start_confirmation_is_single_use(self, mock_quiz_api):
        mock_quiz_api["make_canvas_request"].side_effect = [
            MOCK_QUIZ_DETAIL,
            _submission_response(None),
            MOCK_QUIZ_DETAIL,
            _submission_response(None),
            {"quiz_submissions": [MOCK_SUBMISSION]},
            MOCK_SUBMISSION_QUESTIONS,
            MOCK_QUIZ_DETAIL,
            _submission_response(None),
        ]

        start_quiz_attempt = get_tool_function("start_quiz_attempt")
        preview = await start_quiz_attempt("60366", 101)
        token = _confirmation_token(preview)
        first = await start_quiz_attempt("60366", 101, confirmation_token=token)
        replay = await start_quiz_attempt("60366", 101, confirmation_token=token)

        assert "Started quiz attempt" in first
        assert "already used" in replay
        post_calls = [
            call
            for call in mock_quiz_api["make_canvas_request"].call_args_list
            if call.args[0] == "post"
        ]
        assert len(post_calls) == 1


# --- answer_quiz_questions -------------------------------------------------


class TestAnswerQuizQuestions:
    @pytest.mark.asyncio
    async def test_answer_dict_form(self, mock_quiz_api):
        mock_quiz_api["make_canvas_request"].return_value = {
            "quiz_submission_questions": [
                {"id": 1, "answer": 3, "flagged": False},
                {"id": 2, "answer": "My essay", "flagged": False},
            ]
        }

        answer_quiz_questions = get_tool_function("answer_quiz_questions")
        result = await answer_quiz_questions(
            555, 1, "VTOKEN123", '{"1": 3, "2": "My essay"}'
        )

        assert "Recorded answers for 2" in result
        assert "Not yet submitted" in result

        # Body must carry attempt, validation_token, and normalized quiz_questions
        body = mock_quiz_api["make_canvas_request"].call_args.kwargs["data"]
        assert body["attempt"] == 1
        assert body["validation_token"] == "VTOKEN123"
        assert {"id": "1", "answer": 3} in body["quiz_questions"]
        assert {"id": "2", "answer": "My essay"} in body["quiz_questions"]

    @pytest.mark.asyncio
    async def test_answer_array_form(self, mock_quiz_api):
        mock_quiz_api["make_canvas_request"].return_value = {
            "quiz_submission_questions": [{"id": 1, "answer": [3, 6]}]
        }

        answer_quiz_questions = get_tool_function("answer_quiz_questions")
        result = await answer_quiz_questions(
            555, 1, "VTOKEN123", '[{"id": 1, "answer": [3, 6]}]'
        )

        assert "Recorded answers for 1" in result
        body = mock_quiz_api["make_canvas_request"].call_args.kwargs["data"]
        assert body["quiz_questions"] == [{"id": "1", "answer": [3, 6]}]

    @pytest.mark.asyncio
    async def test_answer_invalid_json(self, mock_quiz_api):
        answer_quiz_questions = get_tool_function("answer_quiz_questions")
        result = await answer_quiz_questions(555, 1, "VTOKEN123", "not json at all")

        assert "Error" in result
        assert "Invalid answers JSON" in result
        # No API call should have been made for malformed input
        mock_quiz_api["make_canvas_request"].assert_not_called()

    @pytest.mark.asyncio
    async def test_answer_api_error(self, mock_quiz_api):
        mock_quiz_api["make_canvas_request"].return_value = {
            "error": "HTTP error: 401, Details: invalid token"
        }

        answer_quiz_questions = get_tool_function("answer_quiz_questions")
        result = await answer_quiz_questions(555, 1, "BAD", '{"1": 3}')

        assert "Error recording answers" in result
        assert "401" in result

    @pytest.mark.asyncio
    async def test_answer_no_confirmation_questions(self, mock_quiz_api):
        # 2xx body lacking quiz_submission_questions -> graceful fallback message
        mock_quiz_api["make_canvas_request"].return_value = {}

        answer_quiz_questions = get_tool_function("answer_quiz_questions")
        result = await answer_quiz_questions(555, 1, "VTOKEN123", '{"1": 3}')

        assert "no confirmation questions" in result


# --- submit_quiz_attempt ---------------------------------------------------


class TestSubmitQuizAttempt:
    @pytest.mark.asyncio
    async def test_preview_submits_nothing(self, mock_quiz_api):
        mock_quiz_api["make_canvas_request"].side_effect = [
            MOCK_QUIZ_DETAIL,
            _submission_response(),
            MOCK_SUBMISSION_QUESTIONS,
        ]

        submit_quiz_attempt = get_tool_function("submit_quiz_attempt")
        preview = await submit_quiz_attempt("60366", 101, 555, 1, "VTOKEN123")

        assert "nothing submitted" in preview
        assert "confirmation_token:" in preview
        assert "UNTRUSTED CANVAS CONTENT" in preview
        assert not any(
            call.args[0] == "post"
            for call in mock_quiz_api["make_canvas_request"].call_args_list
        )

    @pytest.mark.asyncio
    async def test_confirmed_submit_success(self, mock_quiz_api):
        completed = {
            "quiz_submissions": [
                {
                    "attempt": 1,
                    "workflow_state": "complete",
                    "score": 18,
                    "kept_score": 18,
                }
            ]
        }
        mock_quiz_api["make_canvas_request"].side_effect = [
            MOCK_QUIZ_DETAIL,
            _submission_response(),
            MOCK_SUBMISSION_QUESTIONS,
            MOCK_QUIZ_DETAIL,
            _submission_response(),
            MOCK_SUBMISSION_QUESTIONS,
            completed,
        ]

        submit_quiz_attempt = get_tool_function("submit_quiz_attempt")
        preview = await submit_quiz_attempt("60366", 101, 555, 1, "VTOKEN123")
        result = await submit_quiz_attempt(
            "60366",
            101,
            555,
            1,
            "VTOKEN123",
            confirmation_token=_confirmation_token(preview),
        )

        assert "Quiz submitted" in result
        assert "Score: 18" in result
        call = mock_quiz_api["make_canvas_request"].call_args_list[6]
        assert call.args[1].endswith("/submissions/555/complete")
        body = call.kwargs["data"]
        assert body["attempt"] == 1
        assert body["validation_token"] == "VTOKEN123"

    @pytest.mark.asyncio
    async def test_answer_change_invalidates_confirmation(self, mock_quiz_api):
        changed_questions = {
            "quiz_submission_questions": [
                {
                    **MOCK_SUBMISSION_QUESTIONS["quiz_submission_questions"][0],
                    "answer": 6,
                },
                MOCK_SUBMISSION_QUESTIONS["quiz_submission_questions"][1],
            ]
        }
        mock_quiz_api["make_canvas_request"].side_effect = [
            MOCK_QUIZ_DETAIL,
            _submission_response(),
            MOCK_SUBMISSION_QUESTIONS,
            MOCK_QUIZ_DETAIL,
            _submission_response(),
            changed_questions,
        ]

        submit_quiz_attempt = get_tool_function("submit_quiz_attempt")
        preview = await submit_quiz_attempt("60366", 101, 555, 1, "VTOKEN123")
        result = await submit_quiz_attempt(
            "60366",
            101,
            555,
            1,
            "VTOKEN123",
            confirmation_token=_confirmation_token(preview),
        )

        assert "does not match" in result
        assert "Nothing was submitted" in result
        assert not any(
            call.args[0] == "post"
            for call in mock_quiz_api["make_canvas_request"].call_args_list
        )

    @pytest.mark.asyncio
    async def test_submit_confirmation_is_single_use(self, mock_quiz_api):
        completed = {"quiz_submissions": [{"attempt": 1, "workflow_state": "complete"}]}
        mock_quiz_api["make_canvas_request"].side_effect = [
            MOCK_QUIZ_DETAIL,
            _submission_response(),
            MOCK_SUBMISSION_QUESTIONS,
            MOCK_QUIZ_DETAIL,
            _submission_response(),
            MOCK_SUBMISSION_QUESTIONS,
            completed,
            MOCK_QUIZ_DETAIL,
            _submission_response(),
            MOCK_SUBMISSION_QUESTIONS,
        ]

        submit_quiz_attempt = get_tool_function("submit_quiz_attempt")
        preview = await submit_quiz_attempt("60366", 101, 555, 1, "VTOKEN123")
        token = _confirmation_token(preview)
        first = await submit_quiz_attempt(
            "60366", 101, 555, 1, "VTOKEN123", confirmation_token=token
        )
        replay = await submit_quiz_attempt(
            "60366", 101, 555, 1, "VTOKEN123", confirmation_token=token
        )

        assert "Quiz submitted" in first
        assert "already used" in replay
        post_calls = [
            call
            for call in mock_quiz_api["make_canvas_request"].call_args_list
            if call.args[0] == "post"
        ]
        assert len(post_calls) == 1

    @pytest.mark.asyncio
    async def test_expired_confirmation_is_rejected(self, mock_quiz_api):
        mock_quiz_api["make_canvas_request"].side_effect = [
            MOCK_QUIZ_DETAIL,
            _submission_response(),
            MOCK_SUBMISSION_QUESTIONS,
            MOCK_QUIZ_DETAIL,
            _submission_response(),
            MOCK_SUBMISSION_QUESTIONS,
        ]

        submit_quiz_attempt = get_tool_function("submit_quiz_attempt")
        with patch("canvas_mcp.core.write_confirmation.time.time", return_value=1000):
            preview = await submit_quiz_attempt("60366", 101, 555, 1, "VTOKEN123")
        with patch("canvas_mcp.core.write_confirmation.time.time", return_value=1301):
            result = await submit_quiz_attempt(
                "60366",
                101,
                555,
                1,
                "VTOKEN123",
                confirmation_token=_confirmation_token(preview),
            )

        assert "expired" in result
        assert "Nothing was submitted" in result

    @pytest.mark.asyncio
    async def test_confirmation_is_bound_to_caller(self, mock_quiz_api):
        mock_quiz_api["make_canvas_request"].side_effect = [
            MOCK_QUIZ_DETAIL,
            _submission_response(),
            MOCK_SUBMISSION_QUESTIONS,
            MOCK_QUIZ_DETAIL,
            _submission_response(),
            MOCK_SUBMISSION_QUESTIONS,
        ]
        submit_quiz_attempt = get_tool_function("submit_quiz_attempt")

        try:
            set_request_credentials(
                RequestCredentials("student-a", "https://canvas.example/api/v1")
            )
            preview = await submit_quiz_attempt("60366", 101, 555, 1, "VTOKEN123")
            set_request_credentials(
                RequestCredentials("student-b", "https://canvas.example/api/v1")
            )
            result = await submit_quiz_attempt(
                "60366",
                101,
                555,
                1,
                "VTOKEN123",
                confirmation_token=_confirmation_token(preview),
            )
        finally:
            clear_request_credentials()

        assert "does not match" in result
        assert "Nothing was submitted" in result


# --- _normalize_answers (helper) -------------------------------------------


class TestNormalizeAnswers:
    def test_dict_form(self):
        qq, err = _normalize_answers('{"4": 5, "5": "Paris"}')
        assert err is None
        assert {"id": "4", "answer": 5} in qq
        assert {"id": "5", "answer": "Paris"} in qq

    def test_array_form_with_question_id_key(self):
        qq, err = _normalize_answers('[{"question_id": 9, "answer": [1, 2]}]')
        assert err is None
        assert qq == [{"id": "9", "answer": [1, 2]}]

    def test_array_item_missing_answer(self):
        qq, err = _normalize_answers('[{"id": 9}]')
        assert qq is None
        assert "missing" in err.lower()

    def test_invalid_json(self):
        qq, err = _normalize_answers("{nope")
        assert qq is None
        assert "Invalid answers JSON" in err

    def test_wrong_top_level_type(self):
        qq, err = _normalize_answers("42")
        assert qq is None
        assert "must be a JSON object or array" in err
