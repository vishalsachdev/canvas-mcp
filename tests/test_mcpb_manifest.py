"""The desktop extension's launcher pins a supported Python instead of inheriting the system one (issue 391)."""

import json
import tomllib
from pathlib import Path

from packaging.specifiers import SpecifierSet
from packaging.version import Version

REPO_ROOT = Path(__file__).resolve().parent.parent


def _launcher() -> tuple[str, list[str]]:
    config = json.loads((REPO_ROOT / "manifest.json").read_text(encoding="utf-8"))["server"]["mcp_config"]
    return config["command"], config["args"]


def test_launcher_selects_an_explicit_python_before_the_entry_point() -> None:
    command, args = _launcher()
    assert command == "uv"
    assert args[0] == "run"
    assert args[-1] == "canvas-mcp-server"
    # uv only treats --python as its own option when it precedes the command it runs.
    assert "--python" in args[:-1], "the launcher must not inherit an arbitrary system Python"
    assert args.count("--python") == 1


def test_pinned_python_satisfies_requires_python() -> None:
    _, args = _launcher()
    pinned = Version(args[args.index("--python") + 1])
    pyproject = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert pinned in SpecifierSet(pyproject["project"]["requires-python"])
    # A bare major.minor lets uv reuse any installed patch release before downloading one.
    assert pinned.release == (pinned.major, pinned.minor)
