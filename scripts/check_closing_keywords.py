#!/usr/bin/env python3
"""Detect GitHub closing keywords that would auto-close an issue.

Background: issue #172 was closed twice by accident, neither time by work
landing. First by merging PR #202, whose *body* described another PR in prose
("#191 (Copilot, fixes #172)"). Second by a direct commit to `main` (98643ce)
whose message documented the first accident and repeated the offending phrase
verbatim -- GitHub matched it and re-closed the issue four seconds after the
push. The post-incident guard only checked PR bodies, so the commit vector
sailed straight past it.

This module is the single source of truth for that detection, shared by the
`commit-msg` hook (prevention) and the CI workflow (backstop). Keeping one
regex in one place is the point: two copies would drift.

GitHub matches a closing keyword only when the issue reference *directly*
follows it, with at most a colon and whitespace between. "fixed the bug in
#191" does not close anything; "fixes #191" does. We match the same shape, so
this neither over- nor under-reports relative to the platform behavior.

Usage:
    check_closing_keywords.py FILE...      # scan files
    check_closing_keywords.py -            # scan stdin
    ... --label "PR #230 body"             # name the source in output

Exit 0 when clean, 1 when a keyword reference is found.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from dataclasses import dataclass

# GitHub's documented closing keywords.
_KEYWORDS = (
    "close",
    "closes",
    "closed",
    "fix",
    "fixes",
    "fixed",
    "resolve",
    "resolves",
    "resolved",
)

# The forms GitHub accepts for the issue reference itself: bare (#12),
# shorthand (GH-12), cross-repo (owner/repo#12), and full issue URLs.
_REFERENCE = r"""
    (?:
        \#\d+
      | GH-\d+
      | [\w.-]+/[\w.-]+\#\d+
      | https?://github\.com/[\w.-]+/[\w.-]+/issues/\d+
    )
"""

CLOSING_PATTERN = re.compile(
    r"\b(?P<keyword>" + "|".join(_KEYWORDS) + r")\b"
    r"[ \t]*:?[ \t]*"
    r"(?P<ref>" + _REFERENCE + r")",
    re.IGNORECASE | re.VERBOSE,
)

# Escape hatch for a deliberate close. Set in the environment, not in the text,
# so it can never be smuggled in by content this tool is scanning.
BYPASS_ENV = "ALLOW_CLOSING_KEYWORD"


# GitHub treats "Closes #173" and "...bug that closed #173" identically, but
# the *intent* behind them is opposite, and on this repo's real history one
# cheap signal separates them perfectly: position. A line that *opens* with a
# closing keyword is the conventional deliberate trailer; a keyword buried
# mid-sentence is narration about work, not a request to close it.
#
# Validated by replay over all ~400 commits on main: 18 deliberate closures
# all open their line, and every accidental one -- including both #172
# incidents -- is mid-sentence. Flagging trailers too would mean an escape
# hatch on nearly every fix PR, and a bypass used routinely stops being read.
#
# Leading list markers count as "start": "- Closes #12" is still a trailer.
_LINE_PREFIX = re.compile(r"^[\s>*\-+]*")


@dataclass(frozen=True)
class Match:
    """One closing-keyword reference, located for a human to act on."""

    source: str
    line_number: int
    line: str
    keyword: str
    reference: str
    column: int
    is_trailer: bool


def _content_start(line: str) -> int:
    """Index of the line's first real character, past indent and list markers."""
    return _LINE_PREFIX.match(line).end()


def scan_text(text: str, source: str = "<text>") -> list[Match]:
    """Return every closing-keyword reference in ``text``.

    Comment lines are skipped: git strips them before the message is stored,
    so a `#` -prefixed line never reaches GitHub's parser. Scanning them would
    flag the commit template's own instructions on every single commit.
    """
    found: list[Match] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        if line.lstrip().startswith("#"):
            continue
        line_matches = list(CLOSING_PATTERN.finditer(line))
        if not line_matches:
            continue
        # Deliberateness is a property of the line, not of each reference: once
        # a line opens as a trailer, everything it goes on to list is equally
        # intended ("Closes #199, closes #198").
        is_trailer = line_matches[0].start() == _content_start(line)
        for m in line_matches:
            found.append(
                Match(
                    source=source,
                    line_number=lineno,
                    line=line,
                    keyword=m.group("keyword"),
                    reference=m.group("ref"),
                    column=m.start(),
                    is_trailer=is_trailer,
                )
            )
    return found


def format_report(matches: list[Match], *, bypass_hint: str) -> str:
    """Render matches as an actionable message, not just a rejection."""
    issues = ", ".join(sorted({m.reference for m in matches}))
    out = ["", "✗ GitHub closing keyword in prose", ""]
    for m in matches:
        out.append(f"  {m.source}:{m.line_number}: {m.line.strip()}")
        out.append(f"  {' ' * (len(f'{m.source}:{m.line_number}: '))}"
                   f"{'^' * len(m.keyword + ' ' + m.reference)}")
    out += [
        "",
        f"  Landing this on the default branch will CLOSE {issues}.",
        "",
        "  If that is intended:",
        f"    {bypass_hint}",
        "",
        "  If it is not (you are describing or quoting, not closing), rephrase",
        "  so the keyword does not directly precede the reference:",
        '    "closed #172 by accident"  ->  "closed [issue 172] by accident"',
        "",
    ]
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+", help="files to scan, or - for stdin")
    parser.add_argument("--label", default=None, help="name for the source in output")
    parser.add_argument(
        "--bypass-hint",
        default=f"{BYPASS_ENV}=1 git commit ...",
        help="how to intentionally allow, shown on failure",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="also fail on deliberate trailer lines (e.g. 'Closes #12'), "
        "which are allowed by default",
    )
    args = parser.parse_args(argv)

    if os.environ.get(BYPASS_ENV):
        print(f"[closing-keyword-guard] {BYPASS_ENV} set - check skipped.", file=sys.stderr)
        return 0

    matches: list[Match] = []
    for path in args.paths:
        if path == "-":
            matches += scan_text(sys.stdin.read(), args.label or "<stdin>")
        else:
            with open(path, encoding="utf-8") as fh:
                matches += scan_text(fh.read(), args.label or path)

    blocking = matches if args.strict else [m for m in matches if not m.is_trailer]

    # Deliberate trailers still get named, so an intentional close is visible
    # in the log rather than merely unpunished.
    for m in matches:
        if m.is_trailer and not args.strict:
            print(
                f"[closing-keyword-guard] {m.source}:{m.line_number}: "
                f"will close {m.reference} (deliberate trailer, allowed).",
                file=sys.stderr,
            )

    if blocking:
        print(format_report(blocking, bypass_hint=args.bypass_hint), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
