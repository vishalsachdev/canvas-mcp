#!/bin/bash
# Deploy docs/ to Cloudflare Pages without the paths that docs/.assetsignore lists.
#
# `wrangler pages deploy` does not read .assetsignore (that file is a Workers static-assets feature), so a plain
# `wrangler pages deploy docs/` published triage/, audits/ and superpowers/. This script copies docs/ to a staging
# directory without those paths, refuses to deploy if one got through, and deploys the copy.
#
# Usage: ./scripts/deploy_site.sh [--dry-run]
#   --dry-run: stage, check and list the files; do not deploy

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
PYTHON="${PYTHON:-python3}"
STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT

# Write the repeated facts and the sitemap dates into the pages first.
"$PYTHON" "$SCRIPT_DIR/sync_site_facts.py" --dates

rsync -a --exclude-from="$PROJECT_DIR/docs/.assetsignore" --exclude=.assetsignore "$PROJECT_DIR/docs/" "$STAGE/"

# The same patterns, read independently of rsync: a gitignore-style "dir/" names a directory at any depth, and any
# other pattern matches a file name.
"$PYTHON" - "$PROJECT_DIR/docs/.assetsignore" "$STAGE" <<'PY'
import fnmatch
import sys
from pathlib import Path

ignore, stage = Path(sys.argv[1]), Path(sys.argv[2])
patterns = [line.strip() for line in ignore.read_text(encoding="utf-8").splitlines()]
patterns = [p for p in patterns if p and not p.startswith("#")]
leaked = []
for path in stage.rglob("*"):
    rel = path.relative_to(stage)
    for pattern in patterns:
        if pattern.endswith("/"):
            hit = path.is_dir() and fnmatch.fnmatch(path.name, pattern.rstrip("/"))
        else:
            hit = fnmatch.fnmatch(path.name, pattern)
        if hit or rel.name == ".assetsignore":
            leaked.append(str(rel))
if leaked:
    sys.exit("Refusing to deploy; excluded paths are staged: " + ", ".join(sorted(set(leaked))))
PY

if [[ "${1:-}" == "--dry-run" ]]; then
    (cd "$STAGE" && find . -type f | sed 's|^\./||' | sort)
    exit 0
fi

if [[ -z "${CLOUDFLARE_API_TOKEN:-}" && -f "$HOME/.env" ]]; then
    CLOUDFLARE_API_TOKEN="$(grep '^CF_API_TOKEN=' "$HOME/.env" | cut -d= -f2- | tr -d '"')"
    export CLOUDFLARE_API_TOKEN
fi
cd "$PROJECT_DIR"
npx --yes wrangler pages deploy "$STAGE" --project-name=canvas-mcp --branch=main --commit-dirty=true
