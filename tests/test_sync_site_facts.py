"""scripts/sync_site_facts.py keeps the website and README in step with their sources."""

import json
import shutil
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import sync_site_facts  # noqa: E402

SOURCES = ("pyproject.toml", "tools/TOOL_MANIFEST.json", "docs/data/impact.json", "docs/index.html", "docs/llms.txt",
           "README.md")


@pytest.fixture
def root(tmp_path: Path) -> Path:
    for name in SOURCES:
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(REPO_ROOT / name, tmp_path / name)
    for skill in (REPO_ROOT / "skills").glob("*/SKILL.md"):
        (tmp_path / "skills" / skill.parent.name).mkdir(parents=True)
        shutil.copy(skill, tmp_path / "skills" / skill.parent.name / "SKILL.md")
    return tmp_path


def run(root: Path, *flags: str) -> int:
    return sync_site_facts.main([*flags, "--root", str(root)])


def test_repository_facts_are_current():
    # Fails when impact.json, the manifest, pyproject or skills/ change without a sync.
    assert sync_site_facts.main(["--check"]) == 0


def test_new_tool_makes_every_repeated_count_stale(root: Path, capsys):
    manifest = json.loads((root / "tools/TOOL_MANIFEST.json").read_text(encoding="utf-8"))
    manifest["tools"].append(dict(manifest["tools"][0], name="new_tool"))
    (root / "tools/TOOL_MANIFEST.json").write_text(json.dumps(manifest), encoding="utf-8")
    count = str(len(manifest["tools"]))

    assert run(root, "--check") == 1
    err = capsys.readouterr().err
    for name in ("docs/index.html", "docs/llms.txt", "README.md"):
        assert f"{name} tools" in err
    assert (root / "README.md").read_text(encoding="utf-8") == (REPO_ROOT / "README.md").read_text(encoding="utf-8"), "--check must not write"

    assert run(root) == 0
    assert f"**up to {count} tools**" in (root / "README.md").read_text(encoding="utf-8")
    assert f'<div class="stat-value">{count}</div>' in (root / "docs/index.html").read_text(encoding="utf-8")
    assert run(root, "--check") == 0


def test_new_stats_reach_the_static_panel_in_central_time(root: Path):
    impact = json.loads((root / "docs/data/impact.json").read_text(encoding="utf-8"))
    impact["github"].update(stars=999, forks=12, contributors=34)
    impact["collected_at"] = "2026-11-02T04:30:00Z"  # 10:30 PM CST on November 1
    (root / "docs/data/impact.json").write_text(json.dumps(impact), encoding="utf-8")

    assert run(root) == 0
    page = (root / "docs/index.html").read_text(encoding="utf-8")
    for marker in ("<!-- fact:stars -->999<", "<!-- fact:forks -->12<", "<!-- fact:contributors -->34<",
                   "<!-- fact:stats_as_of -->November 1, 2026<"):
        assert marker in page


def test_reworded_page_that_drops_a_place_is_an_error(root: Path, capsys):
    readme = root / "README.md"
    readme.write_text(readme.read_text(encoding="utf-8").replace("**8 agent skills**", "**a set of agent skills**"), encoding="utf-8")
    assert run(root, "--check") == 2
    assert "agent skills" in capsys.readouterr().err


def test_unknown_marker_is_an_error(root: Path, capsys):
    page = root / "docs/index.html"
    page.write_text(page.read_text(encoding="utf-8").replace("<!-- fact:forks -->", "<!-- fact:frks -->"), encoding="utf-8")
    assert run(root, "--check") == 2
    assert "'frks'" in capsys.readouterr().err
