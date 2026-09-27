"""Exhaustive trust-policy gate for registered tools that return Canvas data."""

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
    """Read tools need policy; hybrid tools may keep one after metadata changes."""
    mcp = FastMCP("untrusted-content-registry")
    register_all_tools(mcp, role="all")
    all_tools = {
        tool.name: tool for tool in await mcp.list_tools(run_middleware=False)
    }
    read_tools = {
        name: tool
        for name, tool in all_tools.items()
        if tool.annotations and tool.annotations.read_only_hint
    }
    policies = getattr(untrusted_content, "READ_TOOL_CONTENT_POLICIES", {})

    missing = set(read_tools) - set(policies)
    extra = set(policies) - set(all_tools)
    assert not missing and not extra, (
        "every live read-only tool must be classified for untrusted Canvas "
        "content:\n"
        f"  unclassified tools: {sorted(missing)}\n"
        f"  stale policy entries: {sorted(extra)}"
    )

    for name, policy in policies.items():
        tool = all_tools[name]
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


@pytest.mark.asyncio
async def test_every_resource_declares_and_keeps_its_untrusted_content_policy():
    """Resource templates are a separate MCP surface from read-only tools."""
    from canvas_mcp.resources import register_resources_and_prompts

    mcp = FastMCP("untrusted-resource-registry")
    register_resources_and_prompts(mcp)
    registered = [
        *await mcp.list_resources(run_middleware=False),
        *await mcp.list_resource_templates(run_middleware=False),
    ]
    all_resources = {resource.name: resource for resource in registered}
    policies = getattr(untrusted_content, "RESOURCE_CONTENT_POLICIES", {})
    assert set(all_resources) == set(policies), (
        "every resource and resource template needs a reviewed content policy; "
        f"unclassified: {sorted(set(all_resources) - set(policies))}; "
        f"stale: {sorted(set(policies) - set(all_resources))}"
    )
    for name, policy in policies.items():
        assert policy.category in {"fenced", "safe", "deferred"}, name
        if policy.category == "fenced":
            assert policy.guards, name
            source = inspect.getsource(all_resources[name].fn)
            assert any(guard in source for guard in policy.guards), name
        else:
            assert policy.rationale.strip(), name
