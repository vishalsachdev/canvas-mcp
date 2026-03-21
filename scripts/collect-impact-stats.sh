#!/bin/bash
# Canvas MCP Impact Stats Collector
# Collects GitHub, PyPI, and npm stats into docs/data/impact.json
# Designed to run weekly via launchd or manually via /impact-stats skill
#
# Requirements: gh (GitHub CLI), curl, python3 (Homebrew)
# Usage: ./scripts/collect-impact-stats.sh [--deploy]
#   --deploy: also deploy to Cloudflare Pages after collecting

set -euo pipefail

REPO="vishalsachdev/canvas-mcp"
PYPI_PACKAGE="canvas-mcp"
NPM_PACKAGE="canvas-mcp"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
DATA_FILE="$PROJECT_DIR/docs/data/impact.json"
LOG_FILE="/tmp/canvas-mcp-impact-stats.log"
PYTHON="/opt/homebrew/bin/python3"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"; }

log "Starting impact stats collection"

# --- GitHub Stats ---
log "Fetching GitHub stats..."
GH_REPO=$(gh api "repos/$REPO" 2>/dev/null || echo '{}')
GH_STARS=$(echo "$GH_REPO" | "$PYTHON" -c "import sys,json; print(json.load(sys.stdin).get('stargazers_count', 0))")
GH_FORKS=$(echo "$GH_REPO" | "$PYTHON" -c "import sys,json; print(json.load(sys.stdin).get('forks_count', 0))")
GH_OPEN_ISSUES=$(echo "$GH_REPO" | "$PYTHON" -c "import sys,json; print(json.load(sys.stdin).get('open_issues_count', 0))")

GH_CONTRIBUTORS=$(gh api "repos/$REPO/contributors?per_page=100" 2>/dev/null | "$PYTHON" -c "import sys,json; print(len(json.load(sys.stdin)))" || echo "0")

# Traffic (14-day rolling window — this is why we collect weekly)
GH_VIEWS=$(gh api "repos/$REPO/traffic/views" 2>/dev/null || echo '{"count":0,"uniques":0}')
GH_VIEWS_TOTAL=$(echo "$GH_VIEWS" | "$PYTHON" -c "import sys,json; print(json.load(sys.stdin).get('count', 0))")
GH_VIEWS_UNIQUE=$(echo "$GH_VIEWS" | "$PYTHON" -c "import sys,json; print(json.load(sys.stdin).get('uniques', 0))")

GH_CLONES=$(gh api "repos/$REPO/traffic/clones" 2>/dev/null || echo '{"count":0,"uniques":0}')
GH_CLONES_TOTAL=$(echo "$GH_CLONES" | "$PYTHON" -c "import sys,json; print(json.load(sys.stdin).get('count', 0))")
GH_CLONES_UNIQUE=$(echo "$GH_CLONES" | "$PYTHON" -c "import sys,json; print(json.load(sys.stdin).get('uniques', 0))")

GH_REFERRERS=$(gh api "repos/$REPO/traffic/popular/referrers" 2>/dev/null || echo '[]')

log "GitHub: $GH_STARS stars, $GH_FORKS forks, $GH_CONTRIBUTORS contributors"

# --- PyPI Stats ---
log "Fetching PyPI stats..."
PYPI_RECENT=$(curl -sf "https://pypistats.org/api/packages/$PYPI_PACKAGE/recent" || echo '{"data":{"last_day":0,"last_week":0,"last_month":0}}')
PYPI_DAY=$(echo "$PYPI_RECENT" | "$PYTHON" -c "import sys,json; print(json.load(sys.stdin).get('data',{}).get('last_day', 0))")
PYPI_WEEK=$(echo "$PYPI_RECENT" | "$PYTHON" -c "import sys,json; print(json.load(sys.stdin).get('data',{}).get('last_week', 0))")
PYPI_MONTH=$(echo "$PYPI_RECENT" | "$PYTHON" -c "import sys,json; print(json.load(sys.stdin).get('data',{}).get('last_month', 0))")

log "PyPI: $PYPI_DAY/day, $PYPI_WEEK/week, $PYPI_MONTH/month"

# --- npm Stats ---
log "Fetching npm stats..."
NPM_MONTH=$(curl -sf "https://api.npmjs.org/downloads/point/last-month/$NPM_PACKAGE" | "$PYTHON" -c "import sys,json; print(json.load(sys.stdin).get('downloads', 0))" 2>/dev/null || echo "0")

log "npm: $NPM_MONTH/month"

# --- Build JSON ---
log "Building impact.json..."
COLLECTED_AT=$(date -u '+%Y-%m-%dT%H:%M:%SZ')
TODAY=$(date '+%Y-%m-%d')

"$PYTHON" << PYEOF
import json, os

data_file = "$DATA_FILE"
existing = {"history": []}
if os.path.exists(data_file):
    with open(data_file) as f:
        existing = json.load(f)

# Build new snapshot
snapshot = {
    "collected_at": "$COLLECTED_AT",
    "github": {
        "stars": $GH_STARS,
        "forks": $GH_FORKS,
        "contributors": $GH_CONTRIBUTORS,
        "open_issues": $GH_OPEN_ISSUES,
        "views_14d": $GH_VIEWS_TOTAL,
        "views_14d_unique": $GH_VIEWS_UNIQUE,
        "clones_14d": $GH_CLONES_TOTAL,
        "clones_14d_unique": $GH_CLONES_UNIQUE,
        "referrers": json.loads('''$GH_REFERRERS''')
    },
    "pypi": {
        "last_day": $PYPI_DAY,
        "last_week": $PYPI_WEEK,
        "last_month": $PYPI_MONTH
    },
    "npm": {
        "last_month": $NPM_MONTH
    }
}

# Append to history (deduplicate by date)
history = existing.get("history", [])
history = [h for h in history if h.get("date") != "$TODAY"]
history.append({
    "date": "$TODAY",
    "stars": $GH_STARS,
    "forks": $GH_FORKS,
    "pypi_month": $PYPI_MONTH,
    "npm_month": $NPM_MONTH,
    "views_unique": $GH_VIEWS_UNIQUE,
    "clones_unique": $GH_CLONES_UNIQUE
})
history.sort(key=lambda x: x["date"])
snapshot["history"] = history

with open(data_file, "w") as f:
    json.dump(snapshot, f, indent=2)

print(f"Written to {data_file} ({len(history)} history entries)")
PYEOF

log "Done collecting stats"

# --- Optional deploy ---
if [[ "${1:-}" == "--deploy" ]]; then
    log "Deploying to Cloudflare Pages..."
    cd "$PROJECT_DIR"
    npx wrangler pages deploy docs/ --project-name=canvas-mcp --branch=main --commit-dirty=true 2>&1 | tee -a "$LOG_FILE"
    log "Deploy complete"
fi

log "Impact stats collection finished"
