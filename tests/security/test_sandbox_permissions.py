"""Real execution checks for the sandbox's Node permission boundary.

Removing the permission flags must let these harmless escape probes succeed.
No probe makes a network request or executes a shell command.

The real-execution tests need Node.js 22.18 or later. They skip without it on
a developer machine and fail in CI, where a skip would let the boundary go
unchecked.
"""

import json
import os
import subprocess
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastmcp import FastMCP

from canvas_mcp.core.config import reset_config
from canvas_mcp.tools import code_execution
from canvas_mcp.tools.code_execution import (
    _build_sandboxed_node_command,
    _find_sandbox_node,
    _node_version,
    register_code_execution_tools,
)

CODE_API_DIR = Path(code_execution.__file__).parent.parent / "code_api"


@pytest.fixture
def registered(monkeypatch: pytest.MonkeyPatch):
    """execute_typescript in local sandbox mode, without requiring Node."""
    monkeypatch.setenv("CANVAS_API_TOKEN", "test-token")
    monkeypatch.setenv("CANVAS_API_URL", "https://canvas.invalid/api/v1")
    monkeypatch.setenv("ENABLE_TS_SANDBOX", "true")
    monkeypatch.setenv("TS_SANDBOX_MODE", "local")
    monkeypatch.setenv("TS_SANDBOX_BLOCK_OUTBOUND_NETWORK", "true")
    monkeypatch.delenv("NODE_OPTIONS", raising=False)
    reset_config()
    captured = {}
    mcp = FastMCP("permissions-test")

    def tool(*args, **kwargs):
        def capture(fn):
            captured[fn.__name__] = fn
            return fn
        return capture

    with patch.object(mcp, "tool", tool):
        register_code_execution_tools(mcp)
    yield captured["execute_typescript"]
    reset_config()


@pytest.fixture
def execute(registered):
    """The same tool, for tests that run real code under a real Node."""
    _node, problem = _find_sandbox_node()
    if problem:
        if os.environ.get("CI"):
            pytest.fail(f"CI must run the sandbox boundary tests: {problem}")
        pytest.skip(problem)
    return registered


def _mock_process() -> MagicMock:
    return MagicMock(communicate=AsyncMock(return_value=(b"ok\n", b"")), returncode=0)


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["local", "auto"])
async def test_child_process_cannot_execute(execute, monkeypatch: pytest.MonkeyPatch, mode: str) -> None:
    monkeypatch.setenv("TS_SANDBOX_MODE", mode)
    reset_config()
    with patch("canvas_mcp.tools.code_execution._detect_container_runtime", return_value=None):
        result = await execute(code="""
import { execFileSync } from 'node:child_process';
console.log('ESCAPED:' + execFileSync(process.execPath, ['-e', 'console.log(731)']));
""")
    assert "ESCAPED:731" not in result, result
    assert "ERR_ACCESS_DENIED" in result, result


@pytest.mark.asyncio
@pytest.mark.parametrize("payload", [
    "const cp = await import('node:' + 'child_process'); cp.spawnSync(process.execPath, ['-e', '']);",
    "const { Worker } = await import('node:worker_threads'); new Worker('0', { eval: true });",
    "process.binding('spawn_sync');",
])
async def test_other_host_escape_routes_denied(execute, payload: str) -> None:
    result = await execute(code=payload + "\nconsole.log('ESCAPED');")
    assert "=== Output ===\nESCAPED" not in result, result
    assert "ERR_ACCESS_DENIED" in result, result


@pytest.mark.asyncio
async def test_canvas_api_imports_and_top_level_await_work_without_network(execute) -> None:
    result = await execute(code="""
import { canvasGet } from './client.js';
import { listCourses } from './canvas/courses/listCourses.js';
const calls: string[] = [];
globalThis.fetch = async (url, options) => {
  if (options.headers.Authorization !== 'Bearer test-token') throw Error('wrong token');
  calls.push(String(url));
  return new Response(JSON.stringify([{id: 17, name: 'Fixture course'}]));
};
const direct = await canvasGet('/courses');
const courses = await listCourses();
console.log(JSON.stringify({direct, courses, calls}));
""")
    assert "completed successfully" in result, result
    output = result.split("=== Output ===\n", 1)[1].splitlines()[0]
    data = json.loads(output)
    assert data["direct"] == [{"id": 17, "name": "Fixture course"}]
    assert len(data["calls"]) == 2
    assert all(url.startswith("https://canvas.invalid/api/v1/courses") for url in data["calls"])


@pytest.mark.asyncio
async def test_files_outside_api_cannot_be_read(execute, tmp_path: Path) -> None:
    secret = tmp_path / "private.txt"
    secret.write_text("PRIVATE_SENTINEL", encoding="utf-8")
    result = await execute(code=f"""
import {{ readFileSync }} from 'node:fs';
console.log(readFileSync({json.dumps(str(secret))}, 'utf8'));
""")
    assert "PRIVATE_SENTINEL" not in result, result
    assert "ERR_ACCESS_DENIED" in result, result


@pytest.mark.asyncio
async def test_file_writes_are_denied(execute, tmp_path: Path) -> None:
    target = tmp_path / "written.txt"
    result = await execute(code=f"""
import {{ writeFileSync }} from 'node:fs';
writeFileSync({json.dumps(str(target))}, 'WRITTEN');
console.log('ESCAPED');
""")
    assert not target.exists(), result
    assert "=== Output ===\nESCAPED" not in result, result
    assert "ERR_ACCESS_DENIED" in result, result


@pytest.mark.asyncio
async def test_inherited_node_options_cannot_reopen_child_process(
    execute, monkeypatch: pytest.MonkeyPatch
) -> None:
    # _build_safe_env passes NODE_OPTIONS through; Node honors --allow-* grants
    # from it. The sandboxed run must drop it rather than inherit the grant.
    monkeypatch.setenv("NODE_OPTIONS", "--allow-child-process --allow-fs-write=*")
    result = await execute(code="""
import { execFileSync } from 'node:child_process';
console.log('ESCAPED:' + execFileSync(process.execPath, ['-e', 'console.log(731)']));
""")
    assert "ESCAPED:731" not in result, result
    assert "ERR_ACCESS_DENIED" in result, result


@pytest.mark.asyncio
async def test_every_code_api_module_loads_in_the_sandbox(execute) -> None:
    # The sandbox runs plain Node, not tsx: every documented import must still
    # resolve ('./x.js' onto x.ts) and use only syntax Node can strip.
    modules = sorted(
        "./" + path.relative_to(CODE_API_DIR).with_suffix(".js").as_posix()
        for path in CODE_API_DIR.rglob("*.ts")
    )
    assert len(modules) > 10, modules
    result = await execute(code=f"""
const modules = {json.dumps(modules)};
for (const specifier of modules) {{
  await import(specifier);
}}
console.log('LOADED ' + modules.length);
""")
    assert "completed successfully" in result, result
    assert f"LOADED {len(modules)}" in result, result


@pytest.mark.asyncio
async def test_sandbox_report_names_the_permission_boundary(execute) -> None:
    result = await execute(code="console.log('hi');")
    assert "Mode: local" in result, result
    assert "Permissions: Node permission model" in result, result


def test_sandboxed_command_grants_only_code_api_reads(tmp_path: Path) -> None:
    api = tmp_path / "code_api"
    script = str(api / "script.ts")
    guard = api / "guard.cjs"
    cmd = _build_sandboxed_node_command("/opt/node", api, script, 512, guard)

    assert cmd[:2] == ["/opt/node", "--permission"]
    grants = [arg for arg in cmd if arg.startswith("--allow-")]
    assert grants == [f"--allow-fs-read={api}"]
    loader = cmd[cmd.index("--import") + 1]
    assert loader == (api / "_sandbox_loader.mjs").as_uri()
    assert "--max-old-space-size=512" in cmd
    assert f"--require={guard}" in cmd
    assert cmd[-1] == script


def test_sandboxed_command_omits_unset_limits(tmp_path: Path) -> None:
    cmd = _build_sandboxed_node_command("node", tmp_path, "s.ts", 0, None)
    assert not any(arg.startswith(("--max-old-space-size", "--require")) for arg in cmd)


def test_loader_ships_beside_the_code_api() -> None:
    assert (CODE_API_DIR / "_sandbox_loader.mjs").is_file()


@pytest.mark.parametrize(
    ("stdout", "returncode", "expected"),
    [
        ("v22.18.0\n", 0, (22, 18, 0)),
        ("v24.1.2", 0, (24, 1, 2)),
        ("not a version", 0, None),
        ("v22.18.0\n", 1, None),
    ],
)
def test_node_version_parsing(stdout: str, returncode: int, expected) -> None:
    _node_version.cache_clear()
    completed = subprocess.CompletedProcess(["node"], returncode, stdout=stdout, stderr="")
    with patch("canvas_mcp.tools.code_execution.subprocess.run", return_value=completed):
        assert _node_version("/fake/node") == expected
    _node_version.cache_clear()


def test_node_version_unreadable_binary() -> None:
    _node_version.cache_clear()
    with patch(
        "canvas_mcp.tools.code_execution.subprocess.run", side_effect=OSError("no exec")
    ):
        assert _node_version("/fake/node") is None
    _node_version.cache_clear()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("node_path", "version", "reason"),
    [
        (None, None, "was not found"),
        ("/usr/bin/node", (20, 11, 1), "20.11.1 is too old"),
        ("/usr/bin/node", (22, 17, 9), "22.17.9 is too old"),
        ("/usr/bin/node", None, "could not be read"),
    ],
)
async def test_local_sandbox_without_a_capable_node_refuses(
    registered, node_path, version, reason
) -> None:
    def which(name: str) -> str | None:
        return node_path if name == "node" else None

    with patch("canvas_mcp.tools.code_execution.shutil.which", side_effect=which), patch(
        "canvas_mcp.tools.code_execution._node_version", return_value=version
    ), patch(
        "canvas_mcp.tools.code_execution.asyncio.create_subprocess_exec",
        new_callable=AsyncMock,
    ) as spawn:
        result = await registered(code="console.log(1)")

    assert spawn.call_count == 0, "code ran without the permission boundary"
    assert "refused" in result.lower()
    assert reason in result
    assert "22.18" in result


@pytest.mark.asyncio
async def test_sandboxed_run_uses_node_permissions_and_drops_node_options(
    registered, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("NODE_OPTIONS", "--allow-child-process")
    with patch(
        "canvas_mcp.tools.code_execution._find_sandbox_node",
        return_value=("/usr/bin/node", None),
    ), patch(
        "canvas_mcp.tools.code_execution.asyncio.create_subprocess_exec",
        new_callable=AsyncMock,
        return_value=_mock_process(),
    ) as spawn:
        await registered(code="console.log(1)")

    assert spawn.call_count == 1
    cmd = list(spawn.call_args.args)
    env = spawn.call_args.kwargs["env"]
    assert cmd[:2] == ["/usr/bin/node", "--permission"]
    assert "tsx" not in " ".join(cmd)
    assert "NODE_OPTIONS" not in env
    assert env["CANVAS_API_TOKEN"] == "test-token"


@pytest.mark.asyncio
async def test_disabled_sandbox_still_runs_tsx_unrestricted(
    registered, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ENABLE_TS_SANDBOX", "false")
    reset_config()
    with patch(
        "canvas_mcp.tools.code_execution._build_local_tsx_command",
        return_value=["npx", "tsx", "script.ts"],
    ) as build, patch(
        "canvas_mcp.tools.code_execution._find_sandbox_node"
    ) as find_node, patch(
        "canvas_mcp.tools.code_execution.asyncio.create_subprocess_exec",
        new_callable=AsyncMock,
        return_value=_mock_process(),
    ) as spawn:
        await registered(code="console.log(1)")

    assert build.call_count == 1
    assert find_node.call_count == 0
    assert list(spawn.call_args.args) == ["npx", "tsx", "script.ts"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "code",
    [
        "import { listSubmissions, Submission } from './canvas/assignments/listSubmissions.js';\n"
        "const s: Submission | null = null;\nconsole.log(typeof listSubmissions, s);",
        "enum Color { Red }\nconsole.log(Color.Red);",
    ],
)
async def test_type_stripping_errors_carry_the_fix(execute, code: str) -> None:
    result = await execute(code=code)
    assert "execution failed" in result, result
    assert "import type" in result, result


@pytest.mark.asyncio
async def test_type_only_import_written_with_type_runs(execute) -> None:
    result = await execute(code="""
import { listSubmissions, type Submission } from './canvas/assignments/listSubmissions.js';
const s: Submission | null = null;
console.log('RAN ' + typeof listSubmissions + ' ' + s);
""")
    assert "completed successfully" in result, result
    assert "RAN function null" in result, result
    assert "Hint:" not in result, result
