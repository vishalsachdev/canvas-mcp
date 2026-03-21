# Canvas MCP Impact Tracker — Implementation Plan

## Goal
Automated weekly collection of GitHub + PyPI + npm stats, with a live "Impact" section on canvas-mcp.illinihunt.org that updates automatically.

## Architecture

### Data Collection Script
Location: `/Users/vishal/code/canvas-mcp/scripts/collect-impact-stats.sh`

Collects from 3 sources into a single JSON file (`docs/data/impact.json`):

1. **GitHub** (via `gh api`): stars, forks, contributors, open issues, traffic views/clones/referrers
2. **PyPI** (via pypistats.org API): recent downloads (day/week/month), all-time estimate
3. **npm** (via api.npmjs.org): last-month downloads, total

Output schema:
```json
{
  "collected_at": "2026-03-20T12:00:00Z",
  "github": { "stars": 81, "forks": 30, "contributors": 9, "views_14d": 1230, "clones_14d": 801 },
  "pypi": { "last_day": 20, "last_week": 104, "last_month": 504 },
  "npm": { "last_month": 107 },
  "history": [
    { "date": "2026-03-20", "stars": 81, "pypi_month": 504, "npm_month": 107 }
  ]
}
```

### Website Section
Add to `docs/index.html` — a new "Impact" card/section that reads `docs/data/impact.json` via fetch and renders:
- Total downloads badge (PyPI + npm combined)
- GitHub stars + forks
- Sparkline or simple trend (if history array has 4+ entries)
- "Last updated" timestamp

### Automation Options (pick one)

#### Option A: launchd (local Mac, weekly)
- Plist at `~/Library/LaunchAgents/com.canvas-mcp.impact-stats.plist`
- Runs every Monday at 7am CT
- Script collects stats → writes JSON → runs `wrangler pages deploy`
- Pro: No GitHub Actions needed (which is disabled)
- Con: Only runs when Mac is on

#### Option B: VPS cron (hosted, weekly)
- Add cron job on VPS (76.13.122.44) — already running the MCP server
- `0 7 * * 1 /path/to/collect-impact-stats.sh >> /tmp/impact-stats.log 2>&1`
- Pro: Always-on, reliable
- Con: Needs gh CLI + npm/curl on VPS

#### Option C: Claude Code /schedule trigger
- Use `/schedule` to create a weekly remote agent trigger
- Agent collects stats, updates JSON, deploys
- Pro: No infra to manage
- Con: Newer feature, may have limits

### Recommended: Option A (launchd) + manual fallback
- launchd for weekly auto-collection (you're on your Mac most days)
- `/impact-stats` slash command for on-demand refresh (before talks, etc.)

## Implementation Steps

1. [ ] Create `scripts/collect-impact-stats.sh` (bash, uses gh + curl)
2. [ ] Create `docs/data/impact.json` (initial snapshot)
3. [ ] Add Impact section to `docs/index.html` (fetches JSON, renders cards)
4. [ ] Create launchd plist for weekly execution
5. [ ] Create `/impact-stats` skill for on-demand refresh
6. [ ] Deploy to Cloudflare Pages
7. [ ] Test end-to-end (collect → JSON → deploy → verify on site)

## Critical Notes
- GitHub traffic API only retains 14 days — MUST collect weekly or data is lost
- GitHub Actions is disabled — can't use the existing github-stats-tracker workflow
- Use `/opt/homebrew/bin/python3` in any local scripts (per CLAUDE.md cron rules)
- Always log output for debuggability
- `wrangler pages deploy` required after updating docs/ (no auto-deploy)
