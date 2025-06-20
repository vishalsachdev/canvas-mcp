"""Rubric-related MCP tools for Canvas API."""

from typing import Union, Optional, Dict, Any
from mcp.server.fastmcp import FastMCP

from ..core.client import fetch_all_paginated_results, make_canvas_request
from ..core.cache import get_course_id, get_course_code
from ..core.validation import validate_params
from ..core.dates import format_date, truncate_text


def register_rubric_tools(mcp: FastMCP):
    """Register all rubric-related MCP tools."""
    
    @mcp.tool()
    @validate_params
    async def list_assignment_rubrics(course_identifier: Union[str, int], 
                                    assignment_id: Union[str, int]) -> str:
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
            result += f"Rubric Settings:\n"
            result += f"  Used for Grading: {'Yes' if use_rubric_for_grading else 'No'}\n"
            result += f"  Points Possible: {rubric_settings.get('points_possible', 'N/A')}\n"
            result += f"  Hide Score Total: {'Yes' if rubric_settings.get('hide_score_total') else 'No'}\n"
            result += f"  Hide Points: {'Yes' if rubric_settings.get('hide_points') else 'No'}\n\n"
        
        # Rubric criteria summary
        result += f"Criteria Overview:\n"
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
    async def get_assignment_rubric_details(course_identifier: Union[str, int], 
                                          assignment_id: Union[str, int]) -> str:
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
                
                for j, rating in enumerate(sorted_ratings):
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
                result += f"No rating scale defined for this criterion.\n"
            
            total_points += points
            result += "\n" + "-" * 40 + "\n"
        
        result += f"\nTotal Rubric Points: {total_points}"
        
        return result

    @mcp.tool()
    @validate_params
    async def get_rubric_details(course_identifier: Union[str, int], 
                               rubric_id: Union[str, int]) -> str:
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
    async def get_submission_rubric_assessment(course_identifier: Union[str, int],
                                             assignment_id: Union[str, int],
                                             user_id: Union[str, int]) -> str:
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
        
        result += f"Submission Details:\n"
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
    async def grade_with_rubric(course_identifier: Union[str, int],
                              assignment_id: Union[str, int],
                              user_id: Union[str, int],
                              rubric_assessment: str,
                              comment: Optional[str] = None) -> str:
        """Submit grades using rubric criteria.
        
        Args:
            course_identifier: The Canvas course code (e.g., badm_554_120251_246794) or ID
            assignment_id: The Canvas assignment ID
            user_id: The Canvas user ID of the student
            rubric_assessment: JSON string with rubric assessment data (format: {"criterion_id": {"points": X, "comments": "..."}, ...})
            comment: Optional overall comment for the submission
        """
        course_id = await get_course_id(course_identifier)
        assignment_id_str = str(assignment_id)
        user_id_str = str(user_id)
        
        # Parse rubric assessment JSON
        try:
            import json
            assessment_data = json.loads(rubric_assessment)
        except json.JSONDecodeError:
            return "Error: rubric_assessment must be valid JSON format. Example: {\"123\": {\"points\": 5, \"comments\": \"Good work\"}}"
        
        # Prepare submission data
        submission_data = {
            "rubric_assessment": assessment_data
        }
        
        if comment:
            submission_data["comment"] = comment
        
        # Submit the grade with rubric assessment
        response = await make_canvas_request(
            "put",
            f"/courses/{course_id}/assignments/{assignment_id_str}/submissions/{user_id_str}",
            data=submission_data
        )
        
        if "error" in response:
            return f"Error submitting rubric grade: {response['error']}"
        
        # Get assignment and user details for confirmation
        assignment_response = await make_canvas_request(
            "get", f"/courses/{course_id}/assignments/{assignment_id_str}"
        )
        assignment_name = assignment_response.get("name", "Unknown Assignment") if "error" not in assignment_response else "Unknown Assignment"
        
        # Calculate total points from rubric assessment
        total_points = sum(criterion.get("points", 0) for criterion in assessment_data.values())
        
        course_display = await get_course_code(course_id) or course_identifier
        
        result = f"Rubric Grade Submitted Successfully!\n\n"
        result += f"Course: {course_display}\n"
        result += f"Assignment: {assignment_name}\n"
        result += f"Student ID: {user_id}\n"
        result += f"Total Rubric Points: {total_points}\n"
        result += f"Graded At: {format_date(response.get('graded_at'))}\n"
        
        if comment:
            result += f"Comment: {comment}\n"
        
        result += f"\nRubric Assessment Summary:\n"
        for criterion_id, assessment in assessment_data.items():
            points = assessment.get("points", 0)
            comments = assessment.get("comments", "")
            result += f"  Criterion {criterion_id}: {points} points"
            if comments:
                result += f" - {truncate_text(comments, 50)}"
            result += "\n"
        
        return result