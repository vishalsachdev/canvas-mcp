# Contributing to Canvas MCP

Thanks for contributing.

This project powers Canvas LMS workflows for educators and students, with strong emphasis on reliability, privacy, and test coverage.

## Quick Setup

### Prerequisites
- Python 3.10+
- Canvas API token + Canvas API URL

### Local install
```bash
# from repo root
pip install uv
uv pip install -e .
```

Create `.env`:
```bash
CANVAS_API_TOKEN=...
CANVAS_API_URL=https://your-school.instructure.com/api/v1
```

Start server:
```bash
canvas-mcp-server
```

Useful checks:
```bash
canvas-mcp-server --test
canvas-mcp-server --config
```

## Project Structure

- `src/canvas_mcp/core/` — API client, config, validation, caching
- `src/canvas_mcp/tools/` — MCP tool implementations
- `src/canvas_mcp/resources/` — MCP resources/prompts
- `tests/tools/` — tool unit tests
- `tests/security/` — security/privacy tests
- `docs/` — user and developer docs

## Branching & PR Workflow

This repo is a fork.

- Push to **origin** (`jaymesdec/canvas-mcp`)
- Never push to **upstream** directly
- Use feature/fix branches for code changes

Recommended branch prefixes:
- `feature/...`
- `fix/...`
- `docs/...`
- `refactor/...`

## Code Standards

- Use type hints for all new functions
- Keep API calls async
- Use `@validate_params` on MCP tools
- Use `get_course_id()` for flexible course identifiers
- Return structured error messages (don’t crash on user input)
- Follow existing naming patterns for tools (`action_entity`)

## Testing (Required)

TDD is expected for new/changed tools.

Minimum for new tool logic:
- success case
- error handling case
- edge case

Run before PR:
```bash
pytest
ruff check src/
black src/
mypy src/
```

## Privacy & FERPA

If your change touches student data:
- preserve anonymization behavior
- avoid introducing raw PII exposure in logs/output
- validate behavior with security tests where relevant

## Documentation Updates

Update docs when behavior changes:
- `README.md`
- `AGENTS.md` / `CLAUDE.md` (if developer or agent workflow changes)
- tool docs/manifests under `tools/` when adding/updating tools

## Release Notes Reminder

If bumping version in `pyproject.toml`, also update release references in docs and create a git tag.

---

If in doubt, open a draft PR early with your approach and tradeoffs.
