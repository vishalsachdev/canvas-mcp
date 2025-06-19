#!/usr/bin/env python3
"""
Canvas MCP Server - Refactored
A Model Context Protocol server for Canvas LMS integration.

This is the refactored version of the Canvas MCP server with modular architecture.
"""

import os
import sys
from mcp.server.fastmcp import FastMCP

# Import all modules
from tools.courses import register_course_tools
from tools.assignments import register_assignment_tools  
from tools.other_tools import register_other_tools
from tools.rubrics import register_rubric_tools
from resources.resources import register_resources_and_prompts

# Date/Time Formatting Standard
# ---------------------------
# This MCP server standardizes all date/time values to ISO 8601 format (YYYY-MM-DDTHH:MM:SSZ)
# with the following conventions:
# - All dates include time components (even if they're 00:00:00)
# - All dates include timezone information (Z for UTC or +/-HH:MM offset)
# - UTC timezone is used for all internal date handling
# - Dates without timezone information are assumed to be in UTC
# - The format_date() function handles conversion of various formats to this standard

# Initialize FastMCP server
mcp = FastMCP("canvas-api")

# Configuration
API_BASE_URL = os.environ.get("CANVAS_API_URL", "https://canvas.illinois.edu/api/v1")
API_TOKEN = os.environ.get("CANVAS_API_TOKEN", "")


def register_all_tools():
    """Register all MCP tools, resources, and prompts."""
    print("Registering Canvas MCP tools...", file=sys.stderr)
    
    # Register tools by category
    register_course_tools(mcp)
    register_assignment_tools(mcp)
    register_other_tools(mcp)
    register_rubric_tools(mcp)
    
    # Register resources and prompts
    register_resources_and_prompts(mcp)
    
    print("All Canvas MCP tools registered successfully!", file=sys.stderr)


def main():
    """Main entry point for the Canvas MCP server."""
    # Check for API token
    if not API_TOKEN:
        print("Error: CANVAS_API_TOKEN environment variable is required", file=sys.stderr)
        print("Please set it to your Canvas API token", file=sys.stderr)
        sys.exit(1)
    
    print(f"Starting Canvas MCP server with API URL: {API_BASE_URL}", file=sys.stderr)
    print("Use Ctrl+C to stop the server", file=sys.stderr)
    
    # Register all tools
    register_all_tools()
    
    try:
        # Run the server directly
        mcp.run()
    except KeyboardInterrupt:
        print("\nShutting down server...", file=sys.stderr)
    finally:
        # We'll rely on Python's cleanup to close the client
        pass


if __name__ == "__main__":
    main()