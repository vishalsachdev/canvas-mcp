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

Container mode also delivers the script to the sandboxed process over stdin
instead of a host-side temp file (CodeQL alert 145): the code never sits on
disk where a traversable code_api_dir would make it readable by another
local account on a multi-user host. The network guard file is unaffected
and stays a real, world-readable file on disk.
"""

import asyncio
import os
import tempfile
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
    async def test_root_filesystem_is_read_only(self):
        """The image's own filesystem must be mounted read-only (issue 336).

        With the workspace on a :ro bind mount, the script delivered over
        stdin into $HOME, and /tmp on its own tmpfs, no path outside the two
        tmpfs mounts needs to be writable. Without --read-only the image
        rootfs is writable and executable by the sandbox uid, which is a
        free persistence and staging surface for executed code.
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
        assert "--read-only" in cmd, "container rootfs is not mounted read-only"
        # The flag must sit on the `run` line, before the image name, or the
        # runtime passes it to the container command instead.
        image_index = cmd.index(cmd[-4])
        assert cmd.index("--read-only") < image_index
        # And the two tmpfs mounts still exist, otherwise npx has nowhere to write.
        tmpfs_targets = [cmd[i + 1] for i, a in enumerate(cmd) if a == "--tmpfs"]
        assert any(t.startswith("/tmp:") for t in tmpfs_targets)
        assert any(t.startswith("/home/sandbox:") for t in tmpfs_targets)

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
    async def test_guard_file_is_world_readable_for_the_nonroot_user(self):
        """A 0600 guard file is unreadable to --user 65532:65532 on a plain
        Linux bind mount: neither the container process nor the host share the
        same uid, and the workspace is mounted read-only, so nothing can widen
        the permissions from inside the container. The code itself no longer
        goes through a host-side file in container mode (see the stdin-delivery
        test below), so only the guard file is chmod'd here.
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
        assert len(final_mode_by_path) == 1, chmod_calls
        assert all(mode == 0o644 for mode in final_mode_by_path.values()), chmod_calls

    @pytest.mark.asyncio
    async def test_code_streamed_over_stdin_never_written_to_host(self):
        """The script must not be written to a host-side file in container
        mode: it is piped over stdin and written only inside the exec-allowed
        $HOME tmpfs by the container's own `sh -c` invocation. This is
        CodeQL alert 145; the previous fix widened a host-side temp file's
        permissions to 0644 instead of removing the host-side copy.
        """
        tool = get_execute_typescript(TS_SANDBOX_MODE="container")
        if tool is None:
            pytest.skip("execute_typescript not registered in this configuration")

        process_mock = _mock_process()

        with patch(
            "canvas_mcp.tools.code_execution._detect_container_runtime",
            return_value="docker",
        ), patch(
            "canvas_mcp.tools.code_execution._runtime_available",
            new=AsyncMock(return_value=True),
        ), patch(
            "canvas_mcp.tools.code_execution.asyncio.create_subprocess_exec",
            new_callable=AsyncMock,
            return_value=process_mock,
        ) as spawn, patch(
            "canvas_mcp.tools.code_execution.tempfile.NamedTemporaryFile",
            wraps=tempfile.NamedTemporaryFile,
        ) as named_temp_file:
            await tool(code="console.log(1)")

        # The network guard (.cjs) still goes through NamedTemporaryFile; only
        # the .ts code file is asserted absent here.
        ts_suffix_calls = [
            call for call in named_temp_file.call_args_list
            if call.kwargs.get("suffix") == ".ts"
        ]
        assert not ts_suffix_calls, "container mode must not create a host-side .ts file"

        cmd = list(spawn.call_args.args)
        assert cmd[-3:-1] == ["sh", "-c"]
        script = cmd[-1]
        assert 'cat > "$HOME/run/code.ts"' in script
        assert 'npx tsx "$HOME/run/code.ts"' in script
        assert "/workspace/" not in script.split("cat >")[1], (
            "the script itself must live on the tmpfs, not the host mount"
        )

        assert spawn.call_args.kwargs["stdin"] == asyncio.subprocess.PIPE
        process_mock.communicate.assert_called_once_with(input=b"console.log(1)")

    @pytest.mark.asyncio
    async def test_stdin_script_can_still_import_canvas_modules(self):
        """Moving the script off the read-only workspace must not break the
        tool's documented `./canvas/*` import contract, which resolves
        relative to the script file. A bare `cat > $HOME/code.ts` fails with
        `Cannot find module './canvas/...'` for every real bulk-grading
        script (measured locally with tsx: same script resolves inside
        code_api/, fails from a HOME-like dir, resolves again beside a
        symlinked canvas/). The run dir must link the workspace's canvas/
        before the script is executed.
        """
        tool = get_execute_typescript(TS_SANDBOX_MODE="container")
        if tool is None:
            pytest.skip("execute_typescript not registered in this configuration")

        process_mock = _mock_process()

        with patch(
            "canvas_mcp.tools.code_execution._detect_container_runtime",
            return_value="docker",
        ), patch(
            "canvas_mcp.tools.code_execution._runtime_available",
            new=AsyncMock(return_value=True),
        ), patch(
            "canvas_mcp.tools.code_execution.asyncio.create_subprocess_exec",
            new_callable=AsyncMock,
            return_value=process_mock,
        ) as spawn:
            await tool(code="import { x } from './canvas/x.js';")

        cmd = list(spawn.call_args.args)
        script = cmd[-1]
        link, run = script.split("cat >", 1)
        # The whole code_api/ root is mirrored, not just canvas/: the README
        # also documents `import ... from './client'` and `./index`.
        assert 'ln -s /workspace/src/canvas_mcp/code_api/* "$HOME/run/"' in link
        assert 'ln -s /workspace/node_modules "$HOME/run/node_modules"' in link
        assert 'npx tsx "$HOME/run/code.ts"' in run
        # The code file is delivered on stdin, not on argv.
        assert spawn.call_args.kwargs.get("stdin") is asyncio.subprocess.PIPE
        process_mock.communicate.assert_awaited_once()
        assert process_mock.communicate.await_args.kwargs.get("input") == (
            b"import { x } from './canvas/x.js';"
        )

