"""Keep the facts that the website and README repeat in step with their sources.

Each fact has one source: the version in pyproject.toml, the tool count in tools/TOOL_MANIFEST.json, the skill count
in skills/, and the GitHub counts in docs/data/impact.json. Each place that repeats a fact is a pattern in PLACES or
a `<!-- fact:name -->value<!-- /fact -->` marker. A pattern that matches fewer times than its minimum is an error, so
a reworded page cannot drop out of the check unnoticed.

    python scripts/sync_site_facts.py          rewrite the files
    python scripts/sync_site_facts.py --check  list each stale place and exit 1 (CI)
    python scripts/sync_site_facts.py --dates  also set sitemap.xml lastmod from git (deploy time; never checked)
"""

import argparse
import json
import re
import subprocess
import sys
import tomllib
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
MARKER = re.compile(r"<!-- fact:([a-z_]+) -->(.*?)<!-- /fact -->")
# Each marked file and the markers it must keep: a deleted marker would leave its value to go stale unchecked.
MARKED_FILES = {"docs/index.html": ("stars", "forks", "contributors", "stats_as_of")}

# (file, pattern whose group 1 is the value, fact, minimum matches)
PLACES = (
    ("docs/index.html", r"[Uu]p to (\d+) (?:MCP )?tools", "tools", 5),
    ("docs/index.html", r'"softwareVersion": "([^"]+)"', "version", 1),
    ("docs/index.html", r"v(\d+\.\d+\.\d+) Now Available", "version", 1),
    ("docs/index.html", r'<div class="stat-value">(\d+)</div>\s*<div class="stat-label">MCP Tools</div>', "tools", 1),
    ("docs/llms.txt", r"[Uu]p to (\d+) (?:MCP )?tools", "tools", 2),
    ("docs/llms.txt", r"(\d+) reusable agent skills", "skills", 1),
    ("docs/llms.txt", r"Latest release: v(\d+\.\d+\.\d+)", "version", 1),
    ("README.md", r"\*\*up to (\d+) tools\*\*", "tools", 2),
    ("README.md", r"raise the total to (\d+)", "tools", 1),
    ("README.md", r"\*\*(\d+) agent skills\*\*", "skills", 1),
)

SITEMAP = "docs/sitemap.xml"
CENTRAL = ZoneInfo("America/Chicago")
SITE_URL = "https://canvas-mcp.illinihunt.org/"


def load_facts(root: Path) -> dict[str, str]:
    with (root / "pyproject.toml").open("rb") as handle:
        version = tomllib.load(handle)["project"]["version"]
    manifest = json.loads((root / "tools/TOOL_MANIFEST.json").read_text(encoding="utf-8"))
    impact = json.loads((root / "docs/data/impact.json").read_text(encoding="utf-8"))
    github = impact["github"]
    collected = datetime.fromisoformat(impact["collected_at"].replace("Z", "+00:00"))
    as_of = collected.astimezone(CENTRAL)
    return {
        "version": version,
        "tools": str(len(manifest["tools"])),
        "skills": str(len(list((root / "skills").glob("*/SKILL.md")))),
        "stars": str(github["stars"]),
        "forks": str(github["forks"]),
        "contributors": str(github["contributors"]),
        "stats_as_of": f"{as_of:%B} {as_of.day}, {as_of.year}",
    }


def _replace(text: str, pattern: re.Pattern[str], value_of, where: str, stale: list[str]) -> tuple[str, int]:
    """Set group 2 of a marker or group 1 of a pattern to its fact; record each place that differed."""
    group = 2 if pattern is MARKER else 1
    count = 0

    def swap(match: re.Match[str]) -> str:
        nonlocal count
        count += 1
        value = value_of(match)
        if match.group(group) != value:
            stale.append(f"{where}: {match.group(group)!r} should be {value!r}")
        start, end = match.span(group)
        return match.group(0)[: start - match.start()] + value + match.group(0)[end - match.start():]

    return pattern.sub(swap, text), count


def sync(root: Path, facts: dict[str, str]) -> tuple[dict[Path, str], list[str], list[str]]:
    """Return the updated text of each file, the stale places, and the errors."""
    texts: dict[Path, str] = {}
    stale: list[str] = []
    errors: list[str] = []

    def text_of(name: str) -> str:
        path = root / name
        if path not in texts:
            texts[path] = path.read_text(encoding="utf-8")
        return texts[path]

    for name, required in MARKED_FILES.items():
        def marker_value(match: re.Match[str], name: str = name) -> str:
            if match.group(1) not in facts:
                errors.append(f"{name}: unknown fact marker {match.group(1)!r}")
                return match.group(2)
            return facts[match.group(1)]

        texts[root / name], _ = _replace(text_of(name), MARKER, marker_value, f"{name} fact marker", stale)
        present = {match.group(1) for match in MARKER.finditer(texts[root / name])}
        errors.extend(f"{name}: fact marker {fact!r} is missing" for fact in required if fact not in present)

    for name, pattern, fact, minimum in PLACES:
        compiled = re.compile(pattern)
        texts[root / name], count = _replace(
            text_of(name), compiled, lambda _match, fact=fact: facts[fact], f"{name} {fact} ({pattern})", stale
        )
        if count < minimum:
            errors.append(f"{name}: {pattern!r} matched {count} time(s), expected at least {minimum}")
    return texts, stale, errors


def stamp_sitemap(root: Path) -> str:
    """Set each <lastmod> to the date the page last changed: its git commit date, or today if it is modified."""
    text = (root / SITEMAP).read_text(encoding="utf-8")

    def lastmod(match: re.Match[str]) -> str:
        page = match.group(1)[len(SITE_URL):] or "index.html"
        path = f"docs/{page}"
        dirty = subprocess.run(["git", "-C", str(root), "status", "--porcelain", "--", path],
                               capture_output=True, text=True, check=True).stdout.strip()
        changed = datetime.now(CENTRAL).date().isoformat() if dirty else subprocess.run(
            ["git", "-C", str(root), "log", "-1", "--format=%cs", "--", path],
            capture_output=True, text=True, check=True).stdout.strip()
        start, end = match.span(2)
        return match.group(0)[: start - match.start()] + (changed or match.group(2)) + match.group(0)[end - match.start():]

    return re.sub(r"<loc>([^<]+)</loc>(?:\s*)<lastmod>([^<]+)</lastmod>", lastmod, text)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true", help="report stale places and exit 1; write nothing")
    parser.add_argument("--dates", action="store_true", help="also stamp sitemap.xml lastmod from git")
    parser.add_argument("--root", type=Path, default=ROOT, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)

    facts = load_facts(args.root)
    texts, stale, errors = sync(args.root, facts)
    for error in errors:
        print(f"error: {error}", file=sys.stderr)
    if errors:
        return 2
    if args.check:
        for place in stale:
            print(f"stale: {place}", file=sys.stderr)
        if stale:
            print("Run: python scripts/sync_site_facts.py", file=sys.stderr)
            return 1
        print(f"Site facts are current ({', '.join(f'{k}={v}' for k, v in facts.items())}).")
        return 0
    for path, text in texts.items():
        if path.read_text(encoding="utf-8") != text:
            path.write_text(text, encoding="utf-8")
    if args.dates:
        (args.root / SITEMAP).write_text(stamp_sitemap(args.root), encoding="utf-8")
    print(f"Updated {len(stale)} place(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
