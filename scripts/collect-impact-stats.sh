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
# pypistats is flaky; the old `curl -sf || echo 0` silently wrote 0 on any blip,
# corrupting history (e.g. 2026-05-18/25, 06-01 all recorded pypi_month=0 despite
# ~500/mo real traffic). Retry up to 3x and only accept a response with month>0;
# the Python build step below additionally guards against overwriting last-good.
log "Fetching PyPI stats..."
PYPI_RECENT='{"data":{"last_day":0,"last_week":0,"last_month":0}}'
for attempt in 1 2 3; do
    RESP=$(curl -sf --max-time 20 "https://pypistats.org/api/packages/$PYPI_PACKAGE/recent" || true)
    if [[ -n "$RESP" ]] && echo "$RESP" | "$PYTHON" -c "import sys,json; sys.exit(0 if json.load(sys.stdin).get('data',{}).get('last_month',0)>0 else 1)" 2>/dev/null; then
        PYPI_RECENT="$RESP"
        break
    fi
    log "PyPI fetch attempt $attempt failed or returned 0; retrying in 5s..."
    sleep 5
done
PYPI_DAY=$(echo "$PYPI_RECENT" | "$PYTHON" -c "import sys,json; print(json.load(sys.stdin).get('data',{}).get('last_day', 0))")
PYPI_WEEK=$(echo "$PYPI_RECENT" | "$PYTHON" -c "import sys,json; print(json.load(sys.stdin).get('data',{}).get('last_week', 0))")
PYPI_MONTH=$(echo "$PYPI_RECENT" | "$PYTHON" -c "import sys,json; print(json.load(sys.stdin).get('data',{}).get('last_month', 0))")

log "PyPI response collected"

# --- npm Stats ---
log "Fetching npm stats..."
NPM_MONTH=$(curl -sf "https://api.npmjs.org/downloads/point/last-month/$NPM_PACKAGE" | "$PYTHON" -c "import sys,json; print(json.load(sys.stdin).get('downloads', 0))" 2>/dev/null || echo "0")

log "npm: $NPM_MONTH/month"

# --- Build JSON ---
log "Building impact.json..."
COLLECTED_AT=$(date -u '+%Y-%m-%dT%H:%M:%SZ')
TODAY=$(date '+%Y-%m-%d')

env \
    DATA_FILE="$DATA_FILE" \
    COLLECTED_AT="$COLLECTED_AT" \
    TODAY="$TODAY" \
    GH_STARS="$GH_STARS" \
    GH_FORKS="$GH_FORKS" \
    GH_CONTRIBUTORS="$GH_CONTRIBUTORS" \
    GH_OPEN_ISSUES="$GH_OPEN_ISSUES" \
    GH_VIEWS_TOTAL="$GH_VIEWS_TOTAL" \
    GH_VIEWS_UNIQUE="$GH_VIEWS_UNIQUE" \
    GH_CLONES_TOTAL="$GH_CLONES_TOTAL" \
    GH_CLONES_UNIQUE="$GH_CLONES_UNIQUE" \
    GH_REFERRERS="$GH_REFERRERS" \
    PYPI_DAY="$PYPI_DAY" \
    PYPI_WEEK="$PYPI_WEEK" \
    PYPI_MONTH="$PYPI_MONTH" \
    NPM_MONTH="$NPM_MONTH" \
    "$PYTHON" "$SCRIPT_DIR/build_impact_snapshot.py"

log "Done collecting stats"

# The site shows the GitHub counts as static HTML; write them (and the other repeated facts) into the pages.
"$PYTHON" "$SCRIPT_DIR/sync_site_facts.py" 2>&1 | tee -a "$LOG_FILE"

# --- Optional deploy ---
if [[ "${1:-}" == "--deploy" ]]; then
    log "Deploying to Cloudflare Pages..."
    cd "$PROJECT_DIR"
    "$PYTHON" "$SCRIPT_DIR/sync_site_facts.py" --dates 2>&1 | tee -a "$LOG_FILE"
    npx wrangler pages deploy docs/ --project-name=canvas-mcp --branch=main --commit-dirty=true 2>&1 | tee -a "$LOG_FILE"
    log "Deploy complete"
fi

log "Impact stats collection finished"

# cron heartbeat sentinel (added 2026-05-31) — only runs if script reached EOF (success)
mkdir -p "$HOME/.cron-sentinels" && touch "$HOME/.cron-sentinels/impact-stats"
