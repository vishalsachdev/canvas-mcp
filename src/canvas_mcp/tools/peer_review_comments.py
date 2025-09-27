"""Peer review comment extraction and analysis MCP tools for Canvas API."""

import csv
import json
import sys
from datetime import datetime
from typing import Any

from mcp.server.fastmcp import FastMCP

from ..core.cache import get_course_id
from ..core.client import make_canvas_request
from ..core.peer_review_comments import PeerReviewCommentAnalyzer
from ..core.validation import validate_params


def register_peer_review_comment_tools(mcp: FastMCP):
    """Register all peer review comment analysis MCP tools."""

    @mcp.tool()
    @validate_params
    async def get_peer_review_comments(
        course_identifier: str | int,
        assignment_id: str | int,
        include_reviewer_info: bool = True,
        include_reviewee_info: bool = True,
        include_submission_context: bool = False,
        anonymize_students: bool = False
    ) -> str:
        """
        Retrieve actual comment text for peer reviews on a specific assignment.

        Args:
            course_identifier: Canvas course code (e.g., badm_554_120251_246794) or ID
            assignment_id: Canvas assignment ID
            include_reviewer_info: Include reviewer student information
            include_reviewee_info: Include reviewee student information
            include_submission_context: Include original submission details
            anonymize_students: Replace student names with anonymous IDs
        """
        try:
            course_id = await get_course_id(course_identifier)
            analyzer = PeerReviewCommentAnalyzer()

            result = await analyzer.get_peer_review_comments(
                course_id=course_id,
                assignment_id=int(assignment_id),
                include_reviewer_info=include_reviewer_info,
                include_reviewee_info=include_reviewee_info,
                include_submission_context=include_submission_context,
                anonymize_students=anonymize_students
            )

            if "error" in result:
                return f"Error getting peer review comments: {result['error']}"

            return json.dumps(result, indent=2)

        except Exception as e:
            return f"Error in get_peer_review_comments: {str(e)}"

    @mcp.tool()
    @validate_params
    async def analyze_peer_review_quality(
        course_identifier: str | int,
        assignment_id: str | int,
        analysis_criteria: str | None = None,
        generate_report: bool = True
    ) -> str:
        """
        Analyze the quality and content of peer review comments.

        Args:
            course_identifier: Canvas course code or ID
            assignment_id: Canvas assignment ID
            analysis_criteria: JSON string of custom analysis criteria (optional)
            generate_report: Whether to generate detailed analysis report
        """
        try:
            course_id = await get_course_id(course_identifier)
            analyzer = PeerReviewCommentAnalyzer()

            # Parse analysis criteria if provided
            criteria = None
            if analysis_criteria:
                try:
                    criteria = json.loads(analysis_criteria)
                except json.JSONDecodeError:
                    return "Error: analysis_criteria must be valid JSON"

            result = await analyzer.analyze_peer_review_quality(
                course_id=course_id,
                assignment_id=int(assignment_id),
                analysis_criteria=criteria,
                generate_report=generate_report
            )

            if "error" in result:
                return f"Error analyzing peer review quality: {result['error']}"

            return json.dumps(result, indent=2)

        except Exception as e:
            return f"Error in analyze_peer_review_quality: {str(e)}"

    @mcp.tool()
    @validate_params
    async def identify_problematic_peer_reviews(
        course_identifier: str | int,
        assignment_id: str | int,
        criteria: str | None = None
    ) -> str:
        """
        Flag reviews that may need instructor attention.

        Args:
            course_identifier: Canvas course code or ID
            assignment_id: Canvas assignment ID
            criteria: JSON string of custom flagging criteria (optional)
        """
        try:
            course_id = await get_course_id(course_identifier)
            analyzer = PeerReviewCommentAnalyzer()

            # Parse criteria if provided
            parsed_criteria = None
            if criteria:
                try:
                    parsed_criteria = json.loads(criteria)
                except json.JSONDecodeError:
                    return "Error: criteria must be valid JSON"

            result = await analyzer.identify_problematic_peer_reviews(
                course_id=course_id,
                assignment_id=int(assignment_id),
                criteria=parsed_criteria
            )

            if "error" in result:
                return f"Error identifying problematic reviews: {result['error']}"

            return json.dumps(result, indent=2)

        except Exception as e:
            return f"Error in identify_problematic_peer_reviews: {str(e)}"

    @mcp.tool()
    @validate_params
    async def extract_peer_review_dataset(
        course_identifier: str | int,
        assignment_id: str | int,
        output_format: str = "csv",
        include_analytics: bool = True,
        anonymize_data: bool = True,
        save_locally: bool = True,
        filename: str | None = None
    ) -> str:
        """
        Export all peer review data in various formats for analysis.

        Args:
            course_identifier: Canvas course code or ID
            assignment_id: Canvas assignment ID
            output_format: Output format (csv, json, xlsx)
            include_analytics: Include quality analytics in output
            anonymize_data: Anonymize student data
            save_locally: Save file locally
            filename: Custom filename (optional)
        """
        try:
            course_id = await get_course_id(course_identifier)
            analyzer = PeerReviewCommentAnalyzer()

            # Get the comment data
            comments_data = await analyzer.get_peer_review_comments(
                course_id=course_id,
                assignment_id=int(assignment_id),
                include_reviewer_info=True,
                include_reviewee_info=True,
                include_submission_context=True,
                anonymize_students=anonymize_data
            )

            if "error" in comments_data:
                return f"Error getting comments data: {comments_data['error']}"

            # Generate filename if not provided
            if not filename:
                assignment_name = comments_data.get("assignment_info", {}).get("assignment_name", "assignment")
                safe_name = "".join(c for c in assignment_name if c.isalnum() or c in (' ', '-', '_')).rstrip()
                filename = f"peer_reviews_{safe_name}_{assignment_id}"

            # Include analytics if requested
            if include_analytics:
                analytics_data = await analyzer.analyze_peer_review_quality(
                    course_id=course_id,
                    assignment_id=int(assignment_id)
                )
                if "error" not in analytics_data:
                    comments_data["quality_analytics"] = analytics_data

            # Export based on format
            if output_format.lower() == "json":
                output_filename = f"{filename}.json"
                if save_locally:
                    with open(output_filename, 'w', encoding='utf-8') as f:
                        json.dump(comments_data, f, indent=2, ensure_ascii=False)
                    return f"Data exported to {output_filename}"
                else:
                    return json.dumps(comments_data, indent=2)

            elif output_format.lower() == "csv":
                output_filename = f"{filename}.csv"
                if save_locally:
                    with open(output_filename, 'w', newline='', encoding='utf-8') as f:
                        writer = csv.writer(f)

                        # Write header
                        writer.writerow([
                            'review_id', 'reviewer_id', 'reviewer_name', 'reviewee_id', 'reviewee_name',
                            'comment_text', 'word_count', 'character_count', 'timestamp'
                        ])

                        # Write data
                        for review in comments_data.get("peer_reviews", []):
                            reviewer = review.get("reviewer", {})
                            reviewee = review.get("reviewee", {})
                            content = review.get("review_content", {})

                            writer.writerow([
                                review.get("review_id", ""),
                                reviewer.get("student_id", ""),
                                reviewer.get("student_name", ""),
                                reviewee.get("student_id", ""),
                                reviewee.get("student_name", ""),
                                content.get("comment_text", ""),
                                content.get("word_count", 0),
                                content.get("character_count", 0),
                                content.get("timestamp", "")
                            ])

                    return f"Data exported to {output_filename}"
                else:
                    # Return CSV as string
                    csv_lines = []
                    csv_lines.append("review_id,reviewer_id,reviewer_name,reviewee_id,reviewee_name,comment_text,word_count,character_count,timestamp")

                    for review in comments_data.get("peer_reviews", []):
                        reviewer = review.get("reviewer", {})
                        reviewee = review.get("reviewee", {})
                        content = review.get("review_content", {})

                        # Escape quotes in comment text
                        comment_text = content.get("comment_text", "").replace('"', '""')

                        csv_lines.append(f'"{review.get("review_id", "")}","{reviewer.get("student_id", "")}","{reviewer.get("student_name", "")}","{reviewee.get("student_id", "")}","{reviewee.get("student_name", "")}","{comment_text}",{content.get("word_count", 0)},{content.get("character_count", 0)},"{content.get("timestamp", "")}"')

                    return "\n".join(csv_lines)

            else:
                return f"Error: Unsupported output format '{output_format}'. Supported formats: csv, json"

        except Exception as e:
            return f"Error in extract_peer_review_dataset: {str(e)}"

    @mcp.tool()
    @validate_params
    async def generate_peer_review_feedback_report(
        course_identifier: str | int,
        assignment_id: str | int,
        report_type: str = "comprehensive",
        include_student_names: bool = False,
        format_type: str = "markdown"
    ) -> str:
        """
        Create instructor-ready reports on peer review quality.

        Args:
            course_identifier: Canvas course code or ID
            assignment_id: Canvas assignment ID
            report_type: Report type (comprehensive, summary, individual)
            include_student_names: Whether to include student names
            format_type: Output format (markdown, html, text)
        """
        try:
            course_id = await get_course_id(course_identifier)
            analyzer = PeerReviewCommentAnalyzer()

            # Get analytics data
            analytics_data = await analyzer.analyze_peer_review_quality(
                course_id=course_id,
                assignment_id=int(assignment_id)
            )

            if "error" in analytics_data:
                return f"Error getting analytics data: {analytics_data['error']}"

            # Get problematic reviews
            problematic_data = await analyzer.identify_problematic_peer_reviews(
                course_id=course_id,
                assignment_id=int(assignment_id)
            )

            # Get assignment info
            assignment_response = await make_canvas_request(
                "get",
                f"/courses/{course_id}/assignments/{assignment_id}"
            )
            assignment_name = assignment_response.get("name", "Unknown Assignment") if "error" not in assignment_response else "Unknown Assignment"

            # Generate report based on type
            if format_type.lower() == "markdown":
                return _generate_markdown_report(
                    analytics_data, problematic_data, assignment_name, report_type
                )
            else:
                return f"Error: Unsupported format '{format_type}'. Currently only 'markdown' is supported."

        except Exception as e:
            return f"Error in generate_peer_review_feedback_report: {str(e)}"

    print("Peer review comment analysis tools registered successfully!", file=sys.stderr)


def _generate_markdown_report(
    analytics_data: dict[str, Any],
    problematic_data: dict[str, Any],
    assignment_name: str,
    report_type: str
) -> str:
    """Generate a markdown report from analytics data."""

    overall = analytics_data.get("overall_analysis", {})
    metrics = analytics_data.get("detailed_metrics", {})
    flagged = analytics_data.get("flagged_reviews", [])
    recommendations = analytics_data.get("recommendations", [])

    word_stats = metrics.get("word_count_stats", {})
    constructiveness = metrics.get("constructiveness_analysis", {})
    sentiment = metrics.get("sentiment_analysis", {})

    problematic_summary = problematic_data.get("flag_summary", {})

    report_lines = [
        f"# Peer Review Quality Report: {assignment_name}",
        "",
        f"**Generated on:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"**Report Type:** {report_type.title()}",
        "",
        "## Executive Summary",
        "",
        f"- **Total Reviews Analyzed:** {overall.get('total_reviews_analyzed', 0)}",
        f"- **Average Quality Score:** {overall.get('average_quality_score', 0)}/5.0",
        f"- **High Quality Reviews:** {overall.get('quality_distribution', {}).get('high_quality', 0)}",
        f"- **Medium Quality Reviews:** {overall.get('quality_distribution', {}).get('medium_quality', 0)}",
        f"- **Low Quality Reviews:** {overall.get('quality_distribution', {}).get('low_quality', 0)}",
        "",
        "## Word Count Statistics",
        "",
        f"- **Average Words per Comment:** {word_stats.get('mean', 0)}",
        f"- **Median Words:** {word_stats.get('median', 0)}",
        f"- **Range:** {word_stats.get('min', 0)} - {word_stats.get('max', 0)} words",
        f"- **Standard Deviation:** {word_stats.get('std_dev', 0)}",
        "",
        "## Comment Quality Analysis",
        "",
        f"- **Constructive Feedback:** {constructiveness.get('constructive_feedback_count', 0)} reviews",
        f"- **Generic Comments:** {constructiveness.get('generic_comments', 0)} reviews",
        f"- **Specific Suggestions:** {constructiveness.get('specific_suggestions', 0)} reviews",
        "",
        "## Sentiment Distribution",
        "",
        f"- **Positive Sentiment:** {sentiment.get('positive_sentiment', 0)*100:.1f}%",
        f"- **Neutral Sentiment:** {sentiment.get('neutral_sentiment', 0)*100:.1f}%",
        f"- **Negative Sentiment:** {sentiment.get('negative_sentiment', 0)*100:.1f}%",
        ""
    ]

    if problematic_summary:
        report_lines.extend([
            "## Flagged Issues",
            "",
        ])
        for flag_type, count in problematic_summary.items():
            flag_name = flag_type.replace("_", " ").title()
            report_lines.append(f"- **{flag_name}:** {count} reviews")
        report_lines.append("")

    if flagged and report_type == "comprehensive":
        report_lines.extend([
            "## Sample Low-Quality Reviews",
            "",
        ])
        for i, review in enumerate(flagged[:5]):  # Show top 5
            report_lines.extend([
                f"### Review {i+1}",
                f"- **Quality Score:** {review.get('quality_score', 0)}/5.0",
                f"- **Word Count:** {review.get('word_count', 0)}",
                f"- **Flag Reason:** {review.get('flag_reason', 'Unknown')}",
                f"- **Comment Preview:** \"{review.get('comment', 'No comment')}\"",
                ""
            ])

    if recommendations:
        report_lines.extend([
            "## Recommendations",
            "",
        ])
        for i, rec in enumerate(recommendations, 1):
            report_lines.append(f"{i}. {rec}")
        report_lines.append("")

    report_lines.extend([
        "---",
        "*Generated by Canvas MCP Peer Review Comment Analyzer*"
    ])

    return "\n".join(report_lines)
