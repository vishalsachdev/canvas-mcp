# ADR-004: FastMCP Framework

## Status

Accepted

Date: 2024-10-12

## Context

When building Canvas MCP, we needed to implement the Model Context Protocol (MCP) server. Several options existed for implementing MCP servers in Python:

**Requirements:**
- Robust MCP protocol implementation
- Easy tool registration
- Good error handling
- Type safety
- Active maintenance
- Good documentation

**Challenges:**
- MCP is a new protocol (announced late 2024)
- Limited mature implementations
- Need to balance feature richness with simplicity
- Must work with Claude Desktop and other MCP clients

**Options Evaluated:**
1. Implement MCP protocol from scratch
2. Use official MCP Python SDK
3. Use FastMCP framework
4. Use alternative MCP frameworks

## Decision

Adopt **FastMCP** as the framework for implementing the Canvas MCP server.

**FastMCP** (https://github.com/jlowin/fastmcp) is a Python framework that provides:
- Simple decorator-based tool registration
- Built-in type validation
- Automatic error handling
- Resource support
- Prompt management
- Clean, Pythonic API

**Example Usage:**
```python
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("canvas-mcp")

@mcp.tool()
async def list_courses() -> str:
    """List all courses for the user."""
    # Implementation
    return courses_json

@mcp.resource("course://")
async def get_course_resource(uri: str) -> str:
    """Get course content by URI."""
    # Implementation
    return content
```

## Alternatives Considered

### Alternative 1: Implement from Scratch
- **Pros**:
  - Full control over implementation
  - No external dependencies
  - Tailored to exact needs
- **Cons**:
  - Significant development time
  - Need to maintain protocol compliance
  - Error-prone (protocol details)
  - No community support
- **Rejected**: Too much effort, reinventing the wheel

### Alternative 2: Official MCP Python SDK
- **Pros**:
  - Official implementation
  - Guaranteed protocol compliance
  - Direct from protocol authors
- **Cons**:
  - Lower-level API (more boilerplate)
  - Less opinionated (more decisions needed)
  - More verbose tool registration
- **Rejected**: FastMCP provides better DX while using SDK underneath

### Alternative 3: Build with Raw STDIO
- **Pros**:
  - Maximum control
  - No framework overhead
- **Cons**:
  - Manual JSON-RPC handling
  - Complex error management
  - Tedious message parsing
- **Rejected**: Too low-level, error-prone

## Consequences

### Positive

- **Rapid Development**: Decorator syntax is intuitive and fast
- **Type Safety**: Built-in validation for tool parameters
- **Error Handling**: Framework handles MCP protocol errors
- **Documentation**: Tools self-document through docstrings
- **Resources**: Easy to add MCP resources and prompts
- **Community**: Growing FastMCP community and examples
- **Maintenance**: Framework handles protocol updates
- **Testing**: Can test tools independently of MCP protocol
- **Clean Code**: Minimal boilerplate, focuses on business logic

### Negative

- **Dependency**: Reliance on third-party framework
- **Learning Curve**: Team needs to learn FastMCP patterns
- **Framework Constraints**: Must work within FastMCP's patterns
- **Update Lag**: Framework updates may lag MCP protocol updates
- **Debugging**: Framework layer adds indirection

### Neutral

- **Abstraction Level**: Trade low-level control for high-level convenience
- **Framework Size**: Small dependency, but still a dependency
- **Community Size**: Smaller than massive frameworks, but growing

## Implementation

### Server Setup

```python
# src/canvas_mcp/server.py

from mcp.server.fastmcp import FastMCP

def create_server() -> FastMCP:
    """Create and configure the Canvas MCP server."""
    config = get_config()
    mcp = FastMCP(config.mcp_server_name)
    return mcp

def register_all_tools(mcp: FastMCP) -> None:
    """Register all MCP tools, resources, and prompts."""
    # Import and register tool modules
    register_course_tools(mcp)
    register_assignment_tools(mcp)
    # ... more registrations
```

### Tool Registration Pattern

```python
# src/canvas_mcp/tools/courses.py

def register_course_tools(mcp: FastMCP):
    """Register all course-related MCP tools."""

    @mcp.tool()
    async def list_courses(include_concluded: bool = False) -> str:
        """List courses for the authenticated user.

        Args:
            include_concluded: Include concluded courses

        Returns:
            JSON string with course information
        """
        # Implementation
        pass

    @mcp.tool()
    @validate_params  # Custom validation decorator
    async def get_course_details(course_identifier: str | int) -> str:
        """Get detailed information about a specific course."""
        # Implementation
        pass
```

### Resource Pattern

```python
# src/canvas_mcp/resources/resources.py

def register_resources_and_prompts(mcp: FastMCP):
    """Register MCP resources and prompts."""

    @mcp.resource("canvas://courses")
    async def list_courses_resource() -> str:
        """List all courses as an MCP resource."""
        # Implementation
        pass
```

### Entry Point

```python
# src/canvas_mcp/server.py

def main() -> None:
    """Main entry point for the Canvas MCP server."""
    mcp = create_server()
    register_all_tools(mcp)
    mcp.run()

if __name__ == "__main__":
    main()
```

### CLI Command

```toml
# pyproject.toml

[project.scripts]
canvas-mcp-server = "canvas_mcp.server:main"
```

## Migration Path

From scratch implementation to FastMCP:

1. **Install FastMCP**: `pip install fastmcp>=2.10.0`
2. **Create Server**: Initialize FastMCP instance
3. **Register Tools**: Convert functions to `@mcp.tool()` decorated async functions
4. **Add Docstrings**: FastMCP uses docstrings for tool descriptions
5. **Test**: Verify tools work with Claude Desktop
6. **Cleanup**: Remove old protocol handling code

## References

- FastMCP Repository: https://github.com/jlowin/fastmcp
- FastMCP Documentation: https://github.com/jlowin/fastmcp#readme
- MCP Protocol Spec: https://modelcontextprotocol.io/
- Canvas MCP Server: `src/canvas_mcp/server.py`
- Related: [ADR-001: Modular Architecture](001-modular-architecture.md)

## Notes

### Design Philosophy

FastMCP aligns with Canvas MCP's design philosophy:
- **Simplicity**: Easy to add new tools
- **Pythonic**: Decorator pattern feels natural
- **Type Safe**: Leverages Python type hints
- **Async First**: Built for async/await
- **Testable**: Tools are just async functions

### Decorator Pattern Benefits

```python
# Before (manual MCP protocol handling)
async def handle_list_courses(params):
    try:
        # Parse params
        # Validate types
        # Call implementation
        # Format response
        # Handle errors
    except Exception as e:
        # MCP error response

# After (with FastMCP)
@mcp.tool()
async def list_courses(include_concluded: bool = False) -> str:
    """List courses for the authenticated user."""
    # Just implementation - framework handles the rest
```

### Custom Validation Layer

We added `@validate_params` decorator on top of FastMCP for Canvas-specific validation:
- Union type handling (course_identifier: str | int)
- Canvas ID conversion
- JSON string parsing
- List comma-splitting

This shows FastMCP is extensible and plays well with custom decorators.

### Performance Characteristics

FastMCP overhead:
- Tool registration: One-time at startup
- Request handling: Minimal (< 1ms)
- Memory: Small (decorator metadata)

For Canvas MCP, the bottleneck is Canvas API calls, not the framework.

### Future Considerations

If FastMCP becomes unmaintained:
- Fork and maintain internally
- Migrate to official SDK (more work)
- Consider other frameworks

Currently (as of Nov 2024):
- FastMCP actively maintained
- Regular updates
- Growing adoption
- No migration concerns

This ADR documents a foundational decision that enabled rapid development of Canvas MCP's rich tool ecosystem.
