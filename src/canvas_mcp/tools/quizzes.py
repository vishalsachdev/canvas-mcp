"""Quiz management MCP tools for Canvas API."""

from mcp.server.fastmcp import FastMCP

from ..core.anonymization import anonymize_response_data
from ..core.cache import get_course_code, get_course_id
from ..core.client import fetch_all_paginated_results, make_canvas_request
from ..core.dates import format_date
from ..core.logging import log_error
from ..core.validation import validate_params


def register_quiz_tools(mcp: FastMCP) -> None:
    """Register all quiz management MCP tools."""

    @mcp.tool()
    @validate_params
    async def list_quizzes(
        course_identifier: str | int,
        search_term: str | None = None
    ) -> str:
        """List all quizzes in a course.

        Args:
            course_identifier: The Canvas course code (e.g., badm_554_120251_246794) or ID
            search_term: Optional search term to filter quizzes by title
        """
        course_id = await get_course_id(course_identifier)

        params: dict = {"per_page": 100}
        if search_term:
            params["search_term"] = search_term

        quizzes = await fetch_all_paginated_results(f"/courses/{course_id}/quizzes", params)

        if isinstance(quizzes, dict) and "error" in quizzes:
            return f"Error fetching quizzes: {quizzes['error']}"

        if not quizzes:
            course_display = await get_course_code(course_id) or course_identifier
            return f"No quizzes found for course {course_display}."

        quizzes_info = []
        for quiz in quizzes:
            quiz_id = quiz.get("id")
            title = quiz.get("title", "Untitled Quiz")
            quiz_type = quiz.get("quiz_type", "assignment")
            points_possible = quiz.get("points_possible", 0)
            question_count = quiz.get("question_count", 0)
            published = quiz.get("published", False)
            due_at = format_date(quiz.get("due_at"))
            time_limit = quiz.get("time_limit", "No limit")

            quizzes_info.append(
                f"ID: {quiz_id}\n"
                f"Title: {title}\n"
                f"Type: {quiz_type}\n"
                f"Questions: {question_count}\n"
                f"Points: {points_possible}\n"
                f"Due: {due_at}\n"
                f"Time Limit: {time_limit} min\n"
                f"Published: {published}\n"
            )

        course_display = await get_course_code(course_id) or course_identifier
        return f"Quizzes for Course {course_display}:\n\n" + "\n".join(quizzes_info)

    @mcp.tool()
    @validate_params
    async def get_quiz_details(
        course_identifier: str | int,
        quiz_id: str | int
    ) -> str:
        """Get detailed information about a specific quiz.

        Args:
            course_identifier: The Canvas course code (e.g., badm_554_120251_246794) or ID
            quiz_id: The Canvas quiz ID
        """
        course_id = await get_course_id(course_identifier)
        quiz_id_str = str(quiz_id)

        response = await make_canvas_request(
            "get",
            f"/courses/{course_id}/quizzes/{quiz_id_str}"
        )

        if "error" in response:
            return f"Error fetching quiz details: {response['error']}"

        details = [
            f"ID: {response.get('id')}",
            f"Title: {response.get('title', 'N/A')}",
            f"Type: {response.get('quiz_type', 'assignment')}",
            f"Description: {response.get('description', 'No description')[:200]}...",
            f"Points Possible: {response.get('points_possible', 0)}",
            f"Question Count: {response.get('question_count', 0)}",
            f"Published: {response.get('published', False)}",
            f"Due At: {format_date(response.get('due_at'))}",
            f"Lock At: {format_date(response.get('lock_at'))}",
            f"Unlock At: {format_date(response.get('unlock_at'))}",
            f"Time Limit: {response.get('time_limit', 'No limit')} minutes",
            f"Allowed Attempts: {response.get('allowed_attempts', 'Unlimited')}",
            f"Scoring Policy: {response.get('scoring_policy', 'keep_highest')}",
            f"Shuffle Answers: {response.get('shuffle_answers', False)}",
            f"Show Correct Answers: {response.get('show_correct_answers', True)}",
            f"One Question at a Time: {response.get('one_question_at_a_time', False)}",
            f"Can't Go Back: {response.get('cant_go_back', False)}",
            f"Access Code: {response.get('access_code', 'None')}",
            f"IP Filter: {response.get('ip_filter', 'None')}"
        ]

        course_display = await get_course_code(course_id) or course_identifier
        return f"Quiz Details for Course {course_display}:\n\n" + "\n".join(details)

    @mcp.tool()
    @validate_params
    async def get_quiz_statistics(
        course_identifier: str | int,
        quiz_id: str | int
    ) -> str:
        """Get statistics for a quiz including question analysis.

        Args:
            course_identifier: The Canvas course code (e.g., badm_554_120251_246794) or ID
            quiz_id: The Canvas quiz ID
        """
        course_id = await get_course_id(course_identifier)
        quiz_id_str = str(quiz_id)

        response = await make_canvas_request(
            "get",
            f"/courses/{course_id}/quizzes/{quiz_id_str}/statistics"
        )

        if "error" in response:
            return f"Error fetching quiz statistics: {response['error']}"

        # Canvas returns an array of quiz statistics
        if isinstance(response, dict) and "quiz_statistics" in response:
            stats = response["quiz_statistics"][0] if response["quiz_statistics"] else {}
        elif isinstance(response, list) and len(response) > 0:
            stats = response[0]
        else:
            return "No statistics available for this quiz."

        details = [
            f"Quiz ID: {stats.get('id')}",
            f"Submissions: {stats.get('multiple_attempts_exist', False)}",
            f"Generated At: {format_date(stats.get('generated_at'))}",
        ]

        # Question statistics
        question_stats = stats.get("question_statistics", [])
        if question_stats:
            details.append(f"\nQuestion Statistics ({len(question_stats)} questions):")
            for i, q_stat in enumerate(question_stats[:10], 1):  # Limit to first 10
                q_id = q_stat.get("id")
                q_text = q_stat.get("question_text", "")[:100]  # Truncate
                responses = q_stat.get("responses", 0)
                correct = q_stat.get("correct", 0)
                incorrect = q_stat.get("incorrect", 0)

                if responses > 0:
                    correct_pct = (correct / responses) * 100
                else:
                    correct_pct = 0

                details.append(
                    f"\nQuestion {i} (ID: {q_id}):\n"
                    f"  Text: {q_text}\n"
                    f"  Responses: {responses}\n"
                    f"  Correct: {correct} ({correct_pct:.1f}%)\n"
                    f"  Incorrect: {incorrect}"
                )

        course_display = await get_course_code(course_id) or course_identifier
        return f"Quiz Statistics for Course {course_display}:\n\n" + "\n".join(details)

    @mcp.tool()
    @validate_params
    async def list_quiz_submissions(
        course_identifier: str | int,
        quiz_id: str | int,
        include_user: bool = True
    ) -> str:
        """List all submissions for a quiz.

        Args:
            course_identifier: The Canvas course code (e.g., badm_554_120251_246794) or ID
            quiz_id: The Canvas quiz ID
            include_user: Include user information in results
        """
        course_id = await get_course_id(course_identifier)
        quiz_id_str = str(quiz_id)

        params: dict = {"per_page": 100}
        if include_user:
            params["include[]"] = ["user"]

        # Canvas quiz submissions are nested
        response = await make_canvas_request(
            "get",
            f"/courses/{course_id}/quizzes/{quiz_id_str}/submissions",
            params=params
        )

        if "error" in response:
            return f"Error fetching quiz submissions: {response['error']}"

        # Quiz submissions come wrapped in a quiz_submissions key
        submissions = response.get("quiz_submissions", [])

        if not submissions:
            course_display = await get_course_code(course_id) or course_identifier
            return f"No submissions found for quiz {quiz_id} in course {course_display}."

        # Anonymize submission data
        try:
            submissions = anonymize_response_data(submissions, data_type="submissions")
        except Exception as e:
            log_error(
                "Failed to anonymize quiz submission data",
                exc=e,
                course_id=course_id,
                quiz_id=quiz_id
            )

        submissions_info = []
        for submission in submissions[:50]:  # Limit display
            submission_id = submission.get("id")
            user_id = submission.get("user_id")
            attempt = submission.get("attempt", 1)
            score = submission.get("score", "Not graded")
            kept_score = submission.get("kept_score")
            workflow_state = submission.get("workflow_state", "unknown")
            started_at = format_date(submission.get("started_at"))
            finished_at = format_date(submission.get("finished_at"))
            time_spent = submission.get("time_spent", 0)

            submissions_info.append(
                f"User ID: {user_id}\n"
                f"Submission ID: {submission_id}\n"
                f"Attempt: {attempt}\n"
                f"Score: {score} (Kept: {kept_score})\n"
                f"State: {workflow_state}\n"
                f"Started: {started_at}\n"
                f"Finished: {finished_at}\n"
                f"Time Spent: {time_spent}s\n"
            )

        course_display = await get_course_code(course_id) or course_identifier
        header = f"Quiz Submissions for Quiz {quiz_id} in Course {course_display}:\n"
        header += f"Total Submissions: {len(submissions)}\n\n"

        if len(submissions) > 50:
            header += "(Showing first 50 submissions)\n\n"

        return header + "\n".join(submissions_info)

    @mcp.tool()
    @validate_params
    async def create_quiz(
        course_identifier: str | int,
        title: str,
        description: str | None = None,
        quiz_type: str = "assignment",
        time_limit: int | None = None,
        allowed_attempts: int = -1,
        scoring_policy: str = "keep_highest",
        published: bool = False
    ) -> str:
        """Create a new quiz in a course.

        Args:
            course_identifier: The Canvas course code (e.g., badm_554_120251_246794) or ID
            title: Quiz title
            description: Quiz description/instructions
            quiz_type: Quiz type (practice_quiz, assignment, graded_survey, survey)
            time_limit: Time limit in minutes (None for no limit)
            allowed_attempts: Number of attempts allowed (-1 for unlimited)
            scoring_policy: Scoring policy (keep_highest, keep_latest, keep_average)
            published: Whether to publish the quiz immediately
        """
        course_id = await get_course_id(course_identifier)

        data: dict = {
            "quiz": {
                "title": title,
                "quiz_type": quiz_type,
                "allowed_attempts": allowed_attempts,
                "scoring_policy": scoring_policy,
                "published": published
            }
        }

        if description:
            data["quiz"]["description"] = description

        if time_limit is not None:
            data["quiz"]["time_limit"] = time_limit

        response = await make_canvas_request(
            "post",
            f"/courses/{course_id}/quizzes",
            data=data
        )

        if "error" in response:
            return f"Error creating quiz: {response['error']}"

        quiz_id = response.get("id")
        quiz_title = response.get("title")

        course_display = await get_course_code(course_id) or course_identifier
        return (f"Successfully created quiz in course {course_display}:\n"
                f"Quiz ID: {quiz_id}\n"
                f"Title: {quiz_title}\n"
                f"Type: {quiz_type}\n"
                f"Published: {published}")

    @mcp.tool()
    @validate_params
    async def update_quiz(
        course_identifier: str | int,
        quiz_id: str | int,
        title: str | None = None,
        description: str | None = None,
        published: bool | None = None,
        time_limit: int | None = None
    ) -> str:
        """Update a quiz's properties.

        Args:
            course_identifier: The Canvas course code (e.g., badm_554_120251_246794) or ID
            quiz_id: The Canvas quiz ID
            title: New quiz title
            description: New quiz description
            published: Whether the quiz should be published
            time_limit: New time limit in minutes
        """
        course_id = await get_course_id(course_identifier)
        quiz_id_str = str(quiz_id)

        data: dict = {"quiz": {}}

        if title is not None:
            data["quiz"]["title"] = title
        if description is not None:
            data["quiz"]["description"] = description
        if published is not None:
            data["quiz"]["published"] = published
        if time_limit is not None:
            data["quiz"]["time_limit"] = time_limit

        if not data["quiz"]:
            return "Error: No update parameters provided"

        response = await make_canvas_request(
            "put",
            f"/courses/{course_id}/quizzes/{quiz_id_str}",
            data=data
        )

        if "error" in response:
            return f"Error updating quiz: {response['error']}"

        course_display = await get_course_code(course_id) or course_identifier
        return (f"Successfully updated quiz {quiz_id} in course {course_display}:\n"
                f"Title: {response.get('title')}\n"
                f"Published: {response.get('published')}")

    @mcp.tool()
    @validate_params
    async def delete_quiz(
        course_identifier: str | int,
        quiz_id: str | int
    ) -> str:
        """Delete a quiz from a course.

        Args:
            course_identifier: The Canvas course code (e.g., badm_554_120251_246794) or ID
            quiz_id: The Canvas quiz ID
        """
        course_id = await get_course_id(course_identifier)
        quiz_id_str = str(quiz_id)

        response = await make_canvas_request(
            "delete",
            f"/courses/{course_id}/quizzes/{quiz_id_str}"
        )

        if "error" in response:
            return f"Error deleting quiz: {response['error']}"

        course_display = await get_course_code(course_id) or course_identifier
        return f"Successfully deleted quiz {quiz_id} from course {course_display}"
