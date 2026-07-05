#!/usr/bin/env python
"""Submit rubric evaluations to Canvas for 3 students."""

import json
import os
import urllib.request
import urllib.parse
import urllib.error
from pathlib import Path

# Config
CANVAS_URL = os.environ.get("CANVAS_API_URL", "").rstrip("/api/v1").rstrip("/")
TOKEN = os.environ.get("CANVAS_API_TOKEN", "")
COURSE_ID = 40
ASSIGNMENT_ID = 3869

# Load token from .env if not set
if not TOKEN:
    env_path = Path(__file__).parent.parent / ".env"
    for line in env_path.read_text().splitlines():
        if line.startswith("CANVAS_API_TOKEN="):
            TOKEN = line.split("=", 1)[1].strip()
        elif line.startswith("CANVAS_API_URL="):
            CANVAS_URL = line.split("=", 1)[1].strip().rstrip("/api/v1").rstrip("/")

API_BASE = f"{CANVAS_URL}/api/v1"


def submit_rubric_grade(user_id: int, evaluation: dict, dry_run: bool = False) -> dict:
    """Submit a rubric assessment to Canvas."""
    form_data = {}
    total = 0.0

    for crit_id, ev in evaluation["evaluations"].items():
        pts = ev["points"]
        rid = ev["rating_id"]
        comment = ev.get("comment", "")
        form_data[f"rubric_assessment[{crit_id}][points]"] = str(pts)
        form_data[f"rubric_assessment[{crit_id}][rating_id]"] = str(rid)
        if comment:
            form_data[f"rubric_assessment[{crit_id}][comments]"] = comment
        total += pts

    form_data["submission[posted_grade]"] = str(total)

    url = f"{API_BASE}/courses/{COURSE_ID}/assignments/{ASSIGNMENT_ID}/submissions/{user_id}"

    if dry_run:
        print(f"  [DRY RUN] Would PUT {url}")
        print(f"  Total: {total} pts, criteria: {len(evaluation['evaluations'])}")
        return {"dry_run": True, "total": total}

    encoded = urllib.parse.urlencode(form_data).encode("utf-8")
    req = urllib.request.Request(
        url, data=encoded, method="PUT",
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Content-Type": "application/x-www-form-urlencoded",
        }
    )
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        return {"error": f"HTTP {e.code}: {body[:300]}"}


def main():
    import sys
    dry_run = "--dry-run" in sys.argv

    eval_dir = Path(__file__).parent.parent / "exports" / "evaluations"

    for eval_file in sorted(eval_dir.glob("evaluation_*.json")):
        data = json.loads(eval_file.read_text())
        user_id = data["student_id"]
        total_pts = sum(e["points"] for e in data["evaluations"].values())
        n_criteria = len(data["evaluations"])

        print(f"\nStudent {user_id} — {total_pts:.1f}/342.5 pts ({n_criteria} criteria)")

        result = submit_rubric_grade(user_id, data, dry_run=dry_run)

        if dry_run:
            pass
        elif "error" in result:
            print(f"  ERROR: {result['error']}")
        else:
            grade = result.get("grade", "?")
            score = result.get("score", "?")
            graded_at = result.get("graded_at", "?")
            print(f"  OK — grade={grade}, score={score}, graded_at={graded_at}")


if __name__ == "__main__":
    main()
