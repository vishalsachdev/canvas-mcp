"""A long decimal entity in author HTML must decode, not raise.

html.unescape converts the digits of &#NNN; with int(), and CPython refuses a decimal string of
more than sys.get_int_max_str_digits() digits (4,300 by default) with ValueError. Canvas bodies are
author-controlled, so one such entity crashed every tool that reads the body.

The expected text comes from html.unescape itself with the limit switched off, which is what the
HTML standard asks for: an out-of-range code point decodes to U+FFFD, leading zeros do not count.
"""

import html
import sys

import pytest

from canvas_mcp.core.course_policy import _strip_html
from canvas_mcp.core.html import strip_html_tags
from canvas_mcp.tools.student_groups import _plain_text

LIMIT = 4300
TEXTS = [
    "&#" + "1" * (LIMIT + 1) + ";",
    "&#" + "9" * (LIMIT * 3) + "x",
    "&#" + "0" * (LIMIT + 1) + "65;",
    "&#" + "0" * (LIMIT * 2) + "1114111;",
    "&#" + "0" * (LIMIT * 2) + "1114112;",
    "a&#" + "7" * (LIMIT + 1) + "&#66;b&amp;",
    # Controls the limit never reached.
    "&#" + "1" * LIMIT + ";",
    "&#65;&#x" + "f" * (LIMIT * 2) + ";",
]


def _unlimited_unescape(text: str) -> str:
    before = sys.get_int_max_str_digits()
    sys.set_int_max_str_digits(0)
    try:
        return html.unescape(text)
    finally:
        sys.set_int_max_str_digits(before)


@pytest.mark.parametrize("text", TEXTS, ids=range(len(TEXTS)))
@pytest.mark.parametrize("decode", [strip_html_tags, _plain_text, _strip_html])
def test_long_decimal_entity_decodes_like_the_unlimited_standard(decode, text):
    assert sys.get_int_max_str_digits() == LIMIT
    want = _unlimited_unescape(text).strip()
    assert decode(text).strip() == want


def test_the_oracle_decodes_as_the_standard_says():
    assert _unlimited_unescape("&#" + "1" * (LIMIT + 1) + ";") == "�"
    assert _unlimited_unescape("&#" + "0" * (LIMIT + 1) + "65;") == "A"
    with pytest.raises(ValueError):
        html.unescape("&#" + "1" * (LIMIT + 1) + ";")
