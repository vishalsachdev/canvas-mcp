"""Transdisciplinary discovery tools for Canvas MCP.

Discovers collaboration opportunities by analyzing student overlap,
module timing, and learning outcomes across courses. Maps opportunities
to Franklin's 9 Transdisciplinary Competencies.
"""

import asyncio
import json
import logging
import random
import re
from datetime import datetime

from mcp.server.fastmcp import FastMCP

from ..core.cache import get_course_code, get_course_id
from ..core.client import fetch_all_paginated_results, make_canvas_request
from ..core.config import get_config
from ..core.text_utils import strip_html_tags
from ..core.validation import validate_params

# =============================================================================
# FERPA AUDIT LOGGING
# =============================================================================

pii_audit = logging.getLogger("pii_audit")


def _log_cross_course_access(
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


# =============================================================================
# FRANKLIN'S 9 TRANSDISCIPLINARY COMPETENCIES
# =============================================================================

# Canonical definitions from Franklin's TD Competencies Rubric (2026)
# See: /Users/jdec/Downloads/Copy TD Competencies Rubric.pdf
FRANKLIN_COMPETENCIES: dict[str, str] = {
    "Collaboration": "Works productively and respectfully with others to achieve shared goals",
    "Storytelling / Communication": "Communicates ideas clearly, creatively, and appropriately for audience and purpose",
    "Reflexivity": "Reflects critically on learning, decisions, and assumptions",
    "Empathy / Perspective Taking": "Demonstrates understanding and respect for others' perspectives and experiences",
    "Knowledge-Based Reasoning": "Applies disciplinary and interdisciplinary knowledge to solve problems",
    "Futures Thinking": "Envisions and prepares for multiple and preferred futures",
    "Systems Thinking": "Identifies and understands interconnections within and across systems",
    "Adaptability": "Responds constructively to change and ambiguity",
    "Agency": "Takes initiative and ownership of learning and actions",
}


def _format_competencies_list() -> str:
    """Format all competencies as a readable string."""
    lines = ["Franklin's 9 Transdisciplinary Competencies:", ""]
    for i, (name, desc) in enumerate(FRANKLIN_COMPETENCIES.items(), 1):
        lines.append(f"{i}. **{name}**: {desc}")
    return "\n".join(lines)


# =============================================================================
# WEEK RANGE PARSING
# =============================================================================


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


def _weeks_overlap(range_a: tuple[int, int], range_b: tuple[int, int]) -> tuple[int, int] | None:
    """Calculate overlap between two week ranges.

    Returns (overlap_start, overlap_end) or None if no overlap.
    """
    start = max(range_a[0], range_b[0])
    end = min(range_a[1], range_b[1])
    if start <= end:
        return (start, end)
    return None


# =============================================================================
# BOUNDED CONCURRENCY
# =============================================================================

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


# =============================================================================
# LEARNING OUTCOMES EXTRACTION
# =============================================================================

OUTCOME_INDICATORS = [
    r'by the end of this (unit|lesson|module)',
    r'students will be able to',
    r'students will\s*:',
    r'learning objectives?',
    r'learning outcomes?',
    r'SWBAT',
]

OUTCOME_PATTERN = re.compile('|'.join(OUTCOME_INDICATORS), re.IGNORECASE)


def _extract_outcomes_from_html(html_content: str) -> list[str]:
    """Extract learning outcomes from HTML content.

    Looks for outcome indicator phrases and extracts list items.
    """
    if not html_content:
        return []

    outcomes = []

    # Check if content contains outcome indicators
    if not OUTCOME_PATTERN.search(html_content):
        return []

    # Extract list items from <ol> and <ul> tags
    list_items = re.findall(r'<li[^>]*>(.*?)</li>', html_content, re.IGNORECASE | re.DOTALL)

    for item in list_items:
        clean_item = strip_html_tags(item).strip()
        # Filter out placeholder text and very short items
        if clean_item and len(clean_item) > 10 and not clean_item.lower().startswith('placeholder'):
            outcomes.append(clean_item)

    return outcomes


# =============================================================================
# INTERNAL FUNCTIONS (Not exposed as tools)
# =============================================================================


async def _find_student_overlap(
    course_id: int,
    sample_size: int = 3,
    term_id: int | None = None,
) -> dict:
    """Find courses sharing students with the source course.

    Samples students from the source course and finds their other enrollments.

    Returns dict with:
        - overlapping_courses: list of courses with shared students
        - sample_size: actual number of students sampled
        - sampled_student_ids: list of student IDs that were sampled
    """
    # Get enrollments from source course
    enrollments = await fetch_all_paginated_results(
        f"/courses/{course_id}/enrollments",
        {"type[]": ["StudentEnrollment"], "per_page": 100}
    )

    if isinstance(enrollments, dict) and "error" in enrollments:
        return {"error": enrollments["error"]}

    if not enrollments:
        return {"overlapping_courses": [], "sample_size": 0, "sampled_student_ids": []}

    # Sample students
    sample = random.sample(enrollments, min(sample_size, len(enrollments)))
    sampled_student_ids = [s["user_id"] for s in sample]

    # Fetch other enrollments with bounded concurrency
    fetcher = RateLimitedFetcher()
    other_courses: dict[int, dict] = {}

    async def fetch_user_enrollments(user_id: int):
        params = {"per_page": 100}
        if term_id:
            params["enrollment_term_id"] = term_id
        return await fetcher.fetch(
            make_canvas_request("get", f"/users/{user_id}/enrollments", params=params)
        )

    # Use TaskGroup for structured concurrency
    try:
        async with asyncio.TaskGroup() as tg:
            tasks = [tg.create_task(fetch_user_enrollments(uid)) for uid in sampled_student_ids]

        # Aggregate results
        for task in tasks:
            user_enrollments = task.result()
            if isinstance(user_enrollments, list):
                for enrollment in user_enrollments:
                    cid = enrollment.get("course_id")
                    if cid and cid != course_id:
                        if cid not in other_courses:
                            other_courses[cid] = {
                                "course_id": cid,
                                "course_name": enrollment.get("course_name", "Unknown"),
                                "shared_student_count": 0,
                            }
                        other_courses[cid]["shared_student_count"] += 1

    except Exception:
        # Continue with partial results
        pass

    # Sort by shared student count
    sorted_courses = sorted(
        other_courses.values(),
        key=lambda c: c["shared_student_count"],
        reverse=True
    )

    return {
        "overlapping_courses": sorted_courses,
        "sample_size": len(sample),
        "sampled_student_ids": sampled_student_ids,
    }


async def _find_concurrent_modules(
    source_course_id: int,
    overlapping_courses: list[dict],
) -> dict:
    """Find modules with overlapping week ranges.

    Returns dict with:
        - source_modules: modules from source course with week ranges
        - concurrent_pairs: list of module pairs with overlapping weeks
        - unparsed_modules: modules without detectable week ranges
    """
    # Get source course modules
    source_modules = await fetch_all_paginated_results(
        f"/courses/{source_course_id}/modules",
        {"per_page": 100}
    )

    if isinstance(source_modules, dict) and "error" in source_modules:
        return {"error": source_modules["error"]}

    # Parse week ranges for source modules
    source_with_weeks = []
    unparsed = []
    for mod in source_modules or []:
        week_range = parse_week_range(mod.get("name", ""))
        mod_info = {
            "id": mod.get("id"),
            "name": mod.get("name"),
            "course_id": source_course_id,
        }
        if week_range:
            mod_info["week_range"] = week_range
            source_with_weeks.append(mod_info)
        else:
            unparsed.append(mod_info)

    # Fetch modules from overlapping courses with bounded concurrency
    fetcher = RateLimitedFetcher()
    other_modules = []

    async def fetch_course_modules(course_id: int, course_name: str):
        modules = await fetcher.fetch(
            fetch_all_paginated_results(
                f"/courses/{course_id}/modules",
                {"per_page": 100}
            )
        )
        if isinstance(modules, list):
            for mod in modules:
                week_range = parse_week_range(mod.get("name", ""))
                if week_range:
                    other_modules.append({
                        "id": mod.get("id"),
                        "name": mod.get("name"),
                        "course_id": course_id,
                        "course_name": course_name,
                        "week_range": week_range,
                    })

    # Use TaskGroup for concurrent module fetching
    try:
        async with asyncio.TaskGroup() as tg:
            for course in overlapping_courses:
                tg.create_task(fetch_course_modules(
                    course["course_id"],
                    course.get("course_name", "Unknown")
                ))
    except Exception:
        pass  # Continue with partial results

    # Find concurrent pairs
    concurrent_pairs = []
    for src_mod in source_with_weeks:
        for other_mod in other_modules:
            overlap = _weeks_overlap(src_mod["week_range"], other_mod["week_range"])
            if overlap:
                concurrent_pairs.append({
                    "source_module": src_mod,
                    "other_module": other_mod,
                    "overlap_weeks": overlap,
                })

    return {
        "source_modules": source_with_weeks,
        "concurrent_pairs": concurrent_pairs,
        "unparsed_modules": unparsed,
    }


async def _extract_learning_outcomes(
    module_ids_by_course: dict[int, list[int]],
) -> dict[str, list[str]]:
    """Extract learning outcomes from module pages.

    Args:
        module_ids_by_course: dict mapping course_id -> list of module_ids

    Returns:
        dict mapping "course_id:module_id" -> list of outcomes
    """
    fetcher = RateLimitedFetcher()
    outcomes: dict[str, list[str]] = {}

    async def fetch_module_outcomes(course_id: int, module_id: int):
        # Get module items
        items = await fetcher.fetch(
            fetch_all_paginated_results(
                f"/courses/{course_id}/modules/{module_id}/items",
                {"per_page": 100}
            )
        )

        if not isinstance(items, list):
            return

        # Find page items and fetch their content
        module_outcomes = []
        for item in items:
            if item.get("type") == "Page":
                page_url = item.get("page_url")
                if page_url:
                    page = await fetcher.fetch(
                        make_canvas_request(
                            "get",
                            f"/courses/{course_id}/pages/{page_url}"
                        )
                    )
                    if isinstance(page, dict):
                        body = page.get("body", "")
                        extracted = _extract_outcomes_from_html(body)
                        module_outcomes.extend(extracted)

        key = f"{course_id}:{module_id}"
        outcomes[key] = module_outcomes

    # Flatten into tasks
    tasks_to_run = []
    for course_id, module_ids in module_ids_by_course.items():
        for module_id in module_ids:
            tasks_to_run.append((course_id, module_id))

    # Use TaskGroup for concurrent outcome extraction
    try:
        async with asyncio.TaskGroup() as tg:
            for course_id, module_id in tasks_to_run:
                tg.create_task(fetch_module_outcomes(course_id, module_id))
    except Exception:
        pass  # Continue with partial results

    return outcomes


# =============================================================================
# MCP TOOLS
# =============================================================================


def register_transdisciplinary_tools(mcp: FastMCP):
    """Register transdisciplinary discovery MCP tools."""

    @mcp.tool()
    @validate_params
    async def discover_opportunities(
        course_identifier: str | int,
        sample_size: int = 3,
        term_id: int | None = None,
    ) -> str:
        """Gather transdisciplinary discovery data for a course.

        Collects student overlap, concurrent modules, and learning outcomes.
        Returns structured data for analysis - does not rank or filter.

        Args:
            course_identifier: Course code (e.g., "ENG_100") or Canvas ID
            sample_size: Number of students to sample for overlap detection (default 3)
            term_id: Filter to specific term (defaults to current term from config)

        Returns:
            Structured data including:
            - Overlapping courses with shared student counts
            - Concurrent modules with week ranges
            - Extracted learning outcomes per module
            - Franklin competency definitions for context
        """
        # Resolve course identifier
        course_id = await get_course_id(course_identifier)
        if course_id is None:
            return json.dumps({
                "status": "error",
                "error": f"Could not resolve course identifier: {course_identifier}"
            })

        # Get effective term ID
        config = get_config()
        effective_term_id = term_id if term_id is not None else config.default_term_id

        results = {
            "status": "success",
            "source_course_id": course_id,
            "source_course_code": await get_course_code(course_id),
            "phases_completed": [],
            "errors": [],
            "data": {},
        }

        # Phase 1: Student overlap (REQUIRED)
        overlap = await _find_student_overlap(course_id, sample_size, effective_term_id)

        if "error" in overlap:
            return json.dumps({
                "status": "error",
                "error": f"Cannot proceed without student overlap: {overlap['error']}",
                "phase": 1,
            })

        results["phases_completed"].append("student_overlap")
        results["data"]["student_overlap"] = overlap

        # FERPA audit log
        accessed_course_ids = [c["course_id"] for c in overlap.get("overlapping_courses", [])]
        _log_cross_course_access(
            operation="discover_opportunities",
            source_course_id=course_id,
            accessed_course_ids=accessed_course_ids,
            student_count=overlap.get("sample_size", 0),
        )

        # Phases 2-3 can run in parallel
        overlapping_courses = overlap.get("overlapping_courses", [])

        try:
            async with asyncio.TaskGroup() as tg:
                modules_task = tg.create_task(
                    _find_concurrent_modules(course_id, overlapping_courses)
                )

            modules_result = modules_task.result()
            results["data"]["concurrent_modules"] = modules_result
            results["phases_completed"].append("concurrent_modules")

            # Extract outcomes from concurrent pairs
            module_ids_by_course: dict[int, list[int]] = {}

            # Add source modules
            for mod in modules_result.get("source_modules", []):
                cid = mod.get("course_id")
                mid = mod.get("id")
                if cid and mid:
                    module_ids_by_course.setdefault(cid, []).append(mid)

            # Add other modules from concurrent pairs
            for pair in modules_result.get("concurrent_pairs", []):
                other_mod = pair.get("other_module", {})
                cid = other_mod.get("course_id")
                mid = other_mod.get("id")
                if cid and mid:
                    module_ids_by_course.setdefault(cid, []).append(mid)

            # Remove duplicates
            for cid in module_ids_by_course:
                module_ids_by_course[cid] = list(set(module_ids_by_course[cid]))

            outcomes = await _extract_learning_outcomes(module_ids_by_course)
            results["data"]["learning_outcomes"] = outcomes
            results["phases_completed"].append("learning_outcomes")

        except Exception as exc:
            results["errors"].append(str(exc))
            results["status"] = "partial_success"

        # Add competencies for context
        results["data"]["competencies"] = FRANKLIN_COMPETENCIES

        return json.dumps(results, indent=2)

    @mcp.tool()
    @validate_params
    async def get_crossover_details(
        course_a_identifier: str | int,
        module_a_id: int,
        course_b_identifier: str | int,
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
        # Resolve course identifiers
        course_a_id = await get_course_id(course_a_identifier)
        course_b_id = await get_course_id(course_b_identifier)

        if course_a_id is None:
            return json.dumps({
                "status": "error",
                "error": f"Could not resolve course identifier: {course_a_identifier}"
            })
        if course_b_id is None:
            return json.dumps({
                "status": "error",
                "error": f"Could not resolve course identifier: {course_b_identifier}"
            })

        # Fetch module details in parallel
        async with asyncio.TaskGroup() as tg:
            mod_a_task = tg.create_task(
                make_canvas_request("get", f"/courses/{course_a_id}/modules/{module_a_id}")
            )
            mod_b_task = tg.create_task(
                make_canvas_request("get", f"/courses/{course_b_id}/modules/{module_b_id}")
            )

        mod_a = mod_a_task.result()
        mod_b = mod_b_task.result()

        if isinstance(mod_a, dict) and "error" in mod_a:
            return json.dumps({"status": "error", "error": f"Module A: {mod_a['error']}"})
        if isinstance(mod_b, dict) and "error" in mod_b:
            return json.dumps({"status": "error", "error": f"Module B: {mod_b['error']}"})

        # Parse week ranges
        week_a = parse_week_range(mod_a.get("name", ""))
        week_b = parse_week_range(mod_b.get("name", ""))

        overlap = None
        if week_a and week_b:
            overlap = _weeks_overlap(week_a, week_b)

        # Extract outcomes
        outcomes = await _extract_learning_outcomes({
            course_a_id: [module_a_id],
            course_b_id: [module_b_id],
        })

        result = {
            "status": "success",
            "module_a": {
                "course_id": course_a_id,
                "course_code": await get_course_code(course_a_id),
                "module_id": module_a_id,
                "module_name": mod_a.get("name"),
                "week_range": week_a,
                "outcomes": outcomes.get(f"{course_a_id}:{module_a_id}", []),
            },
            "module_b": {
                "course_id": course_b_id,
                "course_code": await get_course_code(course_b_id),
                "module_id": module_b_id,
                "module_name": mod_b.get("name"),
                "week_range": week_b,
                "outcomes": outcomes.get(f"{course_b_id}:{module_b_id}", []),
            },
            "overlap_weeks": overlap,
            "competencies": FRANKLIN_COMPETENCIES,
        }

        # FERPA audit log
        _log_cross_course_access(
            operation="get_crossover_details",
            source_course_id=course_a_id,
            accessed_course_ids=[course_b_id],
            student_count=0,
        )

        return json.dumps(result, indent=2)

    @mcp.tool()
    @validate_params
    async def list_competencies() -> str:
        """List Franklin's 9 Transdisciplinary Competencies.

        Returns all 9 competencies with descriptions. Use these when analyzing
        crossover opportunities to identify which competencies are addressed.

        Returns:
            All 9 competencies with names and descriptions.
        """
        return _format_competencies_list()
