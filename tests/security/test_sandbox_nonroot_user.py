"""
Sandbox Non-Root User Tests

Container mode previously launched the operator-configured image (default
node:20-alpine) with no --user flag, so execute_typescript ran as whatever
user that image defaults to, which is root for node:*-alpine and most other
images. This pins the fix (issue #157, item 2): the container now runs as a
fixed non-root uid:gid.

The fix needs its own writable, exec-allowed $HOME, because the existing
scratch tmpfs at /tmp is intentionally noexec (defense-in-depth for executed
code) and npx's postinstall of tsx's esbuild dependency spawns a native
binary from wherever $HOME's npm cache lands. Reusing /tmp for $HOME breaks
tsx outright; this file also pins that the two stay separate.
"""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastmcp import FastMCP

from canvas_mcp.core.config import get_config, reset_config
from canvas_mcp.tools.code_execution import register_code_execution_tools


def get_execute_typescript(**env):
    """Register the tool with the given configuration and return it.

    Duplicated from test_sandbox_fail_closed.py: a cross-module `tests.security`
    import only resolves when the repo root happens to be on sys.path, which CI's
    plain `pytest` invocation does not guarantee (see PR review discussion).
    """
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
        get_config()
    return captured.get("execute_typescript")


def _mock_process():
    return MagicMock(
        communicate=AsyncMock(return_value=(b"ok\n", b"")),
        returncode=0,
    )


class TestContainerRunsAsNonRoot:
    @pytest.mark.asyncio
    async def test_user_flag_present_and_non_root(self):
        tool = get_execute_typescript(TS_SANDBOX_MODE="container")
        if tool is None:
            pytest.skip("execute_typescript not registered in this configuration")

        with patch(
            "canvas_mcp.tools.code_execution._detect_container_runtime",
            return_value="docker",
        ), patch(
            "canvas_mcp.tools.code_execution._runtime_available",
            new=AsyncMock(return_value=True),
        ), patch(
            "canvas_mcp.tools.code_execution.asyncio.create_subprocess_exec",
            new_callable=AsyncMock,
            return_value=_mock_process(),
        ) as spawn:
            await tool(code="console.log(1)")

        assert spawn.call_count == 1
        cmd = list(spawn.call_args.args)

        assert "--user" in cmd, "container is started without a --user flag"
        uid_gid = cmd[cmd.index("--user") + 1]
        assert uid_gid != "0:0" and not uid_gid.startswith("root")

    @pytest.mark.asyncio
    async def test_home_is_writable_and_exec_allowed_not_the_noexec_scratch_tmpfs(self):
        """$HOME must land on its own exec-allowed mount, never on /tmp.

        /tmp is intentionally noexec (defense-in-depth for the executed code
        itself). npx's install of tsx's esbuild dependency spawns a native
        binary from $HOME's npm cache, so pointing $HOME at /tmp makes every
        container-mode execution fail before the caller's code ever runs.
        """
        tool = get_execute_typescript(TS_SANDBOX_MODE="container")
        if tool is None:
            pytest.skip("execute_typescript not registered in this configuration")

        with patch(
            "canvas_mcp.tools.code_execution._detect_container_runtime",
            return_value="docker",
        ), patch(
            "canvas_mcp.tools.code_execution._runtime_available",
            new=AsyncMock(return_value=True),
        ), patch(
            "canvas_mcp.tools.code_execution.asyncio.create_subprocess_exec",
            new_callable=AsyncMock,
            return_value=_mock_process(),
        ) as spawn:
            await tool(code="console.log(1)")

        cmd = list(spawn.call_args.args)

        env_pairs = [cmd[i + 1] for i, arg in enumerate(cmd) if arg == "-e"]
        home_entries = [pair for pair in env_pairs if pair.startswith("HOME=")]
        assert home_entries, "no HOME= passed to the container"
        home_path = home_entries[0].split("=", 1)[1]
        assert home_path != "/tmp" and not home_path.startswith("/tmp/")

        tmpfs_mounts = [cmd[i + 1] for i, arg in enumerate(cmd) if arg == "--tmpfs"]
        home_mount = next((m for m in tmpfs_mounts if m.startswith(f"{home_path}:")), None)
        assert home_mount is not None, f"{home_path} is not backed by its own tmpfs mount"
        assert "noexec" not in home_mount.split(":", 1)[1]

        scratch_mount = next((m for m in tmpfs_mounts if m.startswith("/tmp:")), None)
        assert scratch_mount is not None
        assert "noexec" in scratch_mount.split(":", 1)[1], (
            "the /tmp scratch mount must stay noexec regardless of the HOME fix"
        )

    @pytest.mark.asyncio
    async def test_code_and_guard_files_are_world_readable_for_the_nonroot_user(self):
        """A 0600 code/guard file is unreadable to --user 65532:65532 on a plain
        Linux bind mount: neither the container process nor the host share the
        same uid, and the workspace is mounted read-only, so nothing can widen
        the permissions from inside the container.
        """
        tool = get_execute_typescript(
            TS_SANDBOX_MODE="container", TS_SANDBOX_BLOCK_OUTBOUND_NETWORK="true"
        )
        if tool is None:
            pytest.skip("execute_typescript not registered in this configuration")

        chmod_calls = []
        real_chmod = os.chmod

        def recording_chmod(path, mode):
            chmod_calls.append((str(path), mode))
            real_chmod(path, mode)

        with patch(
            "canvas_mcp.tools.code_execution._detect_container_runtime",
            return_value="docker",
        ), patch(
            "canvas_mcp.tools.code_execution._runtime_available",
            new=AsyncMock(return_value=True),
        ), patch(
            "canvas_mcp.tools.code_execution.asyncio.create_subprocess_exec",
            new_callable=AsyncMock,
            return_value=_mock_process(),
        ), patch(
            "canvas_mcp.tools.code_execution.os.chmod", side_effect=recording_chmod,
        ):
            await tool(code="console.log(1)")

        # _write_network_guard sets 0600 first; the last mode per path is what
        # actually reaches disk, so take that rather than every call.
        final_mode_by_path = dict(chmod_calls)
        assert len(final_mode_by_path) == 2, chmod_calls
        assert all(mode == 0o644 for mode in final_mode_by_path.values()), chmod_calls
