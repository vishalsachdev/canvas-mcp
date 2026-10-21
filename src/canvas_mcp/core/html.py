"""Text extraction that does not rescan malformed markup suffixes."""

import html
import re

# Excluding another '<' bounds each attempted match to the next delimiter.
# Possessive repetition avoids rescanning a failed candidate's characters.
_TAG = re.compile(r"<[^<>]++>")
_TAG_NAME = re.compile(r"<\s*(/?)\s*([a-z][a-z0-9]*)\b", re.IGNORECASE)
_BLOCKS = frozenset({
    "p", "div", "h1", "h2", "h3", "h4", "h5", "h6", "li", "ul", "ol",
    "tr", "table", "thead", "tbody", "tfoot", "section", "article", "header",
    "footer", "blockquote", "pre",
})


def remove_html_tags(text: str) -> str:
    """Remove complete tags, retaining plain text and existing whitespace."""
    return _TAG.sub("", text)


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
    for token in _TAG.finditer(html_content):
        if hidden is None:
            parts.append(html_content[cursor:token.start()])
        name_match = _TAG_NAME.match(token.group())
        closing = bool(name_match and name_match.group(1))
        name = name_match.group(2).lower() if name_match else ""
        if hidden is not None:
            if closing and name == hidden:
                hidden = None
        elif not closing and name in {"script", "style"}:
            hidden = name
        elif name == "br" or (closing and name in _BLOCKS):
            parts.append("\n")
        elif closing and name in {"td", "th"}:
            parts.append("\t")
        else:
            parts.append(" ")
        cursor = token.end()
    if hidden is None:
        parts.append(html_content[cursor:])

    text = html.unescape("".join(parts))
    text = re.sub(r"[ \t\xa0]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()
