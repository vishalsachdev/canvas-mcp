"""Student-specific MCP tools for Canvas API.

These tools provide student-focused functionality using Canvas API "/self" endpoints
to access only the student's own data across their enrolled courses.
"""

from datetime import datetime, timedelta, timezone
from typing import Any

from fastmcp import FastMCP
from mcp.types import ToolAnnotations

from ..core.cache import get_course_code, get_course_id
from ..core.client import fetch_all_paginated_results, make_canvas_request
from ..core.dates import format_date, parse_date
from ..core.untrusted_content import fence_untrusted_inline
from ..core.validation import validate_params


async def _fetch_planner_peer_reviews(
    my_id: int, course_id: int | str | None = None
) -> tuple[list[dict], str | None]:
    """Discover pending peer reviews via the Planner API (#275).

    The per-course discovery scan in ``get_my_peer_reviews_todo`` only checks
    assignments whose listing carries ``peer_reviews: true`` and then reads
    the assignment-scoped ``/peer_reviews`` endpoint — but per community
    input on #275 (aesse97, jonespm), Canvas's own student "To Do" UI builds
    its list from the Planner feed instead, where a pending peer review shows
    up as an item with ``plannable_type: "assessment_request"``. That scan
    reportedly misses reviews the Planner feed would have caught, so this is
    queried as an *additional* source, not a replacement.

    No ``start_date`` is passed: ``filter=incomplete_items`` already scopes
    Canvas's response to pending items, and a peer review assigned weeks ago
    and still incomplete is exactly the case #275 is about — a start-date
    window would silently drop it (review round 1 caught this).

    Field shapes are now **live-verified**: the #275 reporter (khagyard)
    posted a real ``/planner/items`` payload from a production UIUC Canvas
    (three ``assessment_request`` items — see the issue for the full JSON).
    That measurement **falsified** the original field assumption, which was
    sourced only from the canvas-lms serializer
    (``lib/api/v1/planner_item.rb``, ``ASSESSMENT_REQUEST_FIELDS``) and the
    Canvas Planner API docs, neither of which is a captured real response.
    The measured ``plannable`` object for ``assessment_request`` items
    carries exactly six keys: ``id``, ``title``, ``todo_date``,
    ``created_at``, ``updated_at``, ``workflow_state`` — **no ``user_id``
    and no ``assessor_id``** on this instance. (Top-level item fields:
    ``course_id``, ``plannable_id``, ``plannable_type``, ``plannable_date``,
    ``html_url`` — which does carry the assignment id in its path, e.g.
    ``/courses/505/assignments/5066/submissions/2898`` — ``context_name``,
    ``context_image``.) The observed payload also confirms
    ``workflow_state == "completed"`` items DO still appear in the
    ``filter=incomplete_items`` feed, so the completed-state filter below is
    load-bearing, not defensive dead code.

    Two consequences of the missing ``user_id``/``assessor_id``:
    - ``found["user_id"]`` is frequently ``None`` on real data; the caller
      must render that case rather than print a bare "Student None".
    - The assessor guard below stays deliberately permissive (skip only on a
      *positively different* assessor) rather than requiring a match,
      because ``assessor_id`` was absent from every item in the real
      payload — a strict requirement would silently discard every Planner
      finding on this instance. It remains in place because some other
      Canvas serialization or version may still include it.

    No other student's name is serialized into this object on any of the
    documented/measured sources, which is also why this endpoint needs no
    additional anonymization gate (see
    ``core/client.py::_endpoint_anonymization_mode`` — same self-scoped-feed
    reasoning already applied to ``/planner/items`` by #222's
    ``get_my_upcoming_assignments``).

    Args:
        my_id: The caller's Canvas user id, used for the assessor guard below.
        course_id: When given, passed as Canvas's own ``context_codes[]``
            filter so the server pre-filters; the caller must still apply a
            client-side filter as backstop since this is not a documented
            guarantee.

    Returns (found_reviews, error). A non-``None`` error means the Planner
    query failed; callers must still surface whatever the assignment-scoped
    scan found rather than let this failure blank out the whole answer.
    """
    params: dict[str, Any] = {
        "filter": "incomplete_items",
        "per_page": 100,
    }
    if course_id is not None:
        params["context_codes[]"] = [f"course_{course_id}"]

    items = await fetch_all_paginated_results("/planner/items", params=params)

    if isinstance(items, dict) and "error" in items:
        return [], str(items["error"])
    if not isinstance(items, list):
        return [], None

    found: list[dict] = []
    for item in items:
        if not isinstance(item, dict) or item.get("plannable_type") != "assessment_request":
            continue
        plannable = item.get("plannable") or {}
        if plannable.get("workflow_state") == "completed":
            continue
        # Permissive assessor guard: the assignment-scan path filters on
        # assessor_id == my_id explicitly. The Planner feed is meant to be
        # the caller's own to-do list, so it should already be self-scoped —
        # but that is not documented, so only skip an item when Canvas
        # positively names a *different* assessor. A missing/None
        # assessor_id (undocumented field, may not always be populated) does
        # not exclude the item.
        item_assessor_id = plannable.get("assessor_id")
        if item_assessor_id is not None and item_assessor_id != my_id:
            continue
        found.append({
            "id": plannable.get("id") or item.get("plannable_id"),
            "user_id": plannable.get("user_id"),
            "_course_id": item.get("course_id"),
            "_assignment_name": plannable.get("title") or "Unnamed Assignment",
            "_source": "planner",
        })
    return found, None


def register_student_tools(mcp: FastMCP) -> None:
    """Register student-specific MCP tools."""

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
    @validate_params
    async def get_my_upcoming_assignments(days: int = 7) -> str:
        """Get your upcoming assignments across all courses.

        Args:
            days: Number of days to look ahead (default: 7)
        """
        if days < 1:
            return "Error: days must be at least 1."

        # /users/self/upcoming_events is hardcoded by Canvas to the
        # dashboard's 7-day "Coming Up" window regardless of parameters
        # (#222), so the Planner API is used instead: it honors an explicit
        # start/end range and already carries per-item submission status,
        # which also removes a per-assignment submissions/self round trip.
        start_date = datetime.now(timezone.utc)
        end_date = start_date + timedelta(days=days)

        items = await fetch_all_paginated_results(
            "/planner/items",
            params={
                "start_date": start_date.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "end_date": end_date.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "per_page": 100,
            },
        )

        if isinstance(items, dict) and "error" in items:
            return f"Error fetching upcoming assignments: {items['error']}"

        assignments = []
        for item in items if isinstance(items, list) else []:
            plannable_type = item.get("plannable_type")
            plannable = item.get("plannable") or {}

            if plannable_type in ("assignment", "quiz"):
                due_at = plannable.get("due_at") or item.get("plannable_date")
            elif plannable_type == "discussion_topic":
                # Graded discussions are assignments too; the planner reports
                # them as discussion_topic but only graded ones carry due_at
                # (ungraded to-do discussions have todo_date instead).
                due_at = plannable.get("due_at")
            else:
                continue

            if not due_at:
                continue
            due_date = parse_date(due_at)
            if not due_date or due_date > end_date:
                continue

            submissions = item.get("submissions")
            submitted = isinstance(submissions, dict) and bool(
                submissions.get("submitted")
            )
            assignments.append({
                "name": plannable.get("title", "Unnamed Assignment"),
                "due_at": due_at,
                "course_id": item.get("course_id"),
                "submitted": submitted,
            })

        if not assignments:
            return f"No assignments due in the next {days} days."

        # Sort by due date (use timezone-aware max for fallback)
        assignments.sort(
            key=lambda x: parse_date(x["due_at"]) or datetime.max.replace(tzinfo=timezone.utc)
        )

        # Format output
        output_lines = [f"Upcoming Assignments (Next {days} Days):\n"]

        for assignment in assignments:
            course_id = assignment["course_id"]
            course_display = await get_course_code(course_id) if course_id else "Unknown Course"
            status = "✅ Submitted" if assignment["submitted"] else "❌ Not Submitted"

            output_lines.append(
                f"• {fence_untrusted_inline(assignment['name'], 'assignment title')}\n"
                f"  Course: {course_display}\n"
                f"  Due: {format_date(assignment['due_at'])}\n"
                f"  Status: {status}\n"
            )

        return "\n".join(output_lines)

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
    @validate_params
    async def get_my_submission_status(course_identifier: str | int | None = None) -> str:
        """Get your submission status for assignments.

        Args:
            course_identifier: Course code or Canvas ID (omit for all courses)
        """
        if course_identifier:
            # Get submissions for specific course
            course_id = await get_course_id(course_identifier)

            assignments = await fetch_all_paginated_results(
                f"/courses/{course_id}/assignments",
                params={"include[]": ["submission"], "per_page": 100}
            )

            if isinstance(assignments, dict) and "error" in assignments:
                return f"Error fetching assignments: {assignments['error']}"

            course_display = await get_course_code(course_id) or course_identifier
            output_lines = [f"Submission Status for {course_display}:\n"]

        else:
            # Get all courses and their assignments
            courses = await fetch_all_paginated_results(
                "/courses",
                params={"enrollment_state": "active", "per_page": 100}
            )

            if isinstance(courses, dict) and "error" in courses:
                return f"Error fetching courses: {courses['error']}"

            output_lines = ["Submission Status (All Courses):\n"]
            all_assignments = []

            for course in courses:
                course_id = course.get("id")
                course_name = course.get("course_code", course.get("name", "Unknown"))

                assignments = await fetch_all_paginated_results(
                    f"/courses/{course_id}/assignments",
                    params={"include[]": ["submission"], "per_page": 100}
                )

                if not isinstance(assignments, dict) or "error" not in assignments:
                    for assignment in assignments if isinstance(assignments, list) else []:
                        assignment["_course_name"] = course_name
                        all_assignments.append(assignment)

            assignments = all_assignments

        if not assignments:
            return "No assignments found."

        # Separate submitted and missing
        submitted = []
        missing = []

        for assignment in assignments:
            submission = assignment.get("submission")
            is_submitted = submission and submission.get("submitted_at") is not None

            if is_submitted:
                submitted.append(assignment)
            else:
                # Check if past due (use timezone-aware datetime)
                due_at = assignment.get("due_at")
                if due_at:
                    due_date = parse_date(due_at)
                    if due_date and due_date < datetime.now(timezone.utc):
                        missing.append((assignment, "OVERDUE"))
                    else:
                        missing.append((assignment, "NOT SUBMITTED"))
                else:
                    missing.append((assignment, "NOT SUBMITTED"))

        # Format output
        if missing:
            output_lines.append(f"⚠️  Missing Submissions ({len(missing)}):\n")
            for assignment, status in missing:
                name = assignment.get("name", "Unnamed")
                due_at = format_date(assignment.get("due_at")) if assignment.get("due_at") else "No due date"
                course_name = assignment.get("_course_name", "")

                output_lines.append(
                    f"• {fence_untrusted_inline(name, 'assignment name')}\n"
                    f"  {f'Course: {course_name}' if course_name else ''}\n"
                    f"  Due: {due_at}\n"
                    f"  Status: {status}\n"
                )

        if submitted:
            output_lines.append(f"\n✅ Submitted ({len(submitted)}):\n")
            for assignment in submitted[:10]:  # Show first 10
                name = assignment.get("name", "Unnamed")
                submission = assignment.get("submission", {})
                submitted_at = format_date(submission.get("submitted_at"))
                course_name = assignment.get("_course_name", "")

                output_lines.append(
                    f"• {fence_untrusted_inline(name, 'assignment name')}\n"
                    f"  {f'Course: {course_name}' if course_name else ''}\n"
                    f"  Submitted: {submitted_at}\n"
                )

        return "\n".join(output_lines)

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
    async def get_my_course_grades() -> str:
        """Get your current grades across all enrolled courses."""
        courses = await fetch_all_paginated_results(
            "/courses",
            params={
                "enrollment_state": "active",
                "include[]": ["total_scores", "current_grading_period_scores"],
                "per_page": 100
            }
        )

        if isinstance(courses, dict) and "error" in courses:
            return f"Error fetching courses: {courses['error']}"

        if not courses:
            return "No active course enrollments found."

        output_lines = ["Your Course Grades:\n"]

        for course in courses:
            name = course.get("name", "Unnamed Course")
            course_code = course.get("course_code", "")

            # Get enrollment data (grades)
            enrollments = course.get("enrollments", [])
            if enrollments:
                enrollment = enrollments[0]  # Student typically has one enrollment per course

                # Current score
                current_score = enrollment.get("computed_current_score")
                final_score = enrollment.get("computed_final_score")
                current_grade = enrollment.get("computed_current_grade", "N/A")

                # Format grade info
                if current_score is not None:
                    grade_info = f"{current_grade} ({current_score:.1f}%)"
                elif final_score is not None:
                    grade_info = f"{final_score:.1f}%"
                else:
                    grade_info = "No grade yet"

                output_lines.append(
                    f"• {course_code}: {name}\n"
                    f"  Current Grade: {grade_info}\n"
                )
            else:
                output_lines.append(
                    f"• {course_code}: {name}\n"
                    f"  Current Grade: No enrollment data\n"
                )

        return "\n".join(output_lines)

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
    async def get_my_todo_items() -> str:
        """Get your Canvas TODO list."""
        todos = await fetch_all_paginated_results(
            "/users/self/todo",
            params={"per_page": 100}
        )

        if isinstance(todos, dict) and "error" in todos:
            return f"Error fetching TODO items: {todos['error']}"

        if not todos:
            return "Your TODO list is empty! 🎉"

        output_lines = ["Your TODO List:\n"]

        for item in todos:
            item_type = item.get("type", "item")
            assignment = item.get("assignment", {})

            name = assignment.get("name") or item.get("title", "Unnamed item")
            due_at = format_date(assignment.get("due_at")) if assignment.get("due_at") else "No due date"
            course_id = item.get("course_id")

            course_display = await get_course_code(course_id) if course_id else "Unknown Course"

            output_lines.append(
                f"• {fence_untrusted_inline(name, 'assignment or item title')}\n"
                f"  Type: {item_type.title()}\n"
                f"  Course: {course_display}\n"
                f"  Due: {due_at}\n"
            )

        return "\n".join(output_lines)

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
    @validate_params
    async def get_my_peer_reviews_todo(
        course_identifier: str | int | None = None,
        assignment_identifier: str | int | None = None,
    ) -> str:
        """Get peer reviews YOU need to complete.

        Args:
            course_identifier: Course code or Canvas ID (omit for all courses).
                Required if assignment_identifier is given.
            assignment_identifier: Canvas assignment ID to check directly, bypassing
                the per-course discovery scan. Use this when you already know which
                assignment has your peer review — the discovery scan only queries
                assignments whose "peer_reviews" flag came back true on the course's
                assignment listing, so an assignment where that flag is missing or
                stale for any reason would otherwise be silently skipped.
        """
        # The peer-review listing is only meaningful relative to the caller:
        # reviews are filtered to assessor_id == the current user.
        me = await make_canvas_request("get", "/users/self")
        if not isinstance(me, dict) or "error" in me or not me.get("id"):
            detail = me.get("error") if isinstance(me, dict) else me
            return f"Error identifying current user: {detail}"
        my_id = me["id"]

        if assignment_identifier is not None:
            if not course_identifier:
                return (
                    "Error: assignment_identifier requires course_identifier "
                    "(peer reviews are looked up within a specific course)."
                )
            course_id = await get_course_id(course_identifier)

            assignment = await make_canvas_request(
                "get", f"/courses/{course_id}/assignments/{assignment_identifier}"
            )
            if not isinstance(assignment, dict) or "error" in assignment:
                detail = assignment.get("error") if isinstance(assignment, dict) else assignment
                return f"Error fetching assignment {assignment_identifier}: {detail}"

            peer_reviews = await fetch_all_paginated_results(
                f"/courses/{course_id}/assignments/{assignment_identifier}/peer_reviews",
                params={"include[]": ["user"], "per_page": 100}
            )
            if isinstance(peer_reviews, dict) and "error" in peer_reviews:
                return f"Error fetching peer reviews: {peer_reviews['error']}"

            assignment_name = assignment.get("name", f"assignment {assignment_identifier}")
            course_display = await get_course_code(course_id)
            my_reviews = [
                review for review in (peer_reviews if isinstance(peer_reviews, list) else [])
                if review.get("assessor_id") == my_id
                and review.get("workflow_state") != "completed"
            ]

            if not my_reviews:
                return (
                    f"No pending peer review found for you on "
                    f"{fence_untrusted_inline(assignment_name, 'assignment name')} "
                    f"({course_display})."
                )

            output_lines = ["Peer Reviews You Need to Complete:\n"]
            for review in my_reviews:
                output_lines.append(
                    f"• {fence_untrusted_inline(assignment_name, 'assignment name')}\n"
                    f"  Course: {course_display}\n"
                    f"  Reviewing: Student {review.get('user_id')}\n"
                    f"  Status: Incomplete\n"
                )
            return "\n".join(output_lines)

        if course_identifier:
            course_ids = [await get_course_id(course_identifier)]
        else:
            # Get all active courses
            courses = await fetch_all_paginated_results(
                "/courses",
                params={"enrollment_state": "active", "per_page": 100}
            )
            if isinstance(courses, dict) and "error" in courses:
                return f"Error fetching courses: {courses['error']}"

            course_ids = [course.get("id") for course in courses if course.get("id")]

        all_peer_reviews = []
        # Endpoints that errored. "No pending reviews" is only a safe answer
        # when every listing actually succeeded — the assignment-level
        # peer_reviews endpoint is permission-gated on some instances, and a
        # swallowed 401 here previously read as "you have nothing to do ✅".
        unchecked: list[str] = []

        for course_id in course_ids:
            # Get assignments for this course
            assignments = await fetch_all_paginated_results(
                f"/courses/{course_id}/assignments",
                params={"per_page": 100}
            )

            if isinstance(assignments, dict) and "error" in assignments:
                unchecked.append(f"course {course_id}: {assignments['error']}")
                continue

            # Check each assignment for peer reviews
            for assignment in assignments if isinstance(assignments, list) else []:
                if assignment.get("peer_reviews"):
                    assignment_id = assignment.get("id")

                    # Get peer reviews for this assignment
                    peer_reviews = await fetch_all_paginated_results(
                        f"/courses/{course_id}/assignments/{assignment_id}/peer_reviews",
                        params={"include[]": ["user"], "per_page": 100}
                    )

                    if isinstance(peer_reviews, dict) and "error" in peer_reviews:
                        name = assignment.get("name", f"assignment {assignment_id}")
                        unchecked.append(
                            f"{fence_untrusted_inline(name, 'assignment name')} "
                            f"(course {course_id}): {peer_reviews['error']}"
                        )
                        continue

                    for review in peer_reviews if isinstance(peer_reviews, list) else []:
                        if (
                            review.get("assessor_id") == my_id
                            and review.get("workflow_state") != "completed"
                        ):
                            review["_course_id"] = course_id
                            review["_assignment_name"] = assignment.get("name")
                            review["_source"] = "assignment scan"
                            all_peer_reviews.append(review)

        # Merge in the Planner-based discovery path (#275). Union, not
        # replacement — the assignment-scoped scan above works on some
        # instances, and we have no way to live-verify the Planner feed
        # against a real pending review, so neither path is dropped.
        # Course IDs are cached/compared as strings (get_course_id's return
        # type), but Canvas returns course_id as a JSON number on planner
        # items — compare both sides as strings or every planner item gets
        # silently filtered out / never dedups against the assignment scan.
        # A single course_id is passed through to Canvas's own
        # context_codes[] filter (server-side pre-filter); the client-side
        # filter below stays as a backstop since that behavior isn't
        # documented as guaranteed.
        planner_course_id = course_ids[0] if course_identifier and len(course_ids) == 1 else None
        planner_reviews, planner_error = await _fetch_planner_peer_reviews(
            my_id, course_id=planner_course_id
        )
        if course_identifier:
            course_id_strs = {str(c) for c in course_ids}
            planner_reviews = [
                r for r in planner_reviews if str(r.get("_course_id")) in course_id_strs
            ]

        # Review "id" is an AssessmentRequest id on both paths, but its type
        # isn't guaranteed to match: the assignment-scan path gets it from
        # the /peer_reviews endpoint (typically an int), while the Planner
        # docs describe the top-level plannable_id as a string even though
        # plannable.id (used here) is typically an int. Normalize with
        # str() on both sides of the key so a type-only mismatch never
        # produces a duplicate entry.
        dedup_keys = {
            (str(r.get("_course_id")), str(r.get("id")))
            for r in all_peer_reviews
            if r.get("id") is not None
        }
        for review in planner_reviews:
            key = (str(review.get("_course_id")), str(review.get("id")))
            if review.get("id") is not None and key in dedup_keys:
                continue
            all_peer_reviews.append(review)
            if review.get("id") is not None:
                dedup_keys.add(key)

        failure_note = ""
        if unchecked:
            failure_note += (
                "\n⚠️  Could not check peer reviews for:\n"
                + "".join(f"  • {item}\n" for item in unchecked)
                + "These assignments may still have reviews assigned to you."
            )
        if planner_error:
            failure_note += (
                "\n⚠️  Could not check the Planner feed for additional peer "
                f"reviews: {planner_error}"
            )

        if not all_peer_reviews:
            if unchecked or planner_error:
                return (
                    "Could not confirm your peer-review to-do list — some "
                    "peer-review listings failed." + failure_note
                )
            return "You have no pending peer reviews! ✅"

        output_lines = ["Peer Reviews You Need to Complete:\n"]

        for review in all_peer_reviews:
            assignment_name = review.get("_assignment_name", "Unknown Assignment")
            course_id = review.get("_course_id")
            course_display = await get_course_code(course_id) if course_id else "Unknown Course"

            user_id = review.get("user_id")
            source = review.get("_source", "assignment scan")
            source_label = "Planner feed" if source == "planner" else "Assignment scan"
            # Measured live (#275, khagyard): the Planner feed's
            # assessment_request plannable carries no user_id at all, so
            # this must render an honest "not identified" note rather than
            # the literal string "Student None".
            reviewing_line = (
                f"  Reviewing: Student {user_id}\n"
                if user_id is not None
                else "  Reviewing: (reviewee not identified in Planner feed)\n"
            )

            output_lines.append(
                f"• {fence_untrusted_inline(assignment_name, 'assignment name')}\n"
                f"  Course: {course_display}\n"
                f"{reviewing_line}"
                f"  Status: Incomplete\n"
                f"  Source: {source_label}\n"
            )

        return "\n".join(output_lines) + failure_note
