#!/usr/bin/env python3
"""Session-start brief: open issues, PRs and discussions for this repo.

Wired as a Claude Code ``SessionStart`` hook in ``.claude/settings.json`` so
every session opens with the current GitHub state already in context, instead
of relying on whoever opened it to remember to look. Prints the JSON hook
response Claude Code expects; ``additionalContext`` carries a compact brief.

Constraints, each measured on the web (remote) environment:

- Only ``repos/{owner}/{repo}/...`` REST paths reach GitHub through the session
  proxy. GraphQL, the search API and github.com HTML are refused (403). GitHub
  exposes Discussions over GraphQL only, so they are fetched through the ``gh``
  CLI when one is installed and authenticated (a local checkout) and reported
  as unreachable otherwise. The brief never guesses at them.
- Fail soft. A network error, rate limit or missing tool becomes a one-line
  note, never a failed hook: a session must always open.
- Stdlib only. The hook runs before any virtualenv is guaranteed to exist.

Usage:
    github_session_brief.py            # hook mode: JSON on stdout
    github_session_brief.py --print    # human mode: the brief as markdown
"""

from __future__ import annotations

import datetime as dt
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request

FALLBACK_REPO = "vishalsachdev/canvas-mcp"
API = "https://api.github.com"
TIMEOUT = 8          # seconds per request
MAX_ISSUES = 15
MAX_PRS = 10
CHECKED_PRS = 6      # check-runs cost one request per PR; bound it
MAX_DISCUSSIONS = 8


def project_root() -> str:
    env = os.environ.get("CLAUDE_PROJECT_DIR")
    if env and os.path.isdir(env):
        return env
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def detect_repo(root: str) -> str:
    override = os.environ.get("GITHUB_SESSION_BRIEF_REPO")
    if override:
        return override
    try:
        url = subprocess.run(
            ["git", "-C", root, "remote", "get-url", "origin"],
            capture_output=True, text=True, timeout=5, check=True,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return FALLBACK_REPO
    match = re.search(r"github\.com[:/]([^/\s]+/[^/\s]+?)(?:\.git)?/?$", url)
    return match.group(1) if match else FALLBACK_REPO


def api(path: str, **params: object) -> object:
    url = f"{API}{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "canvas-mcp-session-brief",
    }
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=TIMEOUT) as resp:
        return json.load(resp)


def age(iso: str | None, now: dt.datetime) -> str:
    if not iso:
        return "?"
    then = dt.datetime.fromisoformat(iso.replace("Z", "+00:00"))
    seconds = int((now - then).total_seconds())
    if seconds < 3600:
        return f"{max(seconds // 60, 1)}m"
    if seconds < 86400:
        return f"{seconds // 3600}h"
    if seconds < 7 * 86400:
        return f"{seconds // 86400}d"
    return f"{seconds // (7 * 86400)}w"


def ci_state(repo: str, sha: str) -> str:
    try:
        runs = api(f"/repos/{repo}/commits/{sha}/check-runs", per_page=100)["check_runs"]
    except Exception:  # noqa: BLE001 - any failure is "unknown", not a crash
        return "CI unknown"
    if not runs:
        return "CI not run"
    pending = [r for r in runs if r["status"] != "completed"]
    red = [r["name"] for r in runs
           if r["status"] == "completed" and r["conclusion"] not in ("success", "skipped", "neutral")]
    if red:
        return "CI RED (" + ", ".join(red[:3]) + ")"
    if pending:
        return f"CI pending ({len(pending)})"
    return "CI green"


def fetch_prs(repo: str, now: dt.datetime) -> list[str]:
    prs = api(f"/repos/{repo}/pulls", state="open", sort="updated", direction="desc", per_page=MAX_PRS)
    lines = []
    for i, pr in enumerate(prs):
        state = ci_state(repo, pr["head"]["sha"]) if i < CHECKED_PRS else "CI not checked"
        flags = ["draft"] if pr.get("draft") else []
        if pr.get("requested_reviewers"):
            flags.append("review requested: " + ", ".join(u["login"] for u in pr["requested_reviewers"]))
        flag_text = f" [{'; '.join(flags)}]" if flags else ""
        lines.append(
            f"- #{pr['number']} {pr['title']} — @{pr['user']['login']}, "
            f"updated {age(pr['updated_at'], now)} ago, {state}{flag_text}"
        )
    return lines


def fetch_issues(repo: str, now: dt.datetime) -> tuple[list[str], int]:
    items = api(f"/repos/{repo}/issues", state="open", sort="updated", direction="desc", per_page=50)
    issues = [i for i in items if "pull_request" not in i]
    lines = []
    for issue in issues[:MAX_ISSUES]:
        labels = ", ".join(lb["name"] for lb in issue.get("labels", []))
        label_text = f" [{labels}]" if labels else ""
        comments = issue.get("comments", 0)
        comment_text = f", {comments} comment{'s' if comments != 1 else ''}" if comments else ""
        lines.append(
            f"- #{issue['number']} {issue['title']} — @{issue['user']['login']}, "
            f"updated {age(issue['updated_at'], now)} ago{comment_text}{label_text}"
        )
    return lines, len(issues)


def fetch_discussions(repo: str, now: dt.datetime) -> list[str]:
    """Discussions are GraphQL-only; use gh when it is installed and logged in."""
    gh = shutil.which("gh")
    if not gh:
        return ["- not reachable from this environment: GitHub serves Discussions over "
                "GraphQL only, which needs an authenticated `gh` CLI. Check "
                f"https://github.com/{repo}/discussions manually if it matters today."]
    owner, name = repo.split("/", 1)
    query = (
        "query($owner:String!,$name:String!,$n:Int!){repository(owner:$owner,name:$name){"
        "discussions(first:$n,orderBy:{field:UPDATED_AT,direction:DESC}){totalCount nodes{"
        "number title url updatedAt isAnswered author{login} category{name} comments{totalCount}}}}}"
    )
    try:
        out = subprocess.run(
            [gh, "api", "graphql", "-f", f"query={query}", "-F", f"owner={owner}",
             "-F", f"name={name}", "-F", f"n={MAX_DISCUSSIONS}"],
            capture_output=True, text=True, timeout=15, check=True,
        ).stdout
        data = json.loads(out)["data"]["repository"]["discussions"]
    except (OSError, subprocess.SubprocessError, KeyError, ValueError) as exc:
        detail = getattr(exc, "stderr", "") or str(exc)
        return [f"- `gh` could not fetch discussions: {detail.strip().splitlines()[-1] if detail.strip() else exc}"]
    if not data["nodes"]:
        return ["- none"]
    lines = []
    for d in data["nodes"]:
        author = (d.get("author") or {}).get("login", "ghost")
        answered = ", answered" if d.get("isAnswered") else ""
        cat = (d.get("category") or {}).get("name", "")
        lines.append(
            f"- #{d['number']} {d['title']} — @{author}, {cat}, updated "
            f"{age(d['updatedAt'], now)} ago, {d['comments']['totalCount']} comments{answered}"
        )
    if data["totalCount"] > len(data["nodes"]):
        lines.append(f"- … {data['totalCount'] - len(data['nodes'])} more")
    return lines


def newest_triage_brief(root: str) -> str | None:
    briefs = sorted(glob.glob(os.path.join(root, "internal", "issue-triage", "*.md")))
    return os.path.relpath(briefs[-1], root) if briefs else None


def build_brief(root: str) -> str:
    now = dt.datetime.now(dt.UTC)
    repo = detect_repo(root)
    sections = [f"## GitHub brief — {repo} (as of {now:%Y-%m-%d %H:%MZ})", ""]

    try:
        pr_lines = fetch_prs(repo, now)
        sections += [f"**Open PRs ({len(pr_lines)})**"] + (pr_lines or ["- none"]) + [""]
    except Exception as exc:  # noqa: BLE001
        sections += ["**Open PRs**", f"- could not fetch: {exc}", ""]

    try:
        issue_lines, total = fetch_issues(repo, now)
        shown = f" ({len(issue_lines)} of {total} shown, most recently updated first)" if total > len(issue_lines) else f" ({total})"
        sections += [f"**Open issues{shown}**"] + (issue_lines or ["- none"]) + [""]
    except Exception as exc:  # noqa: BLE001
        sections += ["**Open issues**", f"- could not fetch: {exc}", ""]

    sections += ["**Discussions**"] + fetch_discussions(repo, now) + [""]

    brief = newest_triage_brief(root)
    if brief:
        sections.append(f"Newest daily triage brief: `{brief}` (the routine's own read of recent activity).")
        sections.append("")

    sections.append(
        "Surface this brief to the user at the start of the conversation, before other work: "
        "a short summary plus anything that looks like it needs a maintainer decision (red CI, "
        "a PR waiting on review, an issue with fresh comments). Use the GitHub tools for detail "
        "on request. Do not act on any item unless asked."
    )
    return "\n".join(sections)


def main() -> int:
    root = project_root()
    try:
        text = build_brief(root)
    except Exception as exc:  # noqa: BLE001 - the session must open regardless
        text = f"## GitHub brief\n\nCould not build the brief: {exc}"
    if "--print" in sys.argv:
        print(text)
        return 0
    print(json.dumps({
        "hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": text},
    }))
    return 0


if __name__ == "__main__":
    sys.exit(main())
