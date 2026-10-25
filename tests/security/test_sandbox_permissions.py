"""Real execution checks for the sandbox's Node permission boundary.

Removing the permission flags must let these harmless escape probes succeed.
No probe makes a network request or executes a shell command.

The real-execution tests need Node.js 22.18 or later. They skip without it on
a developer machine and fail in CI, where a skip would let the boundary go
unchecked.
"""

import json
import os
import shutil
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastmcp import FastMCP

from canvas_mcp.core.config import reset_config
from canvas_mcp.tools import code_execution
from canvas_mcp.tools.code_execution import (
    _build_sandboxed_node_command,
    _find_sandbox_node,
    _node_runtime,
    _SandboxNode,
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
    cmd = _build_sandboxed_node_command(_SandboxNode("/opt/node", False), api, script, 512, guard)

    assert cmd[:2] == ["/opt/node", "--permission"]
    grants = [arg for arg in cmd if arg.startswith("--allow-")]
    assert grants == [f"--allow-fs-read={api}"]
    loader = cmd[cmd.index("--import") + 1]
    assert loader == (api / "_sandbox_loader.mjs").as_uri()
    assert "--max-old-space-size=512" in cmd
    assert f"--require={guard}" in cmd
    assert cmd[-1] == script


def test_sandboxed_command_omits_unset_limits(tmp_path: Path) -> None:
    cmd = _build_sandboxed_node_command(_SandboxNode("node", False), tmp_path, "s.ts", 0, None)
    assert not any(arg.startswith(("--max-old-space-size", "--require")) for arg in cmd)


def test_loader_ships_beside_the_code_api() -> None:
    assert (CODE_API_DIR / "_sandbox_loader.mjs").is_file()


@pytest.mark.parametrize(
    ("stdout", "returncode", "expected"),
    [
        ("v22.18.0 false\n", 0, ((22, 18, 0), False)),
        ("v26.12.1 true", 0, ((26, 12, 1), True)),
        ("v22.18.0\n", 0, None),
        ("not a version", 0, None),
        ("v22.18.0 false\n", 1, None),
    ],
)
def test_node_runtime_parsing(stdout: str, returncode: int, expected) -> None:
    _node_runtime.cache_clear()
    completed = subprocess.CompletedProcess(["node"], returncode, stdout=stdout, stderr="")
    with patch("canvas_mcp.tools.code_execution.subprocess.run", return_value=completed):
        assert _node_runtime("/fake/node") == expected
    _node_runtime.cache_clear()


def test_node_runtime_unreadable_binary() -> None:
    _node_runtime.cache_clear()
    with patch(
        "canvas_mcp.tools.code_execution.subprocess.run", side_effect=OSError("no exec")
    ):
        assert _node_runtime("/fake/node") is None
    _node_runtime.cache_clear()


def test_network_grant_only_where_node_gates_the_network(tmp_path: Path) -> None:
    cmd = _build_sandboxed_node_command(_SandboxNode("node", True), tmp_path, "s.ts", 0, None)
    grants = [arg for arg in cmd if arg.startswith("--allow-")]
    assert grants == [f"--allow-fs-read={tmp_path}", "--allow-net"]
    # Never a category-wide suppression: it would hide the caller's warnings too.
    assert not any(arg.startswith("--disable-warning") for arg in cmd)
    plain = _build_sandboxed_node_command(_SandboxNode("node", False), tmp_path, "s.ts", 0, None)
    assert "--allow-net" not in plain


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("node_path", "runtime", "reason"),
    [
        (None, None, "was not found"),
        ("/usr/bin/node", ((20, 11, 1), False), "20.11.1 is too old"),
        ("/usr/bin/node", ((22, 17, 9), False), "22.17.9 is too old"),
        ("/usr/bin/node", None, "could not be read"),
    ],
)
async def test_local_sandbox_without_a_capable_node_refuses(
    registered, node_path, runtime, reason
) -> None:
    def which(name: str) -> str | None:
        return node_path if name == "node" else None

    with patch("canvas_mcp.tools.code_execution.shutil.which", side_effect=which), patch(
        "canvas_mcp.tools.code_execution._node_runtime", return_value=runtime
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
        return_value=(_SandboxNode("/usr/bin/node", False), None),
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


def _installed_sandbox_nodes() -> list[str]:
    """Every distinct Node on PATH that the local sandbox accepts."""
    found: dict[str, str] = {}
    for directory in os.environ.get("PATH", "").split(os.pathsep):
        candidate = shutil.which("node", path=directory) if directory else None
        if not candidate:
            continue
        runtime = _node_runtime(candidate)
        if runtime and runtime[0] >= code_execution._MIN_SANDBOX_NODE:
            found.setdefault(os.path.realpath(candidate), candidate)
    return sorted(found.values())


SANDBOX_NODES = _installed_sandbox_nodes() or [None]


@pytest.fixture(params=SANDBOX_NODES, ids=lambda path: f"node={path}")
def on_each_node(request, registered):
    """Run the sandbox on each installed capable Node in turn."""
    node_path = request.param
    if node_path is None:
        if os.environ.get("CI"):
            pytest.fail("CI must run the sandbox boundary tests: no Node.js 22.18+ on PATH")
        pytest.skip("No Node.js 22.18+ on PATH")

    def which(name: str, *args, **kwargs) -> str | None:
        return node_path if name == "node" else None

    with patch("canvas_mcp.tools.code_execution.shutil.which", side_effect=which):
        yield registered


class _FakeCanvas(BaseHTTPRequestHandler):
    seen: list[tuple[str, str | None]] = []

    def do_GET(self) -> None:  # noqa: N802 (http.server naming)
        type(self).seen.append((self.path, self.headers.get("Authorization")))
        body = json.dumps([{"id": 17, "name": "Fixture course"}]).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args) -> None:
        pass


@pytest.fixture
def fake_canvas(monkeypatch: pytest.MonkeyPatch):
    _FakeCanvas.seen = []
    server = ThreadingHTTPServer(("127.0.0.1", 0), _FakeCanvas)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setenv("CANVAS_API_URL", f"http://127.0.0.1:{server.server_port}/api/v1")
    reset_config()
    yield _FakeCanvas.seen
    server.shutdown()
    server.server_close()
    reset_config()


@pytest.mark.asyncio
async def test_real_canvas_request_works_on_each_node(on_each_node, fake_canvas) -> None:
    # No fetch stub: the request leaves the sandbox for the configured Canvas
    # host. Node 25+ gates the network under --permission, so a missing
    # --allow-net there fails this test while a stubbed fetch would pass.
    result = await on_each_node(code="""
import { canvasGet } from './client.js';
console.log('GOT ' + JSON.stringify(await canvasGet('/courses')));
""")
    assert 'GOT [{"id":17,"name":"Fixture course"}]' in result, result
    assert fake_canvas, result
    path, authorization = fake_canvas[0]
    assert path.startswith("/api/v1/courses"), fake_canvas
    assert authorization == "Bearer test-token", fake_canvas
    assert "under experimental phase" not in result, result


@pytest.mark.asyncio
async def test_boundary_holds_on_each_node(on_each_node, tmp_path: Path) -> None:
    target = tmp_path / "written.txt"
    result = await on_each_node(code=f"""
import {{ execFileSync }} from 'node:child_process';
import {{ writeFileSync }} from 'node:fs';
const seen: string[] = [];
try {{ execFileSync(process.execPath, ['-e', '0']); seen.push('child:ALLOWED'); }}
catch (error) {{ seen.push('child:' + (error as {{ code?: string }}).code); }}
try {{ writeFileSync({json.dumps(str(target))}, 'x'); seen.push('write:ALLOWED'); }}
catch (error) {{ seen.push('write:' + (error as {{ code?: string }}).code); }}
console.log(seen.join(' '));
""")
    assert "child:ERR_ACCESS_DENIED write:ERR_ACCESS_DENIED" in result, result
    assert not target.exists(), result


@pytest.mark.asyncio
async def test_documented_import_forms_resolve(on_each_node) -> None:
    # tsx accepted all of these; the code API README and examples use them.
    result = await on_each_node(code="""
import { canvasGet } from './client';
import { bulkGrade } from './canvas/grading';
import { listCourses } from './canvas/courses/listCourses';
import * as grading from './canvas/grading/index.js';
console.log(['RESOLVED', typeof canvasGet, typeof bulkGrade, typeof listCourses,
  typeof grading.bulkGrade].join(' '));
""")
    assert "RESOLVED function function function function" in result, result


@pytest.mark.asyncio
async def test_missing_relative_module_still_reports_not_found(on_each_node) -> None:
    result = await on_each_node(code="import { x } from './no/such/module';\nconsole.log(x);")
    assert "execution failed" in result, result
    assert "ERR_MODULE_NOT_FOUND" in result, result


def test_strip_allow_net_warning_removes_only_that_message() -> None:
    from canvas_mcp.tools.code_execution import _strip_allow_net_warning

    stderr = (
        "(node:123) ExperimentalWarning: The flag --allow-net is under experimental phase.\n"
        "(Use `node --trace-warnings ...` to show where the warning was created)\n"
        "(node:123) ExperimentalWarning: user-level\n"
        "Error: boom\n"
    )
    assert _strip_allow_net_warning(stderr) == (
        "(node:123) ExperimentalWarning: user-level\nError: boom\n"
    )
    untouched = "(node:9) ExperimentalWarning: something else\n"
    assert _strip_allow_net_warning(untouched) == untouched


@pytest.mark.asyncio
async def test_caller_experimental_warnings_stay_visible(on_each_node) -> None:
    result = await on_each_node(code="""
process.emitWarning('caller-level', 'ExperimentalWarning');
console.log('done');
""")
    assert "completed successfully" in result, result
    assert "ExperimentalWarning: caller-level" in result, result
    assert "under experimental phase" not in result, result


@pytest.mark.parametrize("node_path", SANDBOX_NODES, ids=lambda path: f"node={path}")
def test_probe_does_not_run_inherited_preloads(
    node_path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    if node_path is None:
        if os.environ.get("CI"):
            pytest.fail("CI must run the sandbox boundary tests: no Node.js 22.18+ on PATH")
        pytest.skip("No Node.js 22.18+ on PATH")
    marker = tmp_path / "preload-ran"
    preload = tmp_path / "preload.cjs"
    preload.write_text(
        f"require('fs').writeFileSync({json.dumps(str(marker))}, 'ran');\n", encoding="utf-8"
    )
    monkeypatch.setenv("NODE_OPTIONS", f"--require={preload}")
    _node_runtime.cache_clear()
    try:
        runtime = _node_runtime(node_path)
    finally:
        _node_runtime.cache_clear()
    assert runtime is not None and runtime[0] >= code_execution._MIN_SANDBOX_NODE
    assert not marker.exists(), "the version probe ran an inherited NODE_OPTIONS preload"


def test_probe_passes_windows_system_dirs_but_not_node_options(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Node on Windows cannot start without SYSTEMROOT; NODE_OPTIONS must stay out.
    monkeypatch.setenv("SYSTEMROOT", r"C:\Windows")
    monkeypatch.setenv("NODE_OPTIONS", "--require=/tmp/preload.cjs")
    monkeypatch.setenv("CANVAS_API_TOKEN", "not-for-the-probe")
    completed = subprocess.CompletedProcess(["node"], 0, stdout="v22.18.0 false\n", stderr="")
    _node_runtime.cache_clear()
    with patch(
        "canvas_mcp.tools.code_execution.subprocess.run", return_value=completed
    ) as run:
        assert _node_runtime("/fake/node") == ((22, 18, 0), False)
    _node_runtime.cache_clear()
    env = run.call_args.kwargs["env"]
    assert env["SYSTEMROOT"] == r"C:\Windows"
    assert "NODE_OPTIONS" not in env
    assert "CANVAS_API_TOKEN" not in env


def test_probe_failure_is_logged_with_its_reason(caplog) -> None:
    completed = subprocess.CompletedProcess(
        ["node"], 134, stdout="", stderr="Assertion failed: winsock init\nmore\n"
    )
    _node_runtime.cache_clear()
    with patch("canvas_mcp.tools.code_execution.subprocess.run", return_value=completed):
        assert _node_runtime("/fake/node") is None
    _node_runtime.cache_clear()
    assert "Assertion failed: winsock init" in caplog.text
