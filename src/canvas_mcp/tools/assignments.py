"""Assignment-related MCP tools for Canvas API."""

import datetime
from statistics import StatisticsError, mean, median, stdev

from mcp.server.fastmcp import FastMCP

from ..core.anonymization import anonymize_response_data
from ..core.cache import get_course_code, get_course_id
from ..core.client import fetch_all_paginated_results, make_canvas_request
from ..core.dates import format_date
from ..core.logging import log_error
from ..core.validation import validate_params


def register_assignment_tools(mcp: FastMCP):
    """Register all assignment-related MCP tools."""

    @mcp.tool()
    @validate_params
    async def list_assignments(course_identifier: str | int) -> str:
        """List assignments for a specific course.

        Args:
            course_identifier: The Canvas course code (e.g., badm_554_120251_246794) or ID
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

    @mcp.tool()
    @validate_params
    async def get_assignment_details(course_identifier: str | int, assignment_id: str | int) -> str:
        """Get detailed information about a specific assignment.

        Args:
            course_identifier: The Canvas course code (e.g., badm_554_120251_246794) or ID
            assignment_id: The Canvas assignment ID
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

    @mcp.tool()
    async def assign_peer_review(course_identifier: str, assignment_id: str, reviewer_id: str, reviewee_id: str) -> str:
        """Manually assign a peer review to a student for a specific assignment.

        Args:
            course_identifier: The Canvas course code (e.g., badm_554_120251_246794) or ID
            assignment_id: The Canvas assignment ID
            reviewer_id: The Canvas user ID of the student who will do the review
            reviewee_id: The Canvas user ID of the student whose submission will be reviewed
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

    @mcp.tool()
    async def list_peer_reviews(course_identifier: str, assignment_id: str) -> str:
        """List all peer review assignments for a specific assignment.

        Args:
            course_identifier: The Canvas course code (e.g., badm_554_120251_246794) or ID
            assignment_id: The Canvas assignment ID
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

    @mcp.tool()
    @validate_params
    async def list_submissions(course_identifier: str | int, assignment_id: str | int) -> str:
        """List submissions for a specific assignment.

        Args:
            course_identifier: The Canvas course code (e.g., badm_554_120251_246794) or ID
            assignment_id: The Canvas assignment ID
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

    @mcp.tool()
    @validate_params
    async def get_assignment_analytics(course_identifier: str | int, assignment_id: str | int) -> str:
        """Get detailed analytics about student performance on a specific assignment.

        Args:
            course_identifier: The Canvas course code (e.g., badm_554_120251_246794) or ID
            assignment_id: The Canvas assignment ID
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
