# Canvas MCP Server - Rubric Tools

This document provides detailed documentation for the rubric-related tools available in the Canvas MCP server.

## Table of Contents
- [list_assignment_rubrics](#list_assignment_rubrics)
- [get_assignment_rubric_details](#get_assignment_rubric_details)
- [get_rubric_details](#get_rubric_details)
- [create_rubric](#create_rubric)
- [update_rubric](#update_rubric)
- [delete_rubric](#delete_rubric)
- [assess_with_rubric](#assess_with_rubric)
- [get_rubric_assessment](#get_rubric_assessment)

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

## create_rubric

Creates a new rubric in a course.

### Parameters
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| course_identifier | string or int | Yes | Canvas course code or ID |
| title | string | Yes | Rubric title |
| criteria | list | Yes | List of criterion objects |
| points_possible | number | No | Total points possible |
| free_form_criterion_comments | boolean | No | Allow free-form comments |

### Returns
A success message with the new rubric ID, or an error message.

### Example
```python
# Create a new rubric
criteria = [
    {
        "description": "Content Quality",
        "points": 10,
        "ratings": [
            {"description": "Excellent", "points": 10},
            {"description": "Good", "points": 7},
            {"description": "Needs Work", "points": 3}
        ]
    }
]
await create_rubric("badm_554_120251_246794", "Research Paper Rubric", criteria, 10)
```

### Error Handling
- Validates input parameters
- Checks for duplicate rubric names
- Returns detailed error messages for API failures

---

## update_rubric

Updates an existing rubric.

### Parameters
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| course_identifier | string or int | Yes | Canvas course code or ID |
| rubric_id | string or int | Yes | Canvas rubric ID |
| updates | dict | Yes | Dictionary of fields to update |

### Returns
A success message with the updated rubric details, or an error message.

### Example
```python
# Update a rubric
updates = {
    "title": "Updated Rubric Name",
    "free_form_criterion_comments": True
}
await update_rubric("badm_554_120251_246794", 54321, updates)
```

### Error Handling
- Validates rubric existence
- Checks for permission to update
- Returns appropriate error messages

---

## delete_rubric

Deletes a rubric from a course.

### Parameters
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| course_identifier | string or int | Yes | Canvas course code or ID |
| rubric_id | string or int | Yes | Canvas rubric ID |

### Returns
A success message, or an error message if the deletion fails.

### Example
```python
# Delete a rubric
await delete_rubric("badm_554_120251_246794", 54321)
```

### Error Handling
- Validates rubric existence
- Checks for rubric usage before deletion
- Returns appropriate error messages

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
