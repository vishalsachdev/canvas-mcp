"""Tests for the closing-keyword guard.

The fixtures that matter most here are the two real incidents, quoted verbatim
from the actual artifacts (commit 98643ce and PR #202's body). A synthetic
fixture would only prove the regex matches text written to match the regex --
the same circularity that let PR #191's New-Quizzes test pass while the filter
matched nothing. See `test_acceptance_replay_real_history` for the check that
runs against this repo's genuine git log.
"""

import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from check_closing_keywords import (  # noqa: E402
    BYPASS_ENV,
    format_report,
    main,
    scan_text,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
CHECKER = REPO_ROOT / "scripts" / "check_closing_keywords.py"


# --------------------------------------------------------------------------
# The real incidents
# --------------------------------------------------------------------------

# Commit 98643ce, pushed directly to main 2026-07-31T13:08:48Z, quoted
# verbatim. Issue #172 closed 4 seconds later. This is the vector the original
# PR-body-only guard did not cover.
#
# Note it carries TWO closing references, not one: "four issues closed: #203"
# as well as "closed #172". The incident write-up only recorded the second.
# The acceptance replay found the first -- a hand-written fixture had missed
# it, which is the whole argument for replaying against real data.
INCIDENT_COMMIT_MSG = """\
docs: session log 2026-07-31 — closed all three zqian bugs + tool-annotation contract

Four PRs merged, four issues closed: #203 (#199 institution-neutral enrollment
matching, #198 upload-to-course-root), #202 (first triage brief), #201 (#200
annotations), #205 (#204 annotation contract + CI gate). Tests 928 -> 968.

Archives the 2026-07-30 (later) entry to internal/session-history.md, checks off
the completed Current Focus items, and records the triage-routine closing-keyword
bug that closed #172 by accident (routine prompt patched; #172 reopened).

Also commits internal/issue-170-followup-draft.md, the record of the #170
follow-up comment posted 2026-07-30.
"""

# PR #202's body: a triage brief describing another PR in prose. Merging it
# closed #172 the first time, on 2026-07-31T05:47Z.
INCIDENT_PR_BODY = "- **`#191`** (Copilot, fixes #172) — draft, blocked on review."


def test_flags_the_direct_commit_incident():
    """The commit that documented the bug must itself be caught -- twice."""
    matches = scan_text(INCIDENT_COMMIT_MSG, "commit 98643ce")
    assert matches, "guard missed the exact commit that re-closed #172"

    by_ref = {m.reference: m.keyword.lower() for m in matches}
    # The closure everyone noticed.
    assert by_ref["#172"] == "closed"
    # And the one nobody did: "four issues closed: #203". Harmless in the
    # event (#203 was an already-merged PR) but the same live directive.
    assert by_ref["#203"] == "closed"
    assert sorted(by_ref) == ["#172", "#203"]


def test_flags_the_pr_body_incident():
    matches = scan_text(INCIDENT_PR_BODY, "PR #202 body")
    assert [m.reference for m in matches] == ["#172"]
    assert matches[0].keyword.lower() == "fixes"


# --------------------------------------------------------------------------
# Success path: text that must pass untouched
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        # Real commit subjects from this repo's history. Conventional-commit
        # "fix:" is followed by prose, not a reference -- GitHub does not close
        # on these, so neither may we.
        "fix: restore make_canvas_request import lost in #224/#225 cross-merge",
        "fix: never report unconfirmed writes as success (#219, #220, #221) (#224)",
        "fix: honor the requested days range in get_my_upcoming_assignments (#222) (#225)",
        "docs: weekly impact stats 2026-08-04 (re-collected after failed Aug 3 run)",
        # Words between keyword and reference: GitHub does not link these.
        "fixed the detection bug reported in #191",
        "this resolves the problem described by #142",
        # The recommended rephrasing from the failure message.
        "closed [issue 172] by accident",
        # Bare references with no keyword at all.
        "See #172 and #191 for context.",
    ],
)
def test_does_not_flag_safe_text(text):
    assert scan_text(text) == []


# --------------------------------------------------------------------------
# Trailer vs prose: the distinction that keeps the escape hatch meaningful
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "line",
    [
        "Closes #173",
        "Fixes #207",
        "Fixes #207, #208",
        "Closes #199, closes #198",
        "Resolves #12 and #13",
        "closes #12.",
        # Deliberate trailers routinely carry trailing prose on the same line.
        "Closes #200 (reported by @zqian).",
        "Closes #204. Follow-up to #200 / #201, which shipped the symptom fix.",
        "- Closes #12",
    ],
)
def test_standalone_trailers_are_classified_deliberate(line):
    matches = scan_text(line)
    assert matches, f"expected a match in {line!r}"
    assert all(m.is_trailer for m in matches)


@pytest.mark.parametrize(
    "line",
    [
        # Both real incidents.
        "bug that closed #172 by accident (routine prompt patched)",
        "Four PRs merged, four issues closed: #203 (#199 enrollment matching,",
        "- **`#191`** (Copilot, fixes #172) — draft, blocked on review.",
        # The two the incident write-up never noticed.
        "docs: close #215 doc gaps — full tool coverage in tools/README.md (#217)",
        "Salvaged from the closed #111 weekly-maintenance report:",
    ],
)
def test_narration_is_classified_prose(line):
    matches = scan_text(line)
    assert matches, f"expected a match in {line!r}"
    assert not any(m.is_trailer for m in matches)


def test_cli_allows_trailers_but_blocks_prose(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv(BYPASS_ENV, raising=False)
    msg = tmp_path / "COMMIT_EDITMSG"

    msg.write_text("fix: real fix\n\nCloses #173\n", encoding="utf-8")
    assert main([str(msg)]) == 0
    assert "deliberate trailer, allowed" in capsys.readouterr().err

    msg.write_text("docs: log the bug that closed #172 by accident\n", encoding="utf-8")
    assert main([str(msg)]) == 1


def test_strict_mode_blocks_trailers_too(tmp_path, monkeypatch):
    monkeypatch.delenv(BYPASS_ENV, raising=False)
    msg = tmp_path / "COMMIT_EDITMSG"
    msg.write_text("fix: real fix\n\nCloses #173\n", encoding="utf-8")
    assert main([str(msg)]) == 0
    assert main([str(msg), "--strict"]) == 1


def test_skips_comment_lines_only_under_git_cleanup():
    """`#` lines are git comments in a commit message -- and nowhere else."""
    msg = "docs: update notes\n\n# On branch main\n# fixes #172 <- template noise\n"
    assert scan_text(msg, git_comments=True) == []
    # Without the flag the same text is scanned, because in a PR body `#`
    # opens a heading that GitHub parses like any other prose.
    assert scan_text(msg) != []


def test_git_comments_truncates_at_scissors():
    """Git discards the scissors line and everything after it."""
    msg = (
        "docs: record example\n\n"
        "# ------------------------ >8 ------------------------\n"
        "Template reminder: never write fixes #172 in prose.\n"
    )
    assert scan_text(msg, git_comments=True) == []
    assert scan_text(msg) != []


# --------------------------------------------------------------------------
# Red-team regressions (2026-08-08)
#
# Found by an independent adversarial pass over the shipped guard. Every input
# below is quoted verbatim from that run and returned exit 0 -- a silent
# bypass -- before these fixes. All three trace to design decisions made when
# the guard was written, not to exotic edge cases.
# --------------------------------------------------------------------------


def test_markdown_heading_is_not_a_comment():
    """FN1, critical: `## ... fixes #172` in a PR body closes #172 on merge.

    The original blanket `#`-line skip was justified by git's comment
    stripping, which does not apply to a PR body at all. The acceptance replay
    never caught it because it replayed `git log` only -- never a PR body.
    """
    line = "## Incident report: the bot fixes #172 by accident."
    matches = scan_text(line)
    assert [m.reference for m in matches] == ["#172"]
    assert not matches[0].is_trailer, "a heading is prose, not a trailer"


def test_trailer_does_not_launder_later_prose_on_the_same_line():
    """FN2: a real trailer must not grant amnesty to narration after it."""
    line = "Closes #173. Historical note: the old bot fixes #172 by accident."
    by_ref = {m.reference: m.is_trailer for m in scan_text(line)}
    assert by_ref == {"#173": True, "#172": False}


def test_punctuation_run_is_not_a_list_marker():
    """FN3: `---` is not a bullet, so it earns no trailer exemption."""
    line = "--- fixes #172 was emitted by the bot, not requested by us."
    matches = scan_text(line)
    assert matches and not matches[0].is_trailer


@pytest.mark.parametrize(
    "line",
    [
        "- Closes #12",
        "* Closes #12",
        "+ Closes #12",
        "> Closes #12",
        "  - Closes #12",
        "1. Closes #12",
    ],
)
def test_real_list_and_quote_markers_still_earn_the_exemption(line):
    """The FN3 fix must not break genuine markdown markers."""
    matches = scan_text(line)
    assert matches and matches[0].is_trailer


# --------------------------------------------------------------------------
# Edge cases: the reference forms GitHub accepts
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text,expected_ref",
    [
        ("closes #12", "#12"),
        ("Closes: #12", "#12"),
        ("CLOSED #12", "#12"),
        ("resolve GH-12", "GH-12"),
        ("fixes vishalsachdev/canvas-mcp#12", "vishalsachdev/canvas-mcp#12"),
        (
            "closed https://github.com/vishalsachdev/canvas-mcp/issues/12",
            "https://github.com/vishalsachdev/canvas-mcp/issues/12",
        ),
        ("fix\t#12", "#12"),
    ],
)
def test_flags_every_reference_form(text, expected_ref):
    matches = scan_text(text)
    assert len(matches) == 1
    assert matches[0].reference == expected_ref


def test_reports_every_occurrence_not_just_the_first():
    matches = scan_text("closes #1 and fixes #2\nresolves #3")
    assert [m.reference for m in matches] == ["#1", "#2", "#3"]
    assert [m.line_number for m in matches] == [1, 1, 2]


# --------------------------------------------------------------------------
# CLI behavior
# --------------------------------------------------------------------------


def test_cli_exits_nonzero_and_names_the_issue(tmp_path, capsys, monkeypatch):
    monkeypatch.delenv(BYPASS_ENV, raising=False)
    msg = tmp_path / "COMMIT_EDITMSG"
    msg.write_text(INCIDENT_COMMIT_MSG, encoding="utf-8")

    assert main([str(msg), "--label", "commit message"]) == 1

    err = capsys.readouterr().err
    assert "#172" in err
    assert BYPASS_ENV in err


def test_cli_exits_zero_on_clean_input(tmp_path, monkeypatch):
    monkeypatch.delenv(BYPASS_ENV, raising=False)
    msg = tmp_path / "COMMIT_EDITMSG"
    msg.write_text("docs: ordinary session log\n", encoding="utf-8")
    assert main([str(msg)]) == 0


def test_bypass_env_var_allows_a_deliberate_close(tmp_path, monkeypatch):
    monkeypatch.setenv(BYPASS_ENV, "1")
    msg = tmp_path / "COMMIT_EDITMSG"
    msg.write_text("feat: ship the thing\n\nCloses #123\n", encoding="utf-8")
    assert main([str(msg)]) == 0


def test_report_tells_the_user_how_to_rephrase():
    report = format_report(scan_text(INCIDENT_PR_BODY, "body"), bypass_hint="HINT=1")
    assert "HINT=1" in report
    assert "[issue 172]" in report  # the suggested rewrite


# --------------------------------------------------------------------------
# Acceptance replay against this repo's real history
# --------------------------------------------------------------------------


def _git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=REPO_ROOT, capture_output=True, text=True
    )


def _history_ref() -> str | None:
    """First ref that resolves: local main, the remote branch, then HEAD.

    A CI checkout (actions/checkout) lands on a detached HEAD with no local
    `main`, so `git log main` exits 128 there while passing on any developer
    machine. Resolving a ref instead of hard-coding one keeps this test running
    in both places rather than being a local-only test.
    """
    for ref in ("main", "origin/main", "HEAD"):
        if _git("rev-parse", "--verify", "--quiet", ref).returncode == 0:
            return ref
    return None


def test_acceptance_replay_real_history():
    """Run the checker over every real commit message on main.

    A validator that has only ever seen its own fixtures has not earned its
    place. This replays it over the actual corpus it will police.

    The expected set is pinned deliberately. Running this the first time is
    what produced the trailer/prose split: the regex flagged 20 commits, of
    which 18 were ordinary `Closes #N` trailers on fix PRs. Blocking those
    would have meant an escape hatch on nearly every PR. It also surfaced two
    accidental closures nobody had recorded -- 2bee9f2 and c63b23b -- plus a
    second reference inside 98643ce itself.
    """
    ref = _history_ref()
    if ref is None:
        pytest.skip("no resolvable git history ref (not a git checkout?)")

    if _git("rev-parse", "--is-shallow-repository").stdout.strip() == "true":
        pytest.skip(
            "shallow clone: the replay needs full history to be meaningful. "
            "CI sets fetch-depth: 0 for exactly this test."
        )

    log = _git("log", "--format=%H%x00%B%x1e", ref).stdout

    # Every accidental closure in this repo's history, and nothing else.
    EXPECTED_PROSE = {
        "98643ce": ["#172", "#203"],  # the incident; #203 previously unrecorded
        "2bee9f2": ["#215"],  # "docs: close #215 doc gaps" -- prose in a subject
        "e3922b3": ["#111"],  # "Salvaged from the closed #111 report:"
    }

    flagged_prose: dict[str, list[str]] = {}
    trailer_shas: set[str] = set()
    for record in log.split("\x1e"):
        record = record.strip()
        if not record:
            continue
        sha, _, body = record.partition("\x00")
        matches = scan_text(body, sha[:7])
        prose = sorted({m.reference for m in matches if not m.is_trailer})
        if prose:
            flagged_prose[sha[:7]] = prose
        if any(m.is_trailer for m in matches):
            trailer_shas.add(sha[:7])

    # Pinned shas absent means we are looking at a partial history (a truncated
    # fetch, or a fork without the original commits), not a regex regression.
    # Skipping is honest; asserting here would report a false failure.
    seen_shas = {record.strip()[:7] for record in log.split("\x1e") if record.strip()}
    missing = sorted(set(EXPECTED_PROSE) - seen_shas)
    if missing:
        pytest.skip(f"partial history: pinned commits not present ({missing})")

    assert flagged_prose == EXPECTED_PROSE, (
        "replay drifted from the known corpus. New keys are either a real "
        f"accidental closure or a regex false positive: {flagged_prose}"
    )

    # Sanity on the other half: deliberate trailers must be recognized and
    # allowed, or the guard degenerates into a bypass-on-every-PR ritual.
    assert len(trailer_shas) >= 15, (
        f"expected the historical `Closes #N` trailers to be classified "
        f"deliberate; only found {len(trailer_shas)}"
    )


def test_hook_is_executable_and_rejects_the_incident(tmp_path):
    """End-to-end: the hook script itself, not just the Python behind it."""
    hook = REPO_ROOT / ".githooks" / "commit-msg"
    assert hook.exists(), "commit-msg hook missing"

    msg = tmp_path / "COMMIT_EDITMSG"
    msg.write_text(INCIDENT_COMMIT_MSG, encoding="utf-8")

    env = {"PATH": "/usr/bin:/bin:/usr/local/bin"}
    result = subprocess.run(
        ["bash", str(hook), str(msg)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.returncode == 1
    assert "#172" in result.stderr
