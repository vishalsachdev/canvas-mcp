# Contributing to Canvas MCP

Thank you for your interest in contributing to Canvas MCP! This document provides guidelines and instructions for contributing to the project.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Development Setup](#development-setup)
- [How to Contribute](#how-to-contribute)
- [Coding Standards](#coding-standards)
- [Testing Guidelines](#testing-guidelines)
- [Documentation Guidelines](#documentation-guidelines)
- [Pull Request Process](#pull-request-process)
- [Release Process](#release-process)

## Code of Conduct

This project adheres to a Code of Conduct that all contributors are expected to follow. Please read [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) before contributing.

## Getting Started

### Prerequisites

- Python 3.10 or higher
- Git
- Canvas LMS account with API access
- Familiarity with the Model Context Protocol (MCP)

### Finding Ways to Contribute

- **Bug Reports**: Check [existing issues](https://github.com/vishalsachdev/canvas-mcp/issues) or create a new one
- **Feature Requests**: Open an issue with the "enhancement" label
- **Documentation**: Help improve guides, add examples, fix typos
- **Code**: Pick an issue labeled "good first issue" or "help wanted"
- **Testing**: Add test coverage for existing features
- **Visual Assets**: Contribute screenshots, GIFs, or diagrams

## Development Setup

### 1. Fork and Clone

```bash
# Fork the repository on GitHub, then clone your fork
git clone https://github.com/YOUR-USERNAME/canvas-mcp.git
cd canvas-mcp

# Add upstream remote
git remote add upstream https://github.com/vishalsachdev/canvas-mcp.git
```

### 2. Install Development Dependencies

```bash
# Install uv package manager
pip install uv

# Install the package in editable mode with dev dependencies
uv pip install -e ".[dev]"
```

### 3. Set Up Environment

```bash
# Copy environment template
cp env.template .env

# Edit .env with your Canvas API credentials
# For testing, use a sandbox Canvas instance if available
```

### 4. Verify Setup

```bash
# Test Canvas API connection
canvas-mcp-server --test

# Run tests (when available)
pytest

# Check code style
black --check src/
ruff check src/
```

## How to Contribute

### Reporting Bugs

Before creating a bug report:
1. Check if the issue already exists
2. Verify the issue with the latest version
3. Test with minimal configuration

When creating a bug report, include:
- **Description**: Clear description of the issue
- **Environment**: OS, Python version, Canvas MCP version
- **Steps to Reproduce**: Detailed steps to reproduce the issue
- **Expected Behavior**: What should happen
- **Actual Behavior**: What actually happens
- **Error Messages**: Full error messages (with sensitive data removed)
- **Configuration**: Relevant parts of your `.env` file (WITHOUT tokens!)

### Suggesting Enhancements

Enhancement suggestions should include:
- **Use Case**: Why is this enhancement needed?
- **Proposed Solution**: How would you implement it?
- **Alternatives Considered**: What other solutions did you consider?
- **Impact**: Who would benefit from this enhancement?
- **Breaking Changes**: Would this break existing functionality?

### Submitting Code Changes

1. **Create a Branch**
   ```bash
   git checkout -b feature/your-feature-name
   # or
   git checkout -b fix/your-bug-fix
   ```

2. **Make Your Changes**
   - Follow the [coding standards](#coding-standards)
   - Add tests for new functionality
   - Update documentation as needed
   - Keep commits focused and atomic

3. **Test Your Changes**
   ```bash
   # Run tests
   pytest

   # Check code style
   black src/
   ruff check src/

   # Test server functionality
   canvas-mcp-server --test
   ```

4. **Commit Your Changes**
   ```bash
   git add .
   git commit -m "feat: Add feature description"
   # or
   git commit -m "fix: Fix bug description"
   ```

   Use [Conventional Commits](https://www.conventionalcommits.org/):
   - `feat:` New features
   - `fix:` Bug fixes
   - `docs:` Documentation changes
   - `style:` Code style changes (formatting, etc.)
   - `refactor:` Code refactoring
   - `test:` Adding or updating tests
   - `chore:` Maintenance tasks

5. **Push to Your Fork**
   ```bash
   git push origin feature/your-feature-name
   ```

6. **Open a Pull Request**
   - Go to the original repository on GitHub
   - Click "New Pull Request"
   - Select your fork and branch
   - Fill out the PR template

## Coding Standards

### Python Style Guide

- **PEP 8**: Follow Python's style guide
- **Type Hints**: Use type hints for all functions
- **Docstrings**: Add docstrings to all modules, classes, and functions
- **Line Length**: Maximum 88 characters (Black default)
- **Imports**: Organize with `isort` or `ruff`

#### Function Docstring Template

```python
def function_name(param1: str, param2: int) -> bool:
    """Brief description of what the function does.

    More detailed description if needed. Explain the purpose,
    behavior, and any important details.

    Args:
        param1: Description of parameter 1
        param2: Description of parameter 2

    Returns:
        Description of return value

    Raises:
        ValueError: When param1 is empty
        RuntimeError: When operation fails

    Example:
        >>> result = function_name("test", 42)
        >>> print(result)
        True
    """
    pass
```

### TypeScript Style Guide

- **JSDoc Comments**: Document all exported functions and types
- **Type Safety**: Use TypeScript types, avoid `any`
- **Naming**: Use camelCase for functions, PascalCase for types/interfaces
- **Async/Await**: Prefer async/await over promises

#### JSDoc Template

```typescript
/**
 * Brief description of the function.
 *
 * More detailed description if needed.
 *
 * @param param1 - Description of parameter 1
 * @param param2 - Description of parameter 2
 * @returns Description of return value
 * @throws {Error} When operation fails
 *
 * @example
 * ```typescript
 * const result = await functionName("test", 42);
 * console.log(result);
 * ```
 */
async function functionName(param1: string, param2: number): Promise<boolean> {
  // implementation
}
```

### MCP Tool Guidelines

When creating new MCP tools:

1. **Naming**: Use pattern `{action}_{entity}[_{specifier}]`
   - Examples: `list_courses`, `get_assignment_details`, `send_conversation`

2. **Validation**: Use `@validate_params` decorator
   ```python
   @mcp.tool()
   @validate_params
   async def tool_name(course_identifier: str | int) -> str:
       """Tool description."""
       pass
   ```

3. **Documentation**: Include clear tool description and parameter descriptions

4. **Error Handling**: Return JSON error responses
   ```python
   if "error" in response:
       return f"Error: {response['error']}"
   ```

5. **Privacy**: Consider anonymization for student data

### Code Organization

- **Core Utilities**: Place in `src/canvas_mcp/core/`
- **MCP Tools**: Place in `src/canvas_mcp/tools/`
- **Code API**: Place in `src/canvas_mcp/code_api/canvas/`
- **Resources**: Place in `src/canvas_mcp/resources/`

## Testing Guidelines

### Writing Tests

```python
import pytest
from canvas_mcp.core.validation import validate_parameter

def test_validate_parameter_string():
    """Test string parameter validation."""
    result = validate_parameter("test_value", str, "param_name")
    assert result == "test_value"

def test_validate_parameter_int():
    """Test integer parameter validation with string input."""
    result = validate_parameter("42", int, "param_name")
    assert result == 42
    assert isinstance(result, int)

@pytest.mark.asyncio
async def test_canvas_api_call():
    """Test Canvas API call functionality."""
    # Test implementation
    pass
```

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=canvas_mcp --cov-report=html

# Run specific test file
pytest tests/test_validation.py

# Run specific test function
pytest tests/test_validation.py::test_validate_parameter_string
```

## Documentation Guidelines

### Documentation Types

1. **Code Documentation**: Docstrings and comments in code
2. **User Documentation**: README, guides for students/educators
3. **API Documentation**: Tool descriptions and parameters
4. **Examples**: Working code examples and tutorials

### Writing Good Documentation

- **Clear and Concise**: Use simple language, avoid jargon
- **Examples**: Include practical examples
- **Up-to-date**: Keep documentation in sync with code
- **Accessible**: Consider different skill levels
- **Visual**: Use diagrams, screenshots, GIFs where helpful

### Documentation Structure

```
docs/
├── STUDENT_GUIDE.md          # For students
├── EDUCATOR_GUIDE.md         # For educators
├── CLAUDE.md                 # For Claude Code development
├── best-practices.md         # Best practices
├── course_documentation_prompt_template.md
└── adr/                      # Architecture Decision Records
    ├── 001-modular-architecture.md
    └── 002-data-anonymization.md
```

## Pull Request Process

### PR Checklist

Before submitting a PR, ensure:

- [ ] Code follows style guidelines (Black, Ruff)
- [ ] All tests pass
- [ ] New features have tests
- [ ] Documentation is updated
- [ ] Commit messages follow Conventional Commits
- [ ] PR description is clear and complete
- [ ] No sensitive data (tokens, passwords) in code

### PR Template

```markdown
## Description
Brief description of the changes

## Type of Change
- [ ] Bug fix
- [ ] New feature
- [ ] Breaking change
- [ ] Documentation update

## Testing
How has this been tested?

## Checklist
- [ ] Code follows style guidelines
- [ ] Tests pass
- [ ] Documentation updated
- [ ] No breaking changes (or documented)
```

### Review Process

1. **Automated Checks**: CI/CD runs automatically
2. **Code Review**: Maintainers review your code
3. **Feedback**: Address review comments
4. **Approval**: At least one maintainer approval required
5. **Merge**: Maintainer merges your PR

## Release Process

Releases are managed by project maintainers:

1. **Version Bump**: Update version in `pyproject.toml`
2. **Changelog**: Update `CHANGELOG.md` with changes
3. **Tag**: Create version tag (`git tag vX.Y.Z`)
4. **Push**: Push tag to trigger automated release
5. **Publish**: GitHub Actions publishes to PyPI and MCP Registry

### Versioning

We follow [Semantic Versioning](https://semver.org/):
- **MAJOR**: Breaking changes
- **MINOR**: New features (backward compatible)
- **PATCH**: Bug fixes (backward compatible)

## Questions?

- **GitHub Issues**: [Open an issue](https://github.com/vishalsachdev/canvas-mcp/issues)
- **Discussions**: Use GitHub Discussions for questions
- **Documentation**: Check existing guides and documentation

## Recognition

Contributors are recognized in:
- GitHub contributors page
- Release notes
- Project documentation

Thank you for contributing to Canvas MCP!
