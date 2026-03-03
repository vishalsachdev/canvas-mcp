"""Canvas quiz management tools (Classic Quizzes API)."""

from typing import Any

from mcp.server.fastmcp import FastMCP

from ..core.cache import get_course_code, get_course_id
from ..core.client import fetch_all_paginated_results, make_canvas_request
from ..core.dates import format_date
from ..core.logging import log_info
from ..core.validation import validate_params


def register_quiz_tools(mcp: FastMCP) -> None:
    """Register Canvas quiz management tools (Classic Quizzes)."""

    @mcp.tool()
    @validate_params
    async def list_quizzes(
        course_identifier: str | int
    ) -> str:
        """List all quizzes in a course.

        Note: This covers Classic Quizzes. New Quizzes (LTI-based) appear as
        assignments with submission_types=['external_tool'].

        Args:
            course_identifier: The Canvas course code or ID
        """
        course_id = await get_course_id(course_identifier)

        quizzes = await fetch_all_paginated_results(
            f"/courses/{course_id}/quizzes",
            {"per_page": 100}
        )

        if isinstance(quizzes, dict) and "error" in quizzes:
            return f"Error fetching quizzes: {quizzes['error']}"

        if not quizzes:
            return f"No quizzes found for this course."

        course_display = await get_course_code(course_id) or course_identifier
        result = f"Quizzes for Course {course_display}:\n\n"

        for quiz in quizzes:
            quiz_id = quiz.get("id")
            title = quiz.get("title", "Untitled")
            quiz_type = quiz.get("quiz_type", "unknown")
            published = quiz.get("published", False)
            question_count = quiz.get("question_count", 0)
            points_possible = quiz.get("points_possible", 0)
            due_at = format_date(quiz.get("due_at"))
            html_url = quiz.get("html_url", "")

            status = "Published" if published else "Unpublished"

            result += f"ID: {quiz_id}\n"
            result += f"Title: {title}\n"
            result += f"Type: {quiz_type}\n"
            result += f"Status: {status}\n"
            result += f"Questions: {question_count}\n"
            result += f"Points: {points_possible}\n"
            result += f"Due: {due_at}\n"
            if html_url:
                result += f"URL: {html_url}\n"
            result += "\n"

        return result

    @mcp.tool()
    @validate_params
    async def get_quiz_details(
        course_identifier: str | int,
        quiz_id: str | int
    ) -> str:
        """Get details of a specific quiz including settings and question count.

        Args:
            course_identifier: The Canvas course code or ID
            quiz_id: The quiz ID
        """
        course_id = await get_course_id(course_identifier)

        response = await make_canvas_request(
            "get", f"/courses/{course_id}/quizzes/{quiz_id}"
        )

        if isinstance(response, dict) and "error" in response:
            return f"Error fetching quiz details: {response['error']}"

        title = response.get("title", "Untitled")
        description = response.get("description", "")
        quiz_type = response.get("quiz_type", "unknown")
        published = response.get("published", False)
        question_count = response.get("question_count", 0)
        points_possible = response.get("points_possible", 0)
        time_limit = response.get("time_limit")
        allowed_attempts = response.get("allowed_attempts", -1)
        shuffle_answers = response.get("shuffle_answers", False)
        due_at = format_date(response.get("due_at"))
        lock_at = format_date(response.get("lock_at"))
        unlock_at = format_date(response.get("unlock_at"))
        html_url = response.get("html_url", "")

        course_display = await get_course_code(course_id) or course_identifier
        result = f"Quiz Details for Course {course_display}:\n\n"
        result += f"Title: {title}\n"
        result += f"ID: {quiz_id}\n"
        result += f"Type: {quiz_type}\n"
        result += f"Status: {'Published' if published else 'Unpublished'}\n"
        result += f"Questions: {question_count}\n"
        result += f"Points: {points_possible}\n"
        if time_limit:
            result += f"Time Limit: {time_limit} minutes\n"
        attempts_display = "Unlimited" if allowed_attempts == -1 else str(allowed_attempts)
        result += f"Allowed Attempts: {attempts_display}\n"
        result += f"Shuffle Answers: {'Yes' if shuffle_answers else 'No'}\n"
        result += f"Due: {due_at}\n"
        result += f"Available: {unlock_at} to {lock_at}\n"
        if html_url:
            result += f"URL: {html_url}\n"
        if description:
            result += f"\nDescription:\n{description}\n"

        return result

    @mcp.tool()
    @validate_params
    async def create_quiz(
        course_identifier: str | int,
        title: str,
        quiz_type: str = "assignment",
        description: str = "",
        time_limit: int | None = None,
        allowed_attempts: int = 1,
        shuffle_answers: bool = False,
        published: bool = False,
        points_possible: float | None = None,
        due_at: str | None = None,
        lock_at: str | None = None,
        unlock_at: str | None = None
    ) -> str:
        """Create a new quiz (Classic Quiz).

        Args:
            course_identifier: The Canvas course code or ID
            title: Quiz title
            quiz_type: "assignment" (graded), "practice_quiz", "graded_survey", or "survey"
            description: HTML description shown to students
            time_limit: Time limit in minutes (None for no limit)
            allowed_attempts: Number of attempts (-1 for unlimited, default 1)
            shuffle_answers: Shuffle answer choices
            published: Whether to publish immediately (default False)
            points_possible: Total points (auto-calculated from questions if None)
            due_at: Due date in ISO 8601 format
            lock_at: Lock date in ISO 8601 format
            unlock_at: Unlock date in ISO 8601 format
        """
        course_id = await get_course_id(course_identifier)

        valid_types = ["assignment", "practice_quiz", "graded_survey", "survey"]
        if quiz_type not in valid_types:
            return f"Error: quiz_type must be one of: {', '.join(valid_types)}"

        data: dict[str, Any] = {
            "quiz": {
                "title": title,
                "quiz_type": quiz_type,
                "description": description,
                "shuffle_answers": shuffle_answers,
                "published": published,
                "allowed_attempts": allowed_attempts
            }
        }

        if time_limit is not None:
            data["quiz"]["time_limit"] = time_limit
        if points_possible is not None:
            data["quiz"]["points_possible"] = points_possible
        if due_at:
            data["quiz"]["due_at"] = due_at
        if lock_at:
            data["quiz"]["lock_at"] = lock_at
        if unlock_at:
            data["quiz"]["unlock_at"] = unlock_at

        response = await make_canvas_request(
            "post",
            f"/courses/{course_id}/quizzes",
            data=data
        )

        if isinstance(response, dict) and "error" in response:
            return f"Error creating quiz: {response['error']}"

        created_quiz_id = response.get("id")
        created_title = response.get("title", title)
        html_url = response.get("html_url", "")

        course_display = await get_course_code(course_id) or course_identifier
        result = f"Quiz created successfully in course {course_display}!\n\n"
        result += f"ID: {created_quiz_id}\n"
        result += f"Title: {created_title}\n"
        result += f"Type: {quiz_type}\n"
        result += f"Status: {'Published' if published else 'Unpublished'}\n"
        if html_url:
            result += f"URL: {html_url}\n"
        result += "\nAdd questions using create_quiz_question.\n"
        return result

    @mcp.tool()
    @validate_params
    async def create_quiz_question(
        course_identifier: str | int,
        quiz_id: str | int,
        question_name: str,
        question_type: str,
        question_text: str,
        points_possible: float = 1.0,
        answers: list[dict[str, Any]] | None = None
    ) -> str:
        """Add a question to a quiz.

        Args:
            course_identifier: The Canvas course code or ID
            quiz_id: The quiz ID to add the question to
            question_name: Short name/label for the question
            question_type: Type of question — "multiple_choice_question",
                "true_false_question", "short_answer_question", "essay_question",
                "matching_question", "multiple_answers_question",
                "numerical_question", "fill_in_multiple_blanks_question"
            question_text: The HTML question text shown to students
            points_possible: Points for this question (default 1.0)
            answers: List of answer objects. Format varies by question_type:
                - multiple_choice: [{"text": "Answer A", "weight": 100}, {"text": "Answer B", "weight": 0}]
                  (weight=100 marks correct answer)
                - true_false: [{"text": "True", "weight": 100}, {"text": "False", "weight": 0}]
                - short_answer: [{"text": "correct answer", "weight": 100}]
                - essay: not needed (graded manually)
        """
        course_id = await get_course_id(course_identifier)

        valid_types = [
            "multiple_choice_question", "true_false_question",
            "short_answer_question", "essay_question",
            "matching_question", "multiple_answers_question",
            "numerical_question", "fill_in_multiple_blanks_question"
        ]
        if question_type not in valid_types:
            return f"Error: question_type must be one of: {', '.join(valid_types)}"

        data: dict[str, Any] = {
            "question": {
                "question_name": question_name,
                "question_type": question_type,
                "question_text": question_text,
                "points_possible": points_possible
            }
        }

        if answers:
            data["question"]["answers"] = answers

        response = await make_canvas_request(
            "post",
            f"/courses/{course_id}/quizzes/{quiz_id}/questions",
            data=data
        )

        if isinstance(response, dict) and "error" in response:
            return f"Error creating quiz question: {response['error']}"

        question_id = response.get("id")
        result = f"Question added to quiz {quiz_id}!\n\n"
        result += f"Question ID: {question_id}\n"
        result += f"Name: {question_name}\n"
        result += f"Type: {question_type}\n"
        result += f"Points: {points_possible}\n"
        return result

    @mcp.tool()
    @validate_params
    async def get_quiz_statistics(
        course_identifier: str | int,
        quiz_id: str | int
    ) -> str:
        """Get submission statistics for a quiz.

        Returns aggregate statistics including average score, standard deviation,
        and per-question breakdown.

        Args:
            course_identifier: The Canvas course code or ID
            quiz_id: The quiz ID
        """
        course_id = await get_course_id(course_identifier)

        response = await make_canvas_request(
            "get",
            f"/courses/{course_id}/quizzes/{quiz_id}/statistics"
        )

        if isinstance(response, dict) and "error" in response:
            return f"Error fetching quiz statistics: {response['error']}"

        # The statistics endpoint returns a wrapper with quiz_statistics array
        stats_list = response.get("quiz_statistics", [])
        if not stats_list:
            return "No statistics available for this quiz (no submissions yet)."

        stats = stats_list[0]
        submission_stats = stats.get("submission_statistics", {})

        course_display = await get_course_code(course_id) or course_identifier
        result = f"Quiz Statistics for Course {course_display}:\n\n"

        # Submission statistics
        result += "Submission Statistics:\n"
        result += f"  Unique Count: {submission_stats.get('unique_count', 0)}\n"
        result += f"  Score Average: {submission_stats.get('score_average', 'N/A')}\n"
        result += f"  Score High: {submission_stats.get('score_high', 'N/A')}\n"
        result += f"  Score Low: {submission_stats.get('score_low', 'N/A')}\n"
        result += f"  Score Stdev: {submission_stats.get('score_stdev', 'N/A')}\n"
        result += f"  Duration Average: {submission_stats.get('duration_average', 'N/A')}s\n\n"

        # Per-question statistics
        question_stats = stats.get("question_statistics", [])
        if question_stats:
            result += f"Question Statistics ({len(question_stats)} questions):\n"
            for question_stat in question_stats:
                question_name = question_stat.get("question_name", "Unknown")
                question_type = question_stat.get("question_type", "unknown")
                responses = question_stat.get("responses", 0)
                correct = question_stat.get("correct", 0)

                result += f"\n  {question_name} ({question_type})\n"
                result += f"    Responses: {responses}\n"
                if responses > 0 and correct > 0:
                    pct = round(correct / responses * 100, 1)
                    result += f"    Correct: {correct} ({pct}%)\n"

        return result

    log_info("Canvas quiz tools registered successfully!")
