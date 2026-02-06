# Canvas API enrollment_term_id Filter is Unreliable

---
title: "Canvas MCP returns all historical courses instead of current term only"
created: 2026-02-06
category: api-issues
tags:
  - canvas
  - enrollment-term
  - filtering
  - courses
  - api
  - data-filtering
module: canvas-mcp
symptoms:
  - list_courses() returns every course the user has ever taught (50+ courses)
  - Student tools show assignments/grades from concluded courses
  - Account-level queries return courses across all enrollment terms
  - discover_opportunities() recommends courses from past semesters
severity: medium
status: resolved
affected_files:
  - src/canvas_mcp/tools/courses.py
  - src/canvas_mcp/tools/student_tools.py
  - src/canvas_mcp/tools/accounts.py
  - src/canvas_mcp/tools/transdisciplinary.py
  - src/canvas_mcp/core/cache.py
root_cause: >
  Canvas API's enrollment_term_id query parameter is unreliable. Even when
  passed explicitly, the API sometimes returns courses from other terms.
solution: >
  Client-side post-filtering after API response. Also include Default Term
  (ID 1) for ongoing courses when using config default.
---

## Problem

Canvas MCP tools were returning **all courses ever taught** instead of just courses from the current enrollment term. This made tools impractical for day-to-day use due to information overload.

### Symptoms Observed

- `list_courses()` returned 50+ courses spanning multiple years
- Student tools (`get_my_course_grades()`, etc.) showed outdated course data
- `discover_opportunities()` recommended courses with no current student overlap
- Account-level queries returned overwhelming amounts of historical data

## Root Cause

The Canvas LMS API's `enrollment_term_id` query parameter **does not reliably filter results**. When passed to endpoints like `/courses`, the API may still return courses from other terms. This is a known quirk of the Canvas REST API.

## Solution

### Two-Part Defensive Filtering

#### Part 1: Configuration-Based Default Term

Added `DEFAULT_TERM_ID` environment variable so institutions can set their current term once.

```bash
# .env
DEFAULT_TERM_ID=155  # Your current term ID (find via list_enrollment_terms)
```

#### Part 2: Client-Side Post-Filtering

Because the Canvas API filter is unreliable, all course-fetching functions now apply **defensive post-filtering** after receiving the API response.

```python
# Pattern applied to 9 functions across 5 files
if effective_term_id:
    # Always include the requested term
    allowed_terms = {int(effective_term_id)}

    # If falling back to config default (and no explicit term requested),
    # also include the system Default Term (1) which holds ongoing content
    if term_id is None:
        allowed_terms.add(1)

    courses = [
        c for c in courses
        if c.get("enrollment_term_id") and int(c.get("enrollment_term_id")) in allowed_terms
    ]
```

### Why Default Term (ID 1) Inclusion Matters

Canvas has a special "Default Term" (ID 1) containing ongoing institutional content:
- Sandbox/development courses
- Training materials
- Template courses

**Inclusion rules:**

| Scenario | Include Term 1? | Rationale |
|----------|-----------------|-----------|
| Using config default (`DEFAULT_TERM_ID`) | Yes | Include ongoing content |
| Explicit `term_id` parameter | No | Respect strict user intent |
| `include_all_terms=True` | N/A (no filtering) | User wants everything |

## Files Modified

| File | Functions | Change |
|------|-----------|--------|
| `core/cache.py` | `refresh_course_cache()` | Term filter + `include_all_terms` param |
| `tools/courses.py` | `list_courses()` | Post-filter + `include_all_terms` param |
| `tools/student_tools.py` | `get_my_submission_status()`, `get_my_course_grades()`, `get_my_peer_reviews_todo()` | Post-filter + `include_all_terms` param |
| `tools/accounts.py` | `list_account_courses()`, `get_account_analytics()`, `search_account_courses()` | Post-filter + `include_all_terms` param |
| `tools/transdisciplinary.py` | `discover_opportunities()`, `_find_student_overlap()` | Post-filter + `include_all_terms` param |

## Usage Examples

```python
# Uses DEFAULT_TERM_ID + Term 1 (ongoing courses)
list_courses()

# Only term 155, no Term 1
list_courses(term_id=155)

# All terms (historical data access)
list_courses(include_all_terms=True)
```

## Prevention

### Best Practice: Always Post-Filter Canvas API Results

When strict term filtering is needed, never trust the API filter alone:

```python
# Send filter to API (reduces payload) but ALWAYS verify client-side
params["enrollment_term_id"] = effective_term_id
courses = await fetch_all_paginated_results("/courses", params)

# Post-filter to guarantee correctness
if effective_term_id:
    allowed_terms = {int(effective_term_id)}
    if term_id is None:
        allowed_terms.add(1)
    courses = [c for c in courses
               if c.get("enrollment_term_id") and int(c["enrollment_term_id"]) in allowed_terms]
```

### Handle Inconsistent Field Names

Different Canvas endpoints return term IDs in different fields:

```python
# Enrollment endpoints may use either field
enc_term = enrollment.get("course_enrollment_term_id") or enrollment.get("enrollment_term_id")
```

## Verification

1. Set `DEFAULT_TERM_ID=<your_term>` in `.env`
2. Run `list_courses()` - should only show current term + ongoing courses
3. Run `list_courses(include_all_terms=True)` - should show all historical courses
4. Run `pytest tests/` - all tests pass (245 passed)

## Related Documentation

- [Canvas Courses API](https://canvas.instructure.com/doc/api/courses.html)
- [Canvas Enrollment Terms API](https://canvas.instructure.com/doc/api/enrollment_terms.html)
- `docs/solutions/configuration-fixes/prevent-accidental-push-to-upstream.md` - Git remote safety

## Key Takeaway

**Canvas API filtering is unreliable for `enrollment_term_id`.** Always implement defensive post-filtering when strict term boundaries are required.
