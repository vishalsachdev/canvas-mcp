# Tool Result Contract Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Canvas MCP failures carry MCP error status and remove duplicate structured output from string-returning tools without changing their application-level payloads.

**Architecture:** Install one idempotent contract on each FastMCP server before tool registration. A middleware classifies established Canvas error returns and sets only `ToolResult.is_error`; a per-instance wrapper around FastMCP's public `tool` decorator disables inferred output schemas only for functions returning `str`.

**Tech Stack:** Python 3.13, FastMCP 3.4.4, MCP 1.28, pytest/pytest-asyncio, Ruff, mypy

**Spec:** `docs/superpowers/specs/2026-08-18-tool-result-contract-design.md`

## Global Constraints

- Keep the dependency range `fastmcp>=3.4.4,<4` unchanged.
- Preserve error and success content byte-for-byte; change only MCP error status and automatic string schemas.
- Mark errors only for a top-level dictionary `error`, an exact legacy `result` string wrapper following a text convention, a text prefix of `Error` or `❌`, or a JSON text block with a top-level `error`.
- Suppress an inferred output schema only when the resolved return annotation is exactly `str` and the registration did not explicitly set `output_schema`.
- Retain inferred schemas and structured content for dictionary-returning tools.
- Do not alter Canvas requests, retries, confirmation tokens, untrusted-content fencing, or tool wording.
- Keep all work local; do not push, create a pull request, or modify GitHub or Canvas.

---

### Task 1: Classify Existing Failure Results at the MCP Boundary

**Files:**
- Create: `src/canvas_mcp/core/tool_results.py`
- Create: `tests/core/test_tool_results.py`

**Interfaces:**
- Consumes: FastMCP `Middleware`, `MiddlewareContext`, `CallNext`, and `ToolResult`.
- Produces: `CanvasToolResultMiddleware` and `install_tool_result_contract(mcp: FastMCP) -> None`.

- [ ] **Step 1: Write failing middleware behavior tests**

Create `tests/core/test_tool_results.py` with a real in-process FastMCP client:

```python
import json
from typing import Any

import pytest
from fastmcp import Client, FastMCP
from mcp.types import ToolAnnotations


def _result_server() -> FastMCP:
    from canvas_mcp.core.tool_results import install_tool_result_contract

    mcp = FastMCP("tool-result-contract")
    install_tool_result_contract(mcp)

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
    async def text_result(value: str) -> str:
        return value

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
    async def dict_result(fail: bool) -> dict[str, Any]:
        if fail:
            return {"error": "boom", "nothing_sent": True}
        return {"success": True, "detail": {"error": "quoted example"}}

    return mcp


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        "Error: invalid course",
        "❌ Submission blocked",
        json.dumps({"error": "invalid course"}),
    ],
)
async def test_text_error_conventions_set_mcp_error_without_rewriting(payload):
    async with Client(_result_server()) as client:
        result = await client.call_tool(
            "text_result", {"value": payload}, raise_on_error=False
        )

    assert result.isError is True
    assert len(result.content) == 1
    assert getattr(result.content[0], "text", None) == payload


@pytest.mark.asyncio
async def test_top_level_dict_error_keeps_structured_payload_and_sets_mcp_error():
    async with Client(_result_server()) as client:
        result = await client.call_tool(
            "dict_result", {"fail": True}, raise_on_error=False
        )

    assert result.isError is True
    assert result.structuredContent == {"error": "boom", "nothing_sent": True}


@pytest.mark.asyncio
async def test_success_text_and_nested_error_field_remain_successful():
    async with Client(_result_server()) as client:
        text_result = await client.call_tool(
            "text_result", {"value": "No errors found"}, raise_on_error=False
        )
        dict_result = await client.call_tool(
            "dict_result", {"fail": False}, raise_on_error=False
        )

    assert text_result.isError is False
    assert dict_result.isError is False
```

- [ ] **Step 2: Run the focused tests and verify RED**

Run:

```bash
uv run python -m pytest tests/core/test_tool_results.py -q
```

Expected: FAIL because `canvas_mcp.core.tool_results` does not exist.

- [ ] **Step 3: Implement the result classifier and middleware**

Create `src/canvas_mcp/core/tool_results.py` with the classifier, middleware, and a middleware-only first version of the installer:

```python
"""Central MCP wire-result behavior for Canvas tools (issues 270 and 271)."""

import json

import mcp.types as mt
from fastmcp import FastMCP
from fastmcp.server.middleware import CallNext, Middleware, MiddlewareContext
from fastmcp.tools import ToolResult

_INSTALL_ATTR = "_canvas_tool_result_contract_installed"


def _text_is_error(text: str) -> bool:
    candidate = text.lstrip()
    if candidate.startswith(("Error", "❌")):
        return True
    try:
        parsed = json.loads(candidate)
    except (json.JSONDecodeError, TypeError):
        return False
    return isinstance(parsed, dict) and "error" in parsed


def _result_is_error(result: ToolResult) -> bool:
    structured = result.structured_content
    if isinstance(structured, dict):
        if "error" in structured:
            return True
        if set(structured) == {"result"}:
            wrapped = structured["result"]
            if isinstance(wrapped, str) and _text_is_error(wrapped):
                return True

    for block in result.content:
        if isinstance(block, mt.TextContent) and _text_is_error(block.text):
            return True
    return False


class CanvasToolResultMiddleware(Middleware):
    """Map established Canvas failure payloads to MCP isError."""

    async def on_call_tool(
        self,
        context: MiddlewareContext[mt.CallToolRequestParams],
        call_next: CallNext[mt.CallToolRequestParams, ToolResult],
    ) -> ToolResult:
        result = await call_next(context)
        if not result.is_error and _result_is_error(result):
            result.is_error = True
        return result


def install_tool_result_contract(mcp: FastMCP) -> None:
    """Install Canvas result behavior once on one FastMCP server."""
    if getattr(mcp, _INSTALL_ATTR, False):
        return
    mcp.add_middleware(CanvasToolResultMiddleware())
    setattr(mcp, _INSTALL_ATTR, True)
```

- [ ] **Step 4: Run the focused tests and verify GREEN**

Run:

```bash
uv run python -m pytest tests/core/test_tool_results.py -q
```

Expected: all Task 1 tests PASS.

- [ ] **Step 5: Run style and type checks for the new module**

Run:

```bash
uv run ruff check src/canvas_mcp/core/tool_results.py tests/core/test_tool_results.py
uv run mypy src/canvas_mcp/core/tool_results.py
```

Expected: both commands PASS.

- [ ] **Step 6: Commit the middleware behavior**

```bash
git add src/canvas_mcp/core/tool_results.py tests/core/test_tool_results.py
git commit -m "fix: mark Canvas tool failures as MCP errors (#270)"
```

---

### Task 2: Remove Duplicate Structured Output from String Tools

**Files:**
- Modify: `src/canvas_mcp/core/tool_results.py`
- Modify: `tests/core/test_tool_results.py`

**Interfaces:**
- Consumes: `install_tool_result_contract(mcp)` from Task 1 and FastMCP's public `tool` decorator.
- Produces: registration behavior that sets `output_schema=None` for inferred `str` returns while respecting explicit schemas.

- [ ] **Step 1: Add failing schema and duplication tests**

Add this explicit-schema fixture beside the imports and register the tool inside
`_result_server()` after `dict_result`:

```python
_EXPLICIT_TEXT_SCHEMA = {
    "type": "object",
    "properties": {"result": {"type": "string"}},
    "required": ["result"],
    "x-fastmcp-wrap-result": True,
}


    @mcp.tool(
        output_schema=_EXPLICIT_TEXT_SCHEMA,
        annotations=ToolAnnotations(readOnlyHint=True),
    )
    async def explicit_text(value: str) -> str:
        return value
```

Append these tests to `tests/core/test_tool_results.py`:

```python
@pytest.mark.asyncio
async def test_string_result_has_one_text_surface_and_no_structured_duplicate():
    async with Client(_result_server()) as client:
        tools = {tool.name: tool for tool in await client.list_tools()}
        result = await client.call_tool(
            "text_result", {"value": "single copy"}, raise_on_error=False
        )

    assert tools["text_result"].outputSchema is None
    assert result.structuredContent is None
    assert len(result.content) == 1
    assert getattr(result.content[0], "text", None) == "single copy"


@pytest.mark.asyncio
async def test_dictionary_tool_retains_schema_and_structured_content():
    async with Client(_result_server()) as client:
        tools = {tool.name: tool for tool in await client.list_tools()}
        result = await client.call_tool(
            "dict_result", {"fail": False}, raise_on_error=False
        )

    assert tools["dict_result"].outputSchema is not None
    assert result.structuredContent == {
        "success": True,
        "detail": {"error": "quoted example"},
    }


@pytest.mark.asyncio
async def test_installing_contract_twice_does_not_double_wrap_registration():
    from canvas_mcp.core.tool_results import install_tool_result_contract

    mcp = FastMCP("double-install")
    install_tool_result_contract(mcp)
    install_tool_result_contract(mcp)

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
    async def once() -> str:
        return "one"

    async with Client(mcp) as client:
        result = await client.call_tool("once", raise_on_error=False)

    assert result.structuredContent is None
    assert [getattr(block, "text", None) for block in result.content] == ["one"]


@pytest.mark.asyncio
async def test_explicit_string_schema_is_respected_and_legacy_wrapper_errors():
    async with Client(_result_server()) as client:
        tools = {tool.name: tool for tool in await client.list_tools()}
        result = await client.call_tool(
            "explicit_text",
            {"value": "Error: explicit schema failure"},
            raise_on_error=False,
        )

    assert tools["explicit_text"].outputSchema["x-fastmcp-wrap-result"] is True
    assert result.structuredContent == {"result": "Error: explicit schema failure"}
    assert result.isError is True
```

- [ ] **Step 2: Run the new tests and verify RED**

Run:

```bash
uv run python -m pytest tests/core/test_tool_results.py -q
```

Expected: FAIL because `text_result` and `once` still expose FastMCP's inferred `{result: string}` output schema and structured duplicate.

- [ ] **Step 3: Add the public-decorator registration wrapper**

Replace the standard-library import block in
`src/canvas_mcp/core/tool_results.py` with this ordered block:

```python
import inspect
import json
from collections.abc import Callable
from typing import Any, get_type_hints
```

Then add these helpers before `install_tool_result_contract`:

```python
def _returns_str(fn: Callable[..., Any]) -> bool:
    try:
        annotation = get_type_hints(fn).get("return", inspect.Signature.empty)
    except (NameError, TypeError):
        annotation = inspect.signature(fn).return_annotation
    return annotation is str


def _install_tool_decorator_wrapper(mcp: FastMCP) -> None:
    original_tool = mcp.tool

    def canvas_tool(name_or_fn: Any = None, **kwargs: Any) -> Any:
        if callable(name_or_fn):
            options = dict(kwargs)
            if "output_schema" not in options and _returns_str(name_or_fn):
                options["output_schema"] = None
            return original_tool(name_or_fn, **options)

        def register(fn: Callable[..., Any]) -> Any:
            options = dict(kwargs)
            if "output_schema" not in options and _returns_str(fn):
                options["output_schema"] = None
            decorator = original_tool(name_or_fn, **options)
            return decorator(fn)

        return register

    setattr(mcp, "tool", canvas_tool)
```

Update the installer so the wrapper is installed before the middleware and before the sentinel is set:

```python
def install_tool_result_contract(mcp: FastMCP) -> None:
    """Install Canvas result behavior once on one FastMCP server."""
    if getattr(mcp, _INSTALL_ATTR, False):
        return
    _install_tool_decorator_wrapper(mcp)
    mcp.add_middleware(CanvasToolResultMiddleware())
    setattr(mcp, _INSTALL_ATTR, True)
```

- [ ] **Step 4: Run the focused tests and verify GREEN**

Run:

```bash
uv run python -m pytest tests/core/test_tool_results.py -q
```

Expected: all Task 1 and Task 2 tests PASS.

- [ ] **Step 5: Run style and type checks**

Run:

```bash
uv run ruff check src/canvas_mcp/core/tool_results.py tests/core/test_tool_results.py
uv run mypy src/canvas_mcp/core/tool_results.py
```

Expected: both commands PASS.

- [ ] **Step 6: Commit string schema handling**

```bash
git add src/canvas_mcp/core/tool_results.py tests/core/test_tool_results.py
git commit -m "fix: emit string tool results once (#271)"
```

---

### Task 3: Install the Contract on Every Canvas MCP Role Profile

**Files:**
- Modify: `src/canvas_mcp/server.py:423-470`
- Modify: `tests/core/test_tool_results.py`

**Interfaces:**
- Consumes: `install_tool_result_contract(mcp)` from Tasks 1-2.
- Produces: identical response behavior for every server built through `register_all_tools(mcp, role)`.

- [ ] **Step 1: Add failing full-server integration tests**

Append these tests to `tests/core/test_tool_results.py`:

```python
@pytest.mark.asyncio
async def test_register_all_tools_marks_existing_validation_failure_as_mcp_error():
    from canvas_mcp.server import register_all_tools

    mcp = FastMCP("full-contract")
    register_all_tools(mcp, role="all")

    async with Client(mcp) as client:
        result = await client.call_tool(
            "get_syllabus",
            {
                "course_identifier": 60366,
                "output_format": "text",
                "max_chars": 0,
            },
            raise_on_error=False,
        )

    assert result.isError is True
    assert getattr(result.content[0], "text", "").startswith("Error: max_chars")


@pytest.mark.asyncio
async def test_full_registry_suppresses_only_string_output_schemas():
    from canvas_mcp.server import register_all_tools

    mcp = FastMCP("full-schema-contract")
    register_all_tools(mcp, role="all")
    tools = {tool.name: tool for tool in await mcp.list_tools(run_middleware=False)}

    string_tools = [tool for tool in tools.values() if tool.return_type is str]
    assert string_tools
    assert all(tool.output_schema is None for tool in string_tools)
    assert tools["list_conversations"].output_schema is not None
```

- [ ] **Step 2: Run the integration tests and verify RED**

Run:

```bash
uv run python -m pytest \
  tests/core/test_tool_results.py::test_register_all_tools_marks_existing_validation_failure_as_mcp_error \
  tests/core/test_tool_results.py::test_full_registry_suppresses_only_string_output_schemas \
  -q
```

Expected: FAIL because `register_all_tools()` has not installed the contract.

- [ ] **Step 3: Install the contract before any tool registration**

Add this import near the other core imports in `src/canvas_mcp/server.py`:

```python
from .core.tool_results import install_tool_result_contract
```

Add this call immediately after the registration log line in `register_all_tools()` and before `register_course_tools(mcp)`:

```python
    install_tool_result_contract(mcp)
```

- [ ] **Step 4: Run all focused result-contract tests and verify GREEN**

Run:

```bash
uv run python -m pytest tests/core/test_tool_results.py -q
```

Expected: all result-contract tests PASS.

- [ ] **Step 5: Run compatibility and metadata regressions**

Run:

```bash
uv run python -m pytest tests/test_fastmcp_compat.py tests/test_tool_metadata.py -q
```

Expected: all tests PASS; dictionary schemas and tool metadata remain available.

- [ ] **Step 6: Commit server installation**

```bash
git add src/canvas_mcp/server.py tests/core/test_tool_results.py
git commit -m "fix: apply tool result contract to every profile (#270 #271)"
```

---

### Task 4: Document and Verify the Wire-Level Changes

**Files:**
- Modify: `CHANGELOG.md:8`

**Interfaces:**
- Consumes: the completed result contract from Tasks 1-3.
- Produces: release-facing documentation and final verification evidence.

- [ ] **Step 1: Add an Unreleased changelog entry**

Under `## [Unreleased]`, add:

```markdown
### Fixed

- Tool failures now set MCP `isError: true` while preserving their existing
  text or structured payload ([issue 270](https://github.com/vishalsachdev/canvas-mcp/issues/270)).
- String-returning tools no longer duplicate the same value in text content
  and `structuredContent.result`; dictionary tools retain their structured
  schemas ([issue 271](https://github.com/vishalsachdev/canvas-mcp/issues/271)).
```

- [ ] **Step 2: Run the complete test suite**

Run:

```bash
uv run python -m pytest tests/ -q
```

Expected: all tests PASS with only the two warnings already present on the clean `origin/main` baseline.

- [ ] **Step 3: Run repository-wide style and source type checks**

Run:

```bash
uv run ruff check .
uv run mypy src
git diff --check
```

Expected: all commands PASS.

- [ ] **Step 4: Inspect the final branch state**

Run:

```bash
git status --short
git log --oneline origin/main..HEAD
git diff --stat origin/main...HEAD
```

Expected: only the planned source, test, changelog, spec, and plan files differ; the branch contains no unrelated or generated changes.

- [ ] **Step 5: Commit the changelog**

```bash
git add CHANGELOG.md
git commit -m "docs: record tool result fixes (#270 #271)"
```
