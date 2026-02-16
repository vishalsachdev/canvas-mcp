"""Code execution tools for running TypeScript in Node.js environment."""

import asyncio
import hashlib
import json
import os
import re
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from mcp.server.fastmcp import FastMCP

from ..core.config import get_config
from ..core.logging import log_warning
from ..core.validation import validate_params


def _validate_container_image(image: str) -> bool:
    """Validate container image name format to prevent command injection.

    Args:
        image: Container image name (e.g., "node:20-alpine", "registry.io/org/image:tag")

    Returns:
        True if the image name is valid, False otherwise
    """
    if not image:
        return False
    # Allow alphanumeric, dots, hyphens, underscores, slashes, and colons
    # Must have at least one colon for tag
    pattern = r'^[a-zA-Z0-9._/-]+:[a-zA-Z0-9._-]+$'
    return bool(re.match(pattern, image))


def _normalize_host(value: str) -> str:
    if not value:
        return ""
    raw = value.strip()
    if not raw:
        return ""
    if "://" in raw:
        parsed = urlparse(raw)
        host = parsed.hostname or ""
    else:
        host = raw.split("/")[0]
        host = host.split(":")[0]
    return host.lower()


def _parse_allowlist_hosts(raw_hosts: str) -> list[str]:
    if not raw_hosts:
        return []
    hosts: list[str] = []
    for token in raw_hosts.replace(",", " ").split():
        host = _normalize_host(token)
        if host:
            hosts.append(host)
    return hosts


def _append_node_options(existing: str | None, extra_args: list[str]) -> str:
    parts = []
    if existing:
        parts.append(existing.strip())
    parts.extend(extra_args)
    return " ".join(part for part in parts if part).strip()


def _write_network_guard(allowlist_hosts: list[str], directory: Path) -> Path:
    guard_contents = f"""\
const net = require('net');
const tls = require('tls');
const http = require('http');
const https = require('https');
const {{ URL }} = require('url');

const ALLOWLIST = new Set({json.dumps(sorted(set(allowlist_hosts)))});

function normalizeHost(value) {{
  if (!value) return '';
  if (typeof value !== 'string') return '';
  let host = value;
  if (value.includes('://')) {{
    try {{
      host = new URL(value).hostname || '';
    }} catch (_) {{
      host = value;
    }}
  }}
  host = host.split('/')[0].split(':')[0].toLowerCase();
  return host;
}}

function isAllowed(host) {{
  if (!host) return true;
  const normalized = normalizeHost(host);
  if (!normalized) return true;
  return ALLOWLIST.has(normalized);
}}

function enforce(host) {{
  if (!isAllowed(host)) {{
    const err = new Error(`Outbound network blocked by sandbox policy (host: ${{host}})`);
    err.code = 'SANDBOX_NETWORK_BLOCKED';
    throw err;
  }}
}}

function getHostFromArgs(args) {{
  if (!args || args.length === 0) return '';
  const first = args[0];
  if (typeof first === 'string') return first;
  if (first && typeof first === 'object') {{
    return first.host || first.hostname || '';
  }}
  if (typeof args[1] === 'string') return args[1];
  return '';
}}

const originalNetConnect = net.connect;
net.connect = function (...args) {{
  const host = getHostFromArgs(args);
  enforce(host);
  return originalNetConnect.apply(this, args);
}};

const originalTlsConnect = tls.connect;
tls.connect = function (...args) {{
  const host = getHostFromArgs(args);
  enforce(host);
  return originalTlsConnect.apply(this, args);
}};

const originalHttpRequest = http.request;
http.request = function (...args) {{
  const host = getHostFromArgs(args);
  enforce(host);
  return originalHttpRequest.apply(this, args);
}};

const originalHttpsRequest = https.request;
https.request = function (...args) {{
  const host = getHostFromArgs(args);
  enforce(host);
  return originalHttpsRequest.apply(this, args);
}};
"""
    guard_file = tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".cjs",
        dir=directory,
        delete=False
    )
    guard_file.write(guard_contents)
    guard_file.flush()
    guard_file.close()
    guard_path = Path(guard_file.name)

    # Set restrictive permissions (owner read/write only) for security
    os.chmod(guard_path, 0o600)

    return guard_path


def _detect_container_runtime() -> str | None:
    for runtime in ("docker", "podman"):
        if shutil.which(runtime):
            return runtime
    return None


async def _runtime_available(runtime: str) -> bool:
    try:
        process = await asyncio.create_subprocess_exec(
            runtime,
            "version",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
    except FileNotFoundError:
        return False

    try:
        await asyncio.wait_for(process.communicate(), timeout=2)
    except asyncio.TimeoutError:
        process.kill()
        await process.wait()
        return False

    return process.returncode == 0


def register_code_execution_tools(mcp: FastMCP) -> None:
    """Register code execution MCP tools."""

    @mcp.tool()
    @validate_params
    async def execute_typescript(
        code: str,
        timeout: int = 120
    ) -> str:
        """Execute TypeScript code in a Node.js environment with access to Canvas API.

        This tool enables token-efficient bulk operations by executing code locally
        rather than loading all data into Claude's context. The code runs in a
        sandboxed Node.js environment with access to:
        - Canvas API credentials from environment
        - All TypeScript modules in src/canvas_mcp/code_api/
        - Standard Node.js modules

        IMPORTANT: This achieves 99.7% token savings for bulk operations!

        Args:
            code: TypeScript code to execute. Can import from './canvas/*' modules.
            timeout: Maximum execution time in seconds (default: 120)

        Example Usage - Bulk Grading:
            ```typescript
            import { bulkGrade } from './canvas/grading/bulkGrade.js';

            await bulkGrade({
              courseIdentifier: "60366",
              assignmentId: "123",
              gradingFunction: (submission) => {
                // This runs locally - no token cost!
                const notebook = submission.attachments?.find(
                  f => f.filename.endsWith('.ipynb')
                );

                if (!notebook) return null;

                // Your grading logic here
                return {
                  points: 100,
                  rubricAssessment: { "_8027": { points: 100 } },
                  comment: "Great work!"
                };
              }
            });
            ```

        Returns:
            Combined stdout and stderr from the execution, or error message if failed.

        Security (best-effort unless container sandboxing is available):
            - Code runs in a temporary file that is deleted after execution
            - Optional network allowlist guard for outbound requests
            - Optional resource limits (timeout, memory, CPU seconds)
        """
        config = get_config()
        warnings: list[str] = []

        sandbox_enabled = config.enable_ts_sandbox
        sandbox_mode_setting = config.ts_sandbox_mode
        if sandbox_mode_setting not in {"auto", "local", "container"}:
            sandbox_mode_setting = "auto"

        block_outbound = config.ts_sandbox_block_outbound_network
        allowlist_hosts = _parse_allowlist_hosts(config.ts_sandbox_allowlist_hosts)
        canvas_host = _normalize_host(config.canvas_api_url)
        if sandbox_enabled and block_outbound and canvas_host:
            if canvas_host not in allowlist_hosts:
                allowlist_hosts.append(canvas_host)
        allowlist_hosts = sorted(set(allowlist_hosts))

        # Get the absolute path to the code_api directory
        code_api_dir = Path(__file__).parent.parent / "code_api"
        repo_root = Path(__file__).parent.parent.parent.parent

        guard_path: Path | None = None
        guard_container_path: str | None = None
        node_options_local: str | None = None
        node_options_container: str | None = None
        sandbox_mode = "disabled"
        container_runtime: str | None = None

        if sandbox_enabled:
            if block_outbound and not allowlist_hosts:
                warnings.append(
                    "Outbound network guard enabled with an empty allowlist; "
                    "requests may fail unless hosts are explicitly allowed."
                )
                log_warning("Sandbox allowlist is empty; outbound requests may fail.")

            if sandbox_mode_setting in {"auto", "container"}:
                # Validate container image format before attempting to use it
                if not _validate_container_image(config.ts_sandbox_container_image):
                    message = (
                        f"Invalid container image format: '{config.ts_sandbox_container_image}'. "
                        "Expected format: 'name:tag' (e.g., 'node:20-alpine'). "
                        "Falling back to local sandbox."
                    )
                    warnings.append(message)
                    log_warning(message)
                    sandbox_mode = "local"
                else:
                    container_runtime = _detect_container_runtime()
                    if container_runtime and await _runtime_available(container_runtime):
                        sandbox_mode = "container"
                    elif sandbox_mode_setting == "container":
                        message = (
                            "Container sandbox requested but no runtime is available; "
                            "falling back to local best-effort sandbox."
                        )
                        warnings.append(message)
                        log_warning(message)
                        sandbox_mode = "local"
                    else:
                        sandbox_mode = "local"
            else:
                sandbox_mode = "local"

            if block_outbound:
                guard_path = _write_network_guard(allowlist_hosts, code_api_dir)
                if guard_path.is_relative_to(repo_root):
                    relative_guard = guard_path.relative_to(repo_root)
                    guard_container_path = f"/workspace/{relative_guard.as_posix()}"
                else:
                    guard_container_path = None

            extra_node_options = []
            if config.ts_sandbox_memory_limit_mb > 0:
                extra_node_options.append(
                    f"--max-old-space-size={config.ts_sandbox_memory_limit_mb}"
                )
            if guard_path:
                extra_node_options.append(f"--require={guard_path}")
            node_options_local = _append_node_options(
                os.environ.get("NODE_OPTIONS"),
                extra_node_options
            )

            if guard_container_path:
                container_extra_options = []
                if config.ts_sandbox_memory_limit_mb > 0:
                    container_extra_options.append(
                        f"--max-old-space-size={config.ts_sandbox_memory_limit_mb}"
                    )
                container_extra_options.append(f"--require={guard_container_path}")
                node_options_container = _append_node_options(
                    os.environ.get("NODE_OPTIONS"),
                    container_extra_options
                )
            else:
                node_options_container = node_options_local

        # Create a temporary file for the code
        temp_file_path: str | None = None
        with tempfile.NamedTemporaryFile(
            mode='w',
            suffix='.ts',
            dir=code_api_dir,
            delete=False
        ) as temp_file:
            # Write the user's code
            temp_file.write(code)
            temp_file_path = temp_file.name

        try:
            # Compute code hash for audit logging (never log raw code)
            code_hash = hashlib.sha256(code.encode()).hexdigest()[:16]
            exec_start = time.monotonic()

            # Prepare environment variables
            env = os.environ.copy()
            env['CANVAS_API_URL'] = config.canvas_api_url
            env['CANVAS_API_TOKEN'] = config.canvas_api_token
            if node_options_local:
                env["NODE_OPTIONS"] = node_options_local

            effective_timeout = timeout
            if sandbox_enabled and config.ts_sandbox_timeout_sec > 0:
                effective_timeout = min(timeout, config.ts_sandbox_timeout_sec)
                if effective_timeout != timeout:
                    message = (
                        f"Timeout reduced to {effective_timeout} seconds by TS_SANDBOX_TIMEOUT_SEC."
                    )
                    warnings.append(message)
                    log_warning(message)

            # Execute using tsx (faster than ts-node) or ts-node as fallback
            # tsx is a fast TypeScript execution engine that doesn't require compilation
            if sandbox_mode == "container" and container_runtime and temp_file_path:
                relative_path = Path(temp_file_path).relative_to(repo_root)
                container_code_path = f"/workspace/{relative_path.as_posix()}"

                cmd = [
                    container_runtime,
                    "run",
                    "--rm",
                    "-i",
                ]
                if config.ts_sandbox_memory_limit_mb > 0:
                    cmd.extend(["--memory", f"{config.ts_sandbox_memory_limit_mb}m"])
                if config.ts_sandbox_cpu_limit > 0:
                    cmd.extend(["--ulimit", f"cpu={config.ts_sandbox_cpu_limit}"])

                cmd.extend([
                    "-v",
                    f"{repo_root}:/workspace",
                    "-w",
                    "/workspace",
                    "-e",
                    f"CANVAS_API_URL={config.canvas_api_url}",
                    "-e",
                    f"CANVAS_API_TOKEN={config.canvas_api_token}",
                ])
                if node_options_container:
                    cmd.extend(["-e", f"NODE_OPTIONS={node_options_container}"])

                cmd.extend([
                    config.ts_sandbox_container_image,
                    "npx",
                    "tsx",
                    container_code_path
                ])
            else:
                cmd = [
                    'npx',
                    'tsx',  # Try tsx first
                    temp_file_path
                ]

            # Run the TypeScript code
            preexec_fn = None
            if sandbox_enabled and config.ts_sandbox_cpu_limit > 0 and sandbox_mode == "local":
                try:
                    import resource

                    def _limit_resources() -> None:
                        resource.setrlimit(
                            resource.RLIMIT_CPU,
                            (config.ts_sandbox_cpu_limit, config.ts_sandbox_cpu_limit)
                        )

                    preexec_fn = _limit_resources
                except Exception:
                    message = (
                        "CPU limits could not be applied on this platform."
                    )
                    warnings.append(message)
                    log_warning(message)
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
                cwd=str(repo_root),
                preexec_fn=preexec_fn
            )

            try:
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    process.communicate(),
                    timeout=effective_timeout
                )

                stdout = stdout_bytes.decode('utf-8', errors='replace')
                stderr = stderr_bytes.decode('utf-8', errors='replace')

                # Format output
                result_lines = []

                if process.returncode == 0:
                    result_lines.append("✅ TypeScript execution completed successfully\n")
                else:
                    result_lines.append(f"❌ TypeScript execution failed with exit code {process.returncode}\n")

                if sandbox_enabled:
                    result_lines.append("=== Sandbox ===")
                    result_lines.append(f"Mode: {sandbox_mode}")
                    if block_outbound:
                        allowlist_label = ", ".join(allowlist_hosts) if allowlist_hosts else "none"
                        result_lines.append(f"Network allowlist: {allowlist_label}")
                    if config.ts_sandbox_memory_limit_mb > 0:
                        result_lines.append(
                            f"Memory limit: {config.ts_sandbox_memory_limit_mb} MB"
                        )
                    if config.ts_sandbox_cpu_limit > 0:
                        result_lines.append(
                            f"CPU limit: {config.ts_sandbox_cpu_limit} sec"
                        )
                    if warnings:
                        result_lines.append("Sandbox warnings:")
                        result_lines.extend(f"- {warning}" for warning in warnings)

                if stdout:
                    result_lines.append("=== Output ===")
                    result_lines.append(stdout)

                if stderr:
                    result_lines.append("=== Errors/Warnings ===")
                    result_lines.append(stderr)

                # Audit: log successful/failed execution
                from ..core.audit import log_code_execution
                duration = time.monotonic() - exec_start
                exec_status = "success" if process.returncode == 0 else "error"
                log_code_execution(
                    code_hash, sandbox_mode, exec_status, duration,
                    error=stderr[:200] if process.returncode != 0 and stderr else None,
                )

                return "\n".join(result_lines) if result_lines else "No output"

            except asyncio.TimeoutError:
                process.kill()
                await process.wait()

                # Audit: log timeout
                from ..core.audit import log_code_execution
                duration = time.monotonic() - exec_start
                log_code_execution(
                    code_hash, sandbox_mode, "timeout", duration,
                )

                return f"❌ Execution timed out after {effective_timeout} seconds"

        except FileNotFoundError as e:
            return (
                "❌ TypeScript execution environment not found.\n\n"
                "Please ensure Node.js and npx are installed:\n"
                "  npm install -g tsx\n\n"
                f"Error: {str(e)}"
            )
        except Exception as e:
            return f"❌ Execution error: {str(e)}"
        finally:
            # Clean up the temporary file
            try:
                if temp_file_path:
                    os.unlink(temp_file_path)
            except Exception:
                pass  # Ignore cleanup errors
            try:
                if guard_path:
                    os.unlink(guard_path)
            except Exception:
                pass  # Ignore cleanup errors

    @mcp.tool()
    @validate_params
    async def list_code_api_modules() -> str:
        """List all available TypeScript modules in the code execution API.

        Returns a formatted list of all TypeScript files that can be imported
        in the execute_typescript tool, organized by category with descriptions.

        This helps Claude discover what operations are available for token-efficient
        bulk processing.

        Returns:
            Formatted string listing all available modules by category with descriptions.
        """
        code_api_dir = Path(__file__).parent.parent / "code_api"

        if not code_api_dir.exists():
            return "❌ Code API directory not found"

        # Module descriptions mapping
        module_descriptions = {
            "bulkGrade": "Grade multiple submissions with local processing function - most token-efficient method",
            "gradeWithRubric": "Grade a single submission with rubric criteria and optional comments",
            "bulkGradeDiscussion": "Grade discussion posts in bulk with local processing function",
            "listSubmissions": "Retrieve all submissions for an assignment (supports includeUser for names/emails)",
            "listCourses": "List all courses accessible to the current user",
            "getCourseDetails": "Get detailed information about a specific course",
            "sendMessage": "Send a message/announcement to course participants",
            "listDiscussions": "List discussion topics in a course",
            "postEntry": "Post an entry to a discussion topic",
        }

        # Organize modules by directory
        modules_by_category: dict[str, list[tuple[str, str]]] = {}

        for ts_file in code_api_dir.rglob("*.ts"):
            # Skip certain files
            if ts_file.name in ['index.ts', 'client.ts']:
                continue

            # Get relative path from code_api
            rel_path = ts_file.relative_to(code_api_dir)

            # Get category (parent directory name)
            category = rel_path.parent.name if rel_path.parent.name != '.' else 'root'

            # Get import path (convert .ts to .js for ESM imports)
            import_path = f"./{rel_path.parent}/{rel_path.stem}.js"

            # Get description from mapping
            module_name = rel_path.stem
            description = module_descriptions.get(module_name, "")

            if category not in modules_by_category:
                modules_by_category[category] = []

            modules_by_category[category].append((import_path, description))

        # Format output
        result_lines = []
        result_lines.append("Available TypeScript Modules for Code Execution")
        result_lines.append("=" * 60)
        result_lines.append("")
        result_lines.append("Import these in execute_typescript tool:")
        result_lines.append("")

        for category, modules in sorted(modules_by_category.items()):
            result_lines.append(f"📁 {category.upper()}")
            result_lines.append("-" * 40)
            for import_path, description in sorted(modules, key=lambda x: x[0]):
                result_lines.append(f"  {import_path}")
                if description:
                    result_lines.append(f"    • {description}")
            result_lines.append("")

        result_lines.append("Example Usage:")
        result_lines.append("```typescript")
        result_lines.append("import { bulkGrade } from './canvas/grading/bulkGrade.js';")
        result_lines.append("import { listSubmissions } from './canvas/assignments/listSubmissions.js';")
        result_lines.append("")
        result_lines.append("// Your code here...")
        result_lines.append("```")

        return "\n".join(result_lines)
