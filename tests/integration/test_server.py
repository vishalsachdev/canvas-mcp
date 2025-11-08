"""Integration tests for server setup and tool registration."""

import pytest

from canvas_mcp.server import create_server, register_all_tools


def test_create_server(mock_env: dict[str, str]) -> None:
    """Test server creation."""
    server = create_server()
    assert server is not None
    assert server.name == "test-canvas-api"


def test_register_all_tools(mock_env: dict[str, str]) -> None:
    """Test registering all tools."""
    server = create_server()

    # Register all tools
    register_all_tools(server)

    # Check that tools were registered
    assert len(server._tools) > 0

    # Check for some expected tool names
    tool_names = [tool.name for tool in server._tools]

    expected_tools = [
        "list_courses",
        "get_course_details",
        "list_assignments",
        "get_assignment_details",
        "list_discussions",
    ]

    for expected_tool in expected_tools:
        assert expected_tool in tool_names, f"Tool {expected_tool} not found"


def test_server_configuration(mock_env: dict[str, str]) -> None:
    """Test server configuration."""
    from canvas_mcp.core.config import get_config

    config = get_config()

    assert config.canvas_api_token == "test_token_123"
    assert config.canvas_api_url == "https://canvas.test.edu/api/v1"
    assert config.mcp_server_name == "test-canvas-api"
