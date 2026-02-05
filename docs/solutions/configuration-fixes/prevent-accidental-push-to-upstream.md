---
title: "Prevent Accidental Push to Upstream Repository"
category: configuration-fixes
tags: [git, fork, remote, upstream, safety]
module: Git Configuration
symptom: "Accidentally created PR on upstream repo when pushing to fork"
root_cause: "Git remotes not configured to block pushes to upstream"
date_solved: 2026-02-04
---

# Prevent Accidental Push to Upstream Repository

## Problem Symptom

When working on a forked repository, pushing a branch to `origin` can inadvertently create a pull request on the upstream (original) repository. GitHub's UI automatically suggests creating PRs to upstream when you push to a fork.

**What happened:**
- Pushed `feat/deanonymization` branch to origin (fork)
- GitHub auto-created draft PR #71 on `vishalsachdev/canvas-mcp` (upstream)
- User didn't intend to submit changes to the original maintainer

## Investigation Steps

1. Checked remote configuration: `git remote -v`
2. Found only `origin` was configured, pointing to the fork
3. No protection against accidentally pushing to upstream or creating PRs

## Root Cause

When you fork a repository on GitHub:
- Your fork is linked to the upstream repository
- GitHub's UI offers to create PRs to upstream whenever you push branches
- There's no git-level protection against this by default

## Working Solution

### Step 1: Add upstream remote (read-only)

```bash
# Add upstream remote for fetching updates
git remote add upstream https://github.com/ORIGINAL_OWNER/ORIGINAL_REPO.git

# Disable push to upstream by setting invalid push URL
git remote set-url --push upstream DISABLE_PUSH_TO_UPSTREAM
```

### Step 2: Verify configuration

```bash
git remote -v
```

Expected output:
```
origin    https://github.com/YOUR_USERNAME/REPO (fetch)
origin    https://github.com/YOUR_USERNAME/REPO (push)
upstream  https://github.com/ORIGINAL_OWNER/REPO.git (fetch)
upstream  DISABLE_PUSH_TO_UPSTREAM (push)
```

### Step 3: If you accidentally pushed, clean up

```bash
# Delete the remote branch
git push origin --delete branch-name

# Then manually close any auto-created PR on GitHub
```

## Safe Workflow After Fix

| Command | Effect |
|---------|--------|
| `git push` | Pushes to your fork (safe) |
| `git push origin branch` | Pushes to your fork (safe) |
| `git push upstream` | **FAILS** with error (protected) |
| `git fetch upstream` | Pulls updates from original (safe) |
| `git merge upstream/main` | Syncs your fork with original (safe) |

## Prevention Strategies

1. **Always configure upstream as read-only** when cloning a fork
2. **Document remote setup** in CLAUDE.md or README for the project
3. **Ignore GitHub's "Create PR" suggestions** after pushing to your fork
4. **Use explicit remote names**: `git push origin` instead of just `git push`

## Test Case

```bash
# This should fail if configured correctly
git push upstream main 2>&1 | grep -q "does not appear to be a git repository" && echo "PROTECTED" || echo "VULNERABLE"
```

## Related

- [GitHub Docs: Working with forks](https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/working-with-forks)
- CLAUDE.md "Fork Remote Configuration" section
