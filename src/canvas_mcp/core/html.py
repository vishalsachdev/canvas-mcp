"""Text extraction that does not rescan malformed markup suffixes."""

import html
import re
from collections.abc import Iterator
from dataclasses import dataclass

_TAG_HEAD = re.compile(r"<\s*(/?)\s*([a-z][a-z0-9:_-]*+)", re.IGNORECASE | re.ASCII)
_RAW_END = {
    name: re.compile(rf"</{name}\s*>", re.IGNORECASE | re.ASCII) for name in ("script", "style")
}
_BLOCKS = frozenset({
    "p", "div", "h1", "h2", "h3", "h4", "h5", "h6", "li", "ul", "ol",
    "tr", "table", "thead", "tbody", "tfoot", "section", "article", "header",
    "footer", "blockquote", "pre",
})
# U+10FFFF has 7 decimal digits, so a reference with more significant digits is out of range.
_LONG_DECIMAL_REF = re.compile(r"&#([0-9]{8,})")


def _shorten_decimal_ref(match: re.Match[str]) -> str:
    digits = match.group(1).lstrip("0") or "0"
    return "&#" + (digits if len(digits) <= 7 else "1114112")


def unescape_html(text: str) -> str:
    """html.unescape that does not raise on a decimal reference of more than 4,300 digits.

    html.unescape converts the digits with int(), which CPython limits to
    sys.get_int_max_str_digits() digits. Leading zeros are dropped and an
    out-of-range value becomes 1114112, which html.unescape decodes to U+FFFD,
    so the result is the one the standard gives without the limit.
    """
    return html.unescape(_LONG_DECIMAL_REF.sub(_shorten_decimal_ref, text))


@dataclass(frozen=True, slots=True)
class HTMLAttribute:
    """One real attribute value and its offsets in the original document."""

    value: str
    start: int
    end: int


@dataclass(frozen=True, slots=True)
class HTMLTag:
    start: int
    end: int
    name_end: int
    name: str
    closing: bool
    attributes: dict[str, HTMLAttribute]


def _attributes(text: str, start: int, end: int) -> dict[str, HTMLAttribute]:
    """Consume attributes once, never interpreting a quoted value as a name."""
    attributes: dict[str, HTMLAttribute] = {}
    cursor = start
    while cursor < end:
        if text[cursor].isspace() or text[cursor] in '/=<>"\'':
            cursor += 1
            continue
        name_start = cursor
        while cursor < end and not text[cursor].isspace() and text[cursor] not in '/=<>"\'':
            cursor += 1
        name = text[name_start:cursor].lower()
        while cursor < end and text[cursor].isspace():
            cursor += 1
        value_start = value_end = cursor
        if cursor < end and text[cursor] == "=":
            cursor += 1
            while cursor < end and text[cursor].isspace():
                cursor += 1
            if cursor < end and text[cursor] in '\"\'':
                quote = text[cursor]
                value_start = cursor + 1
                cursor = text.find(quote, value_start, end)
                if cursor < 0:
                    break
                value_end = cursor
                cursor += 1
            else:
                value_start = cursor
                while cursor < end and not text[cursor].isspace():
                    cursor += 1
                value_end = cursor
        attributes.setdefault(name, HTMLAttribute(text[value_start:value_end], value_start, value_end))
    return attributes


def iter_html_tags(text: str) -> Iterator[HTMLTag]:
    """Yield complete tags in one forward pass, respecting quotes and comments.

    A nested '<' restarts a malformed unquoted candidate. Quoted delimiters
    belong to the attribute, and script/style raw text ends only at its closing
    tag. No failure retries the same suffix at every preceding delimiter.
    This is a bounded tokenizer, not a browser tree builder or sanitizer.
    """
    cursor = 0
    raw: str | None = None
    while cursor < len(text):
        if raw is not None:
            closing = _RAW_END[raw].search(text, cursor)
            if closing is None:
                return
            yield HTMLTag(closing.start(), closing.end(), closing.end() - 1, raw, True, {})
            cursor = closing.end()
            raw = None
            continue
        start = text.find("<", cursor)
        if start < 0:
            return
        if text.startswith("<!--", start):
            end = text.find("-->", start + 4)
            end = len(text) if end < 0 else end + 3
            yield HTMLTag(start, end, end, "", False, {})
            cursor = end
            continue
        head = _TAG_HEAD.match(text, start)
        declaration = text.startswith(("<!", "<?"), start)
        if head is None and not declaration:
            cursor = start + 1
            continue
        name = head.group(2).lower() if head else ""
        name_end = head.end() if head else start + 2
        cursor = name_end
        while cursor < len(text):
            char = text[cursor]
            if char in '\"\'':
                end_quote = text.find(char, cursor + 1)
                if end_quote < 0:
                    # An unmatched quote means this "<" was text, not a tag; rescan after it.
                    cursor = start + 1
                    break
                cursor = end_quote + 1
            elif char == "<":
                break
            elif char == ">":
                closing_tag = bool(head and head.group(1))
                attributes = _attributes(text, name_end, cursor) if name and not closing_tag else {}
                cursor += 1
                yield HTMLTag(start, cursor, name_end, name, closing_tag, attributes)
                if not closing_tag and name in _RAW_END:
                    raw = name
                break
            else:
                cursor += 1


def remove_html_tags(text: str) -> str:
    """Remove complete tags, retaining plain text and existing whitespace."""
    parts = []
    cursor = 0
    for token in iter_html_tags(text):
        parts.append(text[cursor:token.start])
        cursor = token.end
    parts.append(text[cursor:])
    return "".join(parts)


def strip_html_tags(html_content: str | None) -> str:
    """Extract complete text, preserving block boundaries and decoding entities.

    Script/style contents are suppressed until their closing tag or EOF. A
    single pass visits disjoint tag candidates; an unterminated tag remains
    literal text rather than causing a search of every remaining suffix.
    """
    if not html_content:
        return ""

    parts: list[str] = []
    hidden: str | None = None
    cursor = 0
    for token in iter_html_tags(html_content):
        if hidden is None:
            parts.append(html_content[cursor:token.start])
        closing = token.closing
        name = token.name
        if hidden is not None:
            if closing and name == hidden:
                hidden = None
        elif not closing and name in {"script", "style"}:
            hidden = name
        elif name == "br" or (closing and name in _BLOCKS):
            parts.append("\n")
        elif closing and name in {"td", "th"}:
            parts.append("\t")
        elif name:
            parts.append(" ")
        cursor = token.end
    if hidden is None:
        parts.append(html_content[cursor:])

    text = unescape_html("".join(parts))
    text = re.sub(r"[ \t\xa0]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()
