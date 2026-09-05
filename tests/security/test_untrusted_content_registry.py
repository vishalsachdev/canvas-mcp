"""Exhaustive trust-policy gate for every registered read-only tool (#262)."""

import inspect

import pytest
from fastmcp import FastMCP

import canvas_mcp.core.config as config_module
import canvas_mcp.core.untrusted_content as untrusted_content
from canvas_mcp.core.config import STUDENT_WRITE_TOOL_NAMES
from canvas_mcp.server import register_all_tools


@pytest.fixture(autouse=True)
def _all_feature_gated_tools_enabled(monkeypatch):
    """Make the registry gate see every optional tool profile."""
    monkeypatch.setenv("EXECUTE_TYPESCRIPT_ENABLED", "true")
    monkeypatch.setenv(
        "STUDENT_WRITE_TOOLS", ",".join(sorted(STUDENT_WRITE_TOOL_NAMES))
    )
    monkeypatch.setattr(config_module, "_config", None, raising=False)
    yield
    monkeypatch.setattr(config_module, "_config", None, raising=False)


@pytest.mark.asyncio
async def test_every_read_tool_declares_and_keeps_its_untrusted_content_policy():
    """A new read tool cannot ship unclassified or lose its declared fence path."""
    mcp = FastMCP("untrusted-content-registry")
    register_all_tools(mcp, role="all")
    read_tools = {
        tool.name: tool
        for tool in await mcp.list_tools(run_middleware=False)
        if tool.annotations and tool.annotations.read_only_hint
    }
    policies = getattr(untrusted_content, "READ_TOOL_CONTENT_POLICIES", {})

    missing = set(read_tools) - set(policies)
    extra = set(policies) - set(read_tools)
    assert not missing and not extra, (
        "every live read-only tool must be classified for untrusted Canvas "
        "content:\n"
        f"  unclassified tools: {sorted(missing)}\n"
        f"  stale/non-read policy entries: {sorted(extra)}"
    )

    for name, tool in read_tools.items():
        policy = policies[name]
        assert policy.category in {"fenced", "safe", "deferred"}, name

        if policy.category == "fenced":
            assert policy.guards, f"{name}: fenced policy must name its guard path"
            source = inspect.getsource(tool.fn)
            assert any(guard in source for guard in policy.guards), (
                f"{name}: declared fencing path disappeared; expected one of "
                f"{policy.guards} in the registered tool function"
            )
        else:
            assert policy.rationale.strip(), (
                f"{name}: {policy.category} policies require a reviewable rationale"
            )
