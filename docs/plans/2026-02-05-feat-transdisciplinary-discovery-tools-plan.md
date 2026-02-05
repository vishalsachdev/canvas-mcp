---
title: Port TD Serendipity Generator to Canvas MCP
type: feat
date: 2026-02-05
deepened: 2026-02-05
---

# Port TD Serendipity Generator to Canvas MCP

## Enhancement Summary

**Deepened on:** 2026-02-05
**Research agents used:** kieran-python-reviewer, performance-oracle, security-sentinel, code-simplicity-reviewer, architecture-strategist, agent-native-reviewer, pattern-recognition-specialist, best-practices-researcher, Context7 (FastMCP)

### Key Improvements
1. **Simplified architecture**: Reduced from 6 tools to 2-3 agent-native primitives
2. **Modern Python patterns**: Use `list[str]` not `List[str]`, frozen dataclasses, named functions
3. **Performance hardening**: Bounded concurrency, tiered caching, adaptive rate limiting
4. **FERPA compliance**: Audit logging, data minimization, purpose-based access control
5. **Agent-native design**: Primitives over workflows, let Claude do the reasoning

### Critical Findings
- **Simplify**: The 6-tool design is over-fragmented; users want "find opportunities" not intermediate steps
- **Type hints**: Use Python 3.10+ syntax (`list[str]` not `List[str]`, `T | None` not `Optional[T]`)
- **Security**: Cross-course enrollment queries require explicit audit logging for FERPA
- **Performance**: At 100+ courses, unbounded parallelism will exhaust rate limits

---

## Overview

Port the existing TypeScript TD Serendipity Generator to Python MCP tools. This system discovers transdisciplinary collaboration opportunities by analyzing student overlap, module timing, learning outcomes, and using AI to generate project ideas mapped to Franklin's 9 competencies.

**Source**: `/Users/jdec/Documents/TD_Serendipity_Generator_V1/` (TypeScript)
**Target**: `src/canvas_mcp/tools/transdisciplinary.py` (Python MCP)

## Problem Statement / Motivation

Franklin School uses transdisciplinary education to connect learning across courses. Currently, discovering collaboration opportunities requires manual effort from educators. The existing TypeScript tool works but is standalone - integrating into Canvas MCP enables:

1. **Conversational interface**: "Find opportunities for ENG 100"
2. **Unified tooling**: Same MCP server handles all Canvas operations
3. **Institutional scale**: Works with account-level access for admins
4. **Faster iteration**: Python codebase matches existing Canvas MCP patterns

## Proposed Solution (Simplified)

### Research Insight: Simplify to 2-3 Tools

**Original plan**: 6 MCP tools
**Revised plan**: 2-3 agent-native primitives

The simplicity reviewer identified that users want outcomes, not intermediate steps. The agent-native reviewer confirmed: **primitives over workflows**.

| Tool | Purpose | Agent-Native? |
|------|---------|---------------|
| `discover_opportunities` | Gather all discovery data for a course | YES (data gatherer) |
| `get_crossover_details` | Deep dive on a specific module pair | YES (optional detail) |
| `list_competencies` | Reference: Franklin's 9 competencies | YES (static reference) |

**Removed**: `find_student_overlap`, `find_concurrent_modules`, `extract_learning_outcomes`, `analyze_crossover_opportunity` - these become **internal functions**, not exposed tools.

### Research Insight: Inline Helper Modules

**Original plan**: `core/competencies.py` + `core/week_parser.py`
**Revised plan**: Inline at top of `transdisciplinary.py`

The simplicity reviewer found this reduces 150+ lines while maintaining clarity.

## Technical Approach

### Architecture (Simplified)

```
┌─────────────────────────────────────────────────────────────────┐
│                    discover_opportunities()                      │
│               (Data Gatherer - Returns raw data)                │
│                                                                  │
│   Internally calls:                                             │
│   - _find_student_overlap()    (Phase 1)                       │
│   - _find_concurrent_modules() (Phase 2) ─┐                    │
│   - _extract_learning_outcomes() (Phase 3)─┴─ Can parallelize  │
│                                                                  │
│   Returns: Structured data for Claude to analyze               │
│   Does NOT: Make value judgments, rank results, encode logic   │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    get_crossover_details()                       │
│            (Optional deep dive on specific pair)                │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    list_competencies()                          │
│                  (Static reference data)                        │
└─────────────────────────────────────────────────────────────────┘
```

### Research Insight: Phase Parallelization

The architecture reviewer confirmed that **Phases 2-3 can run in parallel** after Phase 1:

```python
async def discover_opportunities(...):
    # Phase 1 - REQUIRED FIRST (identifies which courses to analyze)
    overlap_courses = await _find_student_overlap(...)

    # Phases 2-3 can parallelize - both only depend on Phase 1 output
    async with asyncio.TaskGroup() as tg:
        concurrent_task = tg.create_task(_find_concurrent_modules(...))
        outcomes_task = tg.create_task(_extract_learning_outcomes(...))

    # Combine results into structured output
    return format_discovery_results(overlap_courses, concurrent_task.result(), outcomes_task.result())
```

**Expected performance gain**: 30-40% latency reduction when analyzing multiple courses.

### Research Insight: Agent-Native Design

The agent-native reviewer identified that `discover_opportunities` should be a **data gatherer**, not a decision maker:

**Before (workflow-shaped - WRONG)**:
```python
async def discover_opportunities(...) -> str:
    """End-to-end pipeline that finds... and prepares crossover analysis."""
    # Returns ranked, filtered results with "analysis prompts"
```

**After (agent-native - CORRECT)**:
```python
async def discover_opportunities(...) -> str:
    """Collect student overlap, concurrent modules, and learning outcomes.

    Returns raw data for agent analysis. Does not rank or filter results.
    Agent should use this data with their own criteria to identify opportunities.
    """
    # Returns structured data, no value judgments
```

## Implementation Phases

### Phase 1: Foundation (Single File)

**Tasks:**
- [ ] Create `src/canvas_mcp/tools/transdisciplinary.py` with all code
- [ ] Inline competencies dict at top of file (no separate module)
- [ ] Inline week parser function at top of file (no separate module)
- [ ] Move `strip_html_tags()` to `core/text_utils.py` first
- [ ] Register tools in `__init__.py` and `server.py`
- [ ] Create test file `tests/tools/test_transdisciplinary.py`

**Deliverables:**
- `src/canvas_mcp/core/text_utils.py` (extract from courses.py)
- `src/canvas_mcp/tools/transdisciplinary.py` (single file, ~250 lines)

### Research Insight: Modern Python Type Hints

The Python reviewer identified **critical type hint issues**:

```python
# WRONG - Python 3.9 style (deprecated)
from typing import List, Optional, Tuple
keywords: List[str]
def func() -> Optional[str]: ...

# CORRECT - Python 3.10+ style
keywords: list[str]  # No import needed
def func() -> str | None: ...
```

### Inlined Code: Competencies

```python
"""Transdisciplinary discovery tools for Canvas MCP.

Discovers collaboration opportunities by analyzing student overlap,
module timing, and learning outcomes across courses.
"""

from dataclasses import dataclass
import re
from typing import Union

from mcp.server.fastmcp import FastMCP

from ..core.cache import get_course_code, get_course_id
from ..core.client import fetch_all_paginated_results, make_canvas_request
from ..core.config import get_config
from ..core.text_utils import strip_html_tags
from ..core.validation import validate_params


# =============================================================================
# FRANKLIN'S 9 TRANSDISCIPLINARY COMPETENCIES
# =============================================================================

FRANKLIN_COMPETENCIES: dict[str, str] = {
    "Collaboration": "Works productively with others toward shared goals",
    "Communication & Storytelling": "Communicates ideas clearly, creatively, and appropriately",
    "Reflexivity": "Reflects critically on learning, decisions, and assumptions",
    "Empathy & Perspective-Taking": "Understands and respects others' perspectives",
    "Knowledge-Based Reasoning": "Applies disciplinary and interdisciplinary knowledge",
    "Futures Thinking": "Envisions and prepares for multiple and preferred futures",
    "Systems Thinking": "Identifies interconnections within and across systems",
    "Adaptability": "Responds constructively to change and ambiguity",
    "Agency": "Takes initiative and ownership of learning",
}


def format_competencies_list() -> str:
    """Format all competencies as a readable string."""
    lines = ["Franklin's 9 Transdisciplinary Competencies:", ""]
    for i, (name, desc) in enumerate(FRANKLIN_COMPETENCIES.items(), 1):
        lines.append(f"{i}. **{name}**: {desc}")
    return "\n".join(lines)
```

### Inlined Code: Week Parser

```python
# =============================================================================
# WEEK RANGE PARSING
# =============================================================================

# Named extractor functions (not lambdas - easier to test and debug)
def _extract_range(match: re.Match[str]) -> tuple[int, int]:
    """Extract start and end week from a standard range match."""
    return int(match.group(1)), int(match.group(2))


def _extract_single(match: re.Match[str]) -> tuple[int, int]:
    """Extract a single week as a range (week, week)."""
    week = int(match.group(1))
    return week, week


# Proven patterns from TypeScript implementation
WEEK_PATTERNS: list[tuple[str, callable]] = [
    (r'[Ww]eeks?\s+(\d+)\s*[-–]\s*(\d+)', _extract_range),      # Week 8-15
    (r'[Ww]eeks?\s+(\d+)\s*\+\s*(\d+)', _extract_range),        # Weeks 11+12
    (r'\([Ww]eeks?\s+(\d+)\s*[-–]\s*(\d+)\)', _extract_range),  # (Weeks 1-6)
    (r'[Ww]eek\s+(\d+)(?!\s*[-–+])', _extract_single),          # Week 8 (single)
]


def parse_week_range(module_name: str) -> tuple[int, int] | None:
    """Extract (start_week, end_week) from a module name.

    Returns None if no week pattern found.

    Examples:
        >>> parse_week_range("Week 8-15: Research Methods")
        (8, 15)
        >>> parse_week_range("Introduction to Ethics")
        None
    """
    for pattern, extractor in WEEK_PATTERNS:
        if match := re.search(pattern, module_name):
            start, end = extractor(match)
            return (min(start, end), max(start, end))
    return None
```

### Phase 2: Main Discovery Tool

**Tasks:**
- [ ] Implement `discover_opportunities()` tool
- [ ] Implement internal `_find_student_overlap()` function
- [ ] Implement internal `_find_concurrent_modules()` function
- [ ] Implement internal `_extract_learning_outcomes()` function
- [ ] Use `asyncio.TaskGroup` for parallel Phase 2-3 execution
- [ ] Implement bounded concurrency with semaphore
- [ ] Add FERPA audit logging for cross-course queries
- [ ] Write tests: success path, no overlap, partial failure

### Research Insight: Bounded Concurrency

The performance reviewer identified that unbounded parallelism will exhaust Canvas rate limits:

```python
import asyncio

# Configuration
DEFAULT_MAX_CONCURRENT = 10
DEFAULT_REQUEST_DELAY = 0.1  # seconds


class RateLimitedFetcher:
    """Bounded concurrency for Canvas API requests."""

    def __init__(self, max_concurrent: int = DEFAULT_MAX_CONCURRENT):
        self._semaphore = asyncio.Semaphore(max_concurrent)

    async def fetch(self, coro):
        """Execute coroutine with bounded concurrency."""
        async with self._semaphore:
            await asyncio.sleep(DEFAULT_REQUEST_DELAY)
            return await coro


# Usage in _find_student_overlap
async def _find_student_overlap(course_id: int, sample_size: int = 3) -> dict:
    """Find courses sharing students (internal function)."""
    fetcher = RateLimitedFetcher()

    # Get sample students
    enrollments = await fetch_all_paginated_results(
        f"/courses/{course_id}/enrollments",
        {"type[]": ["StudentEnrollment"], "per_page": 100}
    )

    if not enrollments:
        return {"overlapping_courses": [], "sample_size": 0}

    # Sample students
    import random
    sample = random.sample(enrollments, min(sample_size, len(enrollments)))

    # Fetch their other enrollments with bounded concurrency
    async with asyncio.TaskGroup() as tg:
        tasks = [
            tg.create_task(fetcher.fetch(
                make_canvas_request("get", f"/users/{s['user_id']}/enrollments")
            ))
            for s in sample
        ]

    # Aggregate results
    # ... (overlap calculation logic)
```

### Research Insight: FERPA Audit Logging

The security reviewer identified that cross-course queries **require audit logging**:

```python
import logging
from datetime import datetime

# Dedicated FERPA audit logger
pii_audit = logging.getLogger("pii_audit")


def log_cross_course_access(
    operation: str,
    source_course_id: int,
    accessed_course_ids: list[int],
    student_count: int,
) -> None:
    """Log cross-course data access for FERPA compliance."""
    pii_audit.info(
        f"CROSS_COURSE_ACCESS | "
        f"operation={operation} | "
        f"source_course={source_course_id} | "
        f"accessed_courses={accessed_course_ids} | "
        f"student_count={student_count} | "
        f"timestamp={datetime.utcnow().isoformat()}"
    )


# Usage in discover_opportunities
async def discover_opportunities(...):
    # ... discovery logic ...

    # FERPA audit
    log_cross_course_access(
        operation="discover_opportunities",
        source_course_id=course_id,
        accessed_course_ids=[c["id"] for c in overlap_courses],
        student_count=len(sampled_students),
    )

    return results
```

### Tool Signatures (Revised)

```python
@mcp.tool()
@validate_params
async def discover_opportunities(
    course_identifier: Union[str, int],
    sample_size: int = 3,
    term_id: int | None = None,
) -> str:
    """Gather transdisciplinary discovery data for a course.

    Collects student overlap, concurrent modules, and learning outcomes.
    Returns structured data for analysis - does not rank or filter.

    Args:
        course_identifier: Course code (e.g., "ENG_100") or Canvas ID
        sample_size: Number of students to sample for overlap detection (default 3)
        term_id: Filter to specific term (defaults to current term)

    Returns:
        Structured data including:
        - Overlapping courses with shared student counts
        - Concurrent modules with week ranges
        - Extracted learning outcomes per module
        - Franklin competency definitions for context
    """


@mcp.tool()
@validate_params
async def get_crossover_details(
    course_a_identifier: Union[str, int],
    module_a_id: int,
    course_b_identifier: Union[str, int],
    module_b_id: int,
) -> str:
    """Get detailed learning outcomes for a specific module pair.

    Use this for deep-dive analysis after discover_opportunities
    identifies interesting pairs.

    Args:
        course_a_identifier: First course code or ID
        module_a_id: Module ID in first course
        course_b_identifier: Second course code or ID
        module_b_id: Module ID in second course

    Returns:
        Module details, learning outcomes, week overlap, and competency context.
    """


@mcp.tool()
@validate_params
async def list_competencies() -> str:
    """List Franklin's 9 Transdisciplinary Competencies.

    Returns:
        All 9 competencies with descriptions and keywords.
    """
    return format_competencies_list()
```

### Phase 3: Testing

**Tasks:**
- [ ] Write tests for week parser (various formats, edge cases)
- [ ] Write tests for `discover_opportunities` (mocked API calls)
- [ ] Write tests for `get_crossover_details` (mocked API calls)
- [ ] Write tests for audit logging
- [ ] Minimum 3 tests per tool: success, error, edge case

## Acceptance Criteria

### Functional Requirements
- [ ] All 3 tools register and execute without errors
- [ ] `discover_opportunities` returns structured data (not ranked/filtered)
- [ ] `get_crossover_details` returns detailed module comparison
- [ ] `list_competencies` returns Franklin's 9 competencies
- [ ] Tools work with both course codes and Canvas IDs
- [ ] Phases 2-3 run in parallel for performance

### Non-Functional Requirements
- [ ] Discovery completes in under 30 seconds for typical course
- [ ] Handles courses with 100+ students efficiently
- [ ] Graceful degradation when modules lack week ranges
- [ ] FERPA-compliant: audit logging for cross-course queries
- [ ] Uses bounded concurrency (max 10 concurrent requests)
- [ ] Uses modern Python 3.10+ type hints

### Quality Gates
- [ ] Minimum 3 tests per tool (success, error, edge case)
- [ ] All tests pass: `pytest tests/tools/test_transdisciplinary.py`
- [ ] Type hints on all functions using modern syntax
- [ ] No type checking errors with mypy

## Dependencies & Prerequisites

**Existing Code to Reuse:**
- `core/client.py`: `make_canvas_request()`, `fetch_all_paginated_results()`
- `core/cache.py`: `get_course_id()`, `get_course_code()`
- `core/validation.py`: `@validate_params` decorator
- `core/config.py`: `get_config()` for default term ID

**Files to Create:**
- `src/canvas_mcp/core/text_utils.py` (move `strip_html_tags` from courses.py)
- `src/canvas_mcp/tools/transdisciplinary.py`
- `tests/tools/test_transdisciplinary.py`

**Files to Modify:**
- `src/canvas_mcp/tools/courses.py` - Remove `strip_html_tags`, import from core
- `src/canvas_mcp/tools/__init__.py` - Add import and registration
- `src/canvas_mcp/server.py` - Register transdisciplinary tools

## Risk Analysis & Mitigation

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Rate limiting on large queries | High | High | Bounded concurrency (semaphore), delays between requests |
| Week ranges not in module names | Medium | Medium | Return list of unparsed modules, let agent handle |
| Sparse learning outcomes | Medium | Medium | Document limitation, consider assignment descriptions fallback |
| Cross-course enrollment access denied | Low | High | Validate API access early, document permission requirements |
| FERPA compliance gaps | Medium | High | Audit logging, data minimization, no PII in default output |

### Research Insight: Error Handling Pattern

The architecture reviewer recommended **fail-fast with partial results**:

```python
async def discover_opportunities(...):
    results = {
        "status": "success",
        "phases_completed": [],
        "errors": [],
        "data": {},
    }

    # Phase 1 (required)
    overlap = await _find_student_overlap(...)
    if isinstance(overlap, dict) and "error" in overlap:
        return json.dumps({
            "status": "error",
            "error": f"Cannot proceed without student overlap: {overlap['error']}",
            "phase": 1,
        })
    results["phases_completed"].append("student_overlap")
    results["data"]["overlap"] = overlap

    # Phases 2-3 (can continue with partial data)
    try:
        async with asyncio.TaskGroup() as tg:
            modules_task = tg.create_task(_find_concurrent_modules(...))
            outcomes_task = tg.create_task(_extract_learning_outcomes(...))

        results["data"]["modules"] = modules_task.result()
        results["phases_completed"].append("concurrent_modules")

        results["data"]["outcomes"] = outcomes_task.result()
        results["phases_completed"].append("learning_outcomes")

    except* Exception as eg:
        for exc in eg.exceptions:
            results["errors"].append(str(exc))
        results["status"] = "partial_success"

    return json.dumps(results, indent=2)
```

## Success Metrics

1. **Parity**: Replicates TD Serendipity Generator results for test courses
2. **Accuracy**: Correctly identifies known collaboration opportunities in sandbox
3. **Speed**: Discovery completes in under 30 seconds for typical course
4. **Usability**: Natural language queries work ("Find opportunities for ENG 100")
5. **Agent-native**: Claude can compose tools creatively for queries not anticipated

## References & Research

### Internal References
- Brainstorm: `docs/brainstorms/2026-02-05-transdisciplinary-discovery-brainstorm.md`
- Tool registration pattern: `src/canvas_mcp/tools/modules.py:17-22`
- Server registration: `src/canvas_mcp/server.py:46-66`
- Term filtering pattern: `src/canvas_mcp/tools/accounts.py:96-128`
- Validation decorator: `src/canvas_mcp/core/validation.py:201-229`
- Test patterns: `tests/tools/test_modules.py:61-104`

### External References
- Original TypeScript implementation: `/Users/jdec/Documents/TD_Serendipity_Generator_V1/`
- Canvas API Enrollments: https://canvas.instructure.com/doc/api/enrollments.html
- Canvas API Modules: https://canvas.instructure.com/doc/api/modules.html
- FastMCP Tool Patterns: https://github.com/jlowin/fastmcp
- Canvas Rate Limiting: https://canvas.instructure.com/doc/api/file.throttling.html

### Research Agent Findings

**Kieran Python Reviewer:**
- Use `list[str]` not `List[str]`
- Use `T | None` not `Optional[T]`
- Consider `frozen=True` for dataclasses
- Extract lambdas to named functions

**Performance Oracle:**
- Use bounded concurrency with `asyncio.Semaphore`
- Use `asyncio.TaskGroup` for structured concurrency
- Implement tiered caching for different data volatility
- Add adaptive rate limiting based on Canvas headers

**Security Sentinel:**
- Add FERPA audit logging for cross-course queries
- Change `ENABLE_DATA_ANONYMIZATION` default for production
- Return counts not lists (data minimization)
- Document permission requirements

**Code Simplicity Reviewer:**
- Reduce from 6 tools to 2-3 primitives
- Inline competencies and week_parser
- Defer multi-course cohort features to v2
- Let Claude do the reasoning, not the tools

**Architecture Strategist:**
- Phases 2-3 can parallelize after Phase 1
- Add scope parameter for account-wide vs my-courses
- Define explicit error response schema
- Use fail-fast with partial results

**Agent-Native Reviewer:**
- Tools should be data gatherers, not decision makers
- Remove "analysis prompt" from outputs
- Return objective metrics, let agent make value judgments
- Add to AGENTS.md after implementation

**Best Practices Researcher:**
- Use `asyncio.TaskGroup` over `asyncio.gather`
- Consider DataLoader pattern for batching
- Compile regex patterns for performance
- Implement FERPA audit logging
