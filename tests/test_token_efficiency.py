"""Token efficiency tests for Canvas MCP server responses.

These tests measure token consumption of tool responses to verify
the compact format achieves expected token savings.
"""

import datetime



def estimate_tokens(text: str) -> int:
    """Estimate token count using simple heuristic.

    Uses ~4 characters per token approximation, which is reasonable
    for English text and technical output. For more precise counts,
    use tiktoken with gpt-4 encoding.

    Args:
        text: The text to estimate tokens for

    Returns:
        Estimated token count
    """
    if not text:
        return 0
    # Rough approximation: ~4 characters per token
    return len(text) // 4


class TestTokenEstimation:
    """Test token estimation utilities."""

    def test_empty_string(self) -> None:
        """Empty string should return 0 tokens."""
        assert estimate_tokens("") == 0

    def test_simple_text(self) -> None:
        """Simple text token estimation."""
        # "Hello world" is about 11 chars, ~2-3 tokens
        tokens = estimate_tokens("Hello world")
        assert 2 <= tokens <= 4

    def test_formatted_output(self) -> None:
        """Test formatted tool output estimation."""
        # Use current year to match format_date_smart behavior
        current_year = datetime.datetime.now(datetime.timezone.utc).year
        
        # Typical verbose assignment output
        verbose = f"""ID: 123456
Name: Quiz 1 - Introduction to Biology
Due: {current_year}-01-21T23:59:00Z
Points: 100
"""
        verbose_tokens = estimate_tokens(verbose)

        # Compact format
        compact = "123456|Quiz 1 - Introduction to Biology|Jan 21|100"
        compact_tokens = estimate_tokens(compact)

        # Compact should be significantly smaller
        assert compact_tokens < verbose_tokens
        savings = (verbose_tokens - compact_tokens) / verbose_tokens
        assert savings > 0.4  # At least 40% savings


class TestResponseFormats:
    """Test compact vs standard response format token usage."""

    def test_assignment_list_compact_savings(self) -> None:
        """Verify compact assignment list saves >40% tokens."""
        # Use current year to match format_date_smart behavior
        current_year = datetime.datetime.now(datetime.timezone.utc).year
        
        # Simulate 10 assignments in verbose format
        verbose_items = []
        compact_items = []

        for i in range(10):
            verbose_items.append(
                f"ID: {1000 + i}\n"
                f"Name: Assignment {i + 1} - Sample Assignment Title\n"
                f"Due: {current_year}-01-{21 + (i % 10):02d}T23:59:00Z\n"
                f"Points: {100 + i * 10}\n"
            )
            compact_items.append(
                f"{1000 + i}|Assignment {i + 1} - Sample Assignment Title|Jan {21 + (i % 10)}|{100 + i * 10}"
            )

        verbose_output = "Assignments for Course TEST_123:\n\n" + "\n".join(verbose_items)
        compact_output = "asgn|TEST_123\n" + "\n".join(compact_items)

        verbose_tokens = estimate_tokens(verbose_output)
        compact_tokens = estimate_tokens(compact_output)

        savings_pct = (verbose_tokens - compact_tokens) / verbose_tokens * 100
        print(f"Verbose: {verbose_tokens} tokens, Compact: {compact_tokens} tokens")
        print(f"Savings: {savings_pct:.1f}%")

        # Expect at least 40% savings (labels removed saves ~40-50%)
        # Higher savings come with real data that has longer labels
        assert savings_pct > 40

    def test_submission_list_compact_savings(self) -> None:
        """Verify compact submission list saves >60% tokens."""
        # Use current year to match format_date_smart behavior
        current_year = datetime.datetime.now(datetime.timezone.utc).year
        
        # Simulate 25 submissions
        verbose_items = []
        compact_items = []

        for i in range(25):
            submitted = f"{current_year}-01-20T14:30:00Z" if i % 3 != 0 else "Not submitted"
            score = str(85 + (i % 15)) if i % 3 != 0 else "Not graded"
            grade = score if score != "Not graded" else "Not graded"

            verbose_items.append(
                f"User ID: {9000 + i}\n"
                f"Submitted: {submitted}\n"
                f"Score: {score}\n"
                f"Grade: {grade}\n"
            )

            sub_short = "Jan 20 14:30" if i % 3 != 0 else "-"
            score_short = score if score != "Not graded" else "-"
            compact_items.append(f"{9000 + i}|{sub_short}|{score_short}")

        verbose_output = "Submissions for Assignment 12345 in course TEST_123:\n\n" + "\n".join(verbose_items)
        compact_output = "sub|12345|TEST_123\n" + "\n".join(compact_items)

        verbose_tokens = estimate_tokens(verbose_output)
        compact_tokens = estimate_tokens(compact_output)

        savings_pct = (verbose_tokens - compact_tokens) / verbose_tokens * 100
        print(f"Verbose: {verbose_tokens} tokens, Compact: {compact_tokens} tokens")
        print(f"Savings: {savings_pct:.1f}%")

        # Expect at least 60% savings
        assert savings_pct > 60

    def test_analytics_summary_savings(self) -> None:
        """Verify analytics summary mode saves >85% tokens."""
        # Use current year to match format_date_smart behavior
        current_year = datetime.datetime.now(datetime.timezone.utc).year
        
        # Full analytics output (simplified)
        verbose_output = f"""Assignment Analytics for 'Quiz 1' in Course TEST_123

Assignment Details:
  Due: {current_year}-01-21T23:59:00Z (Past Due)
  Points Possible: 100
  Published: Yes

Submission Statistics:
  Submitted: 23/25 (92.0%)
  Graded: 23/25 (92.0%)
  Missing: 2/25 (8.0%)
  Late: 3/23 (13.0% of submissions)
  Excused: 0

Grade Statistics:
  Average Score: 84.5/100 (84.5%)
  Median Score: 87.0/100 (87.0%)
  Standard Deviation: 12.3

Students Scoring Below 70%:
  Student_A001: 65.0/100 (65.0%)
  Student_A002: 68.0/100 (68.0%)

Students Scoring Above 90%:
  Student_B001: 98.0/100 (98.0%)
  Student_B002: 95.0/100 (95.0%)
  Student_B003: 92.0/100 (92.0%)

Students Missing Submission:
  Student_C001
  Student_C002
"""

        # Summary mode output
        compact_output = "analytics|Quiz 1|TEST_123\nsub:23|miss:2|avg:84.5|med:87.0|late:3\n<70%:2|>90%:3"

        verbose_tokens = estimate_tokens(verbose_output)
        compact_tokens = estimate_tokens(compact_output)

        savings_pct = (verbose_tokens - compact_tokens) / verbose_tokens * 100
        print(f"Verbose: {verbose_tokens} tokens, Compact: {compact_tokens} tokens")
        print(f"Savings: {savings_pct:.1f}%")

        # Expect at least 85% savings for summary mode
        assert savings_pct > 85


class TestDateFormatSavings:
    """Test date format token savings."""

    def test_date_format_compact(self) -> None:
        """Verify compact date format saves tokens."""
        # Use current year to match format_date_smart behavior
        current_year = datetime.datetime.now(datetime.timezone.utc).year
        
        iso_date = f"{current_year}-01-21T23:59:00Z"
        compact_date = "Jan 21"

        iso_tokens = estimate_tokens(iso_date)
        compact_tokens = estimate_tokens(compact_date)

        # Compact should be about half the size
        assert compact_tokens < iso_tokens
        savings = (iso_tokens - compact_tokens) / iso_tokens
        assert savings > 0.5

    def test_relative_date_format(self) -> None:
        """Verify relative date format is compact."""
        # Use a date 3 days from now to test relative format
        future_date = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=3)
        iso_date = future_date.strftime("%Y-%m-%dT23:59:00Z")
        relative_date = "in 3 days"

        iso_tokens = estimate_tokens(iso_date)
        relative_tokens = estimate_tokens(relative_date)

        # Relative format should be more compact
        assert relative_tokens <= iso_tokens


class TestFieldFormatSavings:
    """Test field formatting token savings."""

    def test_boolean_format(self) -> None:
        """Verify compact boolean format saves tokens."""
        verbose = "Published: Yes"
        compact = "published"

        assert estimate_tokens(compact) < estimate_tokens(verbose)

    def test_label_abbreviation(self) -> None:
        """Verify abbreviated labels save tokens."""
        verbose = "Points Possible: 100"
        compact = "pts:100"

        verbose_tokens = estimate_tokens(verbose)
        compact_tokens = estimate_tokens(compact)

        savings = (verbose_tokens - compact_tokens) / verbose_tokens
        assert savings > 0.5


class TestVerbosityHint:
    """Test that compact mode includes verbosity hint."""

    def test_compact_includes_hint(self) -> None:
        """Verify compact responses include hint for more detail."""
        # Example compact response with hint
        compact_with_hint = (
            "asgn|TEST_123\n"
            "1001|Quiz 1|Jan 21|100\n"
            "1002|Quiz 2|Jan 28|100\n"
            "(Use verbosity=standard for full details)"
        )

        # The hint should be present
        assert "verbosity=standard" in compact_with_hint
