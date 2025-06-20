# Canvas MCP Server - Assignment Tools

This document provides detailed documentation for the assignment-related tools available in the Canvas MCP server.

## Table of Contents
- [list_assignments](#list_assignments)
- [get_assignment_details](#get_assignment_details)
- [assign_peer_review](#assign_peer_review)
- [list_peer_reviews](#list_peer_reviews)
- [get_assignment_analytics](#get_assignment_analytics)
- [get_student_analytics](#get_student_analytics)

---

## list_assignments

Lists all assignments for a specific course.

### Parameters
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| course_identifier | string or int | Yes | Canvas course code (e.g., 'badm_554_120251_246794') or ID |

### Returns
A formatted string containing a list of assignments with their IDs, names, due dates, and point values.

### Example
```python
# List all assignments for a course
await list_assignments("badm_554_120251_246794")

# List using course ID
await list_assignments(12345)
```

### Error Handling
- Returns an error message if the course cannot be found
- Returns a message if no assignments are found
- Handles pagination for courses with many assignments

---

## get_assignment_details

Retrieves detailed information about a specific assignment.

### Parameters
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| course_identifier | string or int | Yes | Canvas course code or ID |
| assignment_id | string or int | Yes | Canvas assignment ID |

### Returns
A formatted string containing detailed assignment information including:
- Assignment name and description (truncated)
- Due date
- Points possible
- Submission types
- Publication status
- Lock status

### Example
```python
# Get details for an assignment
await get_assignment_details("badm_554_120251_246794", 98765)
```

### Error Handling
- Validates input parameters
- Returns an error message if the assignment cannot be found
- Handles various assignment states (published, locked, etc.)

---

## assign_peer_review

Manually assigns a peer review to a student for a specific assignment.

### Parameters
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| course_identifier | string or int | Yes | Canvas course code or ID |
| assignment_id | string | Yes | Canvas assignment ID |
| reviewer_id | string | Yes | Canvas user ID of the student who will do the review |
| reviewee_id | string | Yes | Canvas user ID of the student being reviewed |

### Returns
A success message with details of the peer review assignment, or an error message if the operation fails.

### Example
```python
# Assign a peer review
await assign_peer_review("badm_554_120251_246794", "98765", "student123", "student456")
```

### Error Handling
- Validates all input parameters
- Handles cases where the reviewee hasn't submitted work (creates a placeholder submission)
- Returns detailed error messages for API failures

### Notes
- If the reviewee hasn't submitted work, a placeholder submission will be created automatically
- The reviewer must have permission to view the reviewee's submission

---

## list_peer_reviews

Lists all peer review assignments for a specific assignment.

### Parameters
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| course_identifier | string or int | Yes | Canvas course code or ID |
| assignment_id | string | Yes | Canvas assignment ID |

### Returns
A formatted string containing:
- List of all peer review assignments
- For each assignment, shows reviewer and reviewee information
- Review status and completion status

### Example
```python
# List all peer reviews for an assignment
await list_peer_reviews("badm_554_120251_246794", "98765")
```

### Error Handling
- Validates course and assignment existence
- Handles cases with no submissions or peer reviews
- Returns appropriate error messages for API failures

---

## get_assignment_analytics

Retrieves analytics for a specific assignment.

### Parameters
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| course_identifier | string or int | Yes | Canvas course code or ID |
| assignment_id | string or int | Yes | Canvas assignment ID |

### Returns
A formatted string containing assignment analytics including:
- Submission statistics (submitted, graded, late, missing)
- Score distribution
- Grade distribution
- Average, median, and standard deviation of scores

### Example
```python
# Get analytics for an assignment
await get_assignment_analytics("badm_554_120251_246794", 98765)
```

### Error Handling
- Validates course and assignment existence
- Handles cases with no submissions
- Returns appropriate error messages for API failures

---

## get_student_analytics

Retrieves analytics for a specific student across all assignments.

### Parameters
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| course_identifier | string or int | Yes | Canvas course code or ID |
| student_id | string or int | Yes | Canvas user ID of the student |

### Returns
A formatted string containing student analytics including:
- Overall course grade
- Assignment submission status
- Late and missing assignments
- Grade trend over time

### Example
```python
# Get analytics for a student
await get_student_analytics("badm_554_120251_246794", "student123")
```

### Error Handling
- Validates course and student existence
- Handles cases with no submissions
- Returns appropriate error messages for API failures

---

## Best Practices

1. **Caching**: Assignment data is cached to improve performance
2. **Rate Limiting**: Tools respect Canvas API rate limits
3. **Error Handling**: Comprehensive error handling for common scenarios
4. **Pagination**: Handles pagination for large result sets
5. **Data Validation**: Input parameters are validated before making API calls

## Common Error Scenarios

1. **Course Not Found**: Verify the course identifier is correct
2. **Assignment Not Found**: Check the assignment ID and course association
3. **Permission Issues**: Ensure the API token has sufficient permissions
4. **Rate Limiting**: Tools include backoff and retry logic for rate-limited requests
5. **Network Issues**: Tools handle temporary network failures gracefully
