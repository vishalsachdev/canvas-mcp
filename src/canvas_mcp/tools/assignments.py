"""Assignment-related MCP tools for Canvas API."""

import asyncio
import datetime
from statistics import StatisticsError, mean, median, stdev
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from ..core.anonymization import anonymize_response_data
from ..core.cache import get_course_code, get_course_id
from ..core.client import fetch_all_paginated_results, make_canvas_request
from ..core.dates import format_date, parse_date
from ..core.logging import log_error
from ..core.validation import validate_params
from .rubrics import build_rubric_assessment_form_data


def register_shared_assignment_tools(mcp: FastMCP):
    """Register assignment tools accessible to both students and educators."""

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
    @validate_params
    async def list_assignments(course_identifier: str | int) -> str:
        """List assignments for a specific course.

        Args:
            course_identifier: Course code or Canvas ID
        """
        course_id = await get_course_id(course_identifier)

        params = {
            "per_page": 100,
            "include[]": ["all_dates", "submission"]
        }

        all_assignments = await fetch_all_paginated_results(f"/courses/{course_id}/assignments", params)

        if isinstance(all_assignments, dict) and "error" in all_assignments:
            return f"Error fetching assignments: {all_assignments['error']}"

        if not all_assignments:
            return f"No assignments found for course {course_identifier}."

        assignments_info = []
        for assignment in all_assignments:
            assignment_id = assignment.get("id")
            name = assignment.get("name", "Unnamed assignment")
            due_at = assignment.get("due_at", "No due date")
            points = assignment.get("points_possible", 0)

            assignments_info.append(
                f"ID: {assignment_id}\nName: {name}\nDue: {due_at}\nPoints: {points}\n"
            )

        # Try to get the course code for display
        course_display = await get_course_code(course_id) or course_identifier
        return f"Assignments for Course {course_display}:\n\n" + "\n".join(assignments_info)

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
    @validate_params
    async def get_assignment_details(course_identifier: str | int, assignment_id: str | int) -> str:
        """Get detailed information about a specific assignment.

        Args:
            course_identifier: Course code or Canvas ID
            assignment_id: Canvas assignment ID
        """
        course_id = await get_course_id(course_identifier)

        # Ensure assignment_id is a string
        assignment_id_str = str(assignment_id)

        response = await make_canvas_request(
            "get", f"/courses/{course_id}/assignments/{assignment_id_str}"
        )

        if "error" in response:
            return f"Error fetching assignment details: {response['error']}"

        details = [
            f"Name: {response.get('name', 'N/A')}",
            f"Description: {response.get('description', 'N/A')}",
            f"Due Date: {format_date(response.get('due_at'))}",
            f"Points Possible: {response.get('points_possible', 'N/A')}",
            f"Submission Types: {', '.join(response.get('submission_types', ['N/A']))}",
            f"Published: {response.get('published', False)}",
            f"Locked: {response.get('locked_for_user', False)}"
        ]

        # Try to get the course code for display
        course_display = await get_course_code(course_id) or course_identifier
        return f"Assignment Details for ID {assignment_id} in course {course_display}:\n\n" + "\n".join(details)


def register_educator_assignment_tools(mcp: FastMCP):
    """Register educator-only assignment tools (grading, analytics, management)."""

    @mcp.tool()
    @validate_params
    async def assign_peer_review(course_identifier: str, assignment_id: str, reviewer_id: str, reviewee_id: str) -> str:
        """Manually assign a peer review to a student for a specific assignment.

        Args:
            course_identifier: Course code or Canvas ID
            assignment_id: Canvas assignment ID
            reviewer_id: User ID of the student who will review
            reviewee_id: User ID of the student whose submission will be reviewed
        """
        course_id = await get_course_id(course_identifier)

        # First, we need to get the submission ID for the reviewee
        submissions = await make_canvas_request(
            "get",
            f"/courses/{course_id}/assignments/{assignment_id}/submissions",
            params={"per_page": 100}
        )

        if "error" in submissions:
            return f"Error fetching submissions: {submissions['error']}"

        # Find the submission for the reviewee
        reviewee_submission = None
        for submission in submissions:
            if str(submission.get("user_id")) == str(reviewee_id):
                reviewee_submission = submission
                break

        # If no submission exists, we need to create a placeholder submission
        if not reviewee_submission:
            # Create a placeholder submission for the reviewee
            placeholder_data = {
                "submission": {
                    "user_id": reviewee_id,
                    "submission_type": "online_text_entry",
                    "body": "Placeholder submission for peer review"
                }
            }

            reviewee_submission = await make_canvas_request(
                "post",
                f"/courses/{course_id}/assignments/{assignment_id}/submissions",
                data=placeholder_data
            )

            if "error" in reviewee_submission:
                return f"Error creating placeholder submission: {reviewee_submission['error']}"

        # Now assign the peer review using the submission ID
        submission_id = reviewee_submission.get("id")

        # Data for the peer review assignment
        data = {
            "user_id": reviewer_id  # The user who will do the review
        }

        # Make the API request to create the peer review
        response = await make_canvas_request(
            "post",
            f"/courses/{course_id}/assignments/{assignment_id}/submissions/{submission_id}/peer_reviews",
            data=data
        )

        if "error" in response:
            return f"Error assigning peer review: {response['error']}"

        # Try to get the course code for display
        course_display = await get_course_code(course_id) or course_identifier

        return f"Successfully assigned peer review in course {course_display}:\n" + \
               f"Assignment ID: {assignment_id}\n" + \
               f"Reviewer ID: {reviewer_id}\n" + \
               f"Reviewee ID: {reviewee_id}\n" + \
               f"Submission ID: {submission_id}"

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
    @validate_params
    async def list_peer_reviews(course_identifier: str, assignment_id: str) -> str:
        """List all peer review assignments for a specific assignment.

        Args:
            course_identifier: Course code or Canvas ID
            assignment_id: Canvas assignment ID
        """
        course_id = await get_course_id(course_identifier)

        # Get all submissions for this assignment
        submissions = await fetch_all_paginated_results(
            f"/courses/{course_id}/assignments/{assignment_id}/submissions",
            {"include[]": "submission_comments", "per_page": 100}
        )

        if isinstance(submissions, dict) and "error" in submissions:
            return f"Error fetching submissions: {submissions['error']}"

        if not submissions:
            return f"No submissions found for assignment {assignment_id}."

        # Anonymize submission data to protect student privacy
        try:
            submissions = anonymize_response_data(submissions, data_type="submissions")
        except Exception as e:
            log_error(
                "Failed to anonymize submission data in peer reviews",
                exc=e,
                course_id=course_id,
                assignment_id=assignment_id
            )
            # Continue with original data for functionality

        # Get all users in the course for name lookups
        users = await fetch_all_paginated_results(
            f"/courses/{course_id}/users",
            {"per_page": 100}
        )

        if isinstance(users, dict) and "error" in users:
            return f"Error fetching users: {users['error']}"

        # Anonymize user data to protect student privacy
        try:
            users = anonymize_response_data(users, data_type="users")
        except Exception as e:
            log_error(
                "Failed to anonymize user data in peer reviews",
                exc=e,
                course_id=course_id,
                assignment_id=assignment_id
            )
            # Continue with original data for functionality

        # Create a mapping of user IDs to names
        user_map = {}
        for user in users:
            user_id = str(user.get("id"))
            user_name = user.get("name", "Unknown")
            user_map[user_id] = user_name

        # Collect peer review data
        peer_reviews_by_submission = {}

        for submission in submissions:
            submission_id = submission.get("id")
            user_id = str(submission.get("user_id"))
            user_name = user_map.get(user_id, f"User {user_id}")

            # Get peer reviews for this submission
            peer_reviews = await make_canvas_request(
                "get",
                f"/courses/{course_id}/assignments/{assignment_id}/submissions/{submission_id}/peer_reviews"
            )

            if "error" in peer_reviews:
                continue  # Skip if error

            if peer_reviews:
                peer_reviews_by_submission[submission_id] = {
                    "user_id": user_id,
                    "user_name": user_name,
                    "peer_reviews": peer_reviews
                }

        # Format the output
        course_display = await get_course_code(course_id) or course_identifier
        output = f"Peer Reviews for Assignment {assignment_id} in course {course_display}:\n\n"

        if not peer_reviews_by_submission:
            output += "No peer reviews found for this assignment."
            return output

        # Display peer reviews grouped by reviewee
        for _submission_id, data in peer_reviews_by_submission.items():
            reviewee_name = data["user_name"]
            reviewee_id = data["user_id"]
            reviews = data["peer_reviews"]

            output += f"Reviews for {reviewee_name} (ID: {reviewee_id}):\n"

            if not reviews:
                output += "  No peer reviews assigned.\n\n"
                continue

            for review in reviews:
                reviewer_id = str(review.get("user_id"))
                reviewer_name = user_map.get(reviewer_id, f"User {reviewer_id}")
                workflow_state = review.get("workflow_state", "Unknown")

                output += f"  Reviewer: {reviewer_name} (ID: {reviewer_id})\n"
                output += f"  Status: {workflow_state}\n"

                # Add assessment details if available
                if "assessment" in review and review["assessment"]:
                    assessment = review["assessment"]
                    score = assessment.get("score")
                    if score is not None:
                        output += f"  Score: {score}\n"

                output += "\n"

        return output

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
    @validate_params
    async def list_submissions(course_identifier: str | int, assignment_id: str | int) -> str:
        """List submissions for a specific assignment.

        Args:
            course_identifier: Course code or Canvas ID
            assignment_id: Canvas assignment ID
        """
        course_id = await get_course_id(course_identifier)

        # Ensure assignment_id is a string
        assignment_id_str = str(assignment_id)

        params = {
            "per_page": 100
        }

        submissions = await fetch_all_paginated_results(
            f"/courses/{course_id}/assignments/{assignment_id_str}/submissions", params
        )

        if isinstance(submissions, dict) and "error" in submissions:
            return f"Error fetching submissions: {submissions['error']}"

        if not submissions:
            return f"No submissions found for assignment {assignment_id}."

        # Anonymize submission data to protect student privacy
        try:
            submissions = anonymize_response_data(submissions, data_type="submissions")
        except Exception as e:
            log_error(
                "Failed to anonymize submission data",
                exc=e,
                course_id=course_id,
                assignment_id=assignment_id
            )
            # Continue with original data for functionality

        submissions_info = []
        for submission in submissions:
            user_id = submission.get("user_id")
            submitted_at = submission.get("submitted_at", "Not submitted")
            score = submission.get("score", "Not graded")
            grade = submission.get("grade", "Not graded")

            submissions_info.append(
                f"User ID: {user_id}\nSubmitted: {submitted_at}\nScore: {score}\nGrade: {grade}\n"
            )

        # Try to get the course code for display
        course_display = await get_course_code(course_id) or course_identifier
        return f"Submissions for Assignment {assignment_id} in course {course_display}:\n\n" + "\n".join(submissions_info)

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
    @validate_params
    async def get_assignment_analytics(course_identifier: str | int, assignment_id: str | int) -> str:
        """Get detailed analytics about student performance on a specific assignment.

        Args:
            course_identifier: Course code or Canvas ID
            assignment_id: Canvas assignment ID
        """
        course_id = await get_course_id(course_identifier)

        # Ensure assignment_id is a string
        assignment_id_str = str(assignment_id)

        # Get assignment details
        assignment = await make_canvas_request(
            "get", f"/courses/{course_id}/assignments/{assignment_id_str}"
        )

        if isinstance(assignment, dict) and "error" in assignment:
            return f"Error fetching assignment: {assignment['error']}"

        # Get all students in the course
        params = {
            "enrollment_type[]": "student",
            "per_page": 100
        }

        students = await fetch_all_paginated_results(
            f"/courses/{course_id}/users", params
        )

        if isinstance(students, dict) and "error" in students:
            return f"Error fetching students: {students['error']}"

        if not students:
            return f"No students found for course {course_identifier}."

        # Anonymize student data to protect privacy
        try:
            students = anonymize_response_data(students, data_type="users")
        except Exception as e:
            log_error(
                "Failed to anonymize student data in analytics",
                exc=e,
                course_id=course_id,
                assignment_id=assignment_id
            )
            # Continue with original data for functionality

        # Get submissions for this assignment
        submissions = await fetch_all_paginated_results(
            f"/courses/{course_id}/assignments/{assignment_id}/submissions",
            {"per_page": 100, "include[]": ["user"]}
        )

        if isinstance(submissions, dict) and "error" in submissions:
            return f"Error fetching submissions: {submissions['error']}"

        # Anonymize submission data to protect student privacy
        try:
            submissions = anonymize_response_data(submissions, data_type="submissions")
        except Exception as e:
            log_error(
                "Failed to anonymize submission data in analytics",
                exc=e,
                course_id=course_id,
                assignment_id=assignment_id
            )
            # Continue with original data for functionality

        # Extract assignment details
        assignment_name = assignment.get("name", "Unknown Assignment")
        due_date = assignment.get("due_at")
        points_possible = assignment.get("points_possible", 0)
        is_published = assignment.get("published", False)

        # Format the due date
        due_date_str = "No due date"
        if due_date:
            try:
                due_date_obj = datetime.datetime.fromisoformat(due_date.replace('Z', '+00:00'))
                due_date_str = due_date_obj.strftime("%Y-%m-%d %H:%M")
                now = datetime.datetime.now(datetime.timezone.utc)
                is_past_due = due_date_obj < now
            except (ValueError, AttributeError):
                due_date_str = due_date
                is_past_due = False
        else:
            is_past_due = False

        # Process submissions
        submission_stats = {
            "total_students": len(students),
            "submitted_count": 0,
            "missing_count": 0,
            "late_count": 0,
            "graded_count": 0,
            "excused_count": 0,
            "scores": [],
            "status_counts": {
                "submitted": 0,
                "unsubmitted": 0,
                "graded": 0,
                "pending_review": 0
            }
        }

        # Student status tracking
        student_status = []
        missing_students = []
        low_scoring_students = []
        high_scoring_students = []

        # Track which students have submissions
        student_ids_with_submissions = set()

        for submission in submissions:
            student_id = submission.get("user_id")
            student_ids_with_submissions.add(student_id)

            # Find student name
            student_name = "Unknown"
            for student in students:
                if student.get("id") == student_id:
                    student_name = student.get("name", "Unknown")
                    break

            # Process submission data
            score = submission.get("score")
            is_submitted = submission.get("submitted_at") is not None
            is_late = submission.get("late", False)
            is_missing = submission.get("missing", False)
            is_excused = submission.get("excused", False)
            is_graded = score is not None
            status = submission.get("workflow_state", "unsubmitted")
            submitted_at = submission.get("submitted_at")

            if submitted_at:
                try:
                    submitted_at = datetime.datetime.fromisoformat(
                        submitted_at.replace('Z', '+00:00')
                    ).strftime("%Y-%m-%d %H:%M")
                except (ValueError, AttributeError):
                    pass

            # Update statistics
            if is_submitted:
                submission_stats["submitted_count"] += 1
            if is_late:
                submission_stats["late_count"] += 1
            if is_missing:
                submission_stats["missing_count"] += 1
                missing_students.append(student_name)
            if is_excused:
                submission_stats["excused_count"] += 1
            if is_graded:
                submission_stats["graded_count"] += 1
                submission_stats["scores"].append(score)

                # Track high/low scoring students
                if points_possible > 0:
                    percentage = (score / points_possible) * 100
                    if percentage < 70:
                        low_scoring_students.append((student_name, score, percentage))
                    if percentage > 90:
                        high_scoring_students.append((student_name, score, percentage))

            # Update status counts
            if status in submission_stats["status_counts"]:
                submission_stats["status_counts"][status] += 1

            # Add to student status
            student_status.append({
                "name": student_name,
                "submitted": is_submitted,
                "submitted_at": submitted_at,
                "late": is_late,
                "missing": is_missing,
                "excused": is_excused,
                "score": score,
                "status": status
            })

        # Find students with no submissions
        for student in students:
            if student.get("id") not in student_ids_with_submissions:
                student_name = student.get("name", "Unknown")
                missing_students.append(student_name)

                # Add to student status
                student_status.append({
                    "name": student_name,
                    "submitted": False,
                    "submitted_at": None,
                    "late": False,
                    "missing": True,
                    "excused": False,
                    "score": None,
                    "status": "unsubmitted"
                })

        # Compute grade statistics
        scores = submission_stats["scores"]
        avg_score = mean(scores) if scores else 0
        median_score = median(scores) if scores else 0

        try:
            std_dev = stdev(scores) if len(scores) > 1 else 0
        except StatisticsError:
            std_dev = 0

        if points_possible > 0:
            avg_percentage = (avg_score / points_possible) * 100
        else:
            avg_percentage = 0

        # Format the output
        course_display = await get_course_code(course_id) or course_identifier
        output = f"Assignment Analytics for '{assignment_name}' in Course {course_display}\n\n"

        # Assignment details
        output += "Assignment Details:\n"
        output += f"  Due: {due_date_str}"
        if is_past_due:
            output += " (Past Due)"
        output += "\n"

        output += f"  Points Possible: {points_possible}\n"
        output += f"  Published: {'Yes' if is_published else 'No'}\n\n"

        # Submission statistics
        output += "Submission Statistics:\n"
        total_students = submission_stats["total_students"]
        submitted = submission_stats["submitted_count"]
        graded = submission_stats["graded_count"]
        missing = submission_stats["missing_count"] + (total_students - len(submissions))
        late = submission_stats["late_count"]

        # Calculate percentages
        submitted_pct = (submitted / total_students * 100) if total_students > 0 else 0
        graded_pct = (graded / total_students * 100) if total_students > 0 else 0
        missing_pct = (missing / total_students * 100) if total_students > 0 else 0
        late_pct = (late / submitted * 100) if submitted > 0 else 0

        output += f"  Submitted: {submitted}/{total_students} ({round(submitted_pct, 1)}%)\n"
        output += f"  Graded: {graded}/{total_students} ({round(graded_pct, 1)}%)\n"
        output += f"  Missing: {missing}/{total_students} ({round(missing_pct, 1)}%)\n"
        if submitted > 0:
            output += f"  Late: {late}/{submitted} ({round(late_pct, 1)}% of submissions)\n"
        output += f"  Excused: {submission_stats['excused_count']}\n\n"

        # Grade statistics
        if scores:
            output += "Grade Statistics:\n"
            output += f"  Average Score: {round(avg_score, 2)}/{points_possible} ({round(avg_percentage, 1)}%)\n"
            output += f"  Median Score: {round(median_score, 2)}/{points_possible} ({round((median_score/points_possible)*100, 1)}%)\n"
            output += f"  Standard Deviation: {round(std_dev, 2)}\n"

            # High/Low scores
            if low_scoring_students:
                output += "\nStudents Scoring Below 70%:\n"
                for name, score, percentage in sorted(low_scoring_students, key=lambda x: x[2]):
                    output += f"  {name}: {round(score, 1)}/{points_possible} ({round(percentage, 1)}%)\n"

            if high_scoring_students:
                output += "\nStudents Scoring Above 90%:\n"
                for name, score, percentage in sorted(high_scoring_students, key=lambda x: x[2], reverse=True):
                    output += f"  {name}: {round(score, 1)}/{points_possible} ({round(percentage, 1)}%)\n"

        # Missing students
        if missing_students:
            output += "\nStudents Missing Submission:\n"
            # Sort alphabetically and show first 10
            for name in sorted(missing_students)[:10]:
                output += f"  {name}\n"
            if len(missing_students) > 10:
                output += f"  ...and {len(missing_students) - 10} more\n"

        return output

    @mcp.tool()
    @validate_params
    async def create_assignment(
        course_identifier: str | int,
        name: str,
        description: str | None = None,
        submission_types: str | None = None,
        due_at: str | None = None,
        unlock_at: str | None = None,
        lock_at: str | None = None,
        points_possible: float | None = None,
        grading_type: str | None = None,
        published: bool = False,
        assignment_group_id: str | int | None = None,
        peer_reviews: bool = False,
        automatic_peer_reviews: bool = False,
        allowed_extensions: str | None = None
    ) -> str:
        """Create a new assignment in a course.

        Args:
            course_identifier: Course code or Canvas ID
            name: Assignment name/title
            description: HTML description
            submission_types: Comma-separated types (online_text_entry, online_url, online_upload, discussion_topic, none, on_paper, external_tool)
            due_at: Due date in ISO 8601 format
            unlock_at: Available date in ISO 8601 format
            lock_at: Lock date in ISO 8601 format
            points_possible: Maximum points
            grading_type: One of: points, letter_grade, pass_fail, percent, not_graded
            published: Whether to publish immediately (default: False)
            assignment_group_id: Assignment group ID
            peer_reviews: Enable peer reviews
            automatic_peer_reviews: Auto-assign peer reviews
            allowed_extensions: Comma-separated file extensions (e.g., "pdf,docx,txt")
        """
        course_id = await get_course_id(course_identifier)

        # Validate grading_type if provided
        valid_grading_types = ["points", "letter_grade", "pass_fail", "percent", "not_graded"]
        if grading_type and grading_type not in valid_grading_types:
            return f"Invalid grading_type '{grading_type}'. Must be one of: {', '.join(valid_grading_types)}"

        # Validate submission_types if provided
        valid_submission_types = [
            "online_text_entry", "online_url", "online_upload",
            "discussion_topic", "none", "on_paper", "external_tool"
        ]
        submission_types_list = []
        if submission_types:
            submission_types_list = [s.strip() for s in submission_types.split(",")]
            for st in submission_types_list:
                if st not in valid_submission_types:
                    return f"Invalid submission_type '{st}'. Must be one of: {', '.join(valid_submission_types)}"

        # Build assignment data
        assignment_data = {
            "name": name,
            "published": published
        }

        if description:
            assignment_data["description"] = description

        if submission_types_list:
            assignment_data["submission_types"] = submission_types_list

        # Validate and parse date fields
        if due_at:
            parsed_due = parse_date(due_at)
            if not parsed_due:
                return f"Invalid date format for due_at: '{due_at}'. Use ISO 8601 format (e.g., '2026-01-26T23:59:00Z')."
            assignment_data["due_at"] = parsed_due.isoformat()

        if unlock_at:
            parsed_unlock = parse_date(unlock_at)
            if not parsed_unlock:
                return f"Invalid date format for unlock_at: '{unlock_at}'. Use ISO 8601 format (e.g., '2026-01-26T00:00:00Z')."
            assignment_data["unlock_at"] = parsed_unlock.isoformat()

        if lock_at:
            parsed_lock = parse_date(lock_at)
            if not parsed_lock:
                return f"Invalid date format for lock_at: '{lock_at}'. Use ISO 8601 format (e.g., '2026-02-01T23:59:00Z')."
            assignment_data["lock_at"] = parsed_lock.isoformat()

        if points_possible is not None:
            assignment_data["points_possible"] = points_possible

        if grading_type:
            assignment_data["grading_type"] = grading_type

        if assignment_group_id:
            assignment_data["assignment_group_id"] = assignment_group_id

        # Validate peer review settings
        if automatic_peer_reviews and not peer_reviews:
            return "Invalid configuration: automatic_peer_reviews requires peer_reviews=True. Set peer_reviews=True to enable automatic peer review assignment."

        if peer_reviews:
            assignment_data["peer_reviews"] = peer_reviews

        if automatic_peer_reviews:
            assignment_data["automatic_peer_reviews"] = automatic_peer_reviews

        if allowed_extensions:
            extensions_list = [ext.strip() for ext in allowed_extensions.split(",")]
            assignment_data["allowed_extensions"] = extensions_list

        # Make the API request
        response = await make_canvas_request(
            "post",
            f"/courses/{course_id}/assignments",
            data={"assignment": assignment_data}
        )

        if "error" in response:
            return f"Error creating assignment: {response['error']}"

        # Format success response
        assignment_id = response.get("id")
        assignment_name = response.get("name", name)
        assignment_points = response.get("points_possible")
        assignment_published = response.get("published", False)
        assignment_due = response.get("due_at")
        assignment_types = response.get("submission_types", [])
        html_url = response.get("html_url", "")

        course_display = await get_course_code(course_id) or course_identifier

        result = "✅ Assignment created successfully!\n\n"
        result += f"**{assignment_name}**\n"
        result += f"  Course: {course_display}\n"
        result += f"  Assignment ID: {assignment_id}\n"

        if assignment_points is not None:
            result += f"  Points: {assignment_points}\n"

        if assignment_due:
            result += f"  Due: {format_date(assignment_due)}\n"

        result += f"  Published: {'Yes' if assignment_published else 'No'}\n"

        if assignment_types:
            result += f"  Submission Types: {', '.join(assignment_types)}\n"

        if html_url:
            result += f"  URL: {html_url}\n"

        return result

    @mcp.tool()
    @validate_params
    async def update_assignment(
        course_identifier: str | int,
        assignment_id: str | int,
        name: str | None = None,
        description: str | None = None,
        submission_types: str | None = None,
        due_at: str | None = None,
        unlock_at: str | None = None,
        lock_at: str | None = None,
        points_possible: float | None = None,
        grading_type: str | None = None,
        published: bool | None = None,
        assignment_group_id: str | int | None = None,
        peer_reviews: bool | None = None,
        automatic_peer_reviews: bool | None = None,
        allowed_extensions: str | None = None
    ) -> str:
        """Update an existing assignment in a course.

        Args:
            course_identifier: Course code or Canvas ID
            assignment_id: Assignment ID to update
            name: New assignment name/title
            description: New HTML description
            submission_types: Comma-separated types (online_text_entry, online_url, online_upload, discussion_topic, none, on_paper, external_tool)
            due_at: New due date in ISO 8601 format
            unlock_at: New available date in ISO 8601 format
            lock_at: New lock date in ISO 8601 format
            points_possible: New maximum points
            grading_type: One of: points, letter_grade, pass_fail, percent, not_graded
            published: Whether to publish the assignment
            assignment_group_id: Assignment group ID to move to
            peer_reviews: Enable peer reviews
            automatic_peer_reviews: Auto-assign peer reviews
            allowed_extensions: Comma-separated file extensions (e.g., "pdf,docx,txt")
        """
        course_id = await get_course_id(course_identifier)

        # Build assignment data - only include fields that are provided
        assignment_data = {}

        if name is not None:
            assignment_data["name"] = name

        if description is not None:
            assignment_data["description"] = description

        # Validate and process submission_types if provided
        if submission_types is not None:
            valid_submission_types = [
                "online_text_entry", "online_url", "online_upload",
                "discussion_topic", "none", "on_paper", "external_tool"
            ]
            submission_types_list = [s.strip() for s in submission_types.split(",")]
            for st in submission_types_list:
                if st not in valid_submission_types:
                    return f"Invalid submission_type '{st}'. Must be one of: {', '.join(valid_submission_types)}"
            assignment_data["submission_types"] = submission_types_list

        # Validate and parse date fields
        if due_at is not None:
            parsed_due = parse_date(due_at)
            if not parsed_due:
                return f"Invalid date format for due_at: '{due_at}'. Use ISO 8601 format (e.g., '2026-01-26T23:59:00Z')."
            assignment_data["due_at"] = parsed_due.isoformat()

        if unlock_at is not None:
            parsed_unlock = parse_date(unlock_at)
            if not parsed_unlock:
                return f"Invalid date format for unlock_at: '{unlock_at}'. Use ISO 8601 format (e.g., '2026-01-26T00:00:00Z')."
            assignment_data["unlock_at"] = parsed_unlock.isoformat()

        if lock_at is not None:
            parsed_lock = parse_date(lock_at)
            if not parsed_lock:
                return f"Invalid date format for lock_at: '{lock_at}'. Use ISO 8601 format (e.g., '2026-02-01T23:59:00Z')."
            assignment_data["lock_at"] = parsed_lock.isoformat()

        if points_possible is not None:
            assignment_data["points_possible"] = points_possible

        # Validate grading_type if provided
        if grading_type is not None:
            valid_grading_types = ["points", "letter_grade", "pass_fail", "percent", "not_graded"]
            if grading_type not in valid_grading_types:
                return f"Invalid grading_type '{grading_type}'. Must be one of: {', '.join(valid_grading_types)}"
            assignment_data["grading_type"] = grading_type

        if published is not None:
            assignment_data["published"] = published

        if assignment_group_id is not None:
            assignment_data["assignment_group_id"] = assignment_group_id

        # Validate peer review settings
        if automatic_peer_reviews is True and peer_reviews is False:
            return "Invalid configuration: automatic_peer_reviews requires peer_reviews=True. Set peer_reviews=True to enable automatic peer review assignment."

        if peer_reviews is not None:
            assignment_data["peer_reviews"] = peer_reviews

        if automatic_peer_reviews is not None:
            assignment_data["automatic_peer_reviews"] = automatic_peer_reviews

        if allowed_extensions is not None:
            extensions_list = [ext.strip() for ext in allowed_extensions.split(",")]
            assignment_data["allowed_extensions"] = extensions_list

        # Check if there's anything to update
        if not assignment_data:
            return "No fields provided to update. Specify at least one field to modify (e.g., name, description, due_at, points_possible)."

        # Make the API request
        response = await make_canvas_request(
            "put",
            f"/courses/{course_id}/assignments/{assignment_id}",
            data={"assignment": assignment_data}
        )

        if "error" in response:
            return f"Error updating assignment: {response['error']}"

        # Format success response
        updated_name = response.get("name", "")
        updated_points = response.get("points_possible")
        updated_published = response.get("published", False)
        updated_due = response.get("due_at")
        updated_types = response.get("submission_types", [])
        html_url = response.get("html_url", "")

        course_display = await get_course_code(course_id) or course_identifier

        result = "✅ Assignment updated successfully!\n\n"
        result += f"**{updated_name}**\n"
        result += f"  Course: {course_display}\n"
        result += f"  Assignment ID: {assignment_id}\n"

        # Show what was updated
        updated_fields = list(assignment_data.keys())
        result += f"  Updated fields: {', '.join(updated_fields)}\n"

        if updated_points is not None:
            result += f"  Points: {updated_points}\n"

        if updated_due:
            result += f"  Due: {format_date(updated_due)}\n"

        result += f"  Published: {'Yes' if updated_published else 'No'}\n"

        if updated_types:
            result += f"  Submission Types: {', '.join(updated_types)}\n"

        if html_url:
            result += f"  URL: {html_url}\n"

        return result

    @mcp.tool()
    @validate_params
    async def bulk_grade_submissions(
        course_identifier: str | int,
        assignment_id: str | int,
        grades: dict[str, Any],
        dry_run: bool = False,
        max_concurrent: int = 5,
        rate_limit_delay: float = 1.0
    ) -> str:
        """Grade multiple submissions efficiently with concurrent processing.

        Supports both rubric-based and simple point-based grading in batches.

        Args:
            course_identifier: Course code or Canvas ID
            assignment_id: Canvas assignment ID
            grades: Dict mapping user_id to {rubric_assessment?, grade?, comment?}
            dry_run: If True, validate without submitting (default: False)
            max_concurrent: Max concurrent grading operations (default: 5)
            rate_limit_delay: Delay between batches in seconds (default: 1.0)
        """
        course_id = await get_course_id(course_identifier)
        assignment_id_str = str(assignment_id)

        # Validate that we have grades to process
        if not grades:
            return "Error: No grades provided. The grades dictionary is empty."

        # Check if rubric is configured for grading (if using rubric assessments)
        has_rubric_grades = any(
            "rubric_assessment" in grade_info
            for grade_info in grades.values()
        )

        if has_rubric_grades:
            assignment_check = await make_canvas_request(
                "get",
                f"/courses/{course_id}/assignments/{assignment_id_str}",
                params={"include[]": ["rubric_settings"]}
            )

            if "error" not in assignment_check:
                use_rubric_for_grading = assignment_check.get("use_rubric_for_grading", False)
                if not use_rubric_for_grading and not dry_run:
                    return (
                        "⚠️  ERROR: Rubric is not configured for grading!\n\n"
                        "The rubric exists but 'use_for_grading' is set to FALSE.\n"
                        "Grades will NOT be saved to the gradebook.\n\n"
                        "To fix this:\n"
                        "1. Use get_rubric to verify rubric settings\n"
                        "2. Use associate_rubric with use_for_grading=True\n"
                        "3. Or set dry_run=True to test without submitting\n"
                    )

        # Statistics tracking
        stats = {
            "total": len(grades),
            "graded": 0,
            "failed": 0
        }
        failed_results = []

        async def grade_single_submission(user_id: str, grade_info: dict[str, Any]):
            """Grade a single submission."""
            try:
                if dry_run:
                    # In dry run mode, just validate the data
                    if "rubric_assessment" in grade_info:
                        total_points = sum(
                            criterion.get("points", 0)
                            for criterion in grade_info["rubric_assessment"].values()
                        )
                        return {
                            "status": "success",
                            "user_id": user_id,
                            "message": f"DRY RUN: Would grade with {total_points} rubric points"
                        }
                    elif "grade" in grade_info:
                        return {
                            "status": "success",
                            "user_id": user_id,
                            "message": f"DRY RUN: Would grade with {grade_info['grade']} points"
                        }
                    else:
                        return {
                            "status": "failed",
                            "user_id": user_id,
                            "error": "No rubric_assessment or grade provided"
                        }

                # Build form data based on grading type
                form_data = {}

                if "rubric_assessment" in grade_info and grade_info["rubric_assessment"]:
                    # Rubric-based grading
                    form_data = build_rubric_assessment_form_data(
                        grade_info["rubric_assessment"],
                        grade_info.get("comment")
                    )
                elif "grade" in grade_info:
                    # Simple grading
                    form_data["submission[posted_grade]"] = str(grade_info["grade"])
                    if "comment" in grade_info:
                        form_data["comment[text_comment]"] = grade_info["comment"]
                else:
                    return {
                        "status": "failed",
                        "user_id": user_id,
                        "error": "Must provide either rubric_assessment or grade"
                    }

                # Submit the grade
                response = await make_canvas_request(
                    "put",
                    f"/courses/{course_id}/assignments/{assignment_id_str}/submissions/{user_id}",
                    data=form_data,
                    use_form_data=True
                )

                if "error" in response:
                    return {
                        "status": "failed",
                        "user_id": user_id,
                        "error": response["error"]
                    }

                return {
                    "status": "success",
                    "user_id": user_id,
                    "grade": response.get("grade", "N/A")
                }

            except Exception as e:
                return {
                    "status": "failed",
                    "user_id": user_id,
                    "error": str(e)
                }

        # Process in batches
        user_ids = list(grades.keys())
        total_batches = (len(user_ids) + max_concurrent - 1) // max_concurrent

        result_lines = []
        result_lines.append(f"{'=' * 60}")
        result_lines.append(f"Bulk Grading {'(DRY RUN) ' if dry_run else ''}for Assignment {assignment_id}")
        result_lines.append(f"{'=' * 60}")
        result_lines.append(f"Course: {await get_course_code(course_id) or course_identifier}")
        result_lines.append(f"Total submissions to grade: {stats['total']}")
        result_lines.append(f"Concurrent processing: {max_concurrent} per batch")
        result_lines.append(f"Total batches: {total_batches}\n")

        for i in range(0, len(user_ids), max_concurrent):
            batch = user_ids[i:i + max_concurrent]
            batch_num = (i // max_concurrent) + 1

            result_lines.append(f"Processing batch {batch_num}/{total_batches} ({len(batch)} submissions)...")

            # Process batch concurrently
            tasks = [
                grade_single_submission(user_id, grades[user_id])
                for user_id in batch
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Update statistics
            for result in results:
                if isinstance(result, Exception):
                    stats["failed"] += 1
                    failed_results.append({
                        "user_id": "unknown",
                        "error": str(result)
                    })
                elif result["status"] == "success":
                    stats["graded"] += 1
                    result_lines.append(f"  ✓ User {result['user_id']}: {result.get('message', 'Graded')}")
                else:
                    stats["failed"] += 1
                    failed_results.append({
                        "user_id": result["user_id"],
                        "error": result["error"]
                    })
                    result_lines.append(f"  ✗ User {result['user_id']}: {result['error']}")

            # Rate limit between batches (except after last batch)
            if i + max_concurrent < len(user_ids):
                result_lines.append(f"  Waiting {rate_limit_delay}s before next batch...\n")
                await asyncio.sleep(rate_limit_delay)

        # Summary
        result_lines.append(f"\n{'=' * 60}")
        result_lines.append(f"Bulk Grading {'(DRY RUN) ' if dry_run else ''}Complete!")
        result_lines.append(f"{'=' * 60}")
        result_lines.append(f"Total:   {stats['total']}")
        result_lines.append(f"Graded:  {stats['graded']}")
        result_lines.append(f"Failed:  {stats['failed']}")

        if failed_results:
            result_lines.append("\nFailed Submissions:")
            for failure in failed_results[:10]:  # Show first 10 failures
                result_lines.append(f"  User {failure['user_id']}: {failure['error']}")
            if len(failed_results) > 10:
                result_lines.append(f"  ... and {len(failed_results) - 10} more failures")

        if dry_run:
            result_lines.append("\n⚠️  DRY RUN MODE: No grades were actually submitted")
            result_lines.append("Set dry_run=false to apply grades")

        return "\n".join(result_lines)
