"""Restoring unbounded attribute/body regexes must fail bounded completion."""

import subprocess
import sys

import pytest

from canvas_mcp.tools.accessibility import (
    _check_content_accessibility,
    _fix_orange_contrast,
)


@pytest.mark.parametrize("expression", [
    "_check_content_accessibility('<span style=\"color:' + 'a' * 300_000, 'page', 7, 'Synthetic')",
    "_extract_violations_from_html('WCAG 1.1.1\\npage ' + '<' * 300_000)",
    "_check_content_accessibility('<img style=\"' * 10_000, 'page', 7, 'Synthetic')",
    "_check_content_accessibility('<a href=\"a.pdf\">' * 50_000, 'page', 7, 'Synthetic')",
    "_check_content_accessibility('<table>' * 50_000, 'page', 7, 'Synthetic')",
    "_fix_orange_contrast('style=\"' + 'background-color:#ff5f05;' * 25_000)",
])
def test_malformed_accessibility_input_finishes(expression):
    result = subprocess.run(
        [sys.executable, "-c", "from canvas_mcp.tools.accessibility import "
         "_check_content_accessibility, _extract_violations_from_html, _fix_orange_contrast; " + expression],
        capture_output=True, text=True, encoding="utf-8", timeout=8,
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("markup,issue", [
    ('<img src="chart.png">', "missing_alt_text"),
    ("<h2> </h2>", "empty_heading"),
    ("<table><tr><td>Data</td></tr></table>", "table_without_headers"),
    ('<a href="/detail">click here</a>', "non_descriptive_link"),
    ('<a href="/detail"> </a>', "empty_link"),
    ('<a href="/detail">https://example.org</a>', "url_as_link_text"),
    ("<table><th>Heading</th></table>", "th_missing_scope"),
    ("<h2>First</h2><h4>Skipped</h4>", "heading_skip"),
    ('<p style="background-color:#ff5f05;color:white">Text</p>', "low_contrast"),
    ('<div class="kl_wrapper">Text</div>', "legacy_designplus"),
    ('<img src="chart.png" alt="chart.png">', "filename_alt_text"),
    ('<img src="chart.png" alt="image of a chart">', "redundant_alt_prefix"),
    ('<img src="chart.png" alt="abc">', "short_alt_text"),
    ('<img src="chart.png" alt="' + "a" * 101 + '">', "long_alt_text"),
    ('<a href="handout.pdf">Handout</a>', "doc_link_no_type"),
    ('<iframe src="https://youtube.com/embed/synthetic"></iframe>', "video_caption_check"),
    ('<p style="text-decoration:underline">Text</p>', "underline_not_link"),
    ('<p style="font-size:8px">Text</p>', "small_font_size"),
    ("<p>• Manual bullet</p>", "manual_bullets"),
    ('<span style="color:red">Important</span>', "color_only_meaning"),
])
def test_scan_still_identifies_documented_defect(markup, issue):
    issues = _check_content_accessibility(markup, "page", 7, "Synthetic")
    found = next((item for item in issues if item["type"] == issue), None)
    assert found is not None, issues
    assert found["content_type"] == "page"
    assert found["content_id"] == 7
    assert found["content_title"] == "Synthetic"
    assert isinstance(found["auto_fixable"], bool)


@pytest.mark.parametrize("style", [
    "background-color:#ff5f05;color:white",
    "color:#fff;background-color:#ff5f05",
])
def test_contrast_fixer_changes_only_the_foreground(style):
    fixed, count = _fix_orange_contrast(f'<p style="{style}">Synthetic</p>')
    assert count == 1
    assert "background-color:#ff5f05" in fixed
    assert "color: #000000" in fixed
    assert ">Synthetic</p>" in fixed


@pytest.mark.parametrize("markup", [
    '<span style="color:inherit">Important</span>',
    '<span style="color:red;font-weight:bold">Important</span>',
    '<span style="color:red"><strong>Important</strong></span>',
    '<span style="background-color:red">Important</span>',
])
def test_color_rule_does_not_flag_redundant_or_non_foreground_styles(markup):
    assert "color_only_meaning" not in {
        item["type"] for item in _check_content_accessibility(markup, "page", 7, "Synthetic")
    }
