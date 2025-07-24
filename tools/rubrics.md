# Canvas MCP Server - Rubric Tools

This document provides detailed documentation for the rubric-related tools available in the Canvas MCP server.

## Table of Contents
- [list_assignment_rubrics](#list_assignment_rubrics)
- [get_assignment_rubric_details](#get_assignment_rubric_details)
- [get_rubric_details](#get_rubric_details)
- [list_all_rubrics](#list_all_rubrics)
- [create_rubric](#create_rubric)
- [update_rubric](#update_rubric)
- [delete_rubric](#delete_rubric)
- [associate_rubric_with_assignment](#associate_rubric_with_assignment)
- [grade_with_rubric](#grade_with_rubric)
- [get_submission_rubric_assessment](#get_submission_rubric_assessment)

---

## list_assignment_rubrics

Lists rubrics attached to a specific assignment.

### Parameters
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| course_identifier | string or int | Yes | Canvas course code (e.g., 'badm_554_120251_246794') or ID |
| assignment_id | string or int | Yes | Canvas assignment ID |

### Returns
A formatted string containing:
- Assignment and course information
- Rubric settings (points possible, visibility options)
- List of criteria with point values and rating levels
- Total possible points and number of criteria

### Example
```python
# List rubrics for an assignment
await list_assignment_rubrics("badm_554_120251_246794", 98765)
```

### Error Handling
- Returns an error message if the assignment or rubric cannot be found
- Handles cases where no rubric is attached
- Validates input parameters

---

## get_assignment_rubric_details

Gets detailed rubric criteria and rating descriptions for an assignment.

### Parameters
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| course_identifier | string or int | Yes | Canvas course code or ID |
| assignment_id | string or int | Yes | Canvas assignment ID |

### Returns
A formatted string containing:
- Assignment and course information
- Rubric metadata and settings
- Detailed criteria descriptions
- Complete rating scales with point values
- Long descriptions for criteria and ratings

### Example
```python
# Get detailed rubric information
await get_assignment_rubric_details("badm_554_120251_246794", 98765)
```

### Error Handling
- Validates course and assignment existence
- Handles cases with no attached rubric
- Returns appropriate error messages for API failures

---

## get_rubric_details

Gets detailed information about a specific rubric.

### Parameters
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| course_identifier | string or int | Yes | Canvas course code or ID |
| rubric_id | string or int | Yes | Canvas rubric ID |

### Returns
A formatted string containing:
- Rubric metadata and settings
- Detailed criteria and rating scales
- Point values and descriptions
- Usage statistics (if available)

### Example
```python
# Get details for a specific rubric
await get_rubric_details("badm_554_120251_246794", 54321)
```

### Error Handling
- Validates rubric existence
- Handles permission issues
- Returns appropriate error messages

---

## list_all_rubrics

Lists all rubrics in a specific course with optional detailed criteria.

### Parameters
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| course_identifier | string or int | Yes | Canvas course code or ID |
| include_criteria | boolean | No | Whether to include detailed criteria and ratings (default: True) |

### Returns
A formatted string containing all rubrics in the course with their complete criteria structures.

### Example
```python
# List all rubrics in a course
await list_all_rubrics("badm_554_120251_246794", include_criteria=True)
```

### Error Handling
- Validates course existence
- Handles cases with no rubrics
- Returns appropriate error messages

---

## create_rubric

Creates a new rubric in a course with comprehensive validation and flexible criteria formats.

### Parameters
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| course_identifier | string or int | Yes | Canvas course code or ID |
| title | string | Yes | Rubric title |
| criteria | string or dict | Yes | JSON string or dictionary containing rubric criteria structure |
| free_form_criterion_comments | boolean | No | Allow free-form comments (default: True) |
| association_id | string or int | No | ID to associate rubric with (assignment, course, etc.) |
| association_type | string | No | Type of association (Assignment, Course, Account) |
| use_for_grading | boolean | No | Whether to use rubric for grade calculation (default: False) |
| purpose | string | No | Purpose of the rubric association (grading, bookmark) |

### Returns
A success message with the new rubric details, or detailed error message with debugging information.

### Example Criteria Format
```python
# Object format for ratings
criteria = {
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

# Array format for ratings (also supported)
criteria_alt = {
    "1": {
        "description": "Quality of Work",
        "points": 25,
        "ratings": [
            {"description": "Excellent", "points": 25},
            {"description": "Good", "points": 20},
            {"description": "Satisfactory", "points": 15},
            {"description": "Needs Improvement", "points": 10}
        ]
    }
}

await create_rubric("badm_554_120251_246794", "Research Paper Rubric", criteria)
```

### Error Handling
- Comprehensive JSON validation with detailed error messages
- Support for both string and dictionary input
- Debugging information for malformed criteria
- Graceful handling of Canvas API errors

---

## update_rubric

Updates an existing rubric with comprehensive validation and flexible criteria formats.

### Parameters
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| course_identifier | string or int | Yes | Canvas course code or ID |
| rubric_id | string or int | Yes | Canvas rubric ID |
| title | string | No | Optional new title for the rubric |
| criteria | string or dict | No | Optional JSON string or dictionary containing updated rubric criteria |
| free_form_criterion_comments | boolean | No | Optional boolean to allow free-form comments |
| skip_updating_points_possible | boolean | No | Skip updating points possible calculation (default: False) |

### Returns
A success message with the updated rubric details, or detailed error message with debugging information.

### Example
```python
# Update rubric title and settings
await update_rubric("badm_554_120251_246794", 54321, 
                   title="Updated Rubric Name", 
                   free_form_criterion_comments=True)

# Update rubric criteria
new_criteria = {
    "1": {
        "description": "Updated Quality Criterion",
        "points": 30,
        "ratings": [
            {"description": "Excellent", "points": 30},
            {"description": "Good", "points": 20},
            {"description": "Needs Work", "points": 10}
        ]
    }
}
await update_rubric("badm_554_120251_246794", 54321, criteria=new_criteria)
```

### Error Handling
- Validates rubric existence and permissions
- Comprehensive criteria validation with debugging information
- Handles partial updates gracefully

---

## delete_rubric

Deletes a rubric and removes all its associations.

### Parameters
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| course_identifier | string or int | Yes | Canvas course code or ID |
| rubric_id | string or int | Yes | Canvas rubric ID |

### Returns
A success message with deletion confirmation, or an error message if the deletion fails.

### Example
```python
# Delete a rubric
await delete_rubric("badm_554_120251_246794", 54321)
```

### Error Handling
- Validates rubric existence
- Provides confirmation of rubric details before deletion
- Handles association removal automatically

---

## associate_rubric_with_assignment

Associates an existing rubric with an assignment.

### Parameters
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| course_identifier | string or int | Yes | Canvas course code or ID |
| rubric_id | string or int | Yes | Canvas rubric ID |
| assignment_id | string or int | Yes | Canvas assignment ID |
| use_for_grading | boolean | No | Whether to use rubric for grade calculation (default: False) |
| purpose | string | No | Purpose of the association (grading, bookmark) (default: grading) |

### Returns
A success message with association details, or an error message.

### Example
```python
# Associate rubric with assignment for grading
await associate_rubric_with_assignment("badm_554_120251_246794", 54321, 98765, 
                                      use_for_grading=True, purpose="grading")
```

### Error Handling
- Validates rubric and assignment existence
- Confirms association creation
- Returns detailed error messages

---

## assess_with_rubric

Assesses a submission using a rubric.

### Parameters
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| course_identifier | string or int | Yes | Canvas course code or ID |
| assignment_id | string or int | Yes | Canvas assignment ID |
| user_id | string or int | Yes | Canvas user ID of the student being assessed |
| assessor_id | string or int | Yes | Canvas user ID of the assessor |
| assessment | dict | Yes | Assessment data including ratings and comments |

### Returns
A success message with assessment details, or an error message.

### Example
```python
# Assess a submission
assessment = {
    "criteria": {
        "1": {
            "points": 8,
            "comments": "Good work on this section."
        }
    },
    "comments": "Overall good submission."
}
await assess_with_rubric("badm_554_120251_246794", 98765, "student123", "teacher456", assessment)
```

### Error Handling
- Validates all input parameters
- Checks submission and rubric status
- Returns detailed error messages

---

## get_rubric_assessment

Gets a rubric assessment for a submission.

### Parameters
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| course_identifier | string or int | Yes | Canvas course code or ID |
| assignment_id | string or int | Yes | Canvas assignment ID |
| user_id | string or int | Yes | Canvas user ID of the student |
| assessment_type | string | No | Type of assessment ('grading' or 'peer_review') |
| assessor_id | string or int | No | Canvas user ID of the assessor (for peer reviews) |

### Returns
A formatted string containing the rubric assessment details.

### Example
```python
# Get a rubric assessment
await get_rubric_assessment("badm_554_120251_246794", 98765, "student123")

# Get a peer review assessment
await get_rubric_assessment("badm_554_120251_246794", 98765, "student123", 
                          assessment_type="peer_review", 
                          assessor_id="student456")
```

### Error Handling
- Validates submission and assessment existence
- Handles different assessment types
- Returns appropriate error messages

---

## Best Practices

1. **Caching**: Rubric data is cached to improve performance
2. **Validation**: All input parameters are validated
3. **Error Handling**: Comprehensive error handling for common scenarios
4. **Rate Limiting**: Respects Canvas API rate limits
5. **Data Formatting**: Consistent formatting of rubric data

## Common Error Scenarios

1. **Rubric Not Found**: Verify the rubric ID and course association
2. **Permission Issues**: Ensure the API token has sufficient permissions
3. **Invalid Data**: Check that rubric criteria and ratings are properly formatted
4. **Rate Limiting**: Tools include backoff and retry logic
5. **Network Issues**: Handles temporary network failures gracefully

---

## Typical Rubric Workflow

### 1. Discover Rubrics
```bash
# Find rubrics for an assignment
list_assignment_rubrics(course_id, assignment_id)
```

### 2. Understand Criteria
```bash
# Get detailed rubric breakdown
get_rubric_details(course_id, rubric_id)
```

### 3. Review Existing Grades
```bash  
# Check current rubric assessment
get_submission_rubric_assessment(course_id, assignment_id, user_id)
```

### 4. Submit New Grades
```bash
# Grade using rubric criteria
grade_with_rubric(course_id, assignment_id, user_id, assessment_json, comment)
```

## Key Features

### Comprehensive Error Handling
- Validates rubric existence and accessibility
- Provides clear error messages for missing data
- Handles JSON parsing errors gracefully

### Rich Data Display
- Formatted rubric criteria with descriptions
- Point breakdowns and rating level details
- Student-friendly assessment summaries

### Flexible Grading
- Support for partial points within criteria
- Individual comments per criterion
- Overall submission comments

### Integration Ready
- Follows modular architecture patterns
- Consistent with existing tool design
- Compatible with current caching and validation systems

## Benefits for Educators

### Streamlined Grading
- View complete rubric structure before grading
- Apply consistent criteria across submissions
- Track detailed feedback per learning objective

### Quality Assurance
- Review existing rubric assessments
- Ensure grading consistency across sections
- Maintain detailed grading records

### Efficient Workflows
- Batch process rubric-based grading
- Integrate with external grading tools
- Export detailed assessment data

## Getting Started

1. **Update Server**: Use `canvas_server_refactored.py`
2. **Test Connection**: Verify Canvas API access
3. **Find Assignment**: Use existing assignment tools
4. **Explore Rubrics**: Start with `list_assignment_rubrics`
5. **Grade Students**: Use `grade_with_rubric` for assessment
