"""Rubric-related MCP tools for Canvas API."""

import ast
import asyncio
import csv
import json
import math
from io import StringIO
from typing import Any

from fastmcp import FastMCP
from mcp.types import ToolAnnotations

from ..core.cache import get_course_code, get_course_id
from ..core.client import fetch_all_paginated_results, make_canvas_request
from ..core.dates import format_date, truncate_text
from ..core.untrusted_content import (
    FENCE_LEAK_ERROR,
    contains_fence_markers,
    fence_untrusted,
    fence_untrusted_inline,
)
from ..core.validation import validate_params
from ..core.write_confirmation import (
    ConfirmationGuard,
    preview_with_token,
    redeem_confirmation,
    unconfirmed_write_warning,
)

_RUBRIC_UPDATE_GUARD = ConfirmationGuard(
    nothing_done="Nothing was updated.",
)


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


def validate_rubric_update_criteria(
    criteria_json: str,
    current_criteria: list[dict[str, Any]],
) -> dict[str, Any]:
    """Validate a full rubric replacement without permitting ID churn.

    Canvas replaces the complete criteria array on update. Missing criterion or
    rating IDs can silently mint new IDs and orphan existing assessment data, so
    updates require an exact, ID-keyed copy of the current structure.
    """
    criteria = validate_rubric_criteria(criteria_json)
    if not criteria:
        raise ValueError("criteria must contain at least one criterion")

    current_by_id: dict[str, dict[str, Any]] = {}
    for criterion in current_criteria:
        criterion_id = criterion.get("id")
        if criterion_id is None:
            raise ValueError("Canvas returned a criterion without an ID")
        criterion_id_str = str(criterion_id)
        if criterion_id_str in current_by_id:
            raise ValueError(
                f"Canvas returned duplicate criterion ID {criterion_id_str!r}"
            )
        current_by_id[criterion_id_str] = criterion

    if set(criteria) != set(current_by_id):
        raise ValueError(
            "criteria must include the complete existing criterion ID set; "
            "adding or removing criteria is not supported by this guarded tool"
        )

    for criterion_id, proposed in criteria.items():
        if str(proposed.get("id", "")) != criterion_id:
            raise ValueError(
                f"criterion {criterion_id} must include id={criterion_id!r}"
            )
        if not isinstance(proposed.get("description"), str):
            raise ValueError(
                f"criterion {criterion_id} description must be a string"
            )

        # These Canvas flags affect scoring/range behavior but are not editable
        # through this deliberately narrow tool. Carry them forward so a text
        # or points edit cannot silently reset existing behavior.
        for field in ("criterion_use_range", "ignore_for_scoring"):
            if field in current_by_id[criterion_id]:
                proposed[field] = current_by_id[criterion_id][field]
        if "long_description" not in proposed:
            proposed["long_description"] = (
                current_by_id[criterion_id].get("long_description") or ""
            )
        if not isinstance(proposed["long_description"], str):
            raise ValueError(
                f"criterion {criterion_id} long_description must be a string"
            )

        ratings = proposed.get("ratings")
        if not isinstance(ratings, dict):
            raise ValueError(
                f"criterion {criterion_id} ratings must be an ID-keyed object"
            )

        current_ratings = current_by_id[criterion_id].get("ratings", [])
        current_rating_by_id: dict[str, dict[str, Any]] = {}
        for rating in current_ratings:
            rating_id = rating.get("id") if isinstance(rating, dict) else None
            if rating_id is None:
                raise ValueError(
                    f"Canvas returned a rating without an ID in criterion {criterion_id}"
                )
            rating_id_str = str(rating_id)
            if rating_id_str in current_rating_by_id:
                raise ValueError(
                    f"Canvas returned duplicate rating ID {rating_id_str!r} "
                    f"in criterion {criterion_id}"
                )
            current_rating_by_id[rating_id_str] = rating

        if set(ratings) != set(current_rating_by_id):
            raise ValueError(
                f"criterion {criterion_id} must include the complete existing "
                "rating ID set; adding or removing ratings is not supported"
            )
        for rating_id, rating in ratings.items():
            if str(rating.get("id", "")) != rating_id:
                raise ValueError(
                    f"rating {rating_id} in criterion {criterion_id} must include "
                    f"id={rating_id!r}"
                )
            if not isinstance(rating.get("description"), str):
                raise ValueError(
                    f"rating {rating_id} in criterion {criterion_id} "
                    "description must be a string"
                )
            if "long_description" not in rating:
                rating["long_description"] = (
                    current_rating_by_id[rating_id].get("long_description") or ""
                )
            if not isinstance(rating["long_description"], str):
                raise ValueError(
                    f"rating {rating_id} in criterion {criterion_id} "
                    "long_description must be a string"
                )

    ordered_criteria: dict[str, Any] = {}
    for current_criterion in current_criteria:
        criterion_id = str(current_criterion["id"])
        proposed = criteria[criterion_id]
        proposed_ratings = proposed["ratings"]
        proposed["ratings"] = {
            str(current_rating["id"]): proposed_ratings[str(current_rating["id"])]
            for current_rating in current_criterion.get("ratings", [])
        }
        ordered_criteria[criterion_id] = proposed

    return ordered_criteria


def _rubric_update_state(
    response: Any,
    rubric_id: str,
    rubric_association_id: str,
) -> dict[str, Any]:
    """Return the current guarded state or raise when identity is ambiguous."""
    if not isinstance(response, dict) or "error" in response:
        detail = (
            response.get("error") if isinstance(response, dict) else "invalid response"
        )
        raise ValueError(f"could not fetch the rubric: {detail}")
    if str(response.get("id")) != rubric_id:
        raise ValueError("Canvas returned a different rubric ID")
    if response.get("read_only") is True:
        raise ValueError("this rubric is read-only")

    criteria = response.get("data")
    if not isinstance(criteria, list) or not criteria:
        raise ValueError("Canvas returned no complete rubric criteria")

    associations = response.get("associations")
    if not isinstance(associations, list):
        raise ValueError("Canvas returned no association data")
    matches = [
        association
        for association in associations
        if isinstance(association, dict)
        and str(association.get("id")) == rubric_association_id
        and str(association.get("rubric_id")) == rubric_id
    ]
    if len(matches) != 1:
        raise ValueError(
            "the requested rubric association was not returned exactly once"
        )

    return {
        "id": response.get("id"),
        "title": response.get("title"),
        "free_form_criterion_comments": response.get("free_form_criterion_comments"),
        "data": criteria,
        "association": matches[0],
    }


def _rubric_update_fingerprint(
    current: dict[str, Any],
    title: str,
    criteria: dict[str, Any],
    free_form_criterion_comments: bool,
) -> str:
    return _RUBRIC_UPDATE_GUARD.fingerprint(
        json.dumps(current, sort_keys=True, separators=(",", ":"), default=str),
        title,
        json.dumps(criteria, sort_keys=True, separators=(",", ":"), default=str),
        "1" if free_form_criterion_comments else "0",
    )


def _render_rubric_update_preview(
    current: dict[str, Any],
    title: str,
    criteria: dict[str, Any],
    free_form_criterion_comments: bool,
) -> str:
    lines = [
        f"Rubric ID: {current['id']}",
        f"Association ID: {current['association']['id']}",
        f"Current title: {fence_untrusted_inline(str(current.get('title') or ''), 'rubric title')}",
        f"New title: {title}",
        "Replacement criteria (complete ID-preserving set):",
    ]
    current_criteria = {str(item["id"]): item for item in current["data"]}
    for criterion_id, criterion in criteria.items():
        lines.append(
            f"- {criterion_id}: {criterion['description']} ({float(criterion['points']):g} pts)"
        )
        previous = current_criteria[criterion_id]
        lines.append("  Current long description: " + fence_untrusted(
            previous.get("long_description") or "(empty)", "criterion long description"
        ))
        lines.append("  New long description: " + fence_untrusted(
            criterion.get("long_description") or "(empty)", "proposed criterion long description"
        ) if criterion.get("long_description") else "  New long description: (empty)")
        for field in ("criterion_use_range", "ignore_for_scoring"):
            if field in criterion:
                lines.append(f"  {field} (preserved): {criterion[field]}")
        current_ratings = {str(item["id"]): item for item in previous["ratings"]}
        for rating_id, rating in criterion["ratings"].items():
            lines.append(
                f"  - {rating_id}: {rating['description']} "
                f"({float(rating['points']):g} pts)"
            )
            lines.append("    Current long description: " + fence_untrusted(
                current_ratings[rating_id].get("long_description") or "(empty)",
                "rating long description",
            ))
            lines.append("    New long description: " + fence_untrusted(
                rating["long_description"], "proposed rating long description"
            ) if rating.get("long_description") else "    New long description: (empty)")
    lines.append("Assignment points possible: preserved")
    lines.append(
        "Free-form criterion comments: "
        + ("enabled" if free_form_criterion_comments else "disabled")
    )
    return "\n".join(lines)


def build_rubric_update_form_data(
    title: str,
    criteria: dict[str, Any],
    rubric_association_id: str,
    free_form_criterion_comments: bool,
) -> dict[str, str]:
    """Encode a full ID-preserving rubric replacement for Canvas."""
    form_data = {
        "rubric_association_id": rubric_association_id,
        "rubric[skip_updating_points_possible]": "1",
        "rubric[title]": title,
        "rubric[free_form_criterion_comments]": (
            "1" if free_form_criterion_comments else "0"
        ),
    }
    for criterion_index, (criterion_id, criterion) in enumerate(criteria.items()):
        prefix = f"rubric[criteria][{criterion_index}]"
        form_data[f"{prefix}[id]"] = criterion_id
        form_data[f"{prefix}[description]"] = str(criterion["description"])
        form_data[f"{prefix}[long_description]"] = str(
            criterion.get("long_description") or ""
        )
        form_data[f"{prefix}[points]"] = str(float(criterion["points"]))
        for field in ("criterion_use_range", "ignore_for_scoring"):
            if field in criterion:
                form_data[f"{prefix}[{field}]"] = "1" if criterion[field] else "0"

        for rating_index, (rating_id, rating) in enumerate(
            criterion["ratings"].items()
        ):
            rating_prefix = f"{prefix}[ratings][{rating_index}]"
            form_data[f"{rating_prefix}[id]"] = rating_id
            form_data[f"{rating_prefix}[description]"] = str(rating["description"])
            form_data[f"{rating_prefix}[long_description]"] = str(
                rating.get("long_description") or ""
            )
            form_data[f"{rating_prefix}[points]"] = str(float(rating["points"]))
    return form_data


def _update_response_has_expected_identity(
    response: Any,
    rubric_id: str,
    rubric_association_id: str,
) -> bool:
    if not isinstance(response, dict):
        return False
    rubric = response.get("rubric")
    association = response.get("rubric_association")
    return (
        isinstance(rubric, dict)
        and str(rubric.get("id")) == rubric_id
        and isinstance(association, dict)
        and str(association.get("id")) == rubric_association_id
        and str(association.get("rubric_id")) == rubric_id
    )


def _rubric_matches_requested_update(
    current: dict[str, Any],
    title: str,
    criteria: dict[str, Any],
    free_form_criterion_comments: bool,
) -> bool:
    if current.get("title") != title:
        return False
    if (
        bool(current.get("free_form_criterion_comments"))
        != free_form_criterion_comments
    ):
        return False

    returned = {
        str(criterion.get("id")): criterion
        for criterion in current["data"]
        if isinstance(criterion, dict) and criterion.get("id") is not None
    }
    if len(returned) != len(current["data"]) or set(returned) != set(criteria):
        return False
    try:
        for criterion_id, requested in criteria.items():
            actual = returned[criterion_id]
            if actual.get("description") != requested.get("description"):
                return False
            if (actual.get("long_description") or "") != (
                requested.get("long_description") or ""
            ):
                return False
            for field in ("criterion_use_range", "ignore_for_scoring"):
                if field in requested and bool(actual.get(field)) != bool(
                    requested[field]
                ):
                    return False
            actual_points = actual.get("points")
            requested_points = requested.get("points")
            if (
                actual_points is None
                or requested_points is None
                or not math.isclose(
                    float(actual_points),
                    float(requested_points),
                    rel_tol=1e-9,
                    abs_tol=1e-6,
                )
            ):
                return False

            raw_actual_ratings = actual.get("ratings")
            if not isinstance(raw_actual_ratings, list):
                return False
            actual_ratings = {
                str(rating.get("id")): rating
                for rating in raw_actual_ratings
                if isinstance(rating, dict) and rating.get("id") is not None
            }
            requested_ratings = requested["ratings"]
            if len(actual_ratings) != len(raw_actual_ratings) or set(
                actual_ratings
            ) != set(requested_ratings):
                return False
            for rating_id, requested_rating in requested_ratings.items():
                actual_rating = actual_ratings[rating_id]
                if actual_rating.get("description") != requested_rating.get(
                    "description"
                ):
                    return False
                if (actual_rating.get("long_description") or "") != (
                    requested_rating.get("long_description") or ""
                ):
                    return False
                actual_rating_points = actual_rating.get("points")
                requested_rating_points = requested_rating.get("points")
                if (
                    actual_rating_points is None
                    or requested_rating_points is None
                    or not math.isclose(
                        float(actual_rating_points),
                        float(requested_rating_points),
                        rel_tol=1e-9,
                        abs_tol=1e-6,
                    )
                ):
                    return False
    except (KeyError, TypeError, ValueError):
        return False
    return True


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


def rubric_grade_is_confirmed(
    assignment: dict[str, Any], assessment: dict[str, Any], response: dict[str, Any]
) -> bool:
    """Confirm the returned score for a complete rubric, excluding outcome-only criteria.

    Partial assessments or missing rubric metadata cannot establish the expected
    score. A matching score confirms the outcome, not a change or publication.
    """
    criteria = assignment.get("rubric")
    if not isinstance(criteria, list) or not criteria:
        return False
    try:
        ids = {str(c["id"]) for c in criteria}
        if ids != set(assessment):
            return False
        expected = sum(
            float(assessment[str(c["id"])]["points"])
            for c in criteria if not c.get("ignore_for_scoring", False)
        )
        score = response.get("score")
        if isinstance(score, bool) or not isinstance(score, (int, float)):
            return False
        return (
            response.get("grade") is not None
            and math.isfinite(expected) and math.isfinite(score)
            and math.isclose(score, expected, rel_tol=1e-9, abs_tol=1e-6)
        )
    except (KeyError, TypeError, ValueError):
        return False


RUBRIC_GRADE_UNCONFIRMED = (
    "Rubric grade unconfirmed: the assessment may have been saved, but Canvas's "
    "returned grade/score could not be verified against the complete rubric. "
    "Check the submission in Canvas before retrying. No explicit grade was forced."
)


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

    Canvas POST /courses/:id/rubrics expects indexed hashes for criteria and
    nested ratings. This function encodes them as bracket-notation form data,
    producing the flat key/value dict that
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

    @mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
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

            associations = response.get("associations", [])
            if associations:
                result += "Rubric Associations:\n"
                for association in associations:
                    if not isinstance(association, dict):
                        continue
                    result += (
                        f"  Rubric Association ID: {association.get('id', 'N/A')}\n"
                    )
                    association_type = str(
                        association.get("association_type", "Unknown")
                    )
                    association_label = (
                        "Assignment ID"
                        if association_type == "Assignment"
                        else "Associated Object ID"
                    )
                    result += (
                        f"  {association_label}: "
                        f"{association.get('association_id', 'N/A')}\n"
                    )
                    result += (
                        "  Association Type: "
                        f"{fence_untrusted_inline(association_type, 'rubric association type')}\n"
                    )

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
            return (
                "No rubric found for assignment "
                f"{fence_untrusted_inline(assignment_name, 'assignment name')} "
                f"in course {course_display}."
            )

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

    @mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
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
            return (
                f"No rubric assessment found for user {user_id} on assignment "
                f"{fence_untrusted_inline(assignment_name, 'assignment name')} "
                f"in course {course_display}."
            )

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

    @mcp.tool(annotations=ToolAnnotations(destructive_hint=True, idempotent_hint=False))
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
        # Backstop for issue 239: a comment or criterion comment lifted from
        # fenced read output would publish our provenance markers into the
        # student-visible gradebook. Refuse before any write.
        if contains_fence_markers(comment or ""):
            return FENCE_LEAK_ERROR
        for criterion in (rubric_assessment or {}).values():
            if isinstance(criterion, dict) and contains_fence_markers(
                str(criterion.get("comments") or "")
            ):
                return FENCE_LEAK_ERROR

        course_id = await get_course_id(course_identifier)
        assignment_id_str = str(assignment_id)
        user_id_str = str(user_id)

        # CRITICAL: Verify rubric is configured for grading BEFORE submitting
        assignment_check = await make_canvas_request(
            "get",
            f"/courses/{course_id}/assignments/{assignment_id_str}",
            params={"include[]": ["rubric", "rubric_settings"]}
        )

        if "error" in assignment_check:
            return "Error: Could not verify rubric grading settings; no assessment was submitted."

        use_rubric_for_grading = assignment_check.get("use_rubric_for_grading") is True
        if not use_rubric_for_grading:
            return (
                "⚠️  ERROR: Rubric is not configured for grading!\n\n"
                "The rubric exists but 'use_for_grading' is set to FALSE.\n"
                "Grades will NOT be saved to the gradebook.\n\n"
                "To fix this:\n"
                "1. Use get_rubric to verify rubric settings\n"
                "2. Use associate_rubric with use_for_grading=True\n"
                "3. Or configure the rubric in Canvas UI: Assignment Settings → Rubric → Use for Grading\n\n"
                f"Assignment: {fence_untrusted_inline(assignment_check.get('name', 'Unknown'), 'assignment name')}\n"
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

        if not rubric_grade_is_confirmed(assignment_check, rubric_assessment, response):
            return RUBRIC_GRADE_UNCONFIRMED

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
        result += f"Assignment: {fence_untrusted_inline(assignment_name, 'assignment name')}\n"
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

    @mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
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

    @mcp.tool(annotations=ToolAnnotations(destructive_hint=False, idempotent_hint=False))
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
    @mcp.tool(annotations=ToolAnnotations(destructive_hint=True, idempotent_hint=False))
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

        Encodes indexed criteria and ratings using bracket-notation form data.

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
        # Backstop for issue 239: refuse to publish our provenance markers into
        # the rubric's title or ANY criterion/rating description. Scanning the
        # raw criteria JSON covers every nested text field in one check.
        if contains_fence_markers(title) or contains_fence_markers(criteria):
            return FENCE_LEAK_ERROR

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

    @mcp.tool(annotations=ToolAnnotations(destructive_hint=True, idempotent_hint=True))
    @validate_params
    async def update_rubric(
        course_identifier: str | int,
        rubric_id: str | int,
        rubric_association_id: str | int,
        title: str,
        criteria: str,
        free_form_criterion_comments: bool | None = None,
        confirmation_token: str | None = None,
    ) -> str:
        """Safely replace an existing rubric after preview and confirmation.

        Canvas updates replace the full criteria set. ``criteria`` must
        therefore be an ID-keyed JSON object containing every current criterion
        and rating, with each object's ``id`` repeated inside it. This tool does
        not add or remove criteria/ratings; it edits their text and points while
        preserving IDs used by existing assessments.

        Call once without ``confirmation_token`` to receive a preview, show it
        to the educator, then call again with identical arguments and the token.
        Any rubric or association drift invalidates the token.

        Omit ``free_form_criterion_comments`` to preserve the rubric's current
        setting, or pass a boolean to change it explicitly.
        """
        if contains_fence_markers(title) or contains_fence_markers(criteria):
            return FENCE_LEAK_ERROR

        course_id = await get_course_id(course_identifier)
        rubric_id_str = str(rubric_id)
        association_id_str = str(rubric_association_id)
        response = await make_canvas_request(
            "get",
            f"/courses/{course_id}/rubrics/{rubric_id_str}",
            params={"include[]": ["associations"]},
        )
        try:
            current = _rubric_update_state(response, rubric_id_str, association_id_str)
            parsed_criteria = validate_rubric_update_criteria(criteria, current["data"])
        except ValueError as exc:
            return f"Error: Cannot safely update rubric — {exc}. Nothing was updated."

        # Inspect decoded and inherited text before issuing or redeeming a token.
        decoded_records = [
            record
            for criterion in parsed_criteria.values()
            for record in (criterion, *criterion["ratings"].values())
        ]
        if any(
            contains_fence_markers(value)
            for record in decoded_records
            for value in record.values()
            if isinstance(value, str)
        ):
            return FENCE_LEAK_ERROR

        desired_free_form_comments = (
            bool(current.get("free_form_criterion_comments"))
            if free_form_criterion_comments is None
            else free_form_criterion_comments
        )

        fingerprint = _rubric_update_fingerprint(
            current, title, parsed_criteria, desired_free_form_comments
        )
        if not confirmation_token:
            return preview_with_token(
                _RUBRIC_UPDATE_GUARD,
                fingerprint,
                "update_rubric",
                _render_rubric_update_preview(
                    current,
                    title,
                    parsed_criteria,
                    desired_free_form_comments,
                ),
                action="update",
            )

        confirmation_error = redeem_confirmation(
            _RUBRIC_UPDATE_GUARD, confirmation_token, fingerprint
        )
        if confirmation_error:
            return confirmation_error

        form_data = build_rubric_update_form_data(
            title,
            parsed_criteria,
            association_id_str,
            desired_free_form_comments,
        )
        update_response = await make_canvas_request(
            "put",
            f"/courses/{course_id}/rubrics/{rubric_id_str}",
            data=form_data,
            use_form_data=True,
        )
        if isinstance(update_response, dict) and "error" in update_response:
            return f"Error updating rubric: {update_response['error']}"
        if not _update_response_has_expected_identity(
            update_response, rubric_id_str, association_id_str
        ):
            returned_rubric = (
                update_response.get("rubric", {}).get("id")
                if isinstance(update_response, dict)
                and isinstance(update_response.get("rubric"), dict)
                else None
            )
            returned_association = (
                update_response.get("rubric_association", {}).get("id")
                if isinstance(update_response, dict)
                and isinstance(update_response.get("rubric_association"), dict)
                else None
            )
            return unconfirmed_write_warning(
                "Canvas updated the requested rubric rather than creating or "
                "returning a different copy",
                {
                    "Requested rubric ID": rubric_id_str,
                    "Returned rubric ID": returned_rubric,
                    "Requested association ID": association_id_str,
                    "Returned association ID": returned_association,
                },
                "The write may already have happened. Check Canvas before "
                "retrying; this tool will not retry automatically.",
            )

        readback_response = await make_canvas_request(
            "get",
            f"/courses/{course_id}/rubrics/{rubric_id_str}",
            params={"include[]": ["associations"]},
        )
        try:
            readback = _rubric_update_state(
                readback_response, rubric_id_str, association_id_str
            )
        except ValueError as exc:
            return unconfirmed_write_warning(
                "the rubric update by reading it back",
                {
                    "Rubric ID": rubric_id_str,
                    "Association ID": association_id_str,
                    "Read-back error": str(exc),
                },
                "The write may already have happened. Check Canvas before "
                "retrying; this tool will not retry automatically.",
            )
        if not _rubric_matches_requested_update(
            readback, title, parsed_criteria, desired_free_form_comments
        ):
            return unconfirmed_write_warning(
                "the rubric update matched the complete requested state",
                {
                    "Rubric ID": rubric_id_str,
                    "Association ID": association_id_str,
                },
                "Canvas returned different rubric content after the write. "
                "Check Canvas before retrying; this tool will not retry "
                "automatically.",
            )

        course_display = await get_course_code(course_id) or course_identifier
        return (
            "Rubric updated and verified successfully!\n\n"
            f"Course: {course_display}\n"
            f"Rubric ID: {rubric_id_str}\n"
            f"Association ID: {association_id_str}\n"
            f"Title: {title}\n"
            f"Criteria preserved: {len(parsed_criteria)}\n"
        )

    # Replaces the assignment's existing rubric association, and overwrites
    # use_for_grading / purpose even when re-associating the same rubric (#204).
    @mcp.tool(annotations=ToolAnnotations(destructive_hint=True, idempotent_hint=False))
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
                    "Assignment": f"{fence_untrusted_inline(assignment_name, 'assignment name')} (ID: {assignment_id})",
                    "Rubric ID": rubric_id,
                },
                "Canvas accepted the request but returned no association, so the "
                "rubric will most likely not appear on the assignment page. "
                "Verify in Canvas before relying on it.",
            )

        result = "Rubric associated with assignment successfully!\n\n"
        result += f"Course: {course_display}\n"
        result += f"Assignment: {fence_untrusted_inline(assignment_name, 'assignment name')} (ID: {assignment_id})\n"
        result += f"Rubric ID: {rubric_id}\n"
        result += f"Association ID: {association_id}\n"
        result += f"Used for Grading: {'Yes' if use_for_grading else 'No'}\n"
        result += f"Purpose: {purpose}\n"

        return result
