# Canvas MCP Server - Course Tools

This document provides detailed documentation for the course-related tools available in the Canvas MCP server.

## Table of Contents
- [list_courses](#list_courses)
- [get_course_details](#get_course_details)
- [get_course_content_overview](#get_course_content_overview)

---

## list_courses

Lists all available courses for the authenticated user.

### Parameters
| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| include_concluded | boolean | No | False | Include concluded courses in the results |
| include_all | boolean | No | False | Include all courses, not just those where the user is a teacher |

### Returns
A formatted string containing a list of courses with their codes, names, and IDs.

### Example
```python
# List all active courses where user is a teacher
await list_courses()

# Include concluded courses
await list_courses(include_concluded=True)

# Include all courses (not just teacher courses)
await list_courses(include_all=True)
```

### Error Handling
- Returns an error message if there's an issue fetching courses
- Returns "No courses found" if no courses match the criteria

---

## get_course_details

Retrieves detailed information about a specific course.

### Parameters
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| course_identifier | string or int | Yes | Canvas course code (e.g., 'badm_554_120251_246794') or ID |

### Returns
A formatted string containing detailed course information including:
- Course code and name
- Start and end dates
- Time zone
- Default view settings
- Public/private status
- Blueprint status

### Example
```python
# Get details using course code
await get_course_details("badm_554_120251_246794")

# Get details using course ID
await get_course_details(12345)
```

### Error Handling
- Returns an error message if the course cannot be found
- Validates input parameters

---

## get_course_content_overview

Provides a comprehensive overview of course content including pages and modules.

### Parameters
| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| course_identifier | string or int | Yes | - | Canvas course code or ID |
| include_pages | boolean | No | True | Include pages information in the overview |
| include_modules | boolean | No | True | Include modules and their items in the overview |

### Returns
A formatted string containing:
- Course name
- Pages summary (if include_pages is True)
  - Total, published, and unpublished pages
  - Recent page updates
- Modules summary (if include_modules is True)
  - Total modules and items
  - Item type breakdown
  - Module structure overview

### Example
```python
# Get full content overview
await get_course_content_overview("badm_554_120251_246794")

# Get only modules overview
await get_course_content_overview(12345, include_pages=False)

# Get only pages overview
await get_course_content_overview("badm_554_120251_246794", include_modules=False)
```

### Error Handling
- Returns appropriate error messages if the course cannot be accessed
- Handles missing or invalid parameters
- Gracefully handles API limitations (e.g., only shows first 10 modules for performance)

---

## Caching Behavior

All course tools utilize a caching mechanism to improve performance:
- Course codes and IDs are cached for faster lookups
- The cache is automatically updated when courses are listed or details are fetched
- The cache persists for the duration of the server session

## Rate Limiting

These tools respect Canvas API rate limits and include:
- Automatic retry logic for rate-limited requests
- Pagination handling for large result sets
- Efficient batching of API calls
