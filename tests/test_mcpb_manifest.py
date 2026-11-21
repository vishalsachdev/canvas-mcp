"""The desktop extension's launcher pins a supported Python instead of inheriting the system one (issue 391)."""

import json
import re
import tomllib
from pathlib import Path

import pytest
from packaging.specifiers import SpecifierSet
from packaging.version import Version

from canvas_mcp.core.tool_policy import resolve_tool_policy

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


# The extension runs the stdio transport, which is read-only unless
# ALLOWED_WRITE_TOOLS is set. Claude Desktop passes only the env vars the
# manifest maps, so without a user_config entry an extension user could never
# turn writes back on.


def _manifest() -> dict:
    return json.loads((REPO_ROOT / "manifest.json").read_text(encoding="utf-8"))


def test_extension_passes_the_write_allowlist_to_the_server() -> None:
    env = _manifest()["server"]["mcp_config"]["env"]
    assert env.get("ALLOWED_WRITE_TOOLS") == "${user_config.allowed_write_tools}"


def test_every_user_config_reference_names_a_defined_setting() -> None:
    manifest = _manifest()
    env = manifest["server"]["mcp_config"]["env"]
    referenced = {
        match
        for value in env.values()
        for match in re.findall(r"\$\{user_config\.([a-z0-9_]+)\}", value)
    }
    assert referenced, "positive control: the manifest maps user_config values"
    assert referenced <= manifest["user_config"].keys()


def test_write_allowlist_setting_defaults_to_read_only() -> None:
    setting = _manifest()["user_config"]["allowed_write_tools"]
    assert setting["type"] == "string"
    assert setting.get("required") is False
    # A default guarantees the placeholder is substituted. An unsubstituted
    # "${user_config...}" would reach the server as an unknown tool name.
    default = setting["default"]
    policy = resolve_tool_policy(default, "stdio")
    assert policy.enforced and not policy.allowed


@pytest.mark.parametrize("blank", ["", "  "])
def test_blank_write_allowlist_stays_read_only(blank: str) -> None:
    policy = resolve_tool_policy(blank, "stdio")
    assert policy.enforced and not policy.allowed
