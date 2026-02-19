"""Account-level MCP tools for Canvas API.

These tools provide institutional-level access for Canvas administrators,
enabling queries across all courses and users in an account rather than
just the authenticated user's enrollments.
"""

from typing import Optional

from mcp.server.fastmcp import FastMCP

from ..core.client import fetch_all_paginated_results, make_canvas_request
from ..core.config import get_config
from ..core.dates import format_date
from ..core.validation import validate_params


def register_account_tools(mcp: FastMCP):
    """Register all account-level MCP tools."""

    @mcp.tool()
    @validate_params
    async def list_accounts() -> str:
        """List Canvas accounts the authenticated user has admin access to.

        Returns accounts where you have administrative privileges.
        Use the account ID from this list with other account-level tools.
        """
        accounts = await fetch_all_paginated_results("/accounts", {"per_page": 100})

        if isinstance(accounts, dict) and "error" in accounts:
            return f"Error fetching accounts: {accounts['error']}"

        if not accounts:
            return "No accounts found. You may not have admin access to any accounts."

        accounts_info = []
        for account in accounts:
            account_id = account.get("id")
            name = account.get("name", "Unnamed")
            parent_id = account.get("parent_account_id")
            workflow_state = account.get("workflow_state", "unknown")

            account_type = "Root Account" if parent_id is None else f"Sub-account (parent: {parent_id})"

            accounts_info.append(
                f"ID: {account_id}\n"
                f"Name: {name}\n"
                f"Type: {account_type}\n"
                f"State: {workflow_state}\n"
            )

        return f"Accounts ({len(accounts)} found):\n\n" + "\n".join(accounts_info)

    @mcp.tool()
    @validate_params
    async def list_enrollment_terms(account_id: int) -> str:
        """List all enrollment terms (semesters/years) in a Canvas account.

        Use this to find term IDs for filtering courses to a specific semester or school year.

        Args:
            account_id: The Canvas account ID (get from list_accounts)
        """
        response = await make_canvas_request(
            "get",
            f"/accounts/{account_id}/terms",
            params={"per_page": 100}
        )

        if "error" in response:
            return f"Error fetching terms: {response['error']}"

        terms = response.get("enrollment_terms", response)
        if not terms:
            return f"No enrollment terms found in account {account_id}."

        terms_info = []
        for term in terms:
            term_id = term.get("id")
            name = term.get("name", "Unnamed")
            start_at = format_date(term.get("start_at"))
            end_at = format_date(term.get("end_at"))

            terms_info.append(
                f"ID: {term_id}\n"
                f"Name: {name}\n"
                f"Start: {start_at}\n"
                f"End: {end_at}\n"
            )

        return f"Enrollment Terms ({len(terms)} found):\n\n" + "\n".join(terms_info)

    @mcp.tool()
    @validate_params
    async def list_account_courses(
        account_id: int,
        term_id: Optional[int] = None,
        state: Optional[str] = None,
        search_term: Optional[str] = None,
        include_teachers: bool = False,
        include_total_students: bool = False,
        limit: int = 100,
        include_all_terms: bool = False
    ) -> str:
        """List all courses in a Canvas account (requires admin access).

        This returns ALL courses in the account, not just courses you're enrolled in.
        Use list_accounts first to get the account ID.

        Args:
            account_id: The Canvas account ID (get from list_accounts)
            term_id: Filter to a specific enrollment term (use list_enrollment_terms to find IDs).
                     Example: 155 for "2025-26 School Year"
            state: Filter by course state: 'created', 'claimed', 'available',
                   'completed', 'deleted', 'all'. Default shows available courses.
            search_term: Search courses by name, code, or SIS ID
            include_teachers: Include teacher names in output
            include_total_students: Include student count in output
            limit: Maximum number of courses to return (default 100)
            include_all_terms: If True, include courses from all enrollment terms
                             (overrides term_id and DEFAULT_TERM_ID).
        """
        params = {"per_page": min(limit, 100)}

        # Use provided term_id, or fall back to default from config (unless include_all_terms)
        config = get_config()
        if include_all_terms:
            effective_term_id = None
        else:
            effective_term_id = term_id if term_id is not None else (config.default_term_id or None)

        if effective_term_id:
            params["enrollment_term_id"] = effective_term_id

        if state:
            if state == "all":
                params["state[]"] = ["created", "claimed", "available", "completed", "deleted"]
            else:
                params["state[]"] = [state]

        if search_term:
            params["search_term"] = search_term

        includes = []
        if include_teachers:
            includes.append("teachers")
        if include_total_students:
            includes.append("total_students")
        includes.append("term")  # Always include term info for context
        params["include[]"] = includes

        courses = await fetch_all_paginated_results(
            f"/accounts/{account_id}/courses",
            params
        )

        if isinstance(courses, dict) and "error" in courses:
            return f"Error fetching courses: {courses['error']}"

        if not courses:
            term_note = f" for term {effective_term_id}" if effective_term_id else ""
            return f"No courses found in account {account_id}{term_note}."

        # Post-filter to strictly enforce term limits
        if effective_term_id:
            # Always include the requested term
            allowed_terms = {int(effective_term_id)}

            # If falling back to config default (and no explicit term requested),
            # also include the system Default Term (1) which holds ongoing content
            if term_id is None:
                allowed_terms.add(1)

            courses = [
                c for c in courses
                if c.get("enrollment_term_id") and int(c.get("enrollment_term_id")) in allowed_terms
            ]

        if not courses:
            term_note = f" for term {effective_term_id}" if effective_term_id else ""
            return f"No courses found in account {account_id}{term_note}."

        # Limit results
        courses = courses[:limit]

        # Build header with term info if filtering
        header = f"Courses in Account {account_id}"
        if effective_term_id:
            header += f" (Term ID: {effective_term_id})"
        header += f" ({len(courses)} shown):\n\n"

        courses_info = []
        for course in courses:
            course_id = course.get("id")
            name = course.get("name", "Unnamed")
            code = course.get("course_code", "No code")
            workflow_state = course.get("workflow_state", "unknown")

            info_lines = [
                f"ID: {course_id}",
                f"Code: {code}",
                f"Name: {name}",
                f"State: {workflow_state}"
            ]

            if include_teachers:
                teachers = course.get("teachers", [])
                teacher_names = [t.get("display_name", "Unknown") for t in teachers]
                if teacher_names:
                    info_lines.append(f"Teachers: {', '.join(teacher_names)}")

            if include_total_students:
                total = course.get("total_students", "N/A")
                info_lines.append(f"Students: {total}")

            courses_info.append("\n".join(info_lines) + "\n")

        return header + "\n".join(courses_info)

    @mcp.tool()
    @validate_params
    async def list_account_users(
        account_id: int,
        search_term: Optional[str] = None,
        enrollment_type: Optional[str] = None,
        limit: int = 100
    ) -> str:
        """List all users in a Canvas account (requires admin access).

        This returns users across the entire account, not just a single course.

        Args:
            account_id: The Canvas account ID (get from list_accounts)
            search_term: Search users by name, login, SIS ID, or email
            enrollment_type: Filter by role: 'teacher', 'student', 'ta', 'observer', 'designer'
            limit: Maximum number of users to return (default 100)
        """
        params = {"per_page": min(limit, 100)}

        if search_term:
            params["search_term"] = search_term

        if enrollment_type:
            params["enrollment_type"] = enrollment_type

        users = await fetch_all_paginated_results(
            f"/accounts/{account_id}/users",
            params
        )

        if isinstance(users, dict) and "error" in users:
            return f"Error fetching users: {users['error']}"

        if not users:
            return f"No users found in account {account_id}."

        # Limit results
        users = users[:limit]

        users_info = []
        for user in users:
            user_id = user.get("id")
            name = user.get("name", "Unknown")
            login_id = user.get("login_id", "N/A")
            email = user.get("email", "N/A")
            created_at = format_date(user.get("created_at"))

            users_info.append(
                f"ID: {user_id}\n"
                f"Name: {name}\n"
                f"Login: {login_id}\n"
                f"Email: {email}\n"
                f"Created: {created_at}\n"
            )

        return f"Users in Account {account_id} ({len(users)} shown):\n\n" + "\n".join(users_info)

    @mcp.tool()
    @validate_params
    async def get_account_analytics(
        account_id: int,
        term_id: Optional[int] = None,
        include_all_terms: bool = False
    ) -> str:
        """Get high-level analytics for a Canvas account.

        Returns summary statistics about courses, enrollments, and activity.

        Args:
            account_id: The Canvas account ID (get from list_accounts)
            term_id: Filter to a specific enrollment term (use list_enrollment_terms to find IDs).
                     Defaults to DEFAULT_TERM_ID from config if set.
            include_all_terms: If True, include courses from all enrollment terms
                             (overrides term_id and DEFAULT_TERM_ID).
        """
        # Get config for default term
        config = get_config()
        if include_all_terms:
            effective_term_id = None
        else:
            effective_term_id = term_id if term_id is not None else (config.default_term_id or None)

        # Get account details first
        account = await make_canvas_request("get", f"/accounts/{account_id}")

        if "error" in account:
            return f"Error fetching account: {account['error']}"

        account_name = account.get("name", "Unknown")

        # Get course counts by state
        course_states = ["available", "completed", "unpublished"]
        course_counts = {}

        for state in course_states:
            # Just get first page to get a count estimate
            params = {"state[]": [state], "per_page": 100}
            if effective_term_id:
                params["enrollment_term_id"] = effective_term_id

            courses = await make_canvas_request(
                "get",
                f"/accounts/{account_id}/courses",
                params=params
            )
            if isinstance(courses, list):
                course_counts[state] = len(courses) if len(courses) < 100 else "100+"

        # Get user count (first page only for estimate)
        users = await make_canvas_request(
            "get",
            f"/accounts/{account_id}/users",
            params={"per_page": 100}
        )
        user_count = len(users) if isinstance(users, list) and len(users) < 100 else "100+"

        # Get sub-accounts
        sub_accounts = await fetch_all_paginated_results(
            f"/accounts/{account_id}/sub_accounts",
            {"per_page": 100}
        )
        sub_account_count = len(sub_accounts) if isinstance(sub_accounts, list) else 0

        # Build header with term info if filtering
        header = f"Account Analytics for: {account_name} (ID: {account_id})"
        if effective_term_id:
            header += f"\nFiltered to Term ID: {effective_term_id}"

        analytics = [
            header,
            "",
            "Course Summary:",
        ]

        for state, count in course_counts.items():
            analytics.append(f"  {state.title()}: {count}")

        analytics.extend([
            "",
            f"Total Users: {user_count}",
            f"Sub-accounts: {sub_account_count}",
        ])

        if isinstance(sub_accounts, list) and sub_accounts:
            analytics.append("\nSub-accounts:")
            for sub in sub_accounts[:10]:
                sub_name = sub.get("name", "Unknown")
                sub_id = sub.get("id")
                analytics.append(f"  - {sub_name} (ID: {sub_id})")
            if len(sub_accounts) > 10:
                analytics.append(f"  ... and {len(sub_accounts) - 10} more")

        return "\n".join(analytics)

    @mcp.tool()
    @validate_params
    async def search_account_courses(
        account_id: int,
        search_term: str,
        term_id: Optional[int] = None,
        include_concluded: bool = False,
        limit: int = 50,
        include_all_terms: bool = False
    ) -> str:
        """Search for courses by name, code, or SIS ID across an account.

        Args:
            account_id: The Canvas account ID
            search_term: Text to search for in course name, code, or SIS ID
            term_id: Filter to a specific enrollment term (use list_enrollment_terms to find IDs)
            include_concluded: Whether to include concluded/completed courses
            limit: Maximum results to return (default 50)
            include_all_terms: If True, include courses from all enrollment terms
                             (overrides term_id and DEFAULT_TERM_ID).
        """
        params = {
            "search_term": search_term,
            "per_page": min(limit, 100)
        }

        # Use provided term_id, or fall back to default from config (unless include_all_terms)
        config = get_config()
        if include_all_terms:
            effective_term_id = None
        else:
            effective_term_id = term_id if term_id is not None else (config.default_term_id or None)

        if effective_term_id:
            params["enrollment_term_id"] = effective_term_id

        if include_concluded:
            params["state[]"] = ["available", "completed"]
        else:
            params["state[]"] = ["available"]

        courses = await fetch_all_paginated_results(
            f"/accounts/{account_id}/courses",
            params
        )

        if isinstance(courses, dict) and "error" in courses:
            return f"Error searching courses: {courses['error']}"

        if not courses:
            term_note = f" in term {effective_term_id}" if effective_term_id else ""
            return f"No courses found matching '{search_term}' in account {account_id}{term_note}."

        # Post-filter to strictly enforce term limits
        if effective_term_id:
            # Always include the requested term
            allowed_terms = {int(effective_term_id)}
            
            # If falling back to config default (and no explicit term requested),
            # also include the system Default Term (1) which holds ongoing content
            if term_id is None:
                allowed_terms.add(1)

            courses = [
                c for c in courses
                if c.get("enrollment_term_id") and int(c.get("enrollment_term_id")) in allowed_terms
            ]

        if not courses:
            term_note = f" in term {effective_term_id}" if effective_term_id else ""
            return f"No courses found matching '{search_term}' in account {account_id}{term_note}."

        # Limit results
        courses = courses[:limit]

        results = []
        for course in courses:
            course_id = course.get("id")
            name = course.get("name", "Unnamed")
            code = course.get("course_code", "No code")
            state = course.get("workflow_state", "unknown")
            sis_id = course.get("sis_course_id", "None")

            results.append(
                f"ID: {course_id}\n"
                f"Code: {code}\n"
                f"Name: {name}\n"
                f"State: {state}\n"
                f"SIS ID: {sis_id}\n"
            )

        return f"Search Results for '{search_term}' ({len(courses)} found):\n\n" + "\n".join(results)

    @mcp.tool()
    @validate_params
    async def list_user_enrollments(
        user_id: int,
        include_concluded: bool = True,
    ) -> str:
        """List all course enrollments for a specific user across all terms.

        Requires admin access. Uses the enrollments API endpoint which returns
        every enrollment across the entire account (not limited to the
        authenticated user's courses). Deduplicates by course ID.

        Args:
            user_id: The Canvas user ID
            include_concluded: Include completed/concluded courses (default: True)
        """
        states = ["active"]
        if include_concluded:
            states.extend(["completed", "concluded"])

        params = {
            "per_page": 100,
        }

        enrollments = await fetch_all_paginated_results(
            f"/users/{user_id}/enrollments", params
        )

        if isinstance(enrollments, dict) and "error" in enrollments:
            return f"Error fetching enrollments for user {user_id}: {enrollments['error']}"

        if not enrollments:
            return f"No enrollments found for user {user_id}."

        # Filter to student enrollments in desired states
        filtered = []
        for enrollment in enrollments:
            enrollment_state = enrollment.get("enrollment_state", "")
            enrollment_type = enrollment.get("type", "")
            if enrollment_state in states and enrollment_type == "StudentEnrollment":
                filtered.append(enrollment)

        if not filtered:
            return f"No student enrollments found for user {user_id}."

        # Deduplicate by course ID — keep the enrollment with the most info
        courses_seen = {}
        for enrollment in filtered:
            course_id = enrollment.get("course_id")
            if course_id not in courses_seen:
                courses_seen[course_id] = enrollment

        # Fetch course details with term info for each unique course
        course_details = []
        for course_id in courses_seen:
            params = {"include[]": "term"}
            course = await make_canvas_request(
                "get", f"/courses/{course_id}", params
            )
            if isinstance(course, dict) and "id" in course:
                course_details.append(course)

        if not course_details:
            return f"Found {len(courses_seen)} enrollments but could not fetch course details."

        # Sort by term start date (most recent first)
        course_details.sort(
            key=lambda c: c.get("term", {}).get("start_at", "") or "",
            reverse=True,
        )

        lines = [f"Enrollments for User {user_id} ({len(course_details)} courses):\n"]
        for course in course_details:
            course_id = course.get("id")
            name = course.get("name", "Unnamed")
            code = course.get("course_code", "")
            term = course.get("term", {})
            term_name = term.get("name", "Unknown Term")
            state = course.get("workflow_state", "unknown")
            lines.append(
                f"ID: {course_id}\n"
                f"Name: {name}\n"
                f"Code: {code}\n"
                f"Term: {term_name}\n"
                f"State: {state}\n"
            )

        return "\n".join(lines)
