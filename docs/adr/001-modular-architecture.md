# ADR-001: Modular Architecture

## Status

Accepted

Date: 2024-10-15

## Context

The original Canvas MCP implementation was a monolithic single-file server (`canvas_server_cached.py`) that contained all functionality in one ~2000 line file. This approach had several issues:

- **Maintainability**: Difficult to navigate and modify large single file
- **Testing**: Hard to test individual components in isolation
- **Collaboration**: Multiple developers editing same file causes conflicts
- **Organization**: No clear separation of concerns
- **Scalability**: Adding new features increased file size and complexity
- **Code Quality**: Harder to enforce coding standards across mixed concerns

As the project grew to support both students and educators with diverse tool sets, the monolithic approach became increasingly problematic.

## Decision

Refactor Canvas MCP to a modular architecture following modern Python package best practices:

```
src/canvas_mcp/
├── __init__.py           # Package initialization
├── server.py             # Main server entry point
├── core/                 # Core utilities
│   ├── config.py         # Configuration management
│   ├── client.py         # HTTP client
│   ├── cache.py          # Caching system
│   ├── validation.py     # Parameter validation
│   ├── anonymization.py  # Data anonymization
│   └── dates.py          # Date handling
├── tools/                # MCP tool implementations
│   ├── courses.py        # Course tools
│   ├── assignments.py    # Assignment tools
│   ├── discussions.py    # Discussion tools
│   ├── student_tools.py  # Student-specific tools
│   └── ...               # Other tool modules
├── resources/            # MCP resources
└── code_api/             # Code execution API
```

**Key Principles:**
1. **Separation of Concerns**: Each module has a single, well-defined responsibility
2. **Modern Package Structure**: Use `src/` layout with `pyproject.toml`
3. **Functional Grouping**: Tools organized by Canvas entity or audience
4. **Shared Utilities**: Common functionality in `core/` modules
5. **Clear Dependencies**: Minimize coupling between modules

## Alternatives Considered

### Alternative 1: Keep Monolithic Structure
- **Pros**: No refactoring needed, everything in one place
- **Cons**: Technical debt continues to grow, maintainability worsens
- **Rejected**: Not sustainable for long-term development

### Alternative 2: Microservices Architecture
- **Pros**: Maximum separation, independent deployment
- **Cons**: Over-engineered for MCP server, added complexity, deployment overhead
- **Rejected**: Too complex for project scope

### Alternative 3: Class-Based Architecture
- **Pros**: OOP encapsulation, inheritance for shared behavior
- **Cons**: Less Pythonic for MCP tools, added abstraction layers
- **Rejected**: Functional approach better fits MCP pattern

## Consequences

### Positive

- **Maintainability**: Each module is ~200-500 lines, easy to understand
- **Testability**: Can test components in isolation
- **Developer Experience**: Clear structure, easy to find relevant code
- **Collaboration**: Multiple developers can work on different modules
- **Code Quality**: Easier to enforce standards per module
- **Extensibility**: New features add new modules without touching existing code
- **Documentation**: Each module can have focused documentation
- **Reusability**: Core utilities shared across tools

### Negative

- **Migration Effort**: Required significant refactoring of existing code
- **Import Complexity**: More import statements needed
- **Initial Learning Curve**: New contributors need to understand structure
- **Deployment**: More files to manage (mitigated by proper packaging)

### Neutral

- **File Count**: Increased from 1 to ~30 files
- **Navigation**: Need to navigate between files (IDE support helps)
- **Testing Strategy**: Requires both unit and integration tests

## Implementation

### Migration Steps

1. **Create Package Structure**
   - Set up `src/canvas_mcp/` directory
   - Create `__init__.py` files
   - Configure `pyproject.toml`

2. **Extract Core Utilities**
   - Move HTTP client logic to `core/client.py`
   - Extract configuration to `core/config.py`
   - Move caching to `core/cache.py`
   - Create validation module

3. **Organize Tools**
   - Group by Canvas entity (courses, assignments, etc.)
   - Separate by audience (student vs educator)
   - Create registration functions

4. **Update Server**
   - Simplify `server.py` to orchestration only
   - Import and register all tools
   - Maintain CLI interface

5. **Archive Legacy Code**
   - Move `canvas_server_cached.py` to `archive/`
   - Preserve for reference but exclude from package

6. **Testing & Documentation**
   - Test each module independently
   - Update documentation for new structure
   - Create development guide

### Entry Points

```toml
[project.scripts]
canvas-mcp-server = "canvas_mcp.server:main"
```

### Package Configuration

Modern `pyproject.toml` with:
- Hatchling build backend
- Python 3.10+ requirement
- FastMCP framework
- Development dependencies

## References

- Original monolithic file: `archive/canvas_server_cached.py`
- Python packaging guide: https://packaging.python.org/
- FastMCP documentation: https://github.com/jlowin/fastmcp
- Related: [ADR-004: FastMCP Framework](004-fastmcp-framework.md)

## Notes

The modular architecture has proven successful:
- Easier to add new features (student tools, code execution API)
- Better code organization enables faster development
- Clear separation helps new contributors understand codebase
- Maintains backward compatibility with MCP clients

This decision set the foundation for all subsequent architectural improvements.
