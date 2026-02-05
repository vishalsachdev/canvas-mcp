"""
Transdisciplinary Discovery Tools Unit Tests

Tests for the Canvas transdisciplinary discovery tools:
- discover_opportunities
- get_crossover_details
- list_competencies

Also tests internal helper functions:
- parse_week_range
- _weeks_overlap
- _extract_outcomes_from_html

These tests use mocking to avoid requiring real Canvas API access.
"""

import json
import pytest
from unittest.mock import patch, AsyncMock


# Sample mock data - 12 students to support sample_size=10 default
MOCK_ENROLLMENTS = [
    {"user_id": 1000 + i, "course_id": 100, "type": "StudentEnrollment"}
    for i in range(1, 13)
]

MOCK_USER_ENROLLMENTS = [
    {"user_id": 1001, "course_id": 100, "course_name": "ENG 100"},
    {"user_id": 1001, "course_id": 200, "course_name": "ENV 200"},
    {"user_id": 1001, "course_id": 300, "course_name": "MATH 200"},
]

MOCK_MODULES = [
    {
        "id": 12345,
        "name": "Week 1-4: Introduction to Writing",
        "position": 1,
        "state": "active",
        "published": True,
    },
    {
        "id": 12346,
        "name": "Week 5-8: Research Methods",
        "position": 2,
        "state": "active",
        "published": True,
    },
    {
        "id": 12347,
        "name": "Week 9-12: Advanced Topics",
        "position": 3,
        "state": "active",
        "published": True,
    },
]

MOCK_MODULE_ITEMS = [
    {"id": 1, "type": "Page", "page_url": "learning-outcomes"},
    {"id": 2, "type": "Assignment", "content_id": 100},
]

MOCK_PAGE_WITH_OUTCOMES = {
    "title": "Learning Outcomes",
    "body": """
        <h2>Learning Outcomes</h2>
        <p>By the end of this module, students will be able to:</p>
        <ul>
            <li>Analyze complex texts for meaning and structure</li>
            <li>Synthesize multiple sources into coherent arguments</li>
            <li>Apply research methodologies to real-world problems</li>
        </ul>
    """
}


@pytest.fixture
def mock_canvas_api():
    """Fixture to mock Canvas API calls."""
    with patch('canvas_mcp.tools.transdisciplinary.get_course_id') as mock_get_id, \
         patch('canvas_mcp.tools.transdisciplinary.get_course_code') as mock_get_code, \
         patch('canvas_mcp.tools.transdisciplinary.fetch_all_paginated_results') as mock_fetch, \
         patch('canvas_mcp.tools.transdisciplinary.make_canvas_request') as mock_request, \
         patch('canvas_mcp.tools.transdisciplinary.get_config') as mock_config:

        # Setup default mock returns
        mock_get_id.return_value = 100
        mock_get_code.return_value = "ENG_100"

        # Mock config
        mock_config_obj = type('Config', (), {'default_term_id': 155})()
        mock_config.return_value = mock_config_obj

        yield {
            'get_course_id': mock_get_id,
            'get_course_code': mock_get_code,
            'fetch_all_paginated_results': mock_fetch,
            'make_canvas_request': mock_request,
            'get_config': mock_config,
        }


def get_tool_function(tool_name: str):
    """Get a tool function by name from the registered tools."""
    from mcp.server.fastmcp import FastMCP
    from canvas_mcp.tools.transdisciplinary import register_transdisciplinary_tools

    # Create a mock MCP server and register tools
    mcp = FastMCP("test")

    # Store captured functions
    captured_functions = {}

    # Override the tool decorator to capture the function
    original_tool = mcp.tool

    def capturing_tool(*args, **kwargs):
        decorator = original_tool(*args, **kwargs)
        def wrapper(fn):
            captured_functions[fn.__name__] = fn
            return decorator(fn)
        return wrapper

    mcp.tool = capturing_tool
    register_transdisciplinary_tools(mcp)

    return captured_functions.get(tool_name)


# =============================================================================
# WEEK RANGE PARSING TESTS
# =============================================================================


class TestParseWeekRange:
    """Tests for week range parsing."""

    def test_basic_range(self):
        """Test basic week range pattern."""
        from canvas_mcp.tools.transdisciplinary import parse_week_range

        result = parse_week_range("Week 8-15: Research Methods")
        assert result == (8, 15)

    def test_weeks_plural(self):
        """Test plural 'Weeks' pattern."""
        from canvas_mcp.tools.transdisciplinary import parse_week_range

        result = parse_week_range("Weeks 1-4: Introduction")
        assert result == (1, 4)

    def test_single_week(self):
        """Test single week pattern."""
        from canvas_mcp.tools.transdisciplinary import parse_week_range

        result = parse_week_range("Week 8: Special Topics")
        assert result == (8, 8)

    def test_plus_pattern(self):
        """Test weeks with plus pattern (e.g., Weeks 11+12)."""
        from canvas_mcp.tools.transdisciplinary import parse_week_range

        result = parse_week_range("Weeks 11+12: Project Work")
        assert result == (11, 12)

    def test_parenthetical(self):
        """Test parenthetical week pattern."""
        from canvas_mcp.tools.transdisciplinary import parse_week_range

        result = parse_week_range("Introduction (Weeks 1-6)")
        assert result == (1, 6)

    def test_no_week_pattern(self):
        """Test module name without week pattern."""
        from canvas_mcp.tools.transdisciplinary import parse_week_range

        result = parse_week_range("Introduction to Ethics")
        assert result is None

    def test_reversed_range(self):
        """Test that reversed ranges are normalized."""
        from canvas_mcp.tools.transdisciplinary import parse_week_range

        result = parse_week_range("Week 15-8: Reversed")
        assert result == (8, 15)

    def test_en_dash(self):
        """Test en-dash in week range."""
        from canvas_mcp.tools.transdisciplinary import parse_week_range

        result = parse_week_range("Week 8–15: Research Methods")  # en-dash
        assert result == (8, 15)


class TestWeeksOverlap:
    """Tests for week overlap calculation."""

    def test_full_overlap(self):
        """Test ranges that fully overlap."""
        from canvas_mcp.tools.transdisciplinary import _weeks_overlap

        result = _weeks_overlap((1, 10), (1, 10))
        assert result == (1, 10)

    def test_partial_overlap(self):
        """Test ranges that partially overlap."""
        from canvas_mcp.tools.transdisciplinary import _weeks_overlap

        result = _weeks_overlap((1, 5), (3, 8))
        assert result == (3, 5)

    def test_no_overlap(self):
        """Test ranges that don't overlap."""
        from canvas_mcp.tools.transdisciplinary import _weeks_overlap

        result = _weeks_overlap((1, 5), (6, 10))
        assert result is None

    def test_adjacent_ranges(self):
        """Test adjacent ranges that don't overlap."""
        from canvas_mcp.tools.transdisciplinary import _weeks_overlap

        result = _weeks_overlap((1, 5), (6, 10))
        assert result is None

    def test_touching_ranges(self):
        """Test ranges that share a week."""
        from canvas_mcp.tools.transdisciplinary import _weeks_overlap

        result = _weeks_overlap((1, 5), (5, 10))
        assert result == (5, 5)


# =============================================================================
# LEARNING OUTCOMES EXTRACTION TESTS
# =============================================================================


class TestExtractOutcomes:
    """Tests for learning outcomes extraction."""

    def test_extract_outcomes_with_list(self):
        """Test extracting outcomes from HTML with list items."""
        from canvas_mcp.tools.transdisciplinary import _extract_outcomes_from_html

        html = """
        <p>Learning Outcomes:</p>
        <ul>
            <li>Analyze complex texts for meaning and structure</li>
            <li>Synthesize multiple sources into coherent arguments</li>
        </ul>
        """
        result = _extract_outcomes_from_html(html)
        assert len(result) == 2
        assert "Analyze complex texts" in result[0]

    def test_extract_outcomes_no_indicators(self):
        """Test extraction when no outcome indicators present."""
        from canvas_mcp.tools.transdisciplinary import _extract_outcomes_from_html

        html = """
        <p>This module covers the basics of writing.</p>
        <ul>
            <li>Chapter 1</li>
            <li>Chapter 2</li>
        </ul>
        """
        result = _extract_outcomes_from_html(html)
        assert len(result) == 0

    def test_extract_outcomes_empty_content(self):
        """Test extraction with empty content."""
        from canvas_mcp.tools.transdisciplinary import _extract_outcomes_from_html

        result = _extract_outcomes_from_html("")
        assert result == []

        result = _extract_outcomes_from_html(None)
        assert result == []

    def test_extract_outcomes_filters_short_items(self):
        """Test that very short list items are filtered out."""
        from canvas_mcp.tools.transdisciplinary import _extract_outcomes_from_html

        html = """
        <p>Students will be able to:</p>
        <ul>
            <li>Short</li>
            <li>Analyze complex texts for meaning and structure in real-world scenarios</li>
        </ul>
        """
        result = _extract_outcomes_from_html(html)
        # "Short" should be filtered out (< 10 chars)
        assert len(result) == 1
        assert "Analyze" in result[0]


# =============================================================================
# LIST COMPETENCIES TESTS
# =============================================================================


class TestListCompetencies:
    """Tests for list_competencies tool."""

    @pytest.mark.asyncio
    async def test_list_competencies_basic(self):
        """Test basic competencies listing."""
        list_competencies = get_tool_function('list_competencies')
        assert list_competencies is not None

        result = await list_competencies()

        # Verify all 9 competencies are listed (canonical names from TD Rubric)
        assert "Collaboration" in result
        assert "Storytelling / Communication" in result
        assert "Reflexivity" in result
        assert "Empathy / Perspective Taking" in result
        assert "Knowledge-Based Reasoning" in result
        assert "Futures Thinking" in result
        assert "Systems Thinking" in result
        assert "Adaptability" in result
        assert "Agency" in result

    @pytest.mark.asyncio
    async def test_list_competencies_format(self):
        """Test competencies output format."""
        list_competencies = get_tool_function('list_competencies')
        result = await list_competencies()

        assert "Franklin's 9 Transdisciplinary Competencies" in result
        # Check numbered format
        assert "1." in result
        assert "9." in result


# =============================================================================
# DISCOVER OPPORTUNITIES TESTS
# =============================================================================


class TestDiscoverOpportunities:
    """Tests for discover_opportunities tool."""

    @pytest.mark.asyncio
    async def test_discover_opportunities_basic(self, mock_canvas_api):
        """Test basic discovery flow."""
        # Setup mock responses
        mock_canvas_api['fetch_all_paginated_results'].side_effect = [
            MOCK_ENROLLMENTS,  # First call: get enrollments for source course
            MOCK_MODULES,  # Module fetch
        ]
        mock_canvas_api['make_canvas_request'].return_value = MOCK_USER_ENROLLMENTS

        discover_opportunities = get_tool_function('discover_opportunities')
        assert discover_opportunities is not None

        result = await discover_opportunities("ENG_100")
        data = json.loads(result)

        # Verify course ID was resolved
        mock_canvas_api['get_course_id'].assert_called()
        assert data["status"] in ["success", "partial_success"]
        assert "student_overlap" in data["phases_completed"]

    @pytest.mark.asyncio
    async def test_discover_opportunities_invalid_course(self, mock_canvas_api):
        """Test error handling for invalid course."""
        mock_canvas_api['get_course_id'].return_value = None

        discover_opportunities = get_tool_function('discover_opportunities')
        result = await discover_opportunities("INVALID_COURSE")
        data = json.loads(result)

        assert data["status"] == "error"
        assert "Could not resolve" in data["error"]

    @pytest.mark.asyncio
    async def test_discover_opportunities_no_enrollments(self, mock_canvas_api):
        """Test when source course has no students."""
        mock_canvas_api['fetch_all_paginated_results'].return_value = []

        discover_opportunities = get_tool_function('discover_opportunities')
        result = await discover_opportunities("EMPTY_COURSE")
        data = json.loads(result)

        assert data["status"] == "success"
        assert data["data"]["student_overlap"]["sample_size"] == 0

    @pytest.mark.asyncio
    async def test_discover_opportunities_api_error(self, mock_canvas_api):
        """Test error handling when API fails."""
        mock_canvas_api['fetch_all_paginated_results'].return_value = {"error": "API Error"}

        discover_opportunities = get_tool_function('discover_opportunities')
        result = await discover_opportunities("COURSE_WITH_ERROR")
        data = json.loads(result)

        assert data["status"] == "error"
        assert "Cannot proceed" in data["error"]


# =============================================================================
# GET CROSSOVER DETAILS TESTS
# =============================================================================


class TestGetCrossoverDetails:
    """Tests for get_crossover_details tool."""

    @pytest.mark.asyncio
    async def test_get_crossover_details_basic(self, mock_canvas_api):
        """Test basic crossover details retrieval."""
        # Setup mock responses for both modules
        mock_canvas_api['make_canvas_request'].side_effect = [
            {"id": 12345, "name": "Week 1-4: Writing Fundamentals"},
            {"id": 54321, "name": "Week 2-5: Environmental Science"},
        ]
        mock_canvas_api['fetch_all_paginated_results'].return_value = MOCK_MODULE_ITEMS
        mock_canvas_api['get_course_code'].side_effect = ["ENG_100", "ENV_200"]

        get_crossover_details = get_tool_function('get_crossover_details')
        assert get_crossover_details is not None

        result = await get_crossover_details("ENG_100", 12345, "ENV_200", 54321)
        data = json.loads(result)

        assert data["status"] == "success"
        assert "module_a" in data
        assert "module_b" in data
        assert "overlap_weeks" in data

    @pytest.mark.asyncio
    async def test_get_crossover_details_invalid_course(self, mock_canvas_api):
        """Test error handling for invalid course."""
        mock_canvas_api['get_course_id'].side_effect = [None, 200]

        get_crossover_details = get_tool_function('get_crossover_details')
        result = await get_crossover_details("INVALID", 12345, "ENV_200", 54321)
        data = json.loads(result)

        assert data["status"] == "error"
        assert "Could not resolve" in data["error"]

    @pytest.mark.asyncio
    async def test_get_crossover_details_module_error(self, mock_canvas_api):
        """Test error handling when module fetch fails."""
        mock_canvas_api['make_canvas_request'].side_effect = [
            {"error": "Module not found"},
            {"id": 54321, "name": "Week 2-5: Environmental Science"},
        ]

        get_crossover_details = get_tool_function('get_crossover_details')
        result = await get_crossover_details("ENG_100", 99999, "ENV_200", 54321)
        data = json.loads(result)

        assert data["status"] == "error"
        assert "Module A" in data["error"]


# =============================================================================
# FERPA AUDIT LOGGING TESTS
# =============================================================================


class TestFerpaAuditLogging:
    """Tests for FERPA compliance audit logging."""

    @pytest.mark.asyncio
    async def test_audit_log_called_on_discovery(self, mock_canvas_api):
        """Test that audit logging is triggered on discovery."""
        mock_canvas_api['fetch_all_paginated_results'].side_effect = [
            MOCK_ENROLLMENTS,
            MOCK_MODULES,
        ]
        mock_canvas_api['make_canvas_request'].return_value = MOCK_USER_ENROLLMENTS

        with patch('canvas_mcp.tools.transdisciplinary._log_cross_course_access') as mock_log:
            discover_opportunities = get_tool_function('discover_opportunities')
            await discover_opportunities("ENG_100")

            # Verify audit log was called
            mock_log.assert_called()
            call_args = mock_log.call_args
            assert call_args[1]["operation"] == "discover_opportunities"
            assert call_args[1]["source_course_id"] == 100

    @pytest.mark.asyncio
    async def test_audit_log_called_on_crossover_details(self, mock_canvas_api):
        """Test that audit logging is triggered on crossover details."""
        mock_canvas_api['make_canvas_request'].side_effect = [
            {"id": 12345, "name": "Week 1-4: Writing"},
            {"id": 54321, "name": "Week 2-5: Science"},
        ]
        mock_canvas_api['fetch_all_paginated_results'].return_value = []
        mock_canvas_api['get_course_code'].side_effect = ["ENG_100", "ENV_200"]

        with patch('canvas_mcp.tools.transdisciplinary._log_cross_course_access') as mock_log:
            get_crossover_details = get_tool_function('get_crossover_details')
            await get_crossover_details("ENG_100", 12345, "ENV_200", 54321)

            mock_log.assert_called()
            call_args = mock_log.call_args
            assert call_args[1]["operation"] == "get_crossover_details"


# =============================================================================
# RATE LIMITING TESTS
# =============================================================================


class TestRateLimitedFetcher:
    """Tests for bounded concurrency."""

    @pytest.mark.asyncio
    async def test_fetcher_limits_concurrency(self):
        """Test that fetcher limits concurrent requests."""
        from canvas_mcp.tools.transdisciplinary import RateLimitedFetcher
        import asyncio

        fetcher = RateLimitedFetcher(max_concurrent=2)
        execution_order = []

        async def tracked_coro(id: int):
            execution_order.append(f"start-{id}")
            await asyncio.sleep(0.01)
            execution_order.append(f"end-{id}")
            return id

        # Launch 4 tasks with max 2 concurrent
        tasks = [
            asyncio.create_task(fetcher.fetch(tracked_coro(i)))
            for i in range(4)
        ]
        await asyncio.gather(*tasks)

        # Verify all completed
        assert len([e for e in execution_order if e.startswith("end")]) == 4


# =============================================================================
# MINIMUM OVERLAP FILTERING TESTS
# =============================================================================


class TestMinOverlapFiltering:
    """Tests for minimum student overlap filtering."""

    @pytest.mark.asyncio
    async def test_filters_low_overlap_courses(self, mock_canvas_api):
        """Courses with overlap below min_overlap are filtered out."""
        # Setup: Create enrollments and user enrollments where only some users
        # share courses with sufficient overlap
        mock_canvas_api['fetch_all_paginated_results'].side_effect = [
            MOCK_ENROLLMENTS,  # Source course enrollments (12 students)
            MOCK_MODULES,  # Module fetch for concurrent modules
        ]

        # Mock user enrollments - only 2 users are in course 999 (below threshold)
        # 5 users are in course 888 (above threshold)
        def mock_user_enrollments(method, endpoint, **kwargs):
            if "users/1001/enrollments" in endpoint:
                return [{"course_id": 888, "course_name": "High Overlap"},
                        {"course_id": 999, "course_name": "Low Overlap"}]
            elif "users/1002/enrollments" in endpoint:
                return [{"course_id": 888, "course_name": "High Overlap"},
                        {"course_id": 999, "course_name": "Low Overlap"}]
            elif "users/1003/enrollments" in endpoint:
                return [{"course_id": 888, "course_name": "High Overlap"}]
            elif "users/1004/enrollments" in endpoint:
                return [{"course_id": 888, "course_name": "High Overlap"}]
            elif "users/1005/enrollments" in endpoint:
                return [{"course_id": 888, "course_name": "High Overlap"}]
            else:
                return []

        mock_canvas_api['make_canvas_request'].side_effect = mock_user_enrollments

        discover_opportunities = get_tool_function('discover_opportunities')
        result = await discover_opportunities("TEST_COURSE", min_overlap=3)
        data = json.loads(result)

        # Course 999 should be filtered out (only 2 shared students < 3 min)
        # Course 888 should be included (5 shared students >= 3 min)
        overlapping = data["data"]["student_overlap"]["overlapping_courses"]
        course_ids = [c["course_id"] for c in overlapping]

        assert 888 in course_ids, "High overlap course should be included"
        assert 999 not in course_ids, "Low overlap course should be filtered out"

    @pytest.mark.asyncio
    async def test_min_overlap_applied_in_response(self, mock_canvas_api):
        """Response includes min_overlap_applied for transparency."""
        mock_canvas_api['fetch_all_paginated_results'].side_effect = [
            MOCK_ENROLLMENTS,
            MOCK_MODULES,
        ]
        mock_canvas_api['make_canvas_request'].return_value = []

        discover_opportunities = get_tool_function('discover_opportunities')
        result = await discover_opportunities("TEST_COURSE", min_overlap=5)
        data = json.loads(result)

        assert "min_overlap_applied" in data["data"]["student_overlap"]
        assert data["data"]["student_overlap"]["min_overlap_applied"] == 5

    @pytest.mark.asyncio
    async def test_default_min_overlap_is_three(self, mock_canvas_api):
        """Default min_overlap is 3."""
        mock_canvas_api['fetch_all_paginated_results'].side_effect = [
            MOCK_ENROLLMENTS,
            MOCK_MODULES,
        ]
        mock_canvas_api['make_canvas_request'].return_value = []

        discover_opportunities = get_tool_function('discover_opportunities')
        # Call without specifying min_overlap
        result = await discover_opportunities("TEST_COURSE")
        data = json.loads(result)

        assert data["data"]["student_overlap"]["min_overlap_applied"] == 3


# =============================================================================
# FERPA COMPLIANCE TESTS
# =============================================================================


class TestFerpaCompliance:
    """Tests for FERPA compliance - no student IDs in responses."""

    @pytest.mark.asyncio
    async def test_no_student_ids_in_response(self, mock_canvas_api):
        """FERPA compliance: student IDs should not be exposed in response."""
        mock_canvas_api['fetch_all_paginated_results'].side_effect = [
            MOCK_ENROLLMENTS,
            MOCK_MODULES,
        ]
        mock_canvas_api['make_canvas_request'].return_value = MOCK_USER_ENROLLMENTS

        discover_opportunities = get_tool_function('discover_opportunities')
        result = await discover_opportunities("TEST_COURSE")
        data = json.loads(result)

        # Verify no student IDs leaked in student_overlap
        student_overlap = data["data"]["student_overlap"]
        assert "sampled_student_ids" not in student_overlap, \
            "sampled_student_ids should not be in response (FERPA violation)"

    @pytest.mark.asyncio
    async def test_source_course_size_in_response(self, mock_canvas_api):
        """Response includes source_course_size for overlap calculations."""
        mock_canvas_api['fetch_all_paginated_results'].side_effect = [
            MOCK_ENROLLMENTS,  # 12 students
            MOCK_MODULES,
        ]
        mock_canvas_api['make_canvas_request'].return_value = []

        discover_opportunities = get_tool_function('discover_opportunities')
        result = await discover_opportunities("TEST_COURSE")
        data = json.loads(result)

        assert "source_course_size" in data["data"]["student_overlap"]
        assert data["data"]["student_overlap"]["source_course_size"] == 12


# =============================================================================
# MAX SAMPLE SIZE TESTS
# =============================================================================


class TestMaxSampleSize:
    """Tests for MAX_SAMPLE_SIZE enforcement."""

    @pytest.mark.asyncio
    async def test_sample_size_capped_at_max(self, mock_canvas_api):
        """Sample size is capped at MAX_SAMPLE_SIZE (25)."""
        from canvas_mcp.tools.transdisciplinary import MAX_SAMPLE_SIZE

        mock_canvas_api['fetch_all_paginated_results'].side_effect = [
            MOCK_ENROLLMENTS,  # Only 12 students available
            MOCK_MODULES,
        ]
        mock_canvas_api['make_canvas_request'].return_value = []

        discover_opportunities = get_tool_function('discover_opportunities')
        # Request huge sample size
        result = await discover_opportunities("TEST_COURSE", sample_size=1000)
        data = json.loads(result)

        # Sample size should be limited by available students (12)
        # not by MAX_SAMPLE_SIZE since we only have 12 students
        assert data["data"]["student_overlap"]["sample_size"] <= MAX_SAMPLE_SIZE
        assert data["data"]["student_overlap"]["sample_size"] <= 12
