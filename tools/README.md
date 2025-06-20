# Canvas MCP Server Tools Documentation

This directory contains the documentation for all tools available in the Canvas MCP Server. Each tool is organized by category and provides comprehensive documentation for interacting with Canvas LMS features.

> ℹ️ **Note**: For implementation details and advanced usage, see the [Implementation Guides](..) in the project root.

## Tool Categories

### 1. Course Tools
Documentation for course-related functionality.

- [courses.md](courses.md) - Tools for managing and retrieving course information, including:
  - Listing available courses
  - Getting detailed course information
  - Managing course content and structure

### 2. Assignment Tools
Documentation for assignment-related functionality.

- [assignments.md](assignments.md) - Tools for managing assignments, submissions, and peer reviews, including:
  - Creating and managing assignments
  - Handling submissions and feedback
  - Peer review workflows

### 3. Rubric Tools
Documentation for rubric-related functionality.

- [rubrics.md](rubrics.md) - Complete guide to rubric tools including workflows, grading features, and educator benefits.

### 4. Other Tools
Documentation for additional Canvas functionality.

- [other_tools.md](other_tools.md) - Miscellaneous tools including:
  - Discussions and announcements
  - User and enrollment management
  - Analytics and reporting

#### Additional Resources
- [Pages Implementation Guide](../PAGES_IMPLEMENTATION.md) - Comprehensive guide to working with Canvas pages
- [Development Guide](../CLAUDE.md) - For contributors working on the codebase

## Getting Started

To use these tools, you'll need:

1. A running instance of the Canvas MCP Server
2. Valid Canvas API credentials
3. Appropriate permissions for the actions you want to perform

## Common Patterns

### Authentication
All tools require a valid Canvas API token, which should be set in your environment variables:

```bash
export CANVAS_API_TOKEN='your_canvas_token_here'
```

### Error Handling
All tools follow consistent error handling patterns:
- Return meaningful error messages
- Include error codes when available
- Handle rate limiting and retries automatically

### Rate Limiting
The tools respect Canvas API rate limits and include backoff and retry logic.

## Best Practices

1. **Caching**: Take advantage of built-in caching to improve performance
2. **Batching**: Use the appropriate list endpoints before getting individual items
3. **Error Handling**: Always check for and handle potential errors
4. **Pagination**: Be aware that some endpoints return paginated results
5. **Data Validation**: Input validation is performed, but always validate data from external sources

## Development

### Adding New Tools
1. Add your tool to the appropriate module in the `tools/` directory
2. Document the tool following the existing patterns
3. Add any necessary tests
4. Update the relevant documentation file

### Testing
Run the test suite with:

```bash
pytest tests/
```

## Support

For issues or questions, please open an issue in the [GitHub repository](https://github.com/vishalsachdev/canvas-mcp).

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
