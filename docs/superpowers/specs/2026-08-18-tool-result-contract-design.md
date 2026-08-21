# Tool Result Contract Design

## Context

Canvas MCP tools currently return two broad shapes: human-readable strings and
structured dictionaries. Tool functions represent expected failures with
established return conventions rather than exceptions:

- a dictionary whose top-level key is `error`;
- a string beginning with `Error`;
- a string beginning with `❌`; or
- a JSON-encoded string whose top-level object contains `error`.

FastMCP 3.4.4 serializes those ordinary return values as successful MCP tool
results. Clients therefore receive `isError: false` even though the payload
clearly represents a failed tool call (issue 270).

FastMCP also infers an output schema for a function annotated `-> str`. It wraps
the returned string in `structuredContent.result` while also emitting the same
value as text content. Clients that render both surfaces show every string
twice (issue 271).

## Goals

1. Set MCP `isError: true` for every existing Canvas MCP failure convention.
2. Preserve the exact error payload and text so current clients and tests keep
   their useful detail.
3. Emit string-returning tool results once, as text content only.
4. Retain structured output schemas and `structuredContent` for dictionary
   tools.
5. Apply the contract centrally so new and existing tools do not need local
   response rewrites.

## Non-goals

- Do not convert existing return values to exceptions.
- Do not rewrite error wording, remove fields, or standardize every tool onto a
  new application-level result model.
- Do not suppress structured output for dictionary-returning tools.
- Do not classify arbitrary substrings such as a report that mentions the word
  "error" as a failed tool call.
- Do not change Canvas request, retry, confirmation-token, or fencing behavior.

## Architecture

Create `src/canvas_mcp/core/tool_results.py` with one public installer,
`install_tool_result_contract(mcp: FastMCP) -> None`.

`register_all_tools()` calls the installer before any tool registration. The
installer performs two independent jobs and is idempotent for a given FastMCP
instance.

### Registration-time string schema handling

The installer wraps that server instance's public `mcp.tool` registration
method. When a decorated function's resolved return annotation is exactly
`str`, and the caller did not explicitly provide `output_schema`, the wrapper
passes `output_schema=None` to FastMCP. Every other registration argument and
decorator behavior is forwarded unchanged.

This prevents FastMCP from creating the synthetic `{ "result": ... }` schema
for string tools. Their wire result consequently contains the text content
once and has no `structuredContent`. Dictionary-returning tools continue
through FastMCP's normal inference and keep their schemas.

The wrapper must support the decorator form used throughout this repository,
including an optional explicit tool name. An explicit future `output_schema`
always wins; the contract only changes FastMCP's automatic inference.

This approach uses FastMCP's public registration API and the repository's
pinned `fastmcp>=3.4.4,<4` range. It does not mutate the provider's private
component dictionary after registration.

### Result middleware

The installer adds one FastMCP middleware whose `on_call_tool` method awaits
the next handler and receives a `ToolResult`. If the result is already marked
as an error, it is returned unchanged. Otherwise the middleware marks it as an
error when any one of these exact conditions holds:

1. `structured_content` is a dictionary with a top-level `error` key;
2. `structured_content` is the legacy string wrapper
   `{ "result": <string> }` and that string follows a text error convention;
3. a text content block, after trimming leading whitespace only for
   classification, begins with `Error` or `❌`; or
4. a text content block is valid JSON whose top-level value is an object with
   an `error` key.

Classification never changes `content`, `structured_content`, or metadata. It
sets only `ToolResult.is_error = True`, which FastMCP maps to MCP
`CallToolResult.isError`.

The JSON check parses only a complete text block and accepts only a top-level
object. Nested `error` fields and ordinary prose containing the word do not
count. Invalid JSON remains ordinary text. A successful value such as
`"No errors found"` remains successful because it matches neither prefix nor
structured convention.

## Installation and lifecycle

`register_all_tools(mcp, role)` installs the contract before registering shared,
student, educator, or feature-gated tools. This guarantees the same result
behavior for every role profile and for tests that build a server by calling
`register_all_tools()` directly.

The installer records a private sentinel on the FastMCP instance. Repeated
calls do not wrap `mcp.tool` again or add duplicate middleware. Individual unit
tests that register one tool group directly are outside the server lifecycle;
they continue to test the raw Python functions, while contract tests exercise
real MCP calls through a configured FastMCP client.

## Compatibility

Application-level tool return values do not change. A caller reading only text
sees the same string. A caller reading dictionary `structuredContent` sees the
same dictionary. The intentional wire changes are:

- failures now carry `isError: true`; and
- string tools no longer duplicate their value in
  `structuredContent.result`.

This is compatible with MCP clients that inspect only content while fixing
clients that honor error status or render both content surfaces.

## Testing

Add focused tests using an in-process FastMCP `Client`, not mocks of FastMCP:

1. a successful string appears in one text content block, has no structured
   content, and is not an error;
2. an `Error...` string is unchanged and marked as an error;
3. a `❌...` string is unchanged and marked as an error;
4. a JSON-encoded top-level `error` string is marked as an error;
5. a dictionary with a top-level `error` key keeps its structured fields and is
   marked as an error;
6. a successful dictionary keeps its inferred output schema and structured
   content;
7. prose containing "error" away from the prefix remains successful;
8. installing the contract twice neither duplicates output nor middleware;
9. the full live registry has `output_schema=None` for every function whose
   return type is `str`, while at least one dictionary tool retains a schema;
10. one existing Canvas tool failure is exercised through the real MCP call
    boundary to prove the central installation is active.

Run the focused tests first, then the repository's full pytest suite, Ruff, and
mypy against `src`.

## Failure handling

If FastMCP changes its public registration or middleware contracts within the
allowed dependency range, focused compatibility tests must fail. The installer
must not silently skip schema suppression or error classification. No fallback
will mutate registered provider internals.
