import datetime
from statistics import StatisticsError, mean, median, stdev

from ..core.anonymization import anonymize_response_data
from ..core.cache import get_course_code, get_course_id
from ..core.client import fetch_all_paginated_results, make_canvas_request
from ..core.dates import format_date, parse_date
from ..core.logging import log_error


async def get_assignment_analytics_impl(course_identifier: str | int, assignment_id: str | int) -> str:
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
        due_date_obj = parse_date(due_date)
        if due_date_obj:
            due_date_str = format_date(due_date)
            now = datetime.datetime.now(datetime.timezone.utc)
            is_past_due = due_date_obj < now
        else:
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
