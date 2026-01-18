# Canvas MCP Test Suite

This directory contains the test suite for Canvas MCP, covering security, tool functionality, and integration testing.

## Test Structure

```
tests/
├── conftest.py           # Shared pytest fixtures
├── security/             # Security-focused tests
│   ├── test_authentication.py
│   ├── test_code_execution.py
│   ├── test_dependencies.py
│   ├── test_ferpa_compliance.py
│   └── test_input_validation.py
└── tools/                # Tool functionality tests
    ├── test_assignments.py
    ├── test_courses.py
    ├── test_discussions.py
    ├── test_messaging.py
    ├── test_pages.py
    ├── test_peer_reviews.py
    ├── test_rubrics.py
    └── test_student_tools.py
```

## Running Tests

### Run all tests
```bash
pytest
```

### Run specific test category
```bash
pytest tests/tools/          # Run only tool tests
pytest tests/security/       # Run only security tests
```

### Run with coverage
```bash
pytest --cov=src/canvas_mcp --cov-report=html
# Or use coverage directly:
coverage run -m pytest tests/
coverage report
coverage html
```

### Run specific test file
```bash
pytest tests/tools/test_courses.py -v
```

### Run specific test
```bash
pytest tests/tools/test_courses.py::TestStripHtmlTags::test_strip_simple_tags -v
```

## Test Categories

### Tool Tests (`tests/tools/`)
Tests for Canvas MCP tool functionality:
- **Courses**: Course listing, details, content overview
- **Assignments**: Assignment management, submissions, analytics
- **Pages**: Page CRUD operations
- **Rubrics**: Rubric creation, validation, grading
- **Discussions**: Discussion topics and entries
- **Messaging**: Conversations and announcements
- **Peer Reviews**: Peer review assignment and management
- **Student Tools**: Student self-service functionality

**Test Coverage**: 48+ tests covering all major tool categories

### Security Tests (`tests/security/`)
Security-focused tests:
- **Authentication**: API token security, authorization controls
- **Code Execution**: Sandbox security, resource limits
- **Dependencies**: Vulnerability scanning, license compliance
- **FERPA Compliance**: Student data anonymization
- **Input Validation**: Parameter validation, injection prevention

## Testing Patterns

### Mocking Canvas API
Tests use `unittest.mock` to mock Canvas API calls:

```python
from unittest.mock import AsyncMock, patch

@pytest.mark.asyncio
async def test_list_courses():
    mock_data = [{"id": 1, "name": "Course 1"}]
    
    with patch('src.canvas_mcp.core.client.fetch_all_paginated_results', 
               new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = mock_data
        
        # Test code here
        result = await fetch_all_paginated_results("/courses", {})
        assert result == mock_data
```

### Shared Fixtures
Common fixtures are defined in `conftest.py`:
- `mock_canvas_request`: Mock Canvas API request function
- `mock_fetch_paginated`: Mock paginated fetch function
- `sample_course_data`: Sample course data for testing
- `sample_assignment_data`: Sample assignment data for testing

### Test Naming Convention
- Test files: `test_<module_name>.py`
- Test classes: `Test<FeatureName>`
- Test functions: `test_<specific_behavior>`

## Writing New Tests

### 1. Choose the appropriate test file
Add tests to existing files when testing existing tools. Create new files for new features.

### 2. Use fixtures from conftest.py
```python
def test_my_feature(mock_canvas_request, sample_course_data):
    mock_canvas_request.return_value = sample_course_data
    # Test implementation
```

### 3. Follow the AAA pattern
- **Arrange**: Set up test data and mocks
- **Act**: Execute the code being tested
- **Assert**: Verify the results

### 4. Test success, error, and edge cases
Each feature should have at least 3 tests:
- Success case
- Error handling
- Edge case (empty data, invalid input, etc.)

## CI/CD Integration

Tests run automatically on:
- Push to `main` or `development` branches
- Pull requests to `main`
- Weekly security scans

See `.github/workflows/canvas-mcp-testing.yml` for CI configuration.

## Coverage Goals

- **Overall**: Maintain meaningful test coverage
- **Tools**: Test all public API functions
- **Security**: 100% coverage of security-critical code paths
- **New Features**: All new features must include tests

## Best Practices

1. **Mock external dependencies**: Never make real Canvas API calls in tests
2. **Keep tests fast**: Use mocks instead of real I/O operations
3. **Test behavior, not implementation**: Focus on what the code does, not how
4. **Use descriptive test names**: Test names should describe what they're testing
5. **One assertion per test**: Each test should verify one specific behavior
6. **Clean up after tests**: Use fixtures to ensure proper cleanup

## Troubleshooting

### Import errors
Make sure you've installed the package in development mode:
```bash
pip install -e ".[dev]"
```

### Async test warnings
Tests using async functions should use the `@pytest.mark.asyncio` decorator:
```python
@pytest.mark.asyncio
async def test_async_function():
    # Test code
```

### Mock not working
Ensure you're patching at the right location:
```python
# Patch where it's used, not where it's defined
with patch('src.canvas_mcp.tools.courses.make_canvas_request'):
    # Not 'src.canvas_mcp.core.client.make_canvas_request'
```

## Resources

- [pytest documentation](https://docs.pytest.org/)
- [pytest-asyncio documentation](https://pytest-asyncio.readthedocs.io/)
- [unittest.mock documentation](https://docs.python.org/3/library/unittest.mock.html)
- [Coverage.py documentation](https://coverage.readthedocs.io/)
