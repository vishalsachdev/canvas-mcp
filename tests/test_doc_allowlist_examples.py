"""Every documented ALLOWED_WRITE_TOOLS example must start the server.

A user who copies an allowlist example from the docs should get a working
server. ``resolve_tool_policy`` refuses unknown tool names at startup, so an
example that names a tool which does not exist (``update_page`` instead of
``edit_page_content``) turns the docs' own fix for the read-only default into a
server that will not start.

Scope: every tracked Markdown and template file, except CHANGELOG entries for
released versions. Those record what was true at the time and may name tools
that were renamed later.
"""

import re
import subprocess
from pathlib import Path

import pytest

from canvas_mcp.core.tool_policy import TOOL_EFFECTS, resolve_tool_policy

REPO_ROOT = Path(__file__).resolve().parent.parent

# A comma-separated run of identifiers, either in backticks or after `ALLOWED_WRITE_TOOLS=`.
_LIST = re.compile(
    r"(?:ALLOWED_WRITE_TOOLS\s*=\s*['\"]?|`)([a-z][a-z0-9_]*(?:\s*,\s*[a-z][a-z0-9_]*)+)"
)
_SUFFIXES = (".md", ".template", ".example")


def _tracked_doc_files() -> list[Path]:
    out = subprocess.run(
        ["git", "ls-files"], cwd=REPO_ROOT, capture_output=True, text=True, check=True
    ).stdout.split()
    return [REPO_ROOT / name for name in out if name.endswith(_SUFFIXES)]


def _unreleased_only(path: Path, text: str) -> str:
    if path.name != "CHANGELOG.md":
        return text
    released = re.search(r"^## \[\d", text, flags=re.MULTILINE)
    return text[: released.start()] if released else text


def _allowlist_examples() -> list[tuple[str, str]]:
    examples = []
    for path in _tracked_doc_files():
        text = _unreleased_only(path, path.read_text(encoding="utf-8"))
        for lineno, line in enumerate(text.splitlines(), 1):
            for match in _LIST.finditer(line):
                names = [n.strip() for n in match.group(1).split(",")]
                # Only lists that name at least one real tool are allowlist
                # examples; other comma lists in backticks are unrelated.
                if any(n in TOOL_EFFECTS for n in names):
                    where = f"{path.relative_to(REPO_ROOT)}:{lineno}"
                    examples.append((where, match.group(1)))
    return examples


def test_the_scan_finds_the_documented_examples() -> None:
    # Positive control: the docs do carry allowlist examples. A scan that finds
    # none would make the parametrized test below pass vacuously.
    where = [w for w, _ in _allowlist_examples()]
    assert any(w.startswith("AGENTS.md:") for w in where), where


@pytest.mark.parametrize(("where", "example"), _allowlist_examples())
def test_documented_allowlist_example_is_accepted(where: str, example: str) -> None:
    policy = resolve_tool_policy(example, "stdio")
    assert policy.allowed, f"{where}: {example!r} allows no tool"
