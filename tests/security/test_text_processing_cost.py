"""Reintroducing suffix-rescanning regexes must fail bounded completion checks.

Subprocess timeouts contain regressions without blocking pytest's own event loop.
The budget allows interpreter/import overhead; it is not a microbenchmark.
"""

import subprocess
import sys

import pytest

from canvas_mcp.core.anonymization import scrub_free_text
from canvas_mcp.core.html import remove_html_tags
from canvas_mcp.tools.courses import strip_html_tags


@pytest.mark.parametrize("program", [
    "from canvas_mcp.tools.courses import strip_html_tags; "
    "text = '<' * 300_000; assert strip_html_tags(text) == text",
    "from canvas_mcp.tools.courses import strip_html_tags; "
    "assert strip_html_tags('<style>' * 30_000) == ''",
    "from canvas_mcp.core.anonymization import scrub_free_text; "
    "text = 'a.' * 150_000; assert scrub_free_text(text) == text",
    "from canvas_mcp.tools.discussions import _discussion_text; "
    "text = '<' * 300_000; assert _discussion_text(text) == text",
])
def test_unterminated_author_text_finishes_without_suffix_rescanning(program):
    result = subprocess.run(
        [sys.executable, "-c", program], capture_output=True, text=True,
        encoding="utf-8", timeout=8,
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("text,want", [
    ("Write a.b+tag@example.edu or second@sub.example.org.",
     "Write [EMAIL_REDACTED] or [EMAIL_REDACTED]."),
    ("Unicode 中 alice@example.edu résumé", "Unicode 中 [EMAIL_REDACTED] résumé"),
    ("a@b@c.example.edu", "a@[EMAIL_REDACTED]"),
    ("foo@@example.edu", "foo@@example.edu"),
    ("No address in a.a.a.a.", "No address in a.a.a.a."),
])
def test_email_redaction_keeps_surrounding_content(text, want):
    assert scrub_free_text(text) == want


def test_long_valid_html_remains_complete_and_keeps_boundaries():
    text = "<h2>Overview</h2>" + "<p>Unabridged &amp; useful.</p>" * 20_000
    assert strip_html_tags(text) == "Overview\n" + "\n".join(["Unabridged & useful."] * 20_000)


def test_script_and_style_contents_do_not_reappear_in_output():
    assert strip_html_tags(
        "<p>Before</p><style>.hidden{color:red}<style></style>"
        "<script>const x = '<tag>'; '<script>';</script><p>After</p>"
    ) == "Before\nAfter"


@pytest.mark.parametrize("markup,want", [
    ('<p title="x<y">Complete text</p>', "Complete text"),
    ("<p title='x>y'>Complete text</p>", "Complete text"),
    ('<p title="x <script>">Retained syllabus text</p><p>After</p>',
     "Retained syllabus text\nAfter"),
    ('<script data-rule="x<y">alert(1)</script><p>Safe</p>', "Safe"),
    ('<script>const x = \'<p title="\';</script><p>Safe</p>', "Safe"),
    ('<p>A<!-- <img title="x>y"> hidden -->B</p>', "AB"),
])
def test_quoted_delimiters_do_not_hide_or_invent_visible_text(markup, want):
    assert strip_html_tags(markup) == want


@pytest.mark.parametrize("quote", ['"', "'"])
def test_plain_removal_keeps_all_inline_text_with_quoted_angles(quote):
    assert remove_html_tags(f"<span title={quote}x<y>z{quote}>AB</span>CD") == "ABCD"


def test_unclosed_quote_in_text_does_not_hide_later_tags():
    text = strip_html_tags("<p>if a<b, that's true.</p><p>next</p>")
    assert "</p>" not in text and "<p>" not in text
    assert text.startswith("if a<b, that's true.") and text.endswith("next")
