"""
Tool discovery for Canvas code execution API.
Allows Claude to search and explore available TypeScript tools.
"""

import json
import re
from pathlib import Path
from typing import Any, Literal

from mcp.server.fastmcp import FastMCP

DetailLevel = Literal["names", "signatures", "full"]


def register_discovery_tools(mcp: FastMCP) -> None:
    """Register tool discovery tools."""

    @mcp.tool()
    async def search_canvas_tools(
        query: str = "",
        detail_level: DetailLevel = "signatures"
    ) -> str:
        """
        Search available Canvas code API tools by keyword.

        Use this to discover what Canvas operations are available in the code API.
        Search by keyword (e.g., "grading", "assignment", "discussion") to find
        relevant tools.

        Args:
            query: Search term to filter tools. Empty string returns all tools.
            detail_level: How much information to return:
                - "names": Just file paths (most efficient)
                - "signatures": File paths + function signatures (recommended)
                - "full": Complete file contents (use sparingly)

        Returns:
            JSON string with matching tools

        Examples:
            - search_canvas_tools("grading", "signatures")
              → Find all grading-related tools with signatures
            - search_canvas_tools("", "names")
              → List all available tools (just names)
            - search_canvas_tools("bulk", "full")
              → Get full details of bulk operation tools
        """
        try:
            # Get code API directory
            code_api_path = Path(__file__).parent.parent / "code_api" / "canvas"

            if not code_api_path.exists():
                return json.dumps({
                    "error": "Code API directory not found",
                    "help": "The code execution API may not be set up yet"
                }, indent=2)

            # Search through TypeScript files
            matches = []
            query_lower = query.lower()

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
                        content = ts_file.read_text()
                        if query_lower not in content.lower():
                            continue
                    except Exception:
                        continue

                relative_path = str(ts_file.relative_to(code_api_path))

                if detail_level == "names":
                    matches.append(relative_path)

                elif detail_level == "signatures":
                    # Extract function signature from file
                    try:
                        content = ts_file.read_text()
                        signature = extract_function_signature(content)
                        doc_comment = extract_doc_comment(content)

                        matches.append({
                            "file": relative_path,
                            "signature": signature,
                            "description": doc_comment[:200] if doc_comment else None
                        })
                    except Exception as e:
                        matches.append({
                            "file": relative_path,
                            "error": f"Could not parse signature: {str(e)}"
                        })

                else:  # full
                    try:
                        content = ts_file.read_text()
                        matches.append({
                            "file": relative_path,
                            "content": content
                        })
                    except Exception as e:
                        matches.append({
                            "file": relative_path,
                            "error": f"Could not read file: {str(e)}"
                        })

            if not matches:
                return json.dumps({
                    "message": f"No tools found matching '{query}'",
                    "suggestion": "Try a different search term or use empty string to see all tools"
                }, indent=2)

            return json.dumps({
                "query": query,
                "detail_level": detail_level,
                "count": len(matches),
                "tools": matches
            }, indent=2)

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
