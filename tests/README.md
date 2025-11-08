# Canvas MCP Tests

This directory contains comprehensive tests for the Canvas MCP server.

## Test Structure

- `core/` - Unit tests for core modules (config, client, cache, validation, etc.)
- `tools/` - Unit tests for MCP tools (courses, assignments, discussions, etc.)
- `integration/` - Integration tests for end-to-end workflows
- `fixtures/` - Shared test fixtures and mock data
- `conftest.py` - Pytest configuration and shared fixtures

## Running Tests

### Run all tests:
```bash
pytest
```

### Run with coverage:
```bash
pytest --cov=src/canvas_mcp --cov-report=html
```

### Run specific test file:
```bash
pytest tests/core/test_config.py -v
```

### Run specific test:
```bash
pytest tests/core/test_config.py::test_config_initialization -v
```

## Test Coverage

The test suite aims for high code coverage across:
- Core utilities and modules
- API client and error handling
- Configuration management
- Data validation and sanitization
- Tool implementations
- Integration workflows

## Writing Tests

### Guidelines:
1. Use descriptive test names that explain what is being tested
2. Follow the Arrange-Act-Assert pattern
3. Use fixtures for common setup
4. Mock external API calls
5. Test both success and error cases
6. Keep tests isolated and independent

### Example:
```python
def test_config_initialization(mock_env: dict[str, str]) -> None:
    """Test configuration initialization with environment variables."""
    # Arrange - mock_env fixture provides test environment

    # Act
    config = Config()

    # Assert
    assert config.canvas_api_token == "test_token_1234567890abcdefghij"
    assert config.canvas_api_url == "https://canvas.test.edu/api/v1"
```

## Fixtures

Common fixtures available in `conftest.py`:
- `mock_env` - Set up test environment variables
- `mock_http_client` - Mock HTTP client for API requests
- `sample_course_data` - Sample course data for testing
- `sample_assignment_data` - Sample assignment data
- `sample_submission_data` - Sample submission data
- `sample_discussion_data` - Sample discussion data

## Continuous Integration

Tests are automatically run in CI/CD pipelines:
- On every push to main/develop branches
- On pull requests
- Tests Python versions: 3.10, 3.11, 3.12
- Includes linting, type checking, and coverage reporting
