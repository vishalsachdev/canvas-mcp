"""Operator-controlled allowlist for tools with side effects.

A student can plant instructions in content the instructor's assistant reads.
Confirmation tokens cannot stop a model that decides to follow them, because the
model receives and can redeem its own token. The boundary a prompt injection
cannot talk its way past is one the model does not control: which tools exist at
all. These tests pin that boundary.

- Every registered tool has an explicit effect class, and ``read`` agrees with
  ``read_only_hint`` (so a mis-annotated writer cannot slip into the read set).
- On the HTTP transport, no side-effect tool exists unless the operator names it.
- On stdio, behaviour is unchanged unless the operator sets the allowlist.
- A removed tool cannot be called by name.
- Misconfiguration fails at startup rather than being guessed at.
"""

import asyncio

import pytest
from fastmcp import Client, FastMCP
from fastmcp.exceptions import ToolError

import canvas_mcp.core.config as config_module
import canvas_mcp.server as server_module
from canvas_mcp.core.config import STUDENT_WRITE_TOOL_NAMES
from canvas_mcp.core.tool_policy import (
    TOOL_EFFECTS,
    Effect,
    ToolPolicyError,
    apply_tool_policy,
    resolve_tool_policy,
)
from canvas_mcp.server import register_all_tools

SIDE_EFFECT = {name for name, effect in TOOL_EFFECTS.items() if effect is not Effect.READ}
READ = {name for name, effect in TOOL_EFFECTS.items() if effect is Effect.READ}


@pytest.fixture
def all_flags_on(monkeypatch):
    """Register feature-gated tools too, or the policy has a blind spot."""
    monkeypatch.setenv("EXECUTE_TYPESCRIPT_ENABLED", "true")
    monkeypatch.setenv("STUDENT_WRITE_TOOLS", ",".join(sorted(STUDENT_WRITE_TOOL_NAMES)))
    monkeypatch.delenv("ALLOWED_WRITE_TOOLS", raising=False)
    monkeypatch.setattr(config_module, "_config", None, raising=False)
    yield
    monkeypatch.setattr(config_module, "_config", None, raising=False)


def _registry() -> FastMCP:
    mcp = FastMCP(name="test-policy")
    register_all_tools(mcp, role="all")
    return mcp


async def _names(mcp: FastMCP) -> set[str]:
    return {tool.name for tool in await mcp.list_tools(run_middleware=False)}


# --- The classification itself -------------------------------------------------


@pytest.mark.asyncio
async def test_every_registered_tool_has_an_effect_class(all_flags_on):
    registered = await _names(_registry())
    assert registered, "no tools registered; the check would pass vacuously"
    unclassified = registered - TOOL_EFFECTS.keys()
    stale = TOOL_EFFECTS.keys() - registered
    assert not unclassified, f"classify these in core/tool_policy.py: {sorted(unclassified)}"
    assert not stale, f"TOOL_EFFECTS names tools that no longer exist: {sorted(stale)}"


@pytest.mark.asyncio
async def test_read_class_agrees_with_read_only_annotation(all_flags_on):
    """A tool that writes anything must not be annotated read-only, and vice versa.

    ``download_course_file`` carried ``read_only_hint=True`` while writing to the
    local filesystem; any policy keyed on the annotation would have allowed it.
    """
    mismatched = []
    for tool in await _registry().list_tools(run_middleware=False):
        annotated_read = bool(tool.annotations and tool.annotations.read_only_hint)
        classified_read = TOOL_EFFECTS.get(tool.name) is Effect.READ
        if annotated_read != classified_read:
            mismatched.append(
                f"{tool.name}: read_only_hint={annotated_read}, "
                f"class={TOOL_EFFECTS.get(tool.name)}"
            )
    assert not mismatched, "\n  ".join(["annotation and policy disagree:"] + mismatched)


def test_code_execution_is_its_own_class():
    assert TOOL_EFFECTS["execute_typescript"] is Effect.CODE_EXEC


def test_download_course_file_is_a_local_write():
    assert TOOL_EFFECTS["download_course_file"] is Effect.LOCAL_WRITE


# --- Resolving the setting ------------------------------------------------------


def test_http_default_allows_no_side_effect_tools():
    policy = resolve_tool_policy(None, "http")
    assert policy.enforced is True
    assert policy.allowed == frozenset()


def test_stdio_default_is_unrestricted():
    policy = resolve_tool_policy(None, "stdio")
    assert policy.enforced is False


@pytest.mark.parametrize("raw", ["", "   ", " , ", ",,,"])
@pytest.mark.parametrize("transport", ["http", "stdio"])
def test_set_but_empty_means_none(raw, transport):
    """Only an UNSET variable gets the transport default. A generator that
    empties its list must not silently restore unrestricted stdio access."""
    policy = resolve_tool_policy(raw, transport)
    assert policy.enforced is True
    assert policy.allowed == frozenset()


def test_none_keyword_is_case_insensitive_and_may_repeat():
    assert resolve_tool_policy("none,NONE", "stdio").allowed == frozenset()


@pytest.mark.parametrize("transport", ["http", "stdio"])
def test_none_denies_every_side_effect_tool(transport):
    policy = resolve_tool_policy("none", transport)
    assert policy.enforced is True
    assert policy.allowed == frozenset()


def test_explicit_names_allow_exactly_those():
    policy = resolve_tool_policy("send_conversation, update_page_settings", "http")
    assert policy.allowed == {"send_conversation", "update_page_settings"}


def test_all_excludes_code_execution():
    policy = resolve_tool_policy("all", "http")
    assert "execute_typescript" not in policy.allowed
    assert policy.allowed == SIDE_EFFECT - {"execute_typescript"}


def test_code_execution_must_be_named():
    policy = resolve_tool_policy("all,execute_typescript", "http")
    assert policy.allowed == SIDE_EFFECT


@pytest.mark.parametrize(
    "raw",
    [
        "send_convo",  # typo: must not silently allow nothing or everything
        "none,send_conversation",  # contradictory
        "list_courses",  # a read tool: always available, naming it is a mistake
    ],
)
def test_misconfiguration_fails_clearly(raw):
    with pytest.raises(ToolPolicyError):
        resolve_tool_policy(raw, "http")


# --- Applying it to a live registry --------------------------------------------


@pytest.mark.asyncio
async def test_http_default_leaves_only_read_tools(all_flags_on):
    mcp = _registry()
    removed = await apply_tool_policy(mcp, resolve_tool_policy(None, "http"))
    remaining = await _names(mcp)
    assert remaining == READ
    assert set(removed) == SIDE_EFFECT


@pytest.mark.asyncio
async def test_stdio_default_removes_nothing(all_flags_on):
    mcp = _registry()
    before = await _names(mcp)
    removed = await apply_tool_policy(mcp, resolve_tool_policy(None, "stdio"))
    assert removed == []
    assert await _names(mcp) == before


@pytest.mark.asyncio
async def test_allowlist_only_removes_never_adds(all_flags_on, monkeypatch):
    """Naming a tool cannot bring back one its registration gate left out."""
    monkeypatch.delenv("STUDENT_WRITE_TOOLS", raising=False)
    monkeypatch.setattr(config_module, "_config", None, raising=False)
    mcp = _registry()
    await apply_tool_policy(mcp, resolve_tool_policy("submit_assignment", "http"))
    assert "submit_assignment" not in await _names(mcp)


@pytest.mark.asyncio
async def test_removed_tool_cannot_be_called_by_name(all_flags_on):
    mcp = _registry()
    await apply_tool_policy(mcp, resolve_tool_policy("update_page_settings", "http"))
    async with Client(mcp) as client:
        names = {tool.name for tool in await client.list_tools()}
        assert "send_conversation" not in names
        assert "update_page_settings" in names
        with pytest.raises(ToolError, match="Unknown tool"):
            await client.call_tool(
                "send_conversation",
                {"course_identifier": "1", "recipient_ids": ["2"], "subject": "s", "body": "b"},
            )


@pytest.mark.asyncio
async def test_an_unclassified_tool_is_treated_as_a_side_effect(all_flags_on):
    """Fail closed: a tool missing from TOOL_EFFECTS must not survive enforcement."""
    mcp = _registry()

    @mcp.tool()
    def brand_new_tool() -> str:
        return "unreviewed"

    await apply_tool_policy(mcp, resolve_tool_policy(None, "http"))
    assert "brand_new_tool" not in await _names(mcp)


# --- Wiring: main() must apply the policy on both transports -------------------


def _served_registry(monkeypatch, argv, env) -> set[str]:
    """Run main() up to the point of serving and return the tools it would serve."""
    for key in ("ALLOWED_WRITE_TOOLS", "MCP_ACCESS_KEYS", "ENTRA_AUTH_ENABLED",
                "EXECUTE_TYPESCRIPT_ENABLED", "STUDENT_WRITE_TOOLS", "CANVAS_ROLE"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("CANVAS_API_URL", "https://canvas.example.edu/api/v1")
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    config_module.reset_config()

    captured: dict[str, FastMCP] = {}

    def fake_http(mcp, host, port):
        captured["mcp"] = mcp

    def fake_run(self, *args, **kwargs):
        captured["mcp"] = self

    async def fake_validate():
        return True, "Authenticated as: test"

    monkeypatch.setattr(server_module, "_run_http_server", fake_http)
    monkeypatch.setattr(server_module, "_validate_token", fake_validate)
    monkeypatch.setattr(FastMCP, "run", fake_run)
    monkeypatch.setattr("sys.argv", ["canvas-mcp-server", *argv])
    try:
        server_module.main()
    finally:
        config_module.reset_config()
    assert "mcp" in captured, "main() never reached the serve step"
    return asyncio.run(_names(captured["mcp"]))


def test_main_serves_http_read_only_by_default(monkeypatch):
    names = _served_registry(
        monkeypatch,
        ["--transport", "streamable-http"],
        {"MCP_ALLOW_UNAUTHENTICATED": "true"},
    )
    assert "list_courses" in names
    assert not (names & SIDE_EFFECT), f"side-effect tools served: {sorted(names & SIDE_EFFECT)}"


def test_main_serves_http_allowlisted_writes(monkeypatch):
    names = _served_registry(
        monkeypatch,
        ["--transport", "streamable-http"],
        {"MCP_ALLOW_UNAUTHENTICATED": "true", "ALLOWED_WRITE_TOOLS": "update_page_settings"},
    )
    assert names & SIDE_EFFECT == {"update_page_settings"}


def test_main_stdio_default_keeps_writes(monkeypatch):
    names = _served_registry(monkeypatch, [], {"CANVAS_API_TOKEN": "x" * 24})
    assert "send_conversation" in names


def test_main_stdio_none_removes_writes(monkeypatch):
    names = _served_registry(
        monkeypatch, [], {"CANVAS_API_TOKEN": "x" * 24, "ALLOWED_WRITE_TOOLS": "none"}
    )
    assert not (names & SIDE_EFFECT)


def test_main_stdio_empty_allowlist_removes_writes(monkeypatch):
    names = _served_registry(
        monkeypatch, [], {"CANVAS_API_TOKEN": "x" * 24, "ALLOWED_WRITE_TOOLS": ""}
    )
    assert not (names & SIDE_EFFECT)


# --- Read tools must not change anything ---------------------------------------


@pytest.mark.asyncio
async def test_get_conversation_details_never_marks_read(all_flags_on):
    """Canvas marks a conversation read on GET unless told not to. A read tool
    that did so let an injected assistant clear unread markers (for example on
    its own planted message) even with mark_conversations_read removed."""
    from unittest.mock import AsyncMock, patch

    mcp = _registry()
    await apply_tool_policy(mcp, resolve_tool_policy("none", "http"))
    with patch(
        "canvas_mcp.tools.messaging.make_canvas_request", new_callable=AsyncMock
    ) as request:
        request.return_value = {"id": 17, "messages": [], "participants": []}
        async with Client(mcp) as client:
            await client.call_tool("get_conversation_details", {"conversation_id": "17"})
    assert request.await_count == 1
    assert request.await_args.kwargs["params"]["auto_mark_as_read"] is False


@pytest.mark.asyncio
async def test_get_conversation_details_has_no_mark_read_switch(all_flags_on):
    tools = {tool.name: tool for tool in await _registry().list_tools(run_middleware=False)}
    properties = tools["get_conversation_details"].parameters.get("properties", {})
    assert "auto_mark_read" not in properties


def test_main_refuses_to_start_on_a_bad_allowlist(monkeypatch):
    with pytest.raises(SystemExit) as exc:
        _served_registry(
            monkeypatch,
            ["--transport", "streamable-http"],
            {"MCP_ALLOW_UNAUTHENTICATED": "true", "ALLOWED_WRITE_TOOLS": "send_convo"},
        )
    assert exc.value.code == 1
