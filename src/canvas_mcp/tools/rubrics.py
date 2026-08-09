"""Rubric-related MCP tools for Canvas API."""

import ast
import asyncio
import csv
import json
from io import StringIO
from typing import Any

from fastmcp import FastMCP
from mcp.types import ToolAnnotations

from ..core.cache import get_course_code, get_course_id
from ..core.client import fetch_all_paginated_results, make_canvas_request
from ..core.dates import format_date, truncate_text
from ..core.untrusted_content import fence_untrusted_inline
from ..core.validation import validate_params
from ..core.write_confirmation import unconfirmed_write_warning


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


def build_rubric_create_form_data(
    title: str,
    criteria: dict[str, Any],
    assignment_id: str | int | None = None,
    use_for_grading: bool = False,
    reusable: bool = False,
    free_form_criterion_comments: bool = False,
    course_id: str | int | None = None,
) -> dict[str, str]:
    """Build bracket-notation form data for Canvas rubric creation API.

    Canvas POST /courses/:id/rubrics requires bracket-notation form data
    (not JSON body).  This function produces the flat key/value dict that
    ``make_canvas_request`` sends when ``use_form_data=True``.

    Args:
        title: Rubric title
        criteria: Validated criteria dict (from validate_rubric_criteria)
        assignment_id: Optional assignment ID to associate the rubric with
        use_for_grading: Whether the rubric should be used for grade calculation
        reusable: Whether the rubric is reusable across courses
        free_form_criterion_comments: Allow free-form comments per criterion
        course_id: Course to bookmark the rubric into when no assignment_id is
            given. Required for the rubric to appear in the Canvas Rubrics UI.

    Returns:
        Flat dict with Canvas bracket-notation keys, all values as strings.

    Example output keys::

        rubric[title]
        rubric[criteria][0][description]
        rubric[criteria][0][points]
        rubric[criteria][0][ratings][0][description]
        rubric[criteria][0][ratings][0][points]
        rubric_association[association_id]        (only when assignment_id given)
        rubric_association[association_type]      (only when assignment_id given)
        rubric_association[use_for_grading]       (only when assignment_id given)
        rubric_association[purpose]               (only when assignment_id given)
    """
    form_data: dict[str, str] = {}

    form_data["rubric[title]"] = title
    form_data["rubric[reusable]"] = "1" if reusable else "0"
    form_data["rubric[free_form_criterion_comments]"] = "1" if free_form_criterion_comments else "0"

    for crit_idx, (_crit_key, criterion_data) in enumerate(criteria.items()):
        prefix = f"rubric[criteria][{crit_idx}]"

        form_data[f"{prefix}[description]"] = str(criterion_data["description"])
        form_data[f"{prefix}[points]"] = str(float(criterion_data["points"]))

        long_desc = criterion_data.get("long_description", "")
        if long_desc:
            form_data[f"{prefix}[long_description]"] = str(long_desc)

        ratings = criterion_data.get("ratings", [])

        # Normalize to a list of dicts (criteria support both list and dict formats)
        if isinstance(ratings, dict):
            # Dict-format ratings use arbitrary user-provided keys that Canvas does not
            # recognise — only description/points/long_description matter.  Discard keys.
            ratings_list = list(ratings.values())
        else:
            ratings_list = list(ratings)

        # Sort ratings highest → lowest so Canvas displays them correctly
        ratings_list = sorted(
            ratings_list,
            key=lambda r: float(r.get("points", 0)),
            reverse=True,
        )

        for rating_idx, rating_data in enumerate(ratings_list):
            rprefix = f"{prefix}[ratings][{rating_idx}]"
            form_data[f"{rprefix}[description]"] = str(rating_data["description"])
            form_data[f"{rprefix}[points]"] = str(float(rating_data["points"]))
            rating_long_desc = rating_data.get("long_description", "")
            if rating_long_desc:
                form_data[f"{rprefix}[long_description]"] = str(rating_long_desc)

    # Canvas needs a rubric_association, not just the rubric. Without one it
    # creates the rubric row in the course context (so GET /courses/:id/rubrics
    # returns it) but no association row, and the Canvas Rubrics UI lists
    # rubrics via the course's *bookmarked* associations. The result is a rubric
    # that is visible over the API and invisible in the interface, which is
    # exactly what #180 reported.
    if assignment_id is not None:
        form_data["rubric_association[association_id]"] = str(assignment_id)
        form_data["rubric_association[association_type]"] = "Assignment"
        form_data["rubric_association[use_for_grading]"] = "1" if use_for_grading else "0"
        form_data["rubric_association[purpose]"] = "grading"
    elif course_id is not None:
        form_data["rubric_association[association_id]"] = str(course_id)
        form_data["rubric_association[association_type]"] = "Course"
        form_data["rubric_association[purpose]"] = "bookmark"
        form_data["rubric_association[bookmarked]"] = "1"
        form_data["rubric_association[use_for_grading]"] = "0"

    return form_data


def rubric_association_id(response: Any) -> Any | None:
    """Return the id of a rubric association Canvas actually created, or None.

    Canvas answers ``200`` for rubric writes whose association parameters it
    silently ignored, so an HTTP success is not evidence that an association
    exists. The only reliable evidence is an id in the payload. This has now
    bitten three separate call sites — #180 (create, invisible in the Rubrics
    UI), #181 (assignment association never attached), and the CSV import path
    (#190) — so the shapes Canvas uses are recognised in exactly one place
    rather than re-derived per tool.

    Handles the three payload shapes:

    - ``{"rubric": {...}, "rubric_association": {"id": N, ...}}`` — rubric create
    - ``{"id": N, "association_type": "...", ...}`` — POST /rubric_associations
    - ``{"rubric_association": null}`` / ``{}`` — accepted, created nothing
    """
    if not isinstance(response, dict):
        return None

    association = response.get("rubric_association")
    if isinstance(association, dict):
        return association.get("id") or None

    # POST /courses/:id/rubric_associations returns the association itself.
    if response.get("association_type") or response.get("association_id"):
        return response.get("id") or None

    return None




def count_csv_rubrics(csv_content: str) -> int | None:
    """Count distinct rubric names in a Canvas rubric CSV.

    Returns None when the CSV cannot be parsed or does not include a
    ``Rubric Name`` column.
    """
    try:
        reader = csv.DictReader(StringIO(csv_content))
    except csv.Error:
        return None

    if not reader.fieldnames:
        return None

    rubric_name_field = next(
        (name for name in reader.fieldnames if isinstance(name, str) and name.strip().lower() == "rubric name"),
        None,
    )
    if not rubric_name_field:
        return None

    names: set[str] = set()
    for row in reader:
        if not isinstance(row, dict):
            # Defensive guard kept deliberately: typeshed says DictReader always
            # yields dicts, so mypy sees this as dead, but a malformed csv module
            # substitute would otherwise crash the loop.
            continue  # type: ignore[unreachable]
        raw_name = row.get(rubric_name_field)
        if isinstance(raw_name, str) and raw_name.strip():
            names.add(raw_name.strip())

    return len(names)


async def _ensure_course_bookmark(response: Any, course_id: str | int) -> str:
    """Guarantee a created rubric is actually bookmarked into the course.

    Canvas may return the rubric with ``rubric_association: null`` even when the
    create request carried association fields. A rubric in that state is
    returned by ``GET /courses/:id/rubrics`` but does not appear in the Canvas
    Rubrics UI, so reporting plain success would be misleading (#180).

    Returns a line to append to the tool output.
    """
    if rubric_association_id(response):
        return ""

    rubric = (response or {}).get("rubric") or {}
    rubric_id = rubric.get("id") or (response or {}).get("id")
    if not rubric_id:
        return "\n" + unconfirmed_write_warning(
            "this rubric was added to the course's Rubrics list",
            {},
            "Canvas returned no rubric ID to retry with. Check Canvas.",
        )

    retry = await make_canvas_request(
        "post",
        f"/courses/{course_id}/rubric_associations",
        data={
            "rubric_association[rubric_id]": str(rubric_id),
            "rubric_association[association_id]": str(course_id),
            "rubric_association[association_type]": "Course",
            "rubric_association[purpose]": "bookmark",
            "rubric_association[bookmarked]": "1",
        },
        use_form_data=True,
    )
    if isinstance(retry, dict) and "error" in retry:
        return (
            f"\n⚠️  The rubric was created but could not be added to the course's "
            f"Rubrics list ({retry['error']}). It exists via the API but will not "
            f"appear in the Canvas Rubrics tool until it is bookmarked.\n"
        )
    return "\nAdded to the course's Rubrics list.\n"


def register_rubric_tools(mcp: FastMCP) -> None:
    """Register all rubric-related MCP tools."""

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
    @validate_params
    async def get_rubric(course_identifier: str | int,
                         rubric_id: str | int | None = None,
                         assignment_id: str | int | None = None) -> str:
        """Get detailed rubric criteria, ratings, and points.

        Accepts either rubric_id or assignment_id (at least one required).
        If both provided, uses rubric_id (more specific).

        Args:
            course_identifier: Course code or Canvas ID
            rubric_id: Canvas rubric ID (direct lookup)
            assignment_id: Canvas assignment ID (get rubric attached to assignment)
        """
        if rubric_id is None and assignment_id is None:
            return (
                "Error: You must provide either rubric_id or assignment_id.\n\n"
                "Usage:\n"
                "  - get_rubric(course, rubric_id=123) — look up rubric directly\n"
                "  - get_rubric(course, assignment_id=456) — get rubric attached to an assignment\n"
                "\nUse list_rubrics to find rubric IDs for a course."
            )

        course_id = await get_course_id(course_identifier)
        course_display = await get_course_code(course_id) or course_identifier

        # Path 1: Look up by rubric_id (preferred when both provided)
        if rubric_id is not None:
            rubric_id_str = str(rubric_id)

            response = await make_canvas_request(
                "get",
                f"/courses/{course_id}/rubrics/{rubric_id_str}",
                params={"include[]": ["assessments", "associations"]}
            )

            if "error" in response:
                return f"Error fetching rubric: {response['error']}"

            title = response.get("title", "Untitled Rubric")
            points_possible = response.get("points_possible", 0)
            reusable = response.get("reusable", False)
            read_only = response.get("read_only", False)
            data = response.get("data", [])

            # Rubric title, criterion/rating descriptions are author-authored
            # (issue 239).
            result = f"Rubric {fence_untrusted_inline(title, 'rubric title')} in Course {course_display}:\n\n"
            result += f"Rubric ID: {rubric_id}\n"
            result += f"Total Points: {points_possible}\n"
            result += f"Reusable: {'Yes' if reusable else 'No'}\n"
            result += f"Read Only: {'Yes' if read_only else 'No'}\n"

            if data:
                result += f"Number of Criteria: {len(data)}\n\n"
                result += "Criteria and Ratings:\n"
                result += "=" * 50 + "\n"

                for i, criterion in enumerate(data, 1):
                    criterion_id = criterion.get("id", "N/A")
                    description = criterion.get("description", "No description")
                    long_description = criterion.get("long_description", "")
                    points = criterion.get("points", 0)
                    ratings = criterion.get("ratings", [])

                    result += f"\nCriterion #{i}: {fence_untrusted_inline(description, 'rubric criterion description')}\n"
                    result += f"  ID: {criterion_id}\n"
                    result += f"  Points: {points}\n"

                    if long_description and long_description != description:
                        result += f"  Description: {fence_untrusted_inline(truncate_text(long_description, 200), 'rubric criterion description')}\n"

                    if ratings:
                        sorted_ratings = sorted(ratings, key=lambda x: x.get("points", 0), reverse=True)
                        for rating in sorted_ratings:
                            rating_desc = rating.get("description", "No description")
                            rating_points = rating.get("points", 0)
                            rating_id = rating.get("id", "N/A")
                            result += f"  - {rating_points} pts: {fence_untrusted_inline(rating_desc, 'rubric rating description')} [ID: {rating_id}]\n"

                            rating_long_desc = rating.get("long_description", "")
                            if rating_long_desc and rating_long_desc != rating_desc:
                                result += f"    {fence_untrusted_inline(truncate_text(rating_long_desc, 100), 'rubric rating description')}\n"

                    result += "\n"
            else:
                result += "\nNo criteria defined for this rubric.\n"

            return result

        # Path 2: Look up via assignment_id
        assignment_id_str = str(assignment_id)

        response = await make_canvas_request(
            "get",
            f"/courses/{course_id}/assignments/{assignment_id_str}",
            params={"include[]": ["rubric", "rubric_settings"]}
        )

        if "error" in response:
            return f"Error fetching rubric: {response['error']}"

        rubric = response.get("rubric")
        if not rubric:
            assignment_name = response.get("name", "Unknown Assignment")
            return f"No rubric found for assignment '{assignment_name}' in course {course_display}."

        assignment_name = response.get("name", "Unknown Assignment")
        rubric_settings = response.get("rubric_settings", {})
        use_rubric_for_grading = response.get("use_rubric_for_grading", False)

        result = (
            "Rubric for Assignment "
            f"{fence_untrusted_inline(assignment_name, 'assignment name')} "
            f"in Course {course_display}:\n\n"
        )

        # Grading config (only available via assignment path)
        result += "Grading Config:\n"
        result += f"  Used for Grading: {'Yes' if use_rubric_for_grading else 'No'}\n"
        if rubric_settings:
            result += f"  Points Possible: {rubric_settings.get('points_possible', 'N/A')}\n"
        result += f"Number of Criteria: {len(rubric)}\n\n"

        # Criteria and ratings
        result += "Criteria and Ratings:\n"
        result += "=" * 50 + "\n"

        total_points = 0
        for i, criterion in enumerate(rubric, 1):
            criterion_id = criterion.get("id", "N/A")
            description = criterion.get("description", "No description")
            long_description = criterion.get("long_description", "")
            points = criterion.get("points", 0)
            ratings = criterion.get("ratings", [])

            result += f"\nCriterion #{i}: {fence_untrusted_inline(description, 'rubric criterion description')}\n"
            result += f"  ID: {criterion_id}\n"
            result += f"  Points: {points}\n"

            if long_description and long_description != description:
                result += f"  Description: {fence_untrusted_inline(truncate_text(long_description, 200), 'rubric criterion description')}\n"

            if ratings:
                sorted_ratings = sorted(ratings, key=lambda x: x.get("points", 0), reverse=True)
                for rating in sorted_ratings:
                    rating_desc = rating.get("description", "No description")
                    rating_points = rating.get("points", 0)
                    rating_id = rating.get("id", "N/A")
                    result += f"  - {rating_points} pts: {fence_untrusted_inline(rating_desc, 'rubric rating description')} [ID: {rating_id}]\n"

                    rating_long_desc = rating.get("long_description", "")
                    if rating_long_desc and rating_long_desc != rating_desc:
                        result += f"    {fence_untrusted_inline(truncate_text(rating_long_desc, 100), 'rubric rating description')}\n"

            total_points += points
            result += "\n"

        result += f"Total Rubric Points: {total_points}"

        return result

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
    @validate_params
    async def get_rubric_assessment(course_identifier: str | int,
                                             assignment_id: str | int,
                                             user_id: str | int) -> str:
        """Get rubric assessment scores for a specific submission.

        Args:
            course_identifier: Course code or Canvas ID
            assignment_id: Canvas assignment ID
            user_id: Canvas user ID of the student
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

        # Anonymization happens at the client layer (core/client.py) per
        # ENABLE_DATA_ANONYMIZATION (#179)

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

        result = (
            f"Rubric Assessment for User {user_id} on "
            f"{fence_untrusted_inline(assignment_name, 'assignment name')} "
            f"in Course {course_display}:\n\n"
        )

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

            # Criterion/rating descriptions (author) and comments (grader/peer)
            # are author-controlled (issue 239).
            result += f"\n{fence_untrusted_inline(criterion_description, 'rubric criterion description')}:\n"
            result += f"  Points Awarded: {points}\n"

            if rating_id and criterion_info:
                # Find the rating description
                for rating in criterion_info.get("ratings", []):
                    if str(rating.get("id")) == str(rating_id):
                        result += f"  Rating: {fence_untrusted_inline(rating.get('description', 'N/A'), 'rubric rating description')} ({rating.get('points', 0)} pts)\n"
                        break

            if comments:
                result += f"  Comments: {fence_untrusted_inline(comments, 'rubric assessment comment')}\n"

            total_rubric_points += points

        result += f"\nTotal Rubric Points: {total_rubric_points}"

        return result

    @mcp.tool(annotations=ToolAnnotations(destructiveHint=True, idempotentHint=False))
    @validate_params
    async def grade_with_rubric(course_identifier: str | int,
                              assignment_id: str | int,
                              user_id: str | int,
                              rubric_assessment: dict[str, Any],
                              comment: str | None = None) -> str:
        """Submit grades using rubric criteria.

        IMPORTANT: Criterion IDs often start with underscore (e.g., "_8027").
        Use get_rubric to find criterion/rating IDs.
        The rubric must be attached to the assignment and configured for grading (use_for_grading=true).

        Args:
            course_identifier: Course code or Canvas ID
            assignment_id: Canvas assignment ID
            user_id: Canvas user ID of the student
            rubric_assessment: Dict mapping criterion_id to {points (required), rating_id?, comments?}
            comment: Optional overall comment. OMIT it unless the instructor
                explicitly asked for written feedback -- "grade this with the
                rubric" means the grade only. It is visible to the student in
                SpeedGrader, APPENDS rather than replaces on each call, and
                cannot be un-sent. Never generate one that merely restates the
                grade or narrates that grading happened.
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
                    "1. Use get_rubric to verify rubric settings\n"
                    "2. Use associate_rubric with use_for_grading=True\n"
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

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
    @validate_params
    async def list_rubrics(course_identifier: str | int,
                              include_criteria: bool = True) -> str:
        """List all rubrics in a specific course with optional detailed criteria.

        Args:
            course_identifier: Course code or Canvas ID
            include_criteria: Include detailed criteria and ratings (default: True)
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
            result += f"Rubric #{i}: {fence_untrusted_inline(title, 'rubric title')} (ID: {rubric_id})\n"
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

                    result += f"\n{j}. {fence_untrusted_inline(description, 'rubric criterion description')} (ID: {criterion_id}) - {points} points\n"

                    if long_description and long_description != description:
                        # Truncate long descriptions to keep output manageable
                        truncated_desc = truncate_text(long_description, 150)
                        result += f"   Description: {fence_untrusted_inline(truncated_desc, 'rubric criterion description')}\n"

                    if ratings:
                        # Sort ratings by points (highest to lowest)
                        sorted_ratings = sorted(ratings, key=lambda x: x.get("points", 0), reverse=True)

                        for rating in sorted_ratings:
                            rating_description = rating.get("description", "No description")
                            rating_points = rating.get("points", 0)
                            rating_id = rating.get("id", "N/A")

                            result += f"   - {fence_untrusted_inline(rating_description, 'rubric rating description')} ({rating_points} pts) [ID: {rating_id}]\n"

                            # Include long description if it exists and differs
                            rating_long_desc = rating.get("long_description", "")
                            if rating_long_desc and rating_long_desc != rating_description:
                                truncated_rating_desc = truncate_text(rating_long_desc, 100)
                                result += f"     {fence_untrusted_inline(truncated_rating_desc, 'rubric rating description')}\n"
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

    @mcp.tool(annotations=ToolAnnotations(destructiveHint=False, idempotentHint=False))
    @validate_params
    async def create_rubric_from_csv(
        course_identifier: str | int,
        csv_content: str,
    ) -> str:
        """Create one or more rubrics in a course from a CSV string.

        Uses Canvas's native rubric CSV import endpoint, then polls the import
        job until it reaches a terminal workflow_state.

        A ``Rubric Name`` column is REQUIRED — Canvas rejects the import without
        it and creates nothing. Required format (repeat the rating triple per
        rating level; a distinct Rubric Name per row creates multiple rubrics)::

            Rubric Name,Criteria Name,Criteria Description,Criteria Enable Range,Rating Name,Rating Description,Rating Points
            Essay Rubric,Clarity,Is the argument clear,false,Excellent,Very clear,10

        Two Canvas behaviours to be aware of:

        - Imported rubrics land in the ``Draft`` state and are **not** returned
          by ``list_rubrics`` / ``GET /courses/:id/rubrics``, though they do
          appear on the course Rubrics page. An empty ``list_rubrics`` result is
          not evidence the import failed.
        - ``succeeded_with_errors`` is a terminal state, not a transient one, and
          can mean zero rubrics were created.

        Args:
            course_identifier: Course code or Canvas ID
            csv_content: The content of the CSV file as a string
        """
        course_id = await get_course_id(course_identifier)
        if not course_id:
            return f"Error: Could not find course {course_identifier}"

        files = {
            "attachment": ("rubrics.csv", csv_content.encode("utf-8"), "text/csv")
        }

        # Upload the CSV
        response = await make_canvas_request(
            "post",
            f"/courses/{course_id}/rubrics/upload",
            files=files
        )

        if "error" in response:
            return f"Error uploading rubric CSV: {response['error']}"

        import_id = response.get("id")
        if not import_id:
            return f"Error: No import ID returned. Response: {response}"

        # Poll for completion
        status = response.get("workflow_state", "created")
        result_response = response
        csv_rubric_count = count_csv_rubrics(csv_content)

        terminal_states = {"succeeded", "failed", "completed", "succeeded_with_errors"}

        # Poll up to 10 times (20 seconds) for it to finish processing
        for _ in range(10):
            if status in terminal_states:
                break

            await asyncio.sleep(2)
            check_resp = await make_canvas_request(
                "get",
                f"/courses/{course_id}/rubrics/upload/{import_id}"
            )
            if "error" in check_resp:
                return f"Error checking rubric import status: {check_resp['error']}"

            status = check_resp.get("workflow_state", "unknown")
            result_response = check_resp

        course_display = await get_course_code(course_id) or course_identifier

        if status not in terminal_states:
            return unconfirmed_write_warning(
                "the rubric CSV import completed",
                {
                    "Course": course_display,
                    "Import ID": import_id,
                    "Last known workflow_state": status,
                },
                "Canvas may still be processing this import. Check Canvas and retry shortly.",
            )

        error_count = result_response.get("error_count") if isinstance(result_response, dict) else None
        error_data = result_response.get("error_data") if isinstance(result_response, dict) else None
        if isinstance(error_count, int) and error_count > 0:
            warning = unconfirmed_write_warning(
                "the rubric CSV import completed without errors",
                {
                    "Course": course_display,
                    "Import ID": import_id,
                    "workflow_state": status,
                    "error_count": error_count,
                },
                "Fix the CSV issues and retry. Canvas can accept the upload while creating none or only some rubrics.",
            )
            if error_data:
                warning += f"error_data: {error_data}\n"
            if csv_rubric_count is not None:
                warning += f"Rubrics defined in CSV: {csv_rubric_count}\n"
            warning += "Open the course Rubrics page in Canvas to verify what was created.\n"
            return warning

        result = f"Rubric CSV import process finished with status: {status}\n\n"
        result += f"Course: {course_display}\n"
        result += f"Import ID: {import_id}\n"
        if csv_rubric_count is not None:
            result += f"Rubrics defined in CSV: {csv_rubric_count}\n"
        else:
            result += "Rubrics defined in CSV: unknown (missing or unreadable 'Rubric Name' column)\n"
        result += "Open the course Rubrics page in Canvas to review imported Draft rubrics.\n"

        return result

    # With assignment_id, this creates a rubric_association on that
    # assignment, REPLACING any rubric already attached to it (#204).
    @mcp.tool(annotations=ToolAnnotations(destructiveHint=True, idempotentHint=False))
    @validate_params
    async def create_rubric(
        course_identifier: str | int,
        title: str,
        criteria: str,
        assignment_id: str | int | None = None,
        use_for_grading: bool = False,
        reusable: bool = False,
        free_form_criterion_comments: bool = False,
    ) -> str:
        """Create a new rubric in a course, optionally associating it with an assignment.

        Uses bracket-notation form-data encoding required by the Canvas rubric API.

        The ``criteria`` parameter is a JSON string mapping arbitrary criterion keys to
        objects with the following fields:

        - ``description`` (required): Short criterion label shown in the rubric grid
        - ``points`` (required): Maximum points for this criterion (non-negative number)
        - ``long_description`` (optional): Detailed criterion description
        - ``ratings`` (optional): List (or object) of rating levels, each with:
            - ``description`` (required): Rating label (e.g. "Excellent")
            - ``points`` (required): Points for this rating (non-negative number)
            - ``long_description`` (optional): Detailed rating description

        Example ``criteria`` JSON::

            {
              "c1": {
                "description": "Content Quality",
                "points": 10,
                "ratings": [
                  {"description": "Excellent", "points": 10},
                  {"description": "Satisfactory", "points": 7},
                  {"description": "Needs Work", "points": 3}
                ]
              },
              "c2": {
                "description": "Grammar",
                "points": 5,
                "ratings": [
                  {"description": "No errors", "points": 5},
                  {"description": "Minor errors", "points": 3}
                ]
              }
            }

        Args:
            course_identifier: Course code or Canvas ID
            title: Rubric title
            criteria: JSON string defining rubric criteria (see docstring above)
            assignment_id: Optional assignment ID to immediately associate the rubric with
            use_for_grading: When associating with an assignment, use rubric for grade
                             calculation (default: False)
            reusable: Make rubric reusable across courses (default: False)
            free_form_criterion_comments: Allow free-form comments per criterion
                                          instead of rating selection (default: False)
        """
        course_id = await get_course_id(course_identifier)

        # Validate and parse criteria JSON
        try:
            parsed_criteria = validate_rubric_criteria(criteria)
        except ValueError as exc:
            return f"Error: Invalid criteria — {exc}"

        if not parsed_criteria:
            return "Error: criteria must contain at least one criterion."

        # Build bracket-notation form data Canvas expects
        form_data = build_rubric_create_form_data(
            title=title,
            criteria=parsed_criteria,
            assignment_id=assignment_id,
            use_for_grading=use_for_grading,
            reusable=reusable,
            free_form_criterion_comments=free_form_criterion_comments,
            course_id=course_id,
        )

        response = await make_canvas_request(
            "post",
            f"/courses/{course_id}/rubrics",
            data=form_data,
            use_form_data=True,
        )

        if isinstance(response, dict) and "error" in response:
            return f"Error creating rubric: {response['error']}"

        course_display = await get_course_code(course_id) or course_identifier

        # Canvas returns {"rubric": {...}, "rubric_association": {...}}
        result = format_rubric_response(response)
        result += f"\nCourse: {course_display}\n"

        if assignment_id is not None:
            result += f"Assignment ID: {assignment_id}\n"
            result += f"Used for Grading: {'Yes' if use_for_grading else 'No'}\n"
        else:
            # Don't report success on a rubric that is invisible in the Canvas
            # UI. If the inline association did not take, create it explicitly
            # rather than leaving the rubric orphaned (#180).
            warning = await _ensure_course_bookmark(response, course_id)
            if warning:
                result += warning

        return result

    # Replaces the assignment's existing rubric association, and overwrites
    # use_for_grading / purpose even when re-associating the same rubric (#204).
    @mcp.tool(annotations=ToolAnnotations(destructiveHint=True, idempotentHint=False))
    @validate_params
    async def associate_rubric(course_identifier: str | int,
                                             rubric_id: str | int,
                                             assignment_id: str | int,
                                             use_for_grading: bool = False,
                                             purpose: str = "grading") -> str:
        """Associate an existing rubric with an assignment.

        Args:
            course_identifier: Course code or Canvas ID
            rubric_id: ID of the rubric to associate
            assignment_id: ID of the assignment to associate with
            use_for_grading: Use rubric for grade calculation (default: False)
            purpose: Association purpose: grading, bookmark (default: grading)
        """
        course_id = await get_course_id(course_identifier)
        rubric_id_str = str(rubric_id)
        assignment_id_str = str(assignment_id)

        # Canvas needs bracket-notation FORM data on the dedicated
        # rubric_associations endpoint (#181). The previous implementation sent a
        # nested JSON body to PUT /courses/:id/rubrics/:id; Canvas returned 200
        # because the rubric itself is valid, but the association was never
        # created, so the tool reported success while nothing attached to the
        # assignment. This mirrors _ensure_course_bookmark, which works.
        request_data = {
            "rubric_association[rubric_id]": rubric_id_str,
            "rubric_association[association_id]": assignment_id_str,
            "rubric_association[association_type]": "Assignment",
            "rubric_association[use_for_grading]": "1" if use_for_grading else "0",
            "rubric_association[purpose]": purpose,
        }

        response = await make_canvas_request(
            "post",
            f"/courses/{course_id}/rubric_associations",
            data=request_data,
            use_form_data=True,
        )

        if isinstance(response, dict) and "error" in response:
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

        # A 200 carrying no association id means Canvas accepted the request but
        # created nothing. Reporting success there is exactly the #181/#180
        # failure: the user is told it worked and finds nothing in the UI.
        association_id = rubric_association_id(response)
        if not association_id:
            return unconfirmed_write_warning(
                "the rubric was associated with the assignment",
                {
                    "Course": course_display,
                    "Assignment": f"{assignment_name} (ID: {assignment_id})",
                    "Rubric ID": rubric_id,
                },
                "Canvas accepted the request but returned no association, so the "
                "rubric will most likely not appear on the assignment page. "
                "Verify in Canvas before relying on it.",
            )

        result = "Rubric associated with assignment successfully!\n\n"
        result += f"Course: {course_display}\n"
        result += f"Assignment: {assignment_name} (ID: {assignment_id})\n"
        result += f"Rubric ID: {rubric_id}\n"
        result += f"Association ID: {association_id}\n"
        result += f"Used for Grading: {'Yes' if use_for_grading else 'No'}\n"
        result += f"Purpose: {purpose}\n"

        return result
