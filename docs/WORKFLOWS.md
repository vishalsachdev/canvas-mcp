# GitHub Workflows & Branch Protection

## Overview
This document explains the GitHub Actions workflows and branch protection setup for the Canvas MCP project.

## Workflows

### 1. Auto Claude Review (`auto-claude-review.yml`)
- **Purpose**: Automatically triggers Claude code review on new PRs
- **Trigger**: When a PR is opened
- **Action**: Posts `@claude please review` comment
- **Benefits**: Ensures all PRs get reviewed without manual intervention

### 2. Claude Code (`claude.yml`) 
- **Purpose**: Responds to `@claude` mentions in comments
- **Trigger**: Comments containing `@claude`
- **Action**: Provides detailed code review and suggestions
- **Benefits**: Allows manual Claude interaction and responds to auto-triggers

### 3. Canvas MCP Enhancement Testing (`canvas-mcp-testing.yml`)
- **Purpose**: Runs project tests and performance checks
- **Trigger**: Push to main/development, PRs to main
- **Paths**: `src/canvas_mcp/tools/discussions.py`, `tests/**`
- **Action**: Runs tests, generates reports, comments on PRs

## Workflow Evolution

### Removed Workflows
- **`claude-code-review.yml`** - Removed due to redundancy
  - **Issue**: Duplicated functionality of auto-claude-review + claude workflows
  - **Problem**: OIDC token failures on fork-based PRs
  - **Solution**: Use comment-based approach instead

### Key Fixes Applied
- **Upload Artifact**: Updated from deprecated v3 to v4
- **Fork PR Support**: Added `github_token` parameter to claude.yml
- **Permissions**: Updated to `pull-requests: write` and `issues: write`

## Branch Protection

### Ruleset Configuration
The main branch is protected using GitHub Rulesets with the following rules:

#### Required Protections
- ✅ **Deletion protection** - Prevents main branch deletion
- ✅ **Force push protection** - Blocks non-fast-forward pushes  
- ✅ **Pull request requirement** - All changes must go through PRs
- ✅ **Status check requirement** - Tests and Claude review must pass

#### PR Requirements
- **1 approval required** before merging
- **Dismiss stale reviews** when new commits are pushed
- **Branches must be up to date** before merging

#### Required Status Checks
- `test-enhancements` - Canvas MCP testing workflow
- `auto-review` - Automatic Claude review workflow

### Ruleset JSON
```json
{
  "name": "Main Branch Protection",
  "target": "branch",
  "source_type": "Repository", 
  "enforcement": "active",
  "bypass_actors": [],
  "conditions": {
    "ref_name": {
      "exclude": [],
      "include": ["refs/heads/main"]
    }
  },
  "rules": [
    {
      "type": "deletion"
    },
    {
      "type": "non_fast_forward" 
    },
    {
      "type": "pull_request",
      "parameters": {
        "require_code_owner_review": false,
        "require_last_push_approval": false,
        "dismiss_stale_reviews_on_push": true,
        "required_approving_review_count": 1,
        "required_review_thread_resolution": false
      }
    },
    {
      "type": "required_status_checks",
      "parameters": {
        "strict_required_status_checks_policy": true,
        "required_status_checks": [
          {
            "context": "test-enhancements",
            "integration_id": null
          },
          {
            "context": "auto-review", 
            "integration_id": null
          }
        ]
      }
    }
  ]
}
```

## Best Practices Learned

### GitHub Actions
- ✅ Use comment-based approach for fork PR compatibility
- ✅ Keep workflows focused on single responsibilities  
- ✅ Always specify `github_token` for fork support
- ✅ Update deprecated actions promptly (upload-artifact v3→v4)
- ✅ Use proper permissions (`write` access for commenting)

### Branch Protection
- ✅ GitHub Rulesets are preferred over legacy branch protection rules
- ✅ JSON import simplifies complex ruleset configuration
- ✅ Require status checks to ensure quality gates
- ✅ Don't allow bypass permissions unless absolutely necessary

### Workflow Architecture
```
PR Created → Auto-posts @claude → Claude responds with review
Manual @claude comment → Claude responds immediately  
Code changes → Tests run → Results reported
```

## Troubleshooting

### Common Issues
1. **Fork PR failures**: Ensure `github_token` is provided in workflows
2. **OIDC token errors**: Use comment-based triggers instead of direct integration
3. **Deprecated actions**: Keep actions updated to latest versions
4. **Status check failures**: Verify workflow names match ruleset requirements

### Monitoring
- Check workflow runs in Actions tab
- Monitor PR check status
- Review Claude review quality and response times