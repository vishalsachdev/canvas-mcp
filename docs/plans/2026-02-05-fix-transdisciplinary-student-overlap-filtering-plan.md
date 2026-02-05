---
title: "fix: Transdisciplinary discovery should filter by minimum student overlap"
type: fix
date: 2026-02-05
---

# fix: Transdisciplinary discovery should filter by minimum student overlap

## Enhancement Summary

**Deepened on:** 2026-02-05
**Sections enhanced:** 6
**Research agents used:** kieran-python-reviewer, code-simplicity-reviewer, performance-oracle, security-sentinel, agent-native-reviewer, architecture-strategist, pattern-recognition-specialist, best-practices-researcher

### Key Improvements from Deepening
1. **CRITICAL**: Identified FERPA violation - `sampled_student_ids` must be removed from response
2. **Architecture change**: Filter at orchestration layer, not internal function (matches codebase patterns)
3. **Statistical validity**: Current sample sizes (3-10) are below n=30 threshold; consider census for small courses
4. **Better algorithm**: Overlap Coefficient recommended instead of absolute count threshold

### New Considerations Discovered
- Parameter ordering matters for call site compatibility
- `courses_filtered_out` is YAGNI - not used elsewhere in codebase
- Consider proportional threshold (15% + minimum absolute) for better accuracy

---

## Overview

The `discover_opportunities` tool returns courses based on module timing and learning outcomes, but doesn't enforce a minimum student overlap threshold. This results in recommendations for courses that don't actually share meaningful student cohorts with the source course.

## Problem Statement

**Reported behavior:** User ran `discover_opportunities("DES 226")` and received recommendations for Biology, History, Humanities, and Design courses. However, these courses don't actually share students with DES 226.

**Root cause:** The tool samples 3 students (default) and finds their other enrollments. A course with `shared_student_count: 1` (only 1 of 3 sampled students) is still included in results. This is statistically meaningless for collaboration.

**Impact:** Teachers receive transdisciplinary project recommendations that are not actionable because the students in the recommended courses aren't the same students in their course.

## Proposed Solution

1. **Add `min_overlap` parameter** - Filter out courses with fewer than N shared students (default: 3)
2. **Increase default sample size** - Change from 3 to 10 students for better statistical accuracy
3. **Filter at orchestration layer** - Apply filtering in `discover_opportunities()`, keeping internal functions pure

### Research Insights

**Statistical Best Practices:**
- Sample size of 3-10 is below the n=30 threshold for statistical validity
- For Franklin School's small cohorts (15-35 students), consider census (sample all) instead of random sampling
- Use **Overlap Coefficient** (`|A ∩ B| / min(|A|, |B|)`) instead of absolute count for better handling of asymmetric course sizes

**Recommended Threshold Logic:**
```python
def is_meaningful_overlap(
    shared_count: int,
    source_course_size: int,
    other_course_size: int,
    min_absolute: int = 3,        # Minimum students for any recommendation
    min_percentage: float = 0.15  # 15% of smaller course
) -> bool:
    """Require BOTH absolute and proportional thresholds."""
    smaller_course = min(source_course_size, other_course_size)
    percentage_overlap = shared_count / smaller_course if smaller_course > 0 else 0
    return shared_count >= min_absolute and percentage_overlap >= min_percentage
```

**Performance Considerations:**
- 10 parallel API calls is acceptable for Canvas (well within 700 requests/10 minutes limit)
- Current burst+delay rate limiting is adequate at this scale
- Cap maximum sample size at 25 to prevent abuse

**References:**
- [NAEP Minimum Sample Sizes](https://nces.ed.gov/nationsreportcard/tdw/analysis/summary_rules_minimum.aspx)
- [NVIDIA: Jaccard vs. Overlap Coefficient](https://developer.nvidia.com/blog/similarity-in-graphs-jaccard-versus-the-overlap-coefficient/)

---

## Technical Approach

### Research Insights

**Architectural Best Practice:**
The codebase pattern (see `peer_reviews.py`) consistently applies filtering at the tool/orchestration layer, not in internal data-fetching functions. This preserves single responsibility.

**Pattern Reference:**
```python
# From peer_reviews.py - filtering at tool level
async def get_peer_review_followup_list(
    priority_filter: str = "all",  # Filter at TOOL level
    days_threshold: int = 3
) -> str:
```

---

### File: `src/canvas_mcp/tools/transdisciplinary.py`

#### Change 1: Add MAX_SAMPLE_SIZE constant (new, after line 133)

```python
# Security: Prevent abuse via parameter manipulation
MAX_SAMPLE_SIZE = 25
```

**Security Rationale:** Prevents unbounded API calls if a caller passes sample_size=1000.

---

#### Change 2: Update `_find_student_overlap()` - Remove student IDs from response (line 270-274)

```python
# BEFORE (FERPA VIOLATION)
return {
    "overlapping_courses": sorted_courses,
    "sample_size": len(sample),
    "sampled_student_ids": sampled_student_ids,  # REMOVE THIS
}

# AFTER (FERPA COMPLIANT)
return {
    "overlapping_courses": sorted_courses,
    "sample_size": len(sample),
    "source_course_size": len(enrollments),  # For overlap coefficient calculation
}
```

**Security Rationale:** `sampled_student_ids` exposes Canvas user IDs which constitute indirect PII and violate FERPA's "minimum necessary" principle. The agent doesn't need to know WHICH students - only that overlap exists.

---

#### Change 3: Keep internal function signature simple (NO min_overlap here)

```python
# Internal function stays focused on DATA FETCHING only
async def _find_student_overlap(
    course_id: int,
    sample_size: int = 10,  # Increased default
    term_id: int | None = None,
) -> dict:
    """Find courses sharing students with the source course.

    Samples students from the source course and finds their other enrollments.
    Returns ALL overlapping courses - filtering happens at orchestration layer.

    Args:
        course_id: Canvas course ID to find overlap for
        sample_size: Number of students to sample (default 10, max 25)
        term_id: Filter to specific term (optional)

    Returns dict with:
        - overlapping_courses: list of ALL courses with any shared students
        - sample_size: actual number of students sampled
        - source_course_size: total enrollment in source course
    """
```

**Architecture Rationale:** Internal functions should be pure data fetchers. Adding filtering here would violate single responsibility and create mixed concerns.

---

#### Change 4: Update `discover_opportunities()` to filter at orchestration layer (line 439-550)

```python
async def discover_opportunities(
    course_identifier: str | int,
    sample_size: int = 10,
    term_id: int | None = None,
    min_overlap: int = 3,  # Add at END to preserve call compatibility
) -> str:
    """Gather transdisciplinary discovery data for a course.

    Collects student overlap, concurrent modules, and learning outcomes.
    Returns structured data for analysis - does not rank or filter.

    Args:
        course_identifier: Course code (e.g., "ENG_100") or Canvas ID
        sample_size: Number of students to sample for overlap detection (default 10, max 25)
        term_id: Filter to specific term (defaults to current term from config)
        min_overlap: Minimum shared students to include a course (default 3)

    Returns:
        Structured data including:
        - Overlapping courses with shared student counts (filtered by min_overlap)
        - Concurrent modules with week ranges
        - Extracted learning outcomes per module
        - Franklin competency definitions for context
    """
    # Enforce maximum sample size
    effective_sample_size = min(sample_size, MAX_SAMPLE_SIZE)

    # ... existing code ...

    # Phase 1: Get ALL overlap data (unfiltered)
    overlap = await _find_student_overlap(course_id, effective_sample_size, effective_term_id)

    if "error" in overlap:
        return json.dumps({...})

    # FILTER AT ORCHESTRATION LAYER (not in internal function)
    all_overlapping = overlap.get("overlapping_courses", [])
    filtered_courses = [
        course for course in all_overlapping
        if course["shared_student_count"] >= min_overlap
    ]

    # Store filtering metadata for agent transparency
    overlap["overlapping_courses"] = filtered_courses
    overlap["min_overlap_applied"] = min_overlap

    # Continue Phase 2-3 with FILTERED courses only (reduces API calls)
    modules_result = await _find_concurrent_modules(course_id, filtered_courses)

    # ... rest of existing code ...
```

**Architecture Rationale:** Filtering at orchestration layer:
- Keeps internal functions single-purpose (data fetching only)
- Matches `peer_reviews.py` pattern
- Reduces API calls in Phase 2-3 by filtering early
- Preserves agent-native design - threshold is documented in response

---

#### Change 5: Update response structure for agent transparency

```python
results["data"]["student_overlap"] = {
    "overlapping_courses": filtered_courses,
    "sample_size": overlap.get("sample_size", 0),
    "source_course_size": overlap.get("source_course_size", 0),
    "min_overlap_applied": min_overlap,
}
```

**Agent-Native Rationale:** Including `min_overlap_applied` documents what threshold was used, allowing agents to explain filtering logic to users.

**YAGNI Note:** Do NOT add `courses_filtered_out` - this pattern isn't used elsewhere in the codebase and no one has requested it.

---

### File: `tests/tools/test_transdisciplinary.py`

#### Change 6: Expand mock enrollment data

```python
# BEFORE (3 students)
MOCK_ENROLLMENTS = [
    {"user_id": 1, "user": {"name": "Student A"}},
    {"user_id": 2, "user": {"name": "Student B"}},
    {"user_id": 3, "user": {"name": "Student C"}},
]

# AFTER (12 students - ensures sample of 10 works)
MOCK_ENROLLMENTS = [
    {"user_id": i, "user": {"name": f"Student {chr(64+i)}"}}
    for i in range(1, 13)
]
```

---

#### Change 7: Add test for minimum overlap filtering

```python
@pytest.mark.asyncio
async def test_discover_opportunities_filters_low_overlap(mock_canvas_request, mock_course_id):
    """Courses with overlap below min_overlap are filtered out."""
    # Setup: Create enrollments where only 1 student is in the "other" course
    mock_canvas_request.side_effect = [
        MOCK_ENROLLMENTS,  # Source course enrollments
        # User enrollments - only user 1 is in course 999
        [{"course_id": 999, "course_name": "Low Overlap Course"}],
        [],  # user 2 - not in course 999
        [],  # user 3 - not in course 999
        # ... more users not in course 999
    ]

    result = await discover_opportunities("TEST_COURSE", min_overlap=3)
    data = json.loads(result)

    # Course 999 should be filtered out (only 1 shared student < 3 min)
    course_ids = [c["course_id"] for c in data["data"]["student_overlap"]["overlapping_courses"]]
    assert 999 not in course_ids
    assert data["data"]["student_overlap"]["min_overlap_applied"] == 3
```

---

#### Change 8: Add test verifying sampled_student_ids is NOT in response (security)

```python
@pytest.mark.asyncio
async def test_discover_opportunities_no_student_ids_in_response(mock_canvas_request, mock_course_id):
    """FERPA compliance: student IDs should not be exposed in response."""
    # ... setup ...

    result = await discover_opportunities("TEST_COURSE")
    data = json.loads(result)

    # Verify no student IDs leaked
    assert "sampled_student_ids" not in data["data"]["student_overlap"]
```

---

## Acceptance Criteria

### Functional Requirements

- [x] Courses with `shared_student_count` below `min_overlap` are excluded from results
- [x] Default `min_overlap` is 3 (matches institutional guidance for meaningful cohorts)
- [x] Default `sample_size` is 10 (up from 3 for better accuracy)
- [x] Response includes `min_overlap_applied` for transparency
- [x] Can override both parameters when calling the tool
- [x] `sampled_student_ids` is NOT in the response (FERPA compliance)

### Non-Functional Requirements

- [x] No increase in API calls beyond the sample size increase (10 vs 3 = ~3x more user enrollment queries)
- [x] FERPA audit logging continues to work correctly
- [x] Bounded concurrency still respects rate limits
- [x] MAX_SAMPLE_SIZE (25) prevents abuse

### Quality Gates

- [x] All existing tests pass
- [x] New tests for min_overlap filtering pass
- [x] New test for FERPA compliance (no student IDs) passes
- [x] `pytest tests/tools/test_transdisciplinary.py -v` passes

---

## Dependencies & Prerequisites

- None - this is a self-contained fix within the transdisciplinary module

---

## Risk Analysis & Mitigation

| Risk | Impact | Mitigation |
|------|--------|------------|
| Larger sample size increases API calls | Medium | 10 students × 1 API call each = 10 calls vs 3. Still well within rate limits. Capped at MAX_SAMPLE_SIZE=25. |
| min_overlap=3 may be too restrictive for small courses | Low | Parameter is configurable; users can set min_overlap=1 if needed |
| Breaking change for existing callers | Low | `min_overlap` added at END of parameter list; defaults are backwards-compatible |
| Statistical validity concerns | Medium | n=10 is below n=30 threshold. Document that census (sample_size >= course_size) is recommended for small courses. |

### Research Insights

**Edge Cases:**
- Empty enrollments: Already handled, returns early with empty list
- Sample size > enrollment count: Already handled via `min(sample_size, len(enrollments))`
- All courses filtered out: Valid outcome - means no meaningful overlap exists

**Future Enhancements (Not in Scope):**
- Implement Overlap Coefficient for proportional threshold
- Add Fisher's exact test for statistical significance
- Census mode for courses under 50 students

---

## References & Research

### Internal References

- Brainstorm: `docs/brainstorms/2026-02-05-transdisciplinary-discovery-brainstorm.md`
- Implementation plan: `docs/plans/2026-02-05-feat-transdisciplinary-discovery-tools-plan.md`
- Current implementation: `src/canvas_mcp/tools/transdisciplinary.py:439-550`
- Existing tests: `tests/tools/test_transdisciplinary.py`

### Institutional Context

- Multi-course cohorts require 3+ courses with same students to qualify as "high-value" (Franklin policy)
- FERPA audit logging is required for cross-course student queries (already implemented)

### Pattern References

- Threshold parameters: `src/canvas_mcp/tools/peer_reviews.py:160` (`days_threshold: int = 3`)
- Range validation: `src/canvas_mcp/tools/modules.py:401-402`
- Filtering at tool layer: `src/canvas_mcp/tools/peer_reviews.py:156-185`

### External References (from deepening research)

- [NAEP Minimum Sample Sizes](https://nces.ed.gov/nationsreportcard/tdw/analysis/summary_rules_minimum.aspx)
- [NVIDIA: Jaccard vs. Overlap Coefficient](https://developer.nvidia.com/blog/similarity-in-graphs-jaccard-versus-the-overlap-coefficient/)
- [Statistical Significance of Set Overlap - Biostars](https://www.biostars.org/p/78697/)
- [Census vs. Sampling Methods](https://slm.mba/mmpc-005/census-vs-sampling-data-collection-method/)
