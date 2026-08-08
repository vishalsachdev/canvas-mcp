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
#
# This must match *real* markdown markers only. An earlier version consumed any
# run of [\s>*\-+], which handed the trailer exemption to "--- fixes #172 was
# emitted by the bot" -- three hyphens are neither a list marker nor, followed
# by prose, a thematic break. A bullet requires whitespace after it.
_LINE_PREFIX = re.compile(
    r"""^
    [ \t]*                    # indent
    (?:>[ \t]*)*              # blockquote markers, possibly nested
    (?:
        [-*+][ \t]+           # bullet: marker MUST be followed by whitespace
      | \d+[.)][ \t]+         # ordered list item
    )?
    [ \t]*
    """,
    re.VERBOSE,
)

# Only separators may sit between two references for both to count as part of
# the same deliberate trailer ("Closes #199, closes #198"). Prose in between
# means the later reference is narration -- see _classify_line.
_ONLY_SEPARATORS = re.compile(r"^(?:[\s,;&/]|and\b)*$", re.IGNORECASE)

# `git commit` strips `#` comment lines and everything after a scissors line,
# but ONLY under some cleanup modes -- and never in a PR body, where `#` opens
# a markdown heading that GitHub parses like any other text. Applying git's
# rules to a PR body is how "## Incident report: the bot fixes #172" slipped
# through as a "comment".
_SCISSORS = re.compile(r"^#[ \t]*-+[ \t]*>8[ \t]*-+")


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


def _classify_line(line: str) -> list[tuple[re.Match[str], bool]]:
    """Pair each match on ``line`` with whether it is a deliberate trailer.

    Trailer status is earned per match, not granted per line. The first match
    qualifies by opening the line; each later one qualifies only if nothing but
    separators sits between it and the previous qualifying match. So
    "Closes #199, closes #198" is entirely deliberate, while
    "Closes #173. Historical note: the old bot fixes #172 by accident."
    is deliberate for #173 and narration for #172 -- which is exactly the
    accidental closure this guard exists to catch, and which an earlier
    per-line rule laundered through.
    """
    matches = list(CLOSING_PATTERN.finditer(line))
    if not matches:
        return []

    out: list[tuple[re.Match[str], bool]] = []
    cursor = _content_start(line)
    still_trailer = True
    for m in matches:
        if still_trailer and _ONLY_SEPARATORS.match(line[cursor:m.start()]):
            out.append((m, True))
            cursor = m.end()
        else:
            still_trailer = False
            out.append((m, False))
    return out


def scan_text(
    text: str, source: str = "<text>", *, git_comments: bool = False
) -> list[Match]:
    """Return every closing-keyword reference in ``text``.

    ``git_comments`` applies `git commit`'s own message cleanup before
    scanning: drop `#` comment lines and truncate at a scissors marker. Pass it
    ONLY for text git will actually clean up that way -- a commit message under
    the default/strip cleanup mode. It must never be set for a PR body, where
    `#` opens a markdown heading that GitHub parses like any other prose.
    """
    if git_comments:
        kept = []
        for line in text.splitlines():
            if _SCISSORS.match(line):
                break
            if line.lstrip().startswith("#"):
                continue
            kept.append(line)
        lines = list(enumerate(kept, start=1))
    else:
        lines = list(enumerate(text.splitlines(), start=1))

    found: list[Match] = []
    for lineno, line in lines:
        for m, is_trailer in _classify_line(line):
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
    parser.add_argument(
        "--git-comments",
        action="store_true",
        help="apply git's commit-message cleanup before scanning: drop '#' "
        "comment lines and truncate at a scissors marker. ONLY for commit "
        "messages under default/strip cleanup -- never for a PR body, where "
        "'#' opens a markdown heading that GitHub parses as prose.",
    )
    args = parser.parse_args(argv)

    if os.environ.get(BYPASS_ENV):
        print(f"[closing-keyword-guard] {BYPASS_ENV} set - check skipped.", file=sys.stderr)
        return 0

    matches: list[Match] = []
    for path in args.paths:
        if path == "-":
            matches += scan_text(
                sys.stdin.read(),
                args.label or "<stdin>",
                git_comments=args.git_comments,
            )
        else:
            with open(path, encoding="utf-8") as fh:
                matches += scan_text(
                    fh.read(), args.label or path, git_comments=args.git_comments
                )

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
