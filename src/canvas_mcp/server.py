#!/usr/bin/env python3
"""
Canvas MCP Server

A Model Context Protocol server for Canvas LMS integration.
Provides educators and students with AI-powered tools for course management,
assignment handling, discussion facilitation, student analytics, and personal
academic tracking.
"""

import argparse
import sys

from mcp.server.fastmcp import FastMCP

from .core.config import get_config, validate_config
from .resources import register_resources_and_prompts
from .tools import (
    register_accessibility_tools,
    register_assignment_tools,
    register_course_tools,
    register_discussion_tools,
    register_messaging_tools,
    register_other_tools,
    register_peer_review_comment_tools,
    register_peer_review_tools,
    register_rubric_tools,
    register_student_tools,
)


def create_server() -> FastMCP:
    """Create and configure the Canvas MCP server."""
    config = get_config()
    mcp = FastMCP(config.mcp_server_name)
    return mcp


def register_all_tools(mcp: FastMCP) -> None:
    """Register all MCP tools, resources, and prompts."""
    print("Registering Canvas MCP tools...", file=sys.stderr)

    # Register tools by category
    register_course_tools(mcp)
    register_assignment_tools(mcp)
    register_discussion_tools(mcp)
    register_other_tools(mcp)
    register_rubric_tools(mcp)
    register_peer_review_tools(mcp)
    register_peer_review_comment_tools(mcp)
    register_messaging_tools(mcp)
    register_student_tools(mcp)
    register_accessibility_tools(mcp)

    # Register resources and prompts
    register_resources_and_prompts(mcp)

    print("All Canvas MCP tools registered successfully!", file=sys.stderr)


def test_connection() -> bool:
    """Test the Canvas API connection."""
    print("Testing Canvas API connection...", file=sys.stderr)

    try:
        import asyncio

        from .core.client import make_canvas_request

        async def test_api() -> bool:
            # Test with a simple API call
            response = await make_canvas_request("get", "/users/self")
            if "error" in response:
                print(f"API test failed: {response['error']}", file=sys.stderr)
                return False
            else:
                user_name = response.get("name", "Unknown")
                print(f"✓ API connection successful! Connected as: {user_name}", file=sys.stderr)
                return True

        return asyncio.run(test_api())

    except Exception as e:
        print(f"API test failed with exception: {e}", file=sys.stderr)
        return False


def main() -> None:
    """Main entry point for the Canvas MCP server."""
    parser = argparse.ArgumentParser(
        description="Canvas MCP Server - AI-powered Canvas LMS integration"
    )
    parser.add_argument(
        "--test",
        action="store_true",
        help="Test Canvas API connection and exit"
    )
    parser.add_argument(
        "--config",
        action="store_true",
        help="Show current configuration and exit"
    )

    args = parser.parse_args()

    # Validate configuration
    if not validate_config():
        print("\nPlease check your .env file configuration.", file=sys.stderr)
        print("Use the env.template file as a reference.", file=sys.stderr)
        sys.exit(1)

    config = get_config()

    # Handle special commands
    if args.config:
        print("Canvas MCP Server Configuration:", file=sys.stderr)
        print(f"  Server Name: {config.mcp_server_name}", file=sys.stderr)
        print(f"  Canvas API URL: {config.canvas_api_url}", file=sys.stderr)
        print(f"  Debug Mode: {config.debug}", file=sys.stderr)
        print(f"  API Timeout: {config.api_timeout}s", file=sys.stderr)
        print(f"  Cache TTL: {config.cache_ttl}s", file=sys.stderr)
        if config.institution_name:
            print(f"  Institution: {config.institution_name}", file=sys.stderr)
        sys.exit(0)

    if args.test:
        if test_connection():
            print("✓ All tests passed!", file=sys.stderr)
            sys.exit(0)
        else:
            print("✗ Connection test failed!", file=sys.stderr)
            sys.exit(1)

    # Normal server startup
    print(f"Starting Canvas MCP server with API URL: {config.canvas_api_url}", file=sys.stderr)
    if config.institution_name:
        print(f"Institution: {config.institution_name}", file=sys.stderr)
    print("Use Ctrl+C to stop the server", file=sys.stderr)

    # Create and configure server
    mcp = create_server()
    register_all_tools(mcp)

    try:
        # Run the server
        mcp.run()
    except KeyboardInterrupt:
        print("\nShutting down server...", file=sys.stderr)
    except Exception as e:
        print(f"Server error: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        # Cleanup
        print("Server stopped", file=sys.stderr)


if __name__ == "__main__":
    main()
