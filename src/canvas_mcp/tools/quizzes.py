"""Quiz-related MCP tools for Canvas API."""

from fastmcp import FastMCP
from mcp.types import ToolAnnotations

from ..core.cache import get_course_id
from ..core.client import fetch_all_paginated_results, make_canvas_request
from ..core.dates import format_date
from ..core.validation import validate_params


def register_shared_quiz_tools(mcp: FastMCP):
    """Register quiz tools accessible to both students and educators."""

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
    @validate_params
    async def list_quizzes(course_identifier: str | int) -> str:
        """List quizzes for a specific course, including both Classic and New Quizzes.

        Args:
            course_identifier: Course code or Canvas ID
        """
        course_id = await get_course_id(course_identifier)

        # Fetch classic quizzes
        classic_quizzes = await fetch_all_paginated_results(
            f"/courses/{course_id}/quizzes", {"per_page": 100}
        )
        if isinstance(classic_quizzes, dict) and "error" in classic_quizzes:
            classic_quizzes = []

        # Fetch assignments to find New Quizzes
        assignments = await fetch_all_paginated_results(
            f"/courses/{course_id}/assignments", {"per_page": 100}
        )
        if isinstance(assignments, dict) and "error" in assignments:
            assignments = []

        new_quizzes = [
            a for a in assignments
            if a.get("is_quiz_assignment") and "external_tool" in a.get("submission_types", [])
        ]

        if not classic_quizzes and not new_quizzes:
            return f"No quizzes found for course {course_identifier}."

        output = []
        if classic_quizzes:
            output.append("=== Classic Quizzes ===")
            for q in classic_quizzes:
                quiz_id = q.get("id")
                name = q.get("title", "Unnamed quiz")
                due_at = format_date(q.get("due_at")) if q.get("due_at") else "No due date"
                points = q.get("points_possible", "N/A")
                output.append(f"ID: {quiz_id} | Name: {name} | Due: {due_at} | Points: {points}")
            output.append("")

        if new_quizzes:
            output.append("=== New Quizzes ===")
            for q in new_quizzes:
                quiz_id = q.get("id")
                name = q.get("name", "Unnamed quiz")
                due_at = format_date(q.get("due_at")) if q.get("due_at") else "No due date"
                points = q.get("points_possible", "N/A")
                output.append(f"ID: {quiz_id} (Assignment ID) | Name: {name} | Due: {due_at} | Points: {points}")

        return "\n".join(output).strip()

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
    @validate_params
    async def get_quiz_details(course_identifier: str | int, quiz_id: str | int, engine: str = "classic") -> str:
        """Get detailed information about a specific quiz.

        Args:
            course_identifier: Course code or Canvas ID
            quiz_id: Canvas quiz ID (or assignment ID for New Quizzes)
            engine: "classic" or "new"
        """
        course_id = await get_course_id(course_identifier)
        quiz_id_str = str(quiz_id)

        if engine.lower() == "new":
            # We will just fetch the assignment details directly
            response = await make_canvas_request(
                "get", f"/courses/{course_id}/assignments/{quiz_id_str}"
            )
            if "error" in response:
                return f"Error fetching New Quiz details: {response['error']}"

            details = [
                f"Name: {response.get('name', 'N/A')}",
                f"Description: {response.get('description', 'N/A')}",
                f"Due Date: {format_date(response.get('due_at')) if response.get('due_at') else 'No due date'}",
                f"Points Possible: {response.get('points_possible', 'N/A')}",
                f"Published: {response.get('published', False)}",
                f"Locked: {response.get('locked_for_user', False)}",
                "Engine: New Quizzes"
            ]
            return "\n".join(details)

        # Classic Quiz
        response = await make_canvas_request(
            "get", f"/courses/{course_id}/quizzes/{quiz_id_str}"
        )

        if "error" in response:
            return f"Error fetching Classic Quiz details: {response['error']}"

        details = [
            f"Name: {response.get('title', 'N/A')}",
            f"Description: {response.get('description', 'N/A')}",
            f"Type: {response.get('quiz_type', 'N/A')}",
            f"Question Count: {response.get('question_count', 'N/A')}",
            f"Points Possible: {response.get('points_possible', 'N/A')}",
            f"Due Date: {format_date(response.get('due_at')) if response.get('due_at') else 'No due date'}",
            f"Time Limit: {response.get('time_limit', 'None')} minutes",
            f"Allowed Attempts: {response.get('allowed_attempts', 'Unlimited')}",
            f"Published: {response.get('published', False)}",
            "Engine: Classic Quizzes"
        ]
        return "\n".join(details)

def register_educator_quiz_tools(mcp: FastMCP):
    """Register quiz tools accessible only to educators."""

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
    @validate_params
    async def list_quiz_submissions(course_identifier: str | int, quiz_id: str | int, engine: str = "classic") -> str:
        """List submissions for a specific quiz.

        Args:
            course_identifier: Course code or Canvas ID
            quiz_id: Canvas quiz ID (or assignment ID for New Quizzes)
            engine: "classic" or "new"
        """
        course_id = await get_course_id(course_identifier)
        quiz_id_str = str(quiz_id)

        # Both engines can use the assignment submissions endpoint if we know the assignment ID.
        # Classic quizzes expose their assignment_id. Let's find it if engine is classic.
        assignment_id_str = quiz_id_str
        if engine.lower() == "classic":
            quiz = await make_canvas_request("get", f"/courses/{course_id}/quizzes/{quiz_id_str}")
            if isinstance(quiz, dict) and "error" in quiz:
                return f"Error fetching Classic Quiz: {quiz['error']}"
            if not quiz.get("assignment_id"):
                return f"Classic Quiz {quiz_id_str} does not have an associated assignment (it may be a practice quiz)."
            assignment_id_str = str(quiz["assignment_id"])

        params = {
            "per_page": 100,
            "include[]": ["user", "submission_history"]
        }

        all_submissions = await fetch_all_paginated_results(
            f"/courses/{course_id}/assignments/{assignment_id_str}/submissions", params
        )

        if isinstance(all_submissions, dict) and "error" in all_submissions:
            return f"Error fetching submissions: {all_submissions['error']}"

        if not all_submissions:
            return f"No submissions found for quiz {quiz_id}."

        output = [f"Submissions for Quiz {quiz_id} ({engine.title()} Engine):"]
        for sub in all_submissions:
            user = sub.get("user", {})
            user_name = user.get("name", "Unknown Student")
            user_id = sub.get("user_id", "Unknown")

            workflow_state = sub.get("workflow_state", "unsubmitted")
            score = sub.get("score", "N/A")
            submitted_at = format_date(sub.get("submitted_at")) if sub.get("submitted_at") else "Not submitted"

            output.append(f"Student: {user_name} (ID: {user_id}) | State: {workflow_state} | Score: {score} | Submitted: {submitted_at}")

        return "\n".join(output)

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
    @validate_params
    async def get_quiz_analytics(course_identifier: str | int, quiz_id: str | int, engine: str = "classic") -> str:
        """Get analytics for a specific quiz.

        Args:
            course_identifier: Course code or Canvas ID
            quiz_id: Canvas quiz ID (or assignment ID for New Quizzes)
            engine: "classic" or "new"
        """
        course_id = await get_course_id(course_identifier)
        quiz_id_str = str(quiz_id)

        if engine.lower() == "classic":
            stats = await fetch_all_paginated_results(f"/courses/{course_id}/quizzes/{quiz_id_str}/statistics", {"per_page": 100})
            if isinstance(stats, dict) and "error" in stats:
                return f"Error fetching Classic Quiz statistics: {stats['error']}"

            if not stats:
                return f"No statistics found for Classic Quiz {quiz_id_str}."

            output = [f"Statistics for Classic Quiz {quiz_id_str}:"]
            for stat in stats:
                sub_stats = stat.get("submission_statistics", {})
                output.append(f"Score Average: {sub_stats.get('score_average', 'N/A')}")
                output.append(f"Score High: {sub_stats.get('score_high', 'N/A')}")
                output.append(f"Score Low: {sub_stats.get('score_low', 'N/A')}")
                output.append(f"Score Standard Deviation: {sub_stats.get('score_stdev', 'N/A')}")
                output.append(f"User Count: {sub_stats.get('user_count', 'N/A')}")
            return "\n".join(output)

        else:
            from .assignments_analytics import get_assignment_analytics_impl
            return await get_assignment_analytics_impl(course_id, quiz_id_str)

