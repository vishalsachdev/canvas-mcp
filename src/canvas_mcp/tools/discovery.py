"""
Tool discovery for Canvas MCP.
Allows Claude to search and explore both the registered MCP tools
(the ~99 Python tools exposed via @mcp.tool()) and the TypeScript
code-execution API modules used by execute_typescript().
"""

import json
import logging
import re
from pathlib import Path
from typing import Any, Literal

from fastmcp import FastMCP
from mcp.types import ToolAnnotations

from ..core.validation import validate_params

DetailLevel = Literal["names", "signatures", "full"]

# Bumped from the unversioned (schema_version-less) shape to 2 when the
# response gained mcp_tools/code_execution_api sections and the top-level
# "tools" key was removed (issue #281). Scripted consumers should branch on
# this field rather than assume the old flat {query, detail_level, count,
# tools: [...]} shape.
_SCHEMA_VERSION = 2

# Cap on how much of an MCP tool's description is echoed back at
# detail_level="full", so a query that matches many tools can't blow up
# the response size with full multi-paragraph docstrings.
_MCP_FULL_DESCRIPTION_CHARS = 400

# Same idea for "signatures" mode: a tool's first docstring line is usually
# short, but nothing enforces that — cap it so one verbose tool can't
# dominate the response.
_MCP_SIGNATURE_DESCRIPTION_CHARS = 200

# Full TypeScript modules can be tens of thousands of characters. Bound each
# match so discovery cannot consume the model context with source dumps.
_CODE_API_FULL_CONTENT_CHARS = 2000
_TRUNCATION_SENTINEL = "... [truncated]"


def _cap(text: str, max_len: int) -> str:
    """Truncate text to at most max_len characters total, sentinel included."""
    if len(text) <= max_len:
        return text
    keep = max(max_len - len(_TRUNCATION_SENTINEL), 0)
    return text[:keep] + _TRUNCATION_SENTINEL


async def _search_mcp_tools(
    mcp: FastMCP, query_lower: str, detail_level: DetailLevel
) -> tuple[list[str | dict[str, Any]], int]:
    """Search the live registry of registered MCP tools by name/description.

    Queried at call time (not registration time) so results reflect
    whichever tools are actually registered for this process — feature
    flags like EXECUTE_TYPESCRIPT_ENABLED or STUDENT_WRITE_TOOLS change
    the live tool set. Skips FastMCP's middleware chain (run_middleware=False)
    since this is a metadata listing, not a tool invocation — re-running
    ~99 tools' middleware on every search call would be pure overhead.
    """
    tools = await mcp.list_tools(run_middleware=False)

    matches: list[str | dict[str, Any]] = []
    for tool in tools:
        name = tool.name
        description = tool.description or ""
        if query_lower and query_lower not in name.lower() and query_lower not in description.lower():
            continue

        if detail_level == "names":
            matches.append(name)
        else:
            first_line = description.strip().splitlines()[0] if description.strip() else ""
            first_line = _cap(first_line, _MCP_SIGNATURE_DESCRIPTION_CHARS)
            entry: dict[str, Any] = {"name": name, "description": first_line}
            if detail_level == "full" and description.strip():
                entry["description"] = _cap(description.strip(), _MCP_FULL_DESCRIPTION_CHARS)
            matches.append(entry)

    return matches, len(tools)


def register_discovery_tools(mcp: FastMCP) -> None:
    """Register tool discovery tools."""

    @mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
    @validate_params
    async def search_canvas_tools(
        query: str = "",
        detail_level: DetailLevel = "signatures"
    ) -> str:
        """
        Search available Canvas tools by keyword — both the registered MCP
        tools (e.g. list_peer_reviews, create_assignment) and the TypeScript
        code-execution API used by execute_typescript().

        Args:
            query: Search term to filter tools (empty = all)
            detail_level: "names" (names/paths only), "signatures" (recommended), or "full" (fuller descriptions/file contents)
        """
        try:
            query_lower = query.lower()

            mcp_matches, mcp_tool_count = await _search_mcp_tools(mcp, query_lower, detail_level)

            # Get code API directory
            code_api_path = Path(__file__).parent.parent / "code_api" / "canvas"

            code_api_matches: list[str | dict[str, Any]] = []
            code_api_note: str | None = None

            if not code_api_path.exists():
                code_api_note = "Code API directory not found — the code execution API may not be set up yet"
            else:
                for ts_file in code_api_path.rglob("*.ts"):
                    # Skip index files and utilities unless specifically searched
                    if ts_file.name == "index.ts" and query and "index" not in query_lower:
                        continue

                    # Check if query matches filename or path
                    file_match = (
                        not query or
                        query_lower in ts_file.stem.lower() or
                        query_lower in str(ts_file.relative_to(code_api_path)).lower()
                    )

                    if not file_match:
                        # Also check file contents for query
                        try:
                            content = ts_file.read_text(encoding="utf-8")
                            if query_lower not in content.lower():
                                continue
                        except Exception as e:
                            logging.debug("Skipping file %s: %s", ts_file, e)
                            continue

                    relative_path = str(ts_file.relative_to(code_api_path))

                    if detail_level == "names":
                        code_api_matches.append(relative_path)

                    elif detail_level == "signatures":
                        # Extract function signature from file
                        try:
                            content = ts_file.read_text(encoding="utf-8")
                            signature = extract_function_signature(content)
                            doc_comment = extract_doc_comment(content)

                            code_api_matches.append({
                                "file": relative_path,
                                "signature": signature,
                                "description": doc_comment[:200] if doc_comment else None
                            })
                        except Exception as e:
                            code_api_matches.append({
                                "file": relative_path,
                                "error": f"Could not parse signature: {str(e)}"
                            })

                    else:  # full
                        try:
                            content = ts_file.read_text(encoding="utf-8")
                            code_api_matches.append({
                                "file": relative_path,
                                "content": _cap(content, _CODE_API_FULL_CONTENT_CHARS)
                            })
                        except Exception as e:
                            code_api_matches.append({
                                "file": relative_path,
                                "error": f"Could not read file: {str(e)}"
                            })

            total_count = len(mcp_matches) + len(code_api_matches)

            if total_count == 0:
                return json.dumps({
                    "schema_version": _SCHEMA_VERSION,
                    "message": f"No tools found matching '{query}'",
                    "suggestion": "Try a different search term or use empty string to see all tools",
                    "mcp_tools_searched": mcp_tool_count,
                }, indent=2)

            result: dict[str, Any] = {
                "schema_version": _SCHEMA_VERSION,
                "query": query,
                "detail_level": detail_level,
                "count": total_count,
                "mcp_tools": {
                    "description": "Registered MCP tools (Python, called directly — e.g. list_peer_reviews, create_assignment)",
                    "count": len(mcp_matches),
                    "tools": mcp_matches,
                },
                "code_execution_api": {
                    "description": "TypeScript modules usable from execute_typescript() for bulk operations",
                    "count": len(code_api_matches),
                    "tools": code_api_matches,
                },
            }
            if code_api_note:
                result["code_execution_api"]["note"] = code_api_note

            return json.dumps(result, indent=2)

        except Exception as e:
            return json.dumps({
                "error": str(e),
                "type": type(e).__name__
            }, indent=2)


def extract_function_signature(content: str) -> str:
    """Extract main exported function signature from TypeScript file"""
    # Look for: export async function functionName(args): Promise<Type>
    pattern = r'export\s+async\s+function\s+(\w+)\s*\([^)]*\)\s*:\s*Promise<[^>]+>'
    match = re.search(pattern, content)

    if match:
        return match.group(0)

    # Fallback: just find export async function
    pattern = r'export\s+async\s+function\s+\w+[^{]+'
    match = re.search(pattern, content)

    if match:
        return match.group(0).strip()

    return "No exported function found"


def extract_doc_comment(content: str) -> str:
    """Extract JSDoc comment from TypeScript file"""
    # Look for /** ... */ style comments
    pattern = r'/\*\*\s*(.*?)\s*\*/'
    match = re.search(pattern, content, re.DOTALL)

    if match:
        # Clean up the comment
        doc = match.group(1)
        doc = re.sub(r'^\s*\*\s*', '', doc, flags=re.MULTILINE)
        return doc.strip()

    return ""
