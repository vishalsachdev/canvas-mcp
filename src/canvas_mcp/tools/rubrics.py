"""Rubric-related MCP tools for Canvas API."""

import json
from typing import Any

from mcp.server.fastmcp import FastMCP

from ..core.anonymization import anonymize_response_data
from ..core.cache import get_course_code, get_course_id
from ..core.client import fetch_all_paginated_results, make_canvas_request
from ..core.dates import format_date, truncate_text
from ..core.logging import log_error
from ..core.validation import validate_params


def preprocess_criteria_string(criteria_string: str) -> str:
    """Preprocess criteria string to handle common formatting issues.

    Args:
        criteria_string: Raw criteria string that might have formatting issues

    Returns:
        Cleaned criteria string ready for JSON parsing
    """
    # Strip whitespace
    cleaned = criteria_string.strip()

    # Handle cases where quotes might be escaped incorrectly
    # This is a common issue with string serialization
    if cleaned.startswith('"{') and cleaned.endswith('}"'):
        # Remove outer quotes and unescape inner quotes
        cleaned = cleaned[1:-1].replace('\\"', '"').replace('\\\\', '\\')

    return cleaned


def validate_rubric_criteria(criteria_json: str) -> dict[str, Any]:
    """Validate and parse rubric criteria JSON structure.

    Args:
        criteria_json: JSON string containing rubric criteria

    Returns:
        Parsed criteria dictionary

    Raises:
        ValueError: If JSON is invalid or structure is incorrect
    """
    # Preprocess the string to handle common issues
    cleaned_json = preprocess_criteria_string(criteria_json)

    try:
        criteria = json.loads(cleaned_json)
    except json.JSONDecodeError as e:
        # Try alternative parsing methods if JSON fails
        try:
            # Maybe it's a Python literal string representation
            import ast
            criteria = ast.literal_eval(cleaned_json)
            if isinstance(criteria, dict):
                # Successfully parsed as Python literal, continue with validation
                pass
            else:
                raise ValueError("Parsed result is not a dictionary")
        except (ValueError, SyntaxError):
            # Both JSON and literal_eval failed, provide detailed error
            error_msg = f"Invalid JSON format: {str(e)}\n"
            error_msg += f"Original string length: {len(criteria_json)}\n"
            error_msg += f"Cleaned string length: {len(cleaned_json)}\n"
            error_msg += f"First 200 characters of original: {repr(criteria_json[:200])}\n"
            error_msg += f"First 200 characters of cleaned: {repr(cleaned_json[:200])}\n"
            if len(cleaned_json) > 200:
                error_msg += f"Last 100 characters of cleaned: {repr(cleaned_json[-100:])}"
            error_msg += "\nAlso failed to parse as Python literal. Please ensure the criteria is valid JSON."
            raise ValueError(error_msg) from e

    if not isinstance(criteria, dict):
        raise ValueError("Criteria must be a JSON object (dictionary)")

    # Validate each criterion
    for criterion_key, criterion_data in criteria.items():
        if not isinstance(criterion_data, dict):
            raise ValueError(f"Criterion {criterion_key} must be an object")

        if "description" not in criterion_data:
            raise ValueError(f"Criterion {criterion_key} must have a 'description' field")

        if "points" not in criterion_data:
            raise ValueError(f"Criterion {criterion_key} must have a 'points' field")

        try:
            points = float(criterion_data["points"])
            if points < 0:
                raise ValueError(f"Criterion {criterion_key} points must be non-negative")
        except (ValueError, TypeError) as err:
            raise ValueError(f"Criterion {criterion_key} points must be a valid number") from err

        # Validate ratings if present - handle both object and array formats
        if "ratings" in criterion_data:
            ratings = criterion_data["ratings"]

            # Handle both object and array formats
            if isinstance(ratings, dict):
                # Object format: {"1": {...}, "2": {...}}
                for rating_key, rating_data in ratings.items():
                    if not isinstance(rating_data, dict):
                        raise ValueError(f"Rating {rating_key} in criterion {criterion_key} must be an object")

                    if "description" not in rating_data:
                        raise ValueError(f"Rating {rating_key} in criterion {criterion_key} must have a 'description' field")

                    if "points" not in rating_data:
                        raise ValueError(f"Rating {rating_key} in criterion {criterion_key} must have a 'points' field")

                    try:
                        rating_points = float(rating_data["points"])
                        if rating_points < 0:
                            raise ValueError(f"Rating {rating_key} points must be non-negative")
                    except (ValueError, TypeError) as err:
                        raise ValueError(f"Rating {rating_key} points must be a valid number") from err

            elif isinstance(ratings, list):
                # Array format: [{"description": ..., "points": ...}, ...]
                for i, rating_data in enumerate(ratings):
                    if not isinstance(rating_data, dict):
                        raise ValueError(f"Rating {i} in criterion {criterion_key} must be an object")

                    if "description" not in rating_data:
                        raise ValueError(f"Rating {i} in criterion {criterion_key} must have a 'description' field")

                    if "points" not in rating_data:
                        raise ValueError(f"Rating {i} in criterion {criterion_key} must have a 'points' field")

                    try:
                        rating_points = float(rating_data["points"])
                        if rating_points < 0:
                            raise ValueError(f"Rating {i} points must be non-negative")
                    except (ValueError, TypeError) as err:
                        raise ValueError(f"Rating {i} points must be a valid number") from err

            else:
                raise ValueError(f"Criterion {criterion_key} ratings must be an object or array")

    return criteria


def format_rubric_response(response: dict[str, Any]) -> str:
    """Format Canvas API rubric response into readable text.

    Args:
        response: Canvas API response (may be non-standard format)

    Returns:
        Formatted string representation of the rubric
    """
    # Handle Canvas API's non-standard response format
    if "rubric" in response and "rubric_association" in response:
        rubric = response["rubric"]
        association = response["rubric_association"]

        result = "Rubric Created/Updated Successfully!\n\n"
        result += "Rubric Details:\n"
        result += f"  ID: {rubric.get('id', 'N/A')}\n"
        result += f"  Title: {rubric.get('title', 'Untitled')}\n"
        result += f"  Context: {rubric.get('context_type', 'N/A')} (ID: {rubric.get('context_id', 'N/A')})\n"
        result += f"  Points Possible: {rubric.get('points_possible', 0)}\n"
        result += f"  Reusable: {'Yes' if rubric.get('reusable', False) else 'No'}\n"
        result += f"  Free Form Comments: {'Yes' if rubric.get('free_form_criterion_comments', False) else 'No'}\n"

        if association:
            result += "\nAssociation Details:\n"
            result += f"  Associated with: {association.get('association_type', 'N/A')} (ID: {association.get('association_id', 'N/A')})\n"
            result += f"  Used for Grading: {'Yes' if association.get('use_for_grading', False) else 'No'}\n"
            result += f"  Purpose: {association.get('purpose', 'N/A')}\n"

        # Show criteria count
        data = rubric.get('data', [])
        if data:
            result += f"\nCriteria: {len(data)} criterion defined\n"

        return result

    # Handle standard rubric response
    else:
        result = "Rubric Operation Completed!\n\n"
        result += f"ID: {response.get('id', 'N/A')}\n"
        result += f"Title: {response.get('title', 'Untitled')}\n"
        result += f"Points Possible: {response.get('points_possible', 0)}\n"
        return result


def build_criteria_structure(criteria: dict[str, Any]) -> dict[str, Any]:
    """Build Canvas API-compatible criteria structure.

    Args:
        criteria: Validated criteria dictionary

    Returns:
        Canvas API-compatible criteria structure
    """
    # Canvas expects criteria as a flat dictionary with string keys
    formatted_criteria = {}

    for criterion_key, criterion_data in criteria.items():
        formatted_criteria[str(criterion_key)] = {
            "description": criterion_data["description"],
            "points": float(criterion_data["points"]),
            "long_description": criterion_data.get("long_description", "")
        }

        # Handle ratings if present
        if "ratings" in criterion_data:
            ratings = criterion_data["ratings"]

            # Canvas API expects ratings as an array, not object
            # Convert from object format to array format
            formatted_ratings = []

            # Sort ratings by points (highest to lowest) for consistent ordering
            if isinstance(ratings, dict):
                # Convert object-style ratings to array
                rating_items = []
                for _rating_key, rating_data in ratings.items():
                    rating_items.append({
                        "description": rating_data["description"],
                        "points": float(rating_data["points"]),
                        "long_description": rating_data.get("long_description", "")
                    })
                # Sort by points descending
                rating_items.sort(key=lambda x: x["points"], reverse=True)
                formatted_ratings = rating_items
            elif isinstance(ratings, list):
                # Already in array format, just ensure proper typing
                for rating_data in ratings:
                    formatted_ratings.append({
                        "description": rating_data["description"],
                        "points": float(rating_data["points"]),
                        "long_description": rating_data.get("long_description", "")
                    })

            formatted_criteria[str(criterion_key)]["ratings"] = formatted_ratings

    return formatted_criteria


def build_rubric_assessment_form_data(
    rubric_assessment: dict[str, Any],
    comment: str | None = None
) -> dict[str, str]:
    """Convert rubric assessment dict to Canvas form-encoded format.

    Canvas API expects rubric assessment data as form-encoded parameters with
    bracket notation: rubric_assessment[criterion_id][field]=value

    Args:
        rubric_assessment: Dict mapping criterion IDs to assessment data
                          Format: {"criterion_id": {"points": X, "rating_id": Y, "comments": Z}}
        comment: Optional overall comment for the submission

    Returns:
        Flattened dict with Canvas bracket notation keys

    Example:
        Input: {"_8027": {"points": 2, "rating_id": "blank", "comments": "Great work"}}
        Output: {
            "rubric_assessment[_8027][points]": "2",
            "rubric_assessment[_8027][rating_id]": "blank",
            "rubric_assessment[_8027][comments]": "Great work"
        }
    """
    form_data: dict[str, str] = {}

    # Transform rubric_assessment object into Canvas's form-encoded format
    for criterion_id, assessment in rubric_assessment.items():
        # Points are required
        if "points" in assessment:
            form_data[f"rubric_assessment[{criterion_id}][points]"] = str(assessment["points"])

        # Rating ID is optional but recommended
        if "rating_id" in assessment:
            form_data[f"rubric_assessment[{criterion_id}][rating_id]"] = str(assessment["rating_id"])

        # Comments are optional
        if "comments" in assessment:
            form_data[f"rubric_assessment[{criterion_id}][comments]"] = str(assessment["comments"])

    # Add optional overall comment
    if comment:
        form_data["comment[text_comment]"] = comment

    return form_data


def register_rubric_tools(mcp: FastMCP) -> None:
    """Register all rubric-related MCP tools."""

    @mcp.tool()
    @validate_params
    async def list_assignment_rubrics(course_identifier: str | int,
                                    assignment_id: str | int) -> str:
        """Get rubrics attached to a specific assignment.

        Args:
            course_identifier: The Canvas course code (e.g., badm_554_120251_246794) or ID
            assignment_id: The Canvas assignment ID
        """
        course_id = await get_course_id(course_identifier)
        assignment_id_str = str(assignment_id)

        # Get assignment details with rubric information
        response = await make_canvas_request(
            "get",
            f"/courses/{course_id}/assignments/{assignment_id_str}",
            params={"include[]": ["rubric", "rubric_settings"]}
        )

        if "error" in response:
            return f"Error fetching assignment rubrics: {response['error']}"

        # Check if assignment has rubric
        rubric = response.get("rubric")
        rubric_settings = response.get("rubric_settings", {})
        use_rubric_for_grading = response.get("use_rubric_for_grading", False)

        if not rubric:
            assignment_name = response.get("name", "Unknown Assignment")
            course_display = await get_course_code(course_id) or course_identifier
            return f"No rubric found for assignment '{assignment_name}' in course {course_display}."

        # Format rubric information
        assignment_name = response.get("name", "Unknown Assignment")
        course_display = await get_course_code(course_id) or course_identifier

        result = f"Rubric for Assignment '{assignment_name}' in Course {course_display}:\n\n"

        # Rubric settings
        if rubric_settings:
            result += "Rubric Settings:\n"
            result += f"  Used for Grading: {'Yes' if use_rubric_for_grading else 'No'}\n"
            result += f"  Points Possible: {rubric_settings.get('points_possible', 'N/A')}\n"
            result += f"  Hide Score Total: {'Yes' if rubric_settings.get('hide_score_total') else 'No'}\n"
            result += f"  Hide Points: {'Yes' if rubric_settings.get('hide_points') else 'No'}\n\n"

        # Rubric criteria summary
        result += "Criteria Overview:\n"
        total_points = 0

        for i, criterion in enumerate(rubric, 1):
            criterion_description = criterion.get("description", "No description")
            criterion_points = criterion.get("points", 0)
            ratings_count = len(criterion.get("ratings", []))

            result += f"{i}. {criterion_description}\n"
            result += f"   Points: {criterion_points}\n"
            result += f"   Rating Levels: {ratings_count}\n"

            total_points += criterion_points

        result += f"\nTotal Possible Points: {total_points}\n"
        result += f"Number of Criteria: {len(rubric)}\n"

        # Extract rubric ID for use with get_rubric_details
        rubric_id = None
        if rubric and len(rubric) > 0:
            # The rubric ID might be in the first criterion or in rubric_settings
            if rubric_settings and "id" in rubric_settings:
                rubric_id = rubric_settings["id"]
            elif "id" in rubric[0]:
                # Sometimes the rubric ID is embedded in the criteria
                rubric_id = rubric[0].get("id")

        if rubric_id:
            result += f"Rubric ID: {rubric_id}\n"
            result += f"\nTo get detailed criteria descriptions, use: get_assignment_rubric_details with assignment_id {assignment_id}"

        return result

    @mcp.tool()
    @validate_params
    async def get_assignment_rubric_details(course_identifier: str | int,
                                          assignment_id: str | int) -> str:
        """Get detailed rubric criteria and rating descriptions for an assignment.

        Args:
            course_identifier: The Canvas course code (e.g., badm_554_120251_246794) or ID
            assignment_id: The Canvas assignment ID
        """
        course_id = await get_course_id(course_identifier)
        assignment_id_str = str(assignment_id)

        # Get assignment details with full rubric information
        response = await make_canvas_request(
            "get",
            f"/courses/{course_id}/assignments/{assignment_id_str}",
            params={"include[]": ["rubric", "rubric_settings"]}
        )

        if "error" in response:
            return f"Error fetching assignment rubric details: {response['error']}"

        # Check if assignment has rubric
        rubric = response.get("rubric")
        if not rubric:
            assignment_name = response.get("name", "Unknown Assignment")
            course_display = await get_course_code(course_id) or course_identifier
            return f"No rubric found for assignment '{assignment_name}' in course {course_display}."

        # Format detailed rubric information
        assignment_name = response.get("name", "Unknown Assignment")
        course_display = await get_course_code(course_id) or course_identifier
        rubric_settings = response.get("rubric_settings", {})
        use_rubric_for_grading = response.get("use_rubric_for_grading", False)

        result = f"Detailed Rubric for Assignment '{assignment_name}' in Course {course_display}:\n\n"

        # Rubric metadata
        result += f"Assignment ID: {assignment_id}\n"
        result += f"Used for Grading: {'Yes' if use_rubric_for_grading else 'No'}\n"
        if rubric_settings:
            result += f"Total Points Possible: {rubric_settings.get('points_possible', 'N/A')}\n"
        result += f"Number of Criteria: {len(rubric)}\n\n"

        # Detailed criteria and ratings
        result += "Detailed Criteria and Rating Scales:\n"
        result += "=" * 60 + "\n"

        total_points = 0
        for i, criterion in enumerate(rubric, 1):
            criterion_id = criterion.get("id", "N/A")
            description = criterion.get("description", "No description")
            long_description = criterion.get("long_description", "")
            points = criterion.get("points", 0)
            ratings = criterion.get("ratings", [])

            result += f"\nCriterion #{i}: {description}\n"
            result += f"Criterion ID: {criterion_id}\n"
            result += f"Maximum Points: {points}\n"

            if long_description and long_description != description:
                result += f"Full Description: {long_description}\n"

            if ratings:
                result += f"\nRating Scale ({len(ratings)} levels):\n"
                # Sort ratings by points (highest to lowest)
                sorted_ratings = sorted(ratings, key=lambda x: x.get("points", 0), reverse=True)

                for _, rating in enumerate(sorted_ratings):
                    rating_description = rating.get("description", "No description")
                    rating_points = rating.get("points", 0)
                    rating_id = rating.get("id", "N/A")
                    long_desc = rating.get("long_description", "")

                    result += f"  {rating_points} pts: {rating_description}"
                    if rating_id != "N/A":
                        result += f" [ID: {rating_id}]"
                    result += "\n"

                    if long_desc and long_desc != rating_description:
                        # Format long description nicely
                        formatted_desc = long_desc.replace("\\n", "\n    ")
                        result += f"    Details: {formatted_desc}\n"
            else:
                result += "No rating scale defined for this criterion.\n"

            total_points += points
            result += "\n" + "-" * 40 + "\n"

        result += f"\nTotal Rubric Points: {total_points}"

        return result

    @mcp.tool()
    @validate_params
    async def get_rubric_details(course_identifier: str | int,
                               rubric_id: str | int) -> str:
        """Get detailed rubric criteria and scoring information.

        Args:
            course_identifier: The Canvas course code (e.g., badm_554_120251_246794) or ID
            rubric_id: The Canvas rubric ID
        """
        course_id = await get_course_id(course_identifier)
        rubric_id_str = str(rubric_id)

        # Get detailed rubric information
        response = await make_canvas_request(
            "get",
            f"/courses/{course_id}/rubrics/{rubric_id_str}",
            params={"include[]": ["assessments", "associations"]}
        )

        if "error" in response:
            return f"Error fetching rubric details: {response['error']}"

        # Extract rubric details
        title = response.get("title", "Untitled Rubric")
        context_code = response.get("context_code", "")
        context_type = response.get("context_type", "")
        points_possible = response.get("points_possible", 0)
        reusable = response.get("reusable", False)
        read_only = response.get("read_only", False)
        data = response.get("data", [])

        course_display = await get_course_code(course_id) or course_identifier

        result = f"Detailed Rubric Information for Course {course_display}:\n\n"
        result += f"Title: {title}\n"
        result += f"Rubric ID: {rubric_id}\n"
        result += f"Context: {context_type} ({context_code})\n"
        result += f"Total Points: {points_possible}\n"
        result += f"Reusable: {'Yes' if reusable else 'No'}\n"
        result += f"Read Only: {'Yes' if read_only else 'No'}\n\n"

        # Detailed criteria and ratings
        if data:
            result += "Detailed Criteria and Ratings:\n"
            result += "=" * 50 + "\n"

            for i, criterion in enumerate(data, 1):
                criterion_id = criterion.get("id", "N/A")
                description = criterion.get("description", "No description")
                long_description = criterion.get("long_description", "")
                points = criterion.get("points", 0)
                ratings = criterion.get("ratings", [])

                result += f"\nCriterion #{i}: {description}\n"
                result += f"ID: {criterion_id}\n"
                result += f"Points: {points}\n"

                if long_description:
                    result += f"Description: {truncate_text(long_description, 200)}\n"

                if ratings:
                    result += f"Rating Levels ({len(ratings)}):\n"
                    for j, rating in enumerate(ratings):
                        rating_description = rating.get("description", "No description")
                        rating_points = rating.get("points", 0)
                        rating_id = rating.get("id", "N/A")

                        result += f"  {j+1}. {rating_description} ({rating_points} pts) [ID: {rating_id}]\n"

                        if rating.get("long_description"):
                            result += f"     {truncate_text(rating.get('long_description'), 100)}\n"

                result += "\n"

        return result

    @mcp.tool()
    @validate_params
    async def get_submission_rubric_assessment(course_identifier: str | int,
                                             assignment_id: str | int,
                                             user_id: str | int) -> str:
        """Get rubric assessment scores for a specific submission.

        Args:
            course_identifier: The Canvas course code (e.g., badm_554_120251_246794) or ID
            assignment_id: The Canvas assignment ID
            user_id: The Canvas user ID of the student
        """
        course_id = await get_course_id(course_identifier)
        assignment_id_str = str(assignment_id)
        user_id_str = str(user_id)

        # Get submission with rubric assessment
        response = await make_canvas_request(
            "get",
            f"/courses/{course_id}/assignments/{assignment_id_str}/submissions/{user_id_str}",
            params={"include[]": ["rubric_assessment", "full_rubric_assessment"]}
        )

        if "error" in response:
            return f"Error fetching submission rubric assessment: {response['error']}"

        # Anonymize submission data to protect student privacy
        try:
            response = anonymize_response_data(response, data_type="submissions")
        except Exception as e:
            log_error(
                "Failed to anonymize rubric assessment data",
                exc=e,
                course_id=course_id,
                assignment_id=assignment_id,
                user_id=user_id
            )
            # Continue with original data for functionality

        # Check if submission has rubric assessment
        rubric_assessment = response.get("rubric_assessment")

        if not rubric_assessment:
            # Get user and assignment names for better error message
            assignment_response = await make_canvas_request(
                "get", f"/courses/{course_id}/assignments/{assignment_id_str}"
            )
            assignment_name = assignment_response.get("name", "Unknown Assignment") if "error" not in assignment_response else "Unknown Assignment"

            course_display = await get_course_code(course_id) or course_identifier
            return f"No rubric assessment found for user {user_id} on assignment '{assignment_name}' in course {course_display}."

        # Get assignment details for context
        assignment_response = await make_canvas_request(
            "get", f"/courses/{course_id}/assignments/{assignment_id_str}",
            params={"include[]": ["rubric"]}
        )

        assignment_name = assignment_response.get("name", "Unknown Assignment") if "error" not in assignment_response else "Unknown Assignment"
        rubric_data = assignment_response.get("rubric", []) if "error" not in assignment_response else []

        # Format rubric assessment
        course_display = await get_course_code(course_id) or course_identifier

        result = f"Rubric Assessment for User {user_id} on '{assignment_name}' in Course {course_display}:\n\n"

        # Submission details
        submitted_at = format_date(response.get("submitted_at"))
        graded_at = format_date(response.get("graded_at"))
        score = response.get("score", "Not graded")

        result += "Submission Details:\n"
        result += f"  Submitted: {submitted_at}\n"
        result += f"  Graded: {graded_at}\n"
        result += f"  Score: {score}\n\n"

        # Rubric assessment details
        result += "Rubric Assessment:\n"
        result += "=" * 30 + "\n"

        total_rubric_points = 0

        for criterion_id, assessment in rubric_assessment.items():
            # Find criterion details from rubric data
            criterion_info = None
            for criterion in rubric_data:
                if str(criterion.get("id")) == str(criterion_id):
                    criterion_info = criterion
                    break

            criterion_description = criterion_info.get("description", f"Criterion {criterion_id}") if criterion_info else f"Criterion {criterion_id}"
            points = assessment.get("points", 0)
            comments = assessment.get("comments", "")
            rating_id = assessment.get("rating_id")

            result += f"\n{criterion_description}:\n"
            result += f"  Points Awarded: {points}\n"

            if rating_id and criterion_info:
                # Find the rating description
                for rating in criterion_info.get("ratings", []):
                    if str(rating.get("id")) == str(rating_id):
                        result += f"  Rating: {rating.get('description', 'N/A')} ({rating.get('points', 0)} pts)\n"
                        break

            if comments:
                result += f"  Comments: {comments}\n"

            total_rubric_points += points

        result += f"\nTotal Rubric Points: {total_rubric_points}"

        return result

    @mcp.tool()
    @validate_params
    async def grade_with_rubric(course_identifier: str | int,
                              assignment_id: str | int,
                              user_id: str | int,
                              rubric_assessment: dict[str, Any],
                              comment: str | None = None) -> str:
        """Submit grades using rubric criteria.

        This tool submits grades for individual rubric criteria. The rubric must already be
        associated with the assignment and configured for grading (use_for_grading=true).

        IMPORTANT NOTES:
        - Criterion IDs often start with underscore (e.g., "_8027")
        - Use list_assignment_rubrics or get_rubric_details to find criterion IDs and rating IDs
        - Points must be within the range defined by the rubric criterion
        - The rubric must be attached to the assignment before grading

        Args:
            course_identifier: The Canvas course code (e.g., badm_554_120251_246794) or ID
            assignment_id: The Canvas assignment ID
            user_id: The Canvas user ID of the student
            rubric_assessment: Dict mapping criterion IDs to assessment data
                             Format: {
                               "criterion_id": {
                                 "points": <number>,           # Required: points awarded
                                 "rating_id": "<string>",      # Optional: specific rating ID
                                 "comments": "<string>"        # Optional: feedback comments
                               }
                             }
            comment: Optional overall comment for the submission

        Example Usage:
            {
              "course_identifier": "60366",
              "assignment_id": "1440586",
              "user_id": "9824",
              "rubric_assessment": {
                "_8027": {
                  "points": 2,
                  "rating_id": "blank",
                  "comments": "Great work!"
                }
              },
              "comment": "Nice job on this assignment"
            }
        """
        course_id = await get_course_id(course_identifier)
        assignment_id_str = str(assignment_id)
        user_id_str = str(user_id)

        # CRITICAL: Verify rubric is configured for grading BEFORE submitting
        assignment_check = await make_canvas_request(
            "get",
            f"/courses/{course_id}/assignments/{assignment_id_str}",
            params={"include[]": ["rubric_settings"]}
        )

        if "error" not in assignment_check:
            use_rubric_for_grading = assignment_check.get("use_rubric_for_grading", False)
            if not use_rubric_for_grading:
                return (
                    "⚠️  ERROR: Rubric is not configured for grading!\n\n"
                    "The rubric exists but 'use_for_grading' is set to FALSE.\n"
                    "Grades will NOT be saved to the gradebook.\n\n"
                    "To fix this:\n"
                    "1. Use list_assignment_rubrics to verify rubric settings\n"
                    "2. Use associate_rubric_with_assignment with use_for_grading=True\n"
                    "3. Or configure the rubric in Canvas UI: Assignment Settings → Rubric → Use for Grading\n\n"
                    f"Assignment: {assignment_check.get('name', 'Unknown')}\n"
                    f"Course ID: {course_id}\n"
                    f"Assignment ID: {assignment_id}\n"
                )

        # Build form data in Canvas's expected format
        form_data = build_rubric_assessment_form_data(rubric_assessment, comment)

        # Submit the grade with rubric assessment using form encoding
        response = await make_canvas_request(
            "put",
            f"/courses/{course_id}/assignments/{assignment_id_str}/submissions/{user_id_str}",
            data=form_data,
            use_form_data=True
        )

        if "error" in response:
            return f"Error submitting rubric grade: {response['error']}"

        # Get assignment details for confirmation
        assignment_response = await make_canvas_request(
            "get", f"/courses/{course_id}/assignments/{assignment_id_str}"
        )
        assignment_name = assignment_response.get("name", "Unknown Assignment") if "error" not in assignment_response else "Unknown Assignment"

        # Calculate total points from rubric assessment
        total_points = sum(criterion.get("points", 0) for criterion in rubric_assessment.values())

        course_display = await get_course_code(course_id) or course_identifier

        result = "Rubric Grade Submitted Successfully!\n\n"
        result += f"Course: {course_display}\n"
        result += f"Assignment: {assignment_name}\n"
        result += f"Student ID: {user_id}\n"
        result += f"Total Rubric Points: {total_points}\n"
        result += f"Grade: {response.get('grade', 'N/A')}\n"
        result += f"Score: {response.get('score', 'N/A')}\n"
        result += f"Graded At: {format_date(response.get('graded_at'))}\n"

        if comment:
            result += f"Overall Comment: {comment}\n"

        result += "\nRubric Assessment Summary:\n"
        for criterion_id, assessment in rubric_assessment.items():
            points = assessment.get("points", 0)
            rating_id = assessment.get("rating_id", "")
            comments = assessment.get("comments", "")
            result += f"  Criterion {criterion_id}: {points} points"
            if rating_id:
                result += f" (Rating: {rating_id})"
            if comments:
                result += f"\n    Comment: {truncate_text(comments, 100)}"
            result += "\n"

        return result

    @mcp.tool()
    @validate_params
    async def list_all_rubrics(course_identifier: str | int,
                              include_criteria: bool = True) -> str:
        """List all rubrics in a specific course with optional detailed criteria.

        Args:
            course_identifier: The Canvas course code (e.g., badm_554_120251_246794) or ID
            include_criteria: Whether to include detailed criteria and ratings (default: True)
        """
        course_id = await get_course_id(course_identifier)

        # Fetch all rubrics for the course
        rubrics = await fetch_all_paginated_results(f"/courses/{course_id}/rubrics")

        if isinstance(rubrics, dict) and "error" in rubrics:
            return f"Error fetching rubrics: {rubrics['error']}"

        if not rubrics:
            course_display = await get_course_code(course_id) or course_identifier
            return f"No rubrics found for course {course_display}."

        # Get course display name
        course_display = await get_course_code(course_id) or course_identifier

        result = f"All Rubrics for Course {course_display}:\n\n"

        for i, rubric in enumerate(rubrics, 1):
            rubric_id = rubric.get("id", "N/A")
            title = rubric.get("title", "Untitled Rubric")
            points_possible = rubric.get("points_possible", 0)
            reusable = rubric.get("reusable", False)
            read_only = rubric.get("read_only", False)
            data = rubric.get("data", [])

            result += "=" * 80 + "\n"
            result += f"Rubric #{i}: {title} (ID: {rubric_id})\n"
            result += f"Total Points: {points_possible} | Criteria: {len(data)} | "
            result += f"Reusable: {'Yes' if reusable else 'No'} | "
            result += f"Read-only: {'Yes' if read_only else 'No'}\n"

            if include_criteria and data:
                result += "\nCriteria Details:\n"
                result += "-" * 16 + "\n"

                for j, criterion in enumerate(data, 1):
                    criterion_id = criterion.get("id", "N/A")
                    description = criterion.get("description", "No description")
                    long_description = criterion.get("long_description", "")
                    points = criterion.get("points", 0)
                    ratings = criterion.get("ratings", [])

                    result += f"\n{j}. {description} (ID: {criterion_id}) - {points} points\n"

                    if long_description and long_description != description:
                        # Truncate long descriptions to keep output manageable
                        truncated_desc = truncate_text(long_description, 150)
                        result += f"   Description: {truncated_desc}\n"

                    if ratings:
                        # Sort ratings by points (highest to lowest)
                        sorted_ratings = sorted(ratings, key=lambda x: x.get("points", 0), reverse=True)

                        for rating in sorted_ratings:
                            rating_description = rating.get("description", "No description")
                            rating_points = rating.get("points", 0)
                            rating_id = rating.get("id", "N/A")

                            result += f"   - {rating_description} ({rating_points} pts) [ID: {rating_id}]\n"

                            # Include long description if it exists and differs
                            rating_long_desc = rating.get("long_description", "")
                            if rating_long_desc and rating_long_desc != rating_description:
                                truncated_rating_desc = truncate_text(rating_long_desc, 100)
                                result += f"     {truncated_rating_desc}\n"
                    else:
                        result += "   No rating scale defined for this criterion.\n"
            elif include_criteria:
                result += "\nNo criteria defined for this rubric.\n"

            result += "\n"

        # Add summary
        result += "=" * 80 + "\n"
        result += f"Total Rubrics Found: {len(rubrics)}\n"

        if include_criteria:
            result += "\nNote: Use the criterion and rating IDs shown above with the grade_with_rubric tool.\n"
            result += "Example: {\"criterion_id\": {\"points\": X, \"comments\": \"...\", \"rating_id\": \"rating_id\"}}\n"
        else:
            result += "\nTo see detailed criteria and ratings, run this command with include_criteria=True.\n"

        return result

    @mcp.tool()
    @validate_params
    async def create_rubric(course_identifier: str | int,
                          title: str,
                          criteria: str | dict[str, Any],
                          free_form_criterion_comments: bool = True,
                          association_id: str | int | None = None,
                          association_type: str = "Assignment",
                          use_for_grading: bool = False,
                          purpose: str = "grading") -> str:
        """Create a new rubric in the specified course.

        Args:
            course_identifier: The Canvas course code (e.g., badm_554_120251_246794) or ID
            title: The title of the rubric
            criteria: JSON string or dictionary containing rubric criteria structure
            free_form_criterion_comments: Allow free-form comments on rubric criteria (default: True)
            association_id: Optional ID to associate rubric with (assignment, course, etc.)
            association_type: Type of association (Assignment, Course, Account) (default: Assignment)
            use_for_grading: Whether to use rubric for grade calculation (default: False)
            purpose: Purpose of the rubric association (grading, bookmark) (default: grading)

        Example criteria format (as JSON string or dict):
        {
            "1": {
                "description": "Quality of Work",
                "points": 25,
                "long_description": "Detailed description of quality expectations",
                "ratings": {
                    "1": {"description": "Excellent", "points": 25, "long_description": "Exceeds expectations"},
                    "2": {"description": "Good", "points": 20, "long_description": "Meets expectations"},
                    "3": {"description": "Satisfactory", "points": 15, "long_description": "Approaches expectations"},
                    "4": {"description": "Needs Improvement", "points": 10, "long_description": "Below expectations"}
                }
            }
        }

        Note: Ratings can be provided as objects (as above) or arrays - both formats are supported.
        """
        course_id = await get_course_id(course_identifier)

        # Validate and parse criteria
        try:
            # Handle both string and dict input
            if isinstance(criteria, str):
                parsed_criteria = validate_rubric_criteria(criteria)
            elif isinstance(criteria, dict):
                # If it's already a dict, validate it directly
                parsed_criteria = criteria
                # Still run validation to ensure structure is correct (but don't fail if it errors)
                try:
                    validate_rubric_criteria(json.dumps(criteria))
                except ValueError:
                    # If validation fails, continue anyway since we have a dict
                    pass
            else:
                return "Error: criteria must be a JSON string or dictionary object"

            formatted_criteria = build_criteria_structure(parsed_criteria)
        except ValueError as e:
            # If validation fails, provide detailed error and suggest a simpler format
            error_msg = f"Error validating criteria: {str(e)}\n\n"
            error_msg += "=== DEBUGGING INFORMATION ===\n"
            error_msg += f"Criteria type: {type(criteria)}\n"
            if isinstance(criteria, str):
                error_msg += f"Criteria length: {len(criteria)}\n"
                error_msg += f"First 200 chars: {repr(criteria[:200])}\n"
            error_msg += "\n=== SUGGESTED SIMPLE FORMAT ===\n"
            error_msg += "Try using this simple format:\n"
            error_msg += '{"1": {"description": "Test Criterion", "points": 5.0, "ratings": [{"description": "Good", "points": 5.0}, {"description": "Poor", "points": 0.0}]}}'
            return error_msg

        # Build rubric data
        rubric_data = {
            "title": title,
            "free_form_criterion_comments": free_form_criterion_comments,
            "criteria": formatted_criteria
        }

        # Build request data
        request_data = {
            "rubric": rubric_data
        }

        # Add association if provided
        if association_id:
            request_data["rubric_association"] = {
                "association_id": str(association_id),
                "association_type": association_type,
                "use_for_grading": use_for_grading,
                "purpose": purpose
            }

        # Make the API request
        response = await make_canvas_request(
            "post",
            f"/courses/{course_id}/rubrics",
            data=request_data
        )

        if "error" in response:
            return f"Error creating rubric: {response['error']}"

        # Format and return response
        course_display = await get_course_code(course_id) or course_identifier
        formatted_response = format_rubric_response(response)

        return f"Rubric created in course {course_display}!\n\n{formatted_response}"

    @mcp.tool()
    @validate_params
    async def update_rubric(course_identifier: str | int,
                          rubric_id: str | int,
                          title: str | None = None,
                          criteria: str | dict[str, Any] | None = None,
                          free_form_criterion_comments: bool | None = None,
                          skip_updating_points_possible: bool = False) -> str:
        """Update an existing rubric in the specified course.

        Args:
            course_identifier: The Canvas course code (e.g., badm_554_120251_246794) or ID
            rubric_id: The ID of the rubric to update
            title: Optional new title for the rubric
            criteria: Optional JSON string or dictionary containing updated rubric criteria structure
            free_form_criterion_comments: Optional boolean to allow free-form comments
            skip_updating_points_possible: Skip updating points possible calculation (default: False)
        """
        course_id = await get_course_id(course_identifier)
        rubric_id_str = str(rubric_id)

        # Build update data
        rubric_data = {}

        if title is not None:
            rubric_data["title"] = title

        if free_form_criterion_comments is not None:
            rubric_data["free_form_criterion_comments"] = free_form_criterion_comments

        if skip_updating_points_possible:
            rubric_data["skip_updating_points_possible"] = True

        # Handle criteria update
        if criteria is not None:
            try:
                # Handle both string and dict input
                if isinstance(criteria, str):
                    parsed_criteria = validate_rubric_criteria(criteria)
                elif isinstance(criteria, dict):
                    # If it's already a dict, validate it directly
                    parsed_criteria = criteria
                    # Still run validation to ensure structure is correct (but don't fail if it errors)
                    try:
                        validate_rubric_criteria(json.dumps(criteria))
                    except ValueError:
                        # If validation fails, continue anyway since we have a dict
                        pass
                else:
                    return "Error: criteria must be a JSON string or dictionary object"

                formatted_criteria = build_criteria_structure(parsed_criteria)
                rubric_data["criteria"] = formatted_criteria
            except ValueError as e:
                # If validation fails, provide detailed error and suggest a simpler format
                error_msg = f"Error validating criteria: {str(e)}\n\n"
                error_msg += "=== DEBUGGING INFORMATION ===\n"
                error_msg += f"Criteria type: {type(criteria)}\n"
                if isinstance(criteria, str):
                    error_msg += f"Criteria length: {len(criteria)}\n"
                    error_msg += f"First 200 chars: {repr(criteria[:200])}\n"
                error_msg += "\n=== SUGGESTED SIMPLE FORMAT ===\n"
                error_msg += "Try using this simple format:\n"
                error_msg += '{"1": {"description": "Test Criterion", "points": 5.0, "ratings": [{"description": "Good", "points": 5.0}, {"description": "Poor", "points": 0.0}]}}'
                return error_msg

        # If no update data provided, return error
        if not rubric_data:
            return "Error: No update data provided. Specify at least title, criteria, or free_form_criterion_comments."

        # Make the API request
        response = await make_canvas_request(
            "put",
            f"/courses/{course_id}/rubrics/{rubric_id_str}",
            data={"rubric": rubric_data}
        )

        if "error" in response:
            return f"Error updating rubric: {response['error']}"

        # Format and return response
        course_display = await get_course_code(course_id) or course_identifier
        formatted_response = format_rubric_response(response)

        return f"Rubric updated in course {course_display}!\n\n{formatted_response}"

    @mcp.tool()
    @validate_params
    async def delete_rubric(course_identifier: str | int,
                          rubric_id: str | int) -> str:
        """Delete a rubric and remove all its associations.

        Args:
            course_identifier: The Canvas course code (e.g., badm_554_120251_246794) or ID
            rubric_id: The ID of the rubric to delete
        """
        course_id = await get_course_id(course_identifier)
        rubric_id_str = str(rubric_id)

        # Get rubric details before deletion for confirmation
        rubric_response = await make_canvas_request(
            "get",
            f"/courses/{course_id}/rubrics/{rubric_id_str}"
        )

        rubric_title = "Unknown Rubric"
        if "error" not in rubric_response:
            rubric_title = rubric_response.get("title", "Unknown Rubric")

        # Delete the rubric
        response = await make_canvas_request(
            "delete",
            f"/courses/{course_id}/rubrics/{rubric_id_str}"
        )

        if "error" in response:
            return f"Error deleting rubric: {response['error']}"

        course_display = await get_course_code(course_id) or course_identifier

        result = f"Rubric deleted successfully from course {course_display}!\n\n"
        result += "Deleted Rubric Details:\n"
        result += f"  ID: {rubric_id}\n"
        result += f"  Title: {rubric_title}\n"
        result += "  All associations have been removed\n"

        return result

    @mcp.tool()
    @validate_params
    async def associate_rubric_with_assignment(course_identifier: str | int,
                                             rubric_id: str | int,
                                             assignment_id: str | int,
                                             use_for_grading: bool = False,
                                             purpose: str = "grading") -> str:
        """Associate an existing rubric with an assignment.

        Args:
            course_identifier: The Canvas course code (e.g., badm_554_120251_246794) or ID
            rubric_id: The ID of the rubric to associate
            assignment_id: The ID of the assignment to associate with
            use_for_grading: Whether to use rubric for grade calculation (default: False)
            purpose: Purpose of the association (grading, bookmark) (default: grading)
        """
        course_id = await get_course_id(course_identifier)
        rubric_id_str = str(rubric_id)
        assignment_id_str = str(assignment_id)

        # Update the rubric with association
        request_data = {
            "rubric_association": {
                "association_id": assignment_id_str,
                "association_type": "Assignment",
                "use_for_grading": use_for_grading,
                "purpose": purpose
            }
        }

        # Make the API request
        response = await make_canvas_request(
            "put",
            f"/courses/{course_id}/rubrics/{rubric_id_str}",
            data=request_data
        )

        if "error" in response:
            return f"Error associating rubric with assignment: {response['error']}"

        # Get assignment details for confirmation
        assignment_response = await make_canvas_request(
            "get",
            f"/courses/{course_id}/assignments/{assignment_id_str}"
        )

        assignment_name = "Unknown Assignment"
        if "error" not in assignment_response:
            assignment_name = assignment_response.get("name", "Unknown Assignment")

        course_display = await get_course_code(course_id) or course_identifier

        result = "Rubric associated with assignment successfully!\n\n"
        result += f"Course: {course_display}\n"
        result += f"Assignment: {assignment_name} (ID: {assignment_id})\n"
        result += f"Rubric ID: {rubric_id}\n"
        result += f"Used for Grading: {'Yes' if use_for_grading else 'No'}\n"
        result += f"Purpose: {purpose}\n"

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

        This tool applies grades to multiple student submissions in batches, reducing the
        number of individual API calls needed. It supports both rubric-based grading and
        simple point-based grading.

        IMPORTANT: This is the most efficient way to grade bulk submissions!
        Token savings: Processing submissions in batches without loading all data into context.

        Args:
            course_identifier: The Canvas course code (e.g., badm_554_120251_246794) or ID
            assignment_id: The Canvas assignment ID
            grades: Dictionary mapping user IDs to grade information
                   Format: {
                     "user_id": {
                       "rubric_assessment": {...},  # Optional: rubric-based grading
                       "grade": <number>,           # Optional: simple grade
                       "comment": "<string>"        # Optional: feedback comment
                     }
                   }
            dry_run: If True, analyze but don't actually submit grades (for testing)
            max_concurrent: Maximum concurrent grading operations (default: 5)
            rate_limit_delay: Delay between batches in seconds (default: 1.0)

        Example Usage - Rubric Grading:
            {
              "course_identifier": "60366",
              "assignment_id": "1440586",
              "grades": {
                "9824": {
                  "rubric_assessment": {
                    "_8027": {"points": 100, "comments": "Excellent work!"}
                  },
                  "comment": "Great job!"
                },
                "9825": {
                  "rubric_assessment": {
                    "_8027": {"points": 75, "comments": "Good work"}
                  }
                }
              },
              "dry_run": true
            }

        Example Usage - Simple Grading:
            {
              "course_identifier": "60366",
              "assignment_id": "1440586",
              "grades": {
                "9824": {"grade": 100, "comment": "Perfect!"},
                "9825": {"grade": 85, "comment": "Very good"}
              }
            }
        """
        import asyncio

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
                        "1. Use list_assignment_rubrics to verify rubric settings\n"
                        "2. Use associate_rubric_with_assignment with use_for_grading=True\n"
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
            result_lines.append(f"\nFailed Submissions:")
            for failure in failed_results[:10]:  # Show first 10 failures
                result_lines.append(f"  User {failure['user_id']}: {failure['error']}")
            if len(failed_results) > 10:
                result_lines.append(f"  ... and {len(failed_results) - 10} more failures")

        if dry_run:
            result_lines.append(f"\n⚠️  DRY RUN MODE: No grades were actually submitted")
            result_lines.append(f"Set dry_run=false to apply grades")

        return "\n".join(result_lines)
