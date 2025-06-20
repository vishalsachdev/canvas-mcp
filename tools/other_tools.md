# Canvas MCP Server - Other Tools

This document provides detailed documentation for the miscellaneous tools available in the Canvas MCP server.

## Table of Contents
- [Page Tools](#page-tools)
- [User Tools](#user-tools)
  - [list_users](#list_users)
  - [get_user_details](#get_user_details)
- [Analytics Tools](#analytics-tools)
  - [get_student_analytics](#get_student_analytics)
  - [get_assignment_analytics](#get_assignment_analytics)

---

## Page Tools

For comprehensive page-related functionality, see the [Pages Implementation Guide](../PAGES_IMPLEMENTATION.md) which covers:
- Listing and managing pages
- Getting page details and content
- Working with front pages
- Module integration
- Advanced page workflows

---

## User Tools

### list_users

Lists users in a course.

**Parameters:**
- `course_identifier`: Canvas course code or ID
- `enrollment_type`: Filter by enrollment type (student, teacher, ta, etc.)
- `search_term`: Filter by name or email
- `sort`: Sort field (username, email, etc.)

**Example:**
```python
# List all users
await list_users("badm_554_120251_246794")

# List only students
await list_users(12345, enrollment_type="student")
```

---

### get_user_details

Gets details about a specific user.

**Parameters:**
- `user_id`: Canvas user ID
- `include_enrollments`: Include enrollment information (default: True)

**Example:**
```python
await get_user_details(54321)
```

---

## Analytics Tools

### get_student_analytics

Gets analytics for a specific student.

**Parameters:**
- `course_identifier`: Canvas course code or ID
- `student_id`: Canvas user ID
- `include_participation`: Include participation data (default: True)
- `include_assignments`: Include assignment data (default: True)

**Example:**
```python
await get_student_analytics("badm_554_120251_246794", 54321)
```

---

### get_assignment_analytics

Gets analytics for a specific assignment.

**Parameters:**
- `course_identifier`: Canvas course code or ID
- `assignment_id`: Canvas assignment ID
- `include_submissions`: Include submission data (default: True)

**Example:**
```python
await get_assignment_analytics("badm_554_120251_246794", 98765)
```

---

## Best Practices

1. **Error Handling**: All tools include comprehensive error handling
2. **Rate Limiting**: Respects Canvas API rate limits
3. **Caching**: Utilizes caching where appropriate for performance
4. **Pagination**: Handles pagination for large result sets
5. **Input Validation**: Validates all input parameters

## Common Error Scenarios

1. **Authentication Errors**: Check API token and permissions
2. **Not Found Errors**: Verify course, assignment, or user IDs
3. **Rate Limiting**: Tools include backoff and retry logic
4. **Network Issues**: Handles temporary network failures gracefully
