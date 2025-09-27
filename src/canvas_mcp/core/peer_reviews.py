"""
Canvas Peer Review Analytics Module

Provides comprehensive peer review tracking and analytics capabilities
for Canvas assignments with accurate reviewer-to-reviewee mapping.
"""

import datetime
from typing import Any

from .client import fetch_all_paginated_results, make_canvas_request


class PeerReviewAnalyzer:
    """Handles peer review analytics and reporting for Canvas assignments."""

    def __init__(self) -> None:
        pass

    async def get_assignments(
        self,
        course_id: int,
        assignment_id: int,
        include_names: bool = True,
        include_submission_details: bool = False
    ) -> dict[str, Any]:
        """Get peer review assignments with clear reviewer-reviewee mapping."""

        try:
            # Get assignment details
            assignment_response = await make_canvas_request(
                "get",
                f"/courses/{course_id}/assignments/{assignment_id}"
            )

            if "error" in assignment_response:
                return {"error": f"Failed to get assignment: {assignment_response['error']}"}

            # Get peer reviews
            peer_reviews_response = await make_canvas_request(
                "get",
                f"/courses/{course_id}/assignments/{assignment_id}/peer_reviews"
            )

            if "error" in peer_reviews_response:
                return {"error": f"Failed to get peer reviews: {peer_reviews_response['error']}"}

            peer_reviews: list[Any] = peer_reviews_response if isinstance(peer_reviews_response, list) else []

            # Get users if names are requested
            users_map = {}
            if include_names:
                users_response = await fetch_all_paginated_results(
                    f"/courses/{course_id}/users",
                    {"enrollment_type[]": "student", "per_page": 100}
                )
                if isinstance(users_response, list):
                    users_map = {user["id"]: user.get("name", "Unknown") for user in users_response}

            # Process peer review data
            assignments_list = []
            for pr in peer_reviews:
                reviewer_id = pr.get("assessor_id")
                reviewee_id = pr.get("user_id")

                if not reviewer_id or not reviewee_id:
                    continue

                assignment_entry = {
                    "reviewer_id": reviewer_id,
                    "reviewee_id": reviewee_id,
                    "submission_id": pr.get("submission_id"),
                    "status": "completed" if pr.get("workflow_state") == "completed" else "assigned",
                    "assigned_date": pr.get("created_at"),
                    "completed_date": pr.get("updated_at") if pr.get("workflow_state") == "completed" else None,
                    "has_comments": bool(pr.get("comment")),
                    "rubric_completed": bool(pr.get("rubric_assessment_id")),
                    "peer_review_id": pr.get("id")
                }

                if include_names:
                    assignment_entry["reviewer_name"] = users_map.get(reviewer_id, "Unknown")
                    assignment_entry["reviewee_name"] = users_map.get(reviewee_id, "Unknown")

                assignments_list.append(assignment_entry)

            # Calculate peer review settings
            peer_review_settings = {
                "anonymous": assignment_response.get("anonymous_peer_reviews", False),
                "automatic": assignment_response.get("automatic_peer_reviews", False),
                "reviews_per_student": assignment_response.get("peer_review_count", 0)
            }

            return {
                "assignment_info": {
                    "id": assignment_response.get("id"),
                    "name": assignment_response.get("name"),
                    "course_id": course_id,
                    "total_reviews_assigned": len(assignments_list),
                    "peer_review_settings": peer_review_settings
                },
                "assignments": assignments_list
            }

        except Exception as e:
            return {"error": f"Exception in get_assignments: {str(e)}"}

    async def get_completion_analytics(
        self,
        course_id: int,
        assignment_id: int,
        include_student_details: bool = True,
        group_by_status: bool = True
    ) -> dict[str, Any]:
        """Get detailed analytics on peer review completion rates."""

        try:
            # Get the assignments data
            assignments_data = await self.get_assignments(
                course_id, assignment_id, include_names=True
            )

            if "error" in assignments_data:
                return assignments_data

            assignments = assignments_data["assignments"]

            # Get all students in the course
            users_response = await fetch_all_paginated_results(
                f"/courses/{course_id}/users",
                {"enrollment_type[]": "student", "per_page": 100}
            )

            if "error" in users_response:
                return {"error": f"Failed to get users: {users_response}"}

            students = users_response if isinstance(users_response, list) else []

            # Calculate completion statistics
            reviewer_stats = {}
            total_assigned = len(assignments)
            total_completed = sum(1 for a in assignments if a["status"] == "completed")

            # Group assignments by reviewer
            for assignment in assignments:
                reviewer_id = assignment["reviewer_id"]
                if reviewer_id not in reviewer_stats:
                    reviewer_stats[reviewer_id] = {
                        "student_id": reviewer_id,
                        "student_name": assignment.get("reviewer_name", "Unknown"),
                        "assigned_count": 0,
                        "completed_count": 0,
                        "pending_reviews": []
                    }

                reviewer_stats[reviewer_id]["assigned_count"] += 1

                if assignment["status"] == "completed":
                    reviewer_stats[reviewer_id]["completed_count"] += 1
                else:
                    # Calculate days since assigned
                    days_since_assigned = 0
                    if assignment.get("assigned_date"):
                        try:
                            assigned_date = datetime.datetime.fromisoformat(
                                assignment["assigned_date"].replace("Z", "+00:00")
                            )
                            days_since_assigned = (datetime.datetime.now(datetime.timezone.utc) - assigned_date).days
                        except ValueError:
                            days_since_assigned = 0

                    reviewer_stats[reviewer_id]["pending_reviews"].append({
                        "reviewee_id": assignment["reviewee_id"],
                        "reviewee_name": assignment.get("reviewee_name", "Unknown"),
                        "days_since_assigned": days_since_assigned
                    })

            # Calculate completion rates
            for stats in reviewer_stats.values():
                if stats["assigned_count"] > 0:
                    stats["completion_rate"] = (stats["completed_count"] / stats["assigned_count"]) * 100
                else:
                    stats["completion_rate"] = 0.0

            # Group by completion status
            completion_groups: dict[str, list[Any]] = {
                "all_complete": [],
                "partial_complete": [],
                "none_complete": []
            }

            if group_by_status:
                for stats in reviewer_stats.values():
                    if stats["completion_rate"] == 100.0:
                        completion_groups["all_complete"].append(stats)
                    elif stats["completion_rate"] == 0.0:
                        completion_groups["none_complete"].append(stats)
                    else:
                        completion_groups["partial_complete"].append(stats)

            # Calculate summary statistics
            students_with_submissions = len([s for s in students if any(
                a["reviewee_id"] == s["id"] for a in assignments
            )])

            completion_rate = (total_completed / total_assigned * 100) if total_assigned > 0 else 0

            reviews_per_student = assignments_data["assignment_info"]["peer_review_settings"]["reviews_per_student"]

            summary = {
                "total_students_enrolled": len(students),
                "students_with_submissions": students_with_submissions,
                "total_reviews_assigned": total_assigned,
                "reviews_completed": total_completed,
                "completion_rate_percent": round(completion_rate, 1),
                "students_all_complete": len(completion_groups["all_complete"]),
                "students_partial_complete": len(completion_groups["partial_complete"]),
                "students_none_complete": len(completion_groups["none_complete"]),
                "average_reviews_per_student": reviews_per_student
            }

            result = {"summary": summary}

            if include_student_details:
                result["completion_groups"] = completion_groups

            return result

        except Exception as e:
            return {"error": f"Exception in get_completion_analytics: {str(e)}"}

    async def generate_report(
        self,
        course_id: int,
        assignment_id: int,
        report_format: str = "markdown",
        include_executive_summary: bool = True,
        include_student_details: bool = True,
        include_action_items: bool = True,
        include_timeline_analysis: bool = True
    ) -> dict[str, Any]:
        """Generate comprehensive peer review completion report."""

        try:
            # Get analytics data
            analytics = await self.get_completion_analytics(
                course_id, assignment_id, include_student_details=True
            )

            if "error" in analytics:
                return analytics

            # Get assignment info
            assignments_data = await self.get_assignments(course_id, assignment_id)
            if "error" in assignments_data:
                return assignments_data

            assignment_info = assignments_data["assignment_info"]

            if report_format == "markdown":
                return self._generate_markdown_report(
                    analytics, assignment_info, include_executive_summary,
                    include_student_details, include_action_items, include_timeline_analysis
                )
            elif report_format == "csv":
                return self._generate_csv_report(analytics, assignment_info)
            elif report_format == "json":
                return {
                    "assignment_info": assignment_info,
                    "analytics": analytics,
                    "generated_at": datetime.datetime.now().isoformat()
                }
            else:
                return {"error": f"Unsupported report format: {report_format}"}

        except Exception as e:
            return {"error": f"Exception in generate_report: {str(e)}"}

    def _generate_markdown_report(
        self,
        analytics: dict[str, Any],
        assignment_info: dict[str, Any],
        include_executive_summary: bool,
        include_student_details: bool,
        include_action_items: bool,
        include_timeline_analysis: bool
    ) -> dict[str, str]:
        """Generate a markdown-formatted report."""

        summary = analytics["summary"]
        completion_groups = analytics.get("completion_groups", {})

        report_lines = []

        # Header
        report_lines.extend([
            "# Peer Review Completion Report",
            f"**Assignment:** {assignment_info['name']} (ID: {assignment_info['id']})",
            f"**Generated:** {datetime.datetime.now().strftime('%B %d, %Y')}",
            "",
            "---",
            ""
        ])

        # Executive Summary
        if include_executive_summary:
            report_lines.extend([
                "## Executive Summary",
                "",
                "| Metric | Count | Percentage |",
                "|--------|-------|------------|",
                f"| **Total Students Enrolled** | {summary['total_students_enrolled']} | 100% |",
                f"| **Students with Submissions** | {summary['students_with_submissions']} | {round(summary['students_with_submissions']/summary['total_students_enrolled']*100, 1)}% |",
                f"| **Total Peer Reviews Assigned** | {summary['total_reviews_assigned']} | - |",
                f"| **Peer Reviews Completed** | {summary['reviews_completed']} | {summary['completion_rate_percent']}% |",
                f"| **Students with All Reviews Complete** | {summary['students_all_complete']} | {round(summary['students_all_complete']/summary['total_students_enrolled']*100, 1)}% |",
                "",
                "---",
                ""
            ])

        # Action items
        if include_action_items:
            urgent_students = completion_groups.get("none_complete", [])
            partial_students = completion_groups.get("partial_complete", [])

            if urgent_students:
                report_lines.extend([
                    "## 🚨 Immediate Action Required",
                    "",
                    f"**Students with NO peer reviews completed ({len(urgent_students)} students):**",
                ])

                for student in urgent_students[:5]:  # Show first 5
                    pending_reviews = student.get("pending_reviews", [])
                    reviewee_names = [pr["reviewee_name"] for pr in pending_reviews[:2]]
                    report_lines.append(
                        f"- {student['student_name']} (ID: {student['student_id']}): "
                        f"Assigned to review {' and '.join(reviewee_names)} "
                        f"({student['completed_count']}/{student['assigned_count']} complete)"
                    )

                if len(urgent_students) > 5:
                    report_lines.append(f"- [{len(urgent_students) - 5} more students...]")

                report_lines.extend([
                    "",
                    "**Contact Information:**",
                    "- Send urgent reminder emails",
                    "- Consider deadline extensions",
                    "- Follow up within 24 hours",
                    "",
                    "---",
                    ""
                ])

            if partial_students:
                report_lines.extend([
                    "## ⚠️ Partial Completion Follow-up",
                    "",
                    f"**Students with partial reviews completed ({len(partial_students)} students):**",
                ])

                for student in partial_students[:5]:  # Show first 5
                    pending_reviews = student.get("pending_reviews", [])
                    if pending_reviews:
                        pending_name = pending_reviews[0]["reviewee_name"]
                        report_lines.append(
                            f"- {student['student_name']}: "
                            f"{student['completed_count']}/{student['assigned_count']} complete, "
                            f"pending review of {pending_name}"
                        )

                if len(partial_students) > 5:
                    report_lines.append(f"- [{len(partial_students) - 5} more students...]")

                report_lines.extend([
                    "",
                    "---",
                    ""
                ])

        # Fully engaged students
        complete_students = completion_groups.get("all_complete", [])
        if complete_students:
            report_lines.extend([
                f"## ✅ Fully Engaged Students ({len(complete_students)} students)",
                "",
                "**Students with all peer reviews completed:**",
                "- High participation rate indicates good course engagement",
                "- Consider highlighting exemplary completion in class",
                "",
                "---",
                ""
            ])

        # Recommendations
        if include_action_items:
            report_lines.extend([
                "## Recommendations",
                "",
                "### Immediate (Next 24 hours)",
                f"1. Contact {len(urgent_students)} students with zero completions",
                f"2. Send automated reminder to {len(partial_students)} partial completions",
                "",
                "### Short-term (Next week)",
                "1. Review peer review assignment timing",
                "2. Consider automated reminders for future assignments",
                "",
                "### Process Improvements",
                "1. Set peer review assignments 24-48 hours after due date",
                "2. Implement interim completion checkpoints",
                "3. Add peer review completion to participation grade",
                "",
                "---",
                "",
                "*Report generated using Canvas Peer Review Analytics Tool*"
            ])

        return {"report": "\n".join(report_lines)}

    def _generate_csv_report(self, analytics: dict[str, Any], assignment_info: dict[str, Any]) -> dict[str, str]:
        """Generate a CSV-formatted report."""

        csv_lines = [
            "student_id,student_name,assigned_count,completed_count,completion_rate,status,pending_reviews,priority_level"
        ]

        completion_groups = analytics.get("completion_groups", {})

        # Add urgent students
        for student in completion_groups.get("none_complete", []):
            pending_reviews = "; ".join([
                f"{pr['reviewee_name']} ({pr['reviewee_id']})"
                for pr in student.get("pending_reviews", [])
            ])
            csv_lines.append(
                f"{student['student_id']},{student['student_name']},"
                f"{student['assigned_count']},{student['completed_count']},"
                f"{student['completion_rate']},none_complete,"
                f"\"{pending_reviews}\",urgent"
            )

        # Add partial completion students
        for student in completion_groups.get("partial_complete", []):
            pending_reviews = "; ".join([
                f"{pr['reviewee_name']} ({pr['reviewee_id']})"
                for pr in student.get("pending_reviews", [])
            ])
            csv_lines.append(
                f"{student['student_id']},{student['student_name']},"
                f"{student['assigned_count']},{student['completed_count']},"
                f"{student['completion_rate']},partial_complete,"
                f"\"{pending_reviews}\",medium"
            )

        # Add complete students
        for student in completion_groups.get("all_complete", []):
            csv_lines.append(
                f"{student['student_id']},{student['student_name']},"
                f"{student['assigned_count']},{student['completed_count']},"
                f"{student['completion_rate']},all_complete,,low"
            )

        return {"report": "\n".join(csv_lines)}

    async def get_followup_list(
        self,
        course_id: int,
        assignment_id: int,
        priority_filter: str = "all",
        include_contact_info: bool = False,
        days_threshold: int = 3
    ) -> dict[str, Any]:
        """Get prioritized list of students requiring instructor follow-up."""

        try:
            # Get completion analytics
            analytics = await self.get_completion_analytics(
                course_id, assignment_id, include_student_details=True
            )

            if "error" in analytics:
                return analytics

            # Get assignment info
            assignments_data = await self.get_assignments(course_id, assignment_id)
            if "error" in assignments_data:
                return assignments_data

            assignment_info = assignments_data["assignment_info"]
            completion_groups = analytics.get("completion_groups", {})

            # Calculate days since assignment
            days_since_assigned = days_threshold  # Default value

            # Process followup categories
            followup_categories = {
                "urgent": {
                    "description": "Students with 0 peer reviews completed",
                    "count": len(completion_groups.get("none_complete", [])),
                    "students": []
                },
                "medium": {
                    "description": "Students with partial completion",
                    "count": len(completion_groups.get("partial_complete", [])),
                    "students": []
                },
                "low": {
                    "description": "Students with all reviews completed - no action needed",
                    "count": len(completion_groups.get("all_complete", []))
                }
            }

            # Add urgent students
            for student in completion_groups.get("none_complete", []):
                student_data = {
                    "student_id": student["student_id"],
                    "student_name": student["student_name"],
                    "assigned_count": student["assigned_count"],
                    "completed_count": student["completed_count"],
                    "completion_rate": student["completion_rate"],
                    "days_since_assigned": days_since_assigned,
                    "pending_reviews": student.get("pending_reviews", []),
                    "recommended_action": "Send urgent reminder email"
                }

                if include_contact_info:
                    student_data["contact_email"] = "student@illinois.edu"  # Placeholder

                followup_categories["urgent"]["students"].append(student_data)

            # Add medium priority students
            for student in completion_groups.get("partial_complete", []):
                student_data = {
                    "student_id": student["student_id"],
                    "student_name": student["student_name"],
                    "assigned_count": student["assigned_count"],
                    "completed_count": student["completed_count"],
                    "completion_rate": student["completion_rate"],
                    "pending_reviews": student.get("pending_reviews", []),
                    "recommended_action": "Send gentle reminder"
                }

                if include_contact_info:
                    student_data["contact_email"] = "student@illinois.edu"  # Placeholder

                followup_categories["medium"]["students"].append(student_data)

            # Filter by priority if specified
            if priority_filter != "all":
                filtered_categories = {priority_filter: followup_categories.get(priority_filter, {})}
                followup_categories = filtered_categories

            # Generate recommended actions
            recommended_actions = {
                "immediate": [
                    f"Send urgent emails to {followup_categories.get('urgent', {}).get('count', 0)} students with zero completion"
                ],
                "this_week": [
                    f"Send automated reminder to {followup_categories.get('medium', {}).get('count', 0)} partial completion students",
                    "Review peer review timing for future assignments"
                ],
                "next_assignment": [
                    "Implement 48-hour buffer between due date and peer review assignment",
                    "Add peer review completion tracking to gradebook"
                ]
            }

            return {
                "generated_at": datetime.datetime.now().isoformat(),
                "assignment_info": {
                    "id": assignment_info["id"],
                    "name": assignment_info["name"],
                    "days_since_assigned": days_since_assigned
                },
                "followup_categories": followup_categories,
                "recommended_actions": recommended_actions
            }

        except Exception as e:
            return {"error": f"Exception in get_followup_list: {str(e)}"}
