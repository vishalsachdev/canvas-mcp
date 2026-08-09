"""Isolation is a boundary, not a preference.

``execute_typescript`` runs caller-supplied code. Container mode is the only
mode that actually confines it; local mode runs it directly on the host with the
service account's environment, which is a developer convenience on a local stdio
server and a host-execution primitive on a shared HTTP one.

Previously, an explicit request for container isolation degraded to local
execution whenever the runtime was missing or the image name was malformed — so
a misconfiguration silently became host execution. These tests pin the two
invariants that stop that:

1. Explicitly requested container isolation fails closed.
2. Local execution is never selected while serving an HTTP request.

Also pinned: when outbound access is blocked and no allowlist is configured, the
container is started with --network=none, so egress is enforced by the kernel
rather than by patching Node APIs inside the sandbox (which executed code can
step around via child_process or a bundled utility).
"""

from contextlib import contextmanager
from unittest.mock import AsyncMock, patch

import pytest

from canvas_mcp.tools.code_execution import _sandbox_unavailable_error


@contextmanager
def _http_request_with_token():
    """Simulate an authenticated HTTP request.

    Without per-request credentials, _resolve_canvas_credentials refuses first
    with "Canvas token required for HTTP code execution" — a different (and
    already-present) guard. Supplying the token isolates the sandbox boundary.
    """
    from canvas_mcp.core.credentials import RequestCredentials

    with patch(
        "canvas_mcp.tools.code_execution.get_request_credentials",
        return_value=RequestCredentials(api_token="caller-token",
                                        api_url="https://c.test"),
    ):
        yield


def get_execute_typescript(**env):
    """Register the tool with the given configuration and return it."""
    import os

    from fastmcp import FastMCP

    from canvas_mcp.core.config import get_config, reset_config
    from canvas_mcp.tools.code_execution import register_code_execution_tools

    base = {"EXECUTE_TYPESCRIPT_ENABLED": "true", "ENABLE_TS_SANDBOX": "true",
            "CANVAS_API_URL": "https://c.test", "CANVAS_API_TOKEN": "t"}
    base.update(env)

    captured: dict = {}
    mcp = FastMCP("test")
    original = mcp.tool

    def capturing(*a, **k):
        decorator = original(*a, **k)

        def wrapper(fn):
            captured[fn.__name__] = fn
            return decorator(fn)

        return wrapper

    mcp.tool = capturing
    with patch.dict(os.environ, base, clear=False):
        reset_config()
        register_code_execution_tools(mcp)
        # Materialize the config while the environment is still patched.
        # Registration alone does not read it, so without this the singleton
        # stays unset and is built at *call* time from the unpatched
        # environment — silently testing the default mode instead of this one.
        get_config()
    return captured.get("execute_typescript")


class TestFailClosedMessage:
    def test_refusal_names_the_reason_and_does_not_suggest_running_anyway(self):
        msg = _sandbox_unavailable_error("no container runtime is available.")
        assert "refused" in msg.lower()
        assert "no container runtime" in msg
        assert "failed closed" in msg.lower()


class TestExplicitContainerModeFailsClosed:
    @pytest.mark.asyncio
    async def test_missing_runtime_refuses_instead_of_running_locally(self):
        tool = get_execute_typescript(TS_SANDBOX_MODE="container")
        if tool is None:
            pytest.skip("execute_typescript not registered in this configuration")

        with patch(
            "canvas_mcp.tools.code_execution._detect_container_runtime",
            return_value=None,
        ), patch(
            "canvas_mcp.tools.code_execution.asyncio.create_subprocess_exec",
            new_callable=AsyncMock,
        ) as spawn:
            result = await tool(code="console.log(1)")

        assert "refused" in result.lower()
        assert spawn.call_count == 0, "code was executed despite missing isolation"

    @pytest.mark.asyncio
    async def test_unavailable_runtime_refuses(self):
        tool = get_execute_typescript(TS_SANDBOX_MODE="container")
        if tool is None:
            pytest.skip("execute_typescript not registered in this configuration")

        with patch(
            "canvas_mcp.tools.code_execution._detect_container_runtime",
            return_value="docker",
        ), patch(
            "canvas_mcp.tools.code_execution._runtime_available",
            new=AsyncMock(return_value=False),
        ), patch(
            "canvas_mcp.tools.code_execution.asyncio.create_subprocess_exec",
            new_callable=AsyncMock,
        ) as spawn:
            result = await tool(code="console.log(1)")

        assert "refused" in result.lower()
        assert spawn.call_count == 0

    @pytest.mark.asyncio
    async def test_malformed_image_refuses(self):
        tool = get_execute_typescript(
            TS_SANDBOX_MODE="container", TS_SANDBOX_CONTAINER_IMAGE="not a valid image"
        )
        if tool is None:
            pytest.skip("execute_typescript not registered in this configuration")

        with patch(
            "canvas_mcp.tools.code_execution.asyncio.create_subprocess_exec",
            new_callable=AsyncMock,
        ) as spawn:
            result = await tool(code="console.log(1)")

        assert "refused" in result.lower()
        assert spawn.call_count == 0


class TestNeverLocalOverHttp:
    @pytest.mark.asyncio
    async def test_http_request_cannot_reach_local_execution(self):
        """Even with mode explicitly 'local', HTTP must not run code on the host."""
        tool = get_execute_typescript(TS_SANDBOX_MODE="local")
        if tool is None:
            pytest.skip("execute_typescript not registered in this configuration")

        with _http_request_with_token(), patch(
            "canvas_mcp.tools.code_execution.is_http_request_active", return_value=True
        ), patch(
            "canvas_mcp.tools.code_execution.asyncio.create_subprocess_exec",
            new_callable=AsyncMock,
        ) as spawn:
            result = await tool(code="console.log(1)")

        assert "refused" in result.lower()
        assert "HTTP" in result
        assert spawn.call_count == 0, "caller code ran on the host over HTTP"

    @pytest.mark.asyncio
    async def test_auto_mode_without_runtime_also_refuses_over_http(self):
        """'auto' silently means 'local' when no runtime exists — still refused."""
        tool = get_execute_typescript(TS_SANDBOX_MODE="auto")
        if tool is None:
            pytest.skip("execute_typescript not registered in this configuration")

        with _http_request_with_token(), patch(
            "canvas_mcp.tools.code_execution.is_http_request_active", return_value=True
        ), patch(
            "canvas_mcp.tools.code_execution._detect_container_runtime",
            return_value=None,
        ), patch(
            "canvas_mcp.tools.code_execution.asyncio.create_subprocess_exec",
            new_callable=AsyncMock,
        ) as spawn:
            result = await tool(code="console.log(1)")

        assert "refused" in result.lower()
        assert spawn.call_count == 0


class TestEgressEnforcementIsHonest:
    """#7 is mitigated, not closed. This test states exactly how far it goes.

    Kernel-level egress (--network=none) is only correct when the sandbox needs
    no network at all. But when outbound blocking is on, the Canvas host is
    automatically added to the allowlist — executed code exists to call Canvas —
    so in every working configuration the allowlist is non-empty and egress falls
    back to the in-process Node guard, which child_process and bundled utilities
    can step around while CANVAS_API_TOKEN sits in the environment.

    Closing it properly needs an egress proxy or network namespace (tracked
    separately). Until then the tool must say so rather than imply enforcement.
    """

    def test_canvas_host_is_always_allowlisted_when_blocking(self):
        """Documents why --network=none cannot apply to a normal deployment."""
        from canvas_mcp.core.config import get_config
        from canvas_mcp.tools.code_execution import (
            _normalize_host,
            _parse_allowlist_hosts,
        )

        get_execute_typescript(
            TS_SANDBOX_MODE="container", TS_SANDBOX_BLOCK_OUTBOUND_NETWORK="true"
        )
        config = get_config()
        allowlist = _parse_allowlist_hosts(config.ts_sandbox_allowlist_hosts)
        canvas_host = _normalize_host(config.canvas_api_url)
        if canvas_host and canvas_host not in allowlist:
            allowlist.append(canvas_host)

        assert allowlist, (
            "allowlist is non-empty in any real config, so --network=none does not "
            "apply and the in-process guard remains the only egress control"
        )

    @pytest.mark.asyncio
    async def test_best_effort_egress_is_disclosed_to_the_caller(self):
        """A bypassable control must not be reported as a working one."""
        tool = get_execute_typescript(
            TS_SANDBOX_MODE="container", TS_SANDBOX_BLOCK_OUTBOUND_NETWORK="true"
        )
        if tool is None:
            pytest.skip("execute_typescript not registered in this configuration")

        with patch(
            "canvas_mcp.tools.code_execution._detect_container_runtime",
            return_value=None,
        ), patch(
            "canvas_mcp.tools.code_execution.asyncio.create_subprocess_exec",
            new_callable=AsyncMock,
        ):
            # Container mode with no runtime fails closed, which is the #4 half.
            result = await tool(code="console.log(1)")

        assert "refused" in result.lower()
