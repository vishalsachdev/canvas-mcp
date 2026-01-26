# GitHub Actions Workflows

This directory contains automated workflows for the Canvas MCP project.

## Release and Publishing Workflows

### create-release.yml
**Purpose**: Automatically creates GitHub releases and updates the README with release information.

**Triggers**:
- Tag push matching `v*` pattern (e.g., `v1.0.7`)
- Manual workflow dispatch (for testing)

**What it does**:
1. Extracts version information from the tag
2. Generates release notes from commit history since last tag
3. Creates a GitHub release with the generated notes
4. Updates the README.md "Latest Release" section with:
   - New version number
   - Release date
   - Link to full release notes
5. Commits and pushes the README changes to main branch
   - If main is protected, creates a PR instead

**Manual testing**:
```bash
# Option 1: Via GitHub UI
Go to Actions → "Create Release and Update README" → Run workflow
Enter tag name (e.g., v1.0.7-test)

# Option 2: Via gh CLI
gh workflow run create-release.yml -f tag_name=v1.0.7-test
```

### publish-mcp.yml
**Purpose**: Publishes the package to PyPI and MCP Registry.

**Triggers**:
- Tag push matching `v*` pattern (e.g., `v1.0.7`)

**What it does**:
1. Runs tests to ensure code quality
2. Builds the Python package
3. Publishes to PyPI using OIDC authentication
4. Publishes to MCP Registry

**Prerequisites**:
- PyPI trusted publisher configured
- Package version in `pyproject.toml` and `src/canvas_mcp/__init__.py` must match tag

## Code Quality Workflows

### auto-update-docs.yml
**Purpose**: Automatically updates documentation when tool files are modified.

**Triggers**:
- Pull requests that modify files in `src/canvas_mcp/tools/` or `src/canvas_mcp/server.py`

**What it does**:
- Uses Claude Code to review tool changes
- Updates README.md with new tools or modified signatures
- Commits documentation updates directly to the PR branch

### claude-code-review.yml
**Purpose**: Automated code review using Claude.

**Triggers**:
- Pull requests
- Comments on pull requests

### auto-claude-review.yml
**Purpose**: Lightweight automated code review.

**Triggers**:
- Pull requests

## Testing Workflows

### canvas-mcp-testing.yml
**Purpose**: Runs the test suite.

**Triggers**:
- Pull requests
- Push to main branch
- Manual workflow dispatch

**What it does**:
- Runs pytest with coverage reporting
- Tests all Canvas MCP tools and functionality

### security-testing.yml
**Purpose**: Security scanning and vulnerability detection.

**Triggers**:
- Pull requests
- Push to main branch
- Scheduled (weekly)

**What it does**:
- Runs Bandit for Python security issues
- Scans dependencies for known vulnerabilities
- Checks for secrets in code

## Maintenance Workflows

### weekly-maintenance.yml
**Purpose**: Automated weekly maintenance tasks.

**Triggers**:
- Scheduled (Sunday at midnight UTC)
- Manual workflow dispatch

**What it does**:
- Checks for outdated dependencies
- Reviews Canvas API compatibility
- Scans for code quality issues
- Creates maintenance report as GitHub issue

### auto-label-issues.yml
**Purpose**: Automatically labels issues based on content.

**Triggers**:
- New issues created

## Interactive Workflows

### claude.yml
**Purpose**: Interactive Claude integration for pull requests.

**Triggers**:
- Comments mentioning `@claude` in pull requests

## Workflow Best Practices

1. **Testing workflows before merge**: Most workflows have `workflow_dispatch` triggers for manual testing
2. **Skipping CI**: Use `[skip ci]` in commit messages to prevent workflow loops
3. **Protected branches**: Workflows that commit changes (like `create-release.yml`) will create PRs if main is protected
4. **Secrets management**: All workflows use GitHub secrets for authentication, never hardcode credentials

## Release Process

To create a new release:

1. **Update version files**:
   ```bash
   # Edit pyproject.toml and src/canvas_mcp/__init__.py
   git commit -am "chore: bump version to X.Y.Z"
   git push
   ```

2. **Create and push tag**:
   ```bash
   git tag vX.Y.Z
   git push origin vX.Y.Z
   ```

3. **Automated process**:
   - `publish-mcp.yml` publishes to PyPI and MCP Registry
   - `create-release.yml` creates GitHub release and updates README
   - README "Latest Release" section is automatically updated
   - GitHub repository right panel shows the new release

4. **Verify**:
   - Check GitHub releases page for new release
   - Verify README.md shows correct version
   - Confirm PyPI shows new version
   - Check MCP Registry listing

## Troubleshooting

### Release workflow fails to push README changes
- If main branch is protected, the workflow will create a PR instead
- Review and merge the PR to complete the release process

### Publish workflow fails
- Verify version numbers match in all files
- Check PyPI trusted publisher configuration
- Ensure all tests pass before tagging

### Documentation not updating
- Check if `auto-update-docs.yml` workflow ran successfully
- Review Claude Code action logs for errors
- Manually update documentation if needed
