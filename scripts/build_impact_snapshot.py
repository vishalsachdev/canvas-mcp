"""Build the existing impact snapshot from validated data, never source code."""

import json
import os
import re
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any


def _count(values: Mapping[str, str], name: str) -> int:
    raw = values[name]
    if not re.fullmatch(r"[0-9]{1,20}", raw):
        raise ValueError(f"Expected a nonnegative integer count for {name}")
    return int(raw)


def build_snapshot(values: Mapping[str, str], existing: dict[str, Any]) -> dict[str, Any]:
    fields = {
        "stars": "GH_STARS", "forks": "GH_FORKS", "contributors": "GH_CONTRIBUTORS",
        "open_issues": "GH_OPEN_ISSUES", "views_14d": "GH_VIEWS_TOTAL",
        "views_14d_unique": "GH_VIEWS_UNIQUE", "clones_14d": "GH_CLONES_TOTAL",
        "clones_14d_unique": "GH_CLONES_UNIQUE",
    }
    github: dict[str, Any] = {key: _count(values, name) for key, name in fields.items()}
    referrers = json.loads(values["GH_REFERRERS"])
    if not isinstance(referrers, list):
        raise ValueError("Expected a referrer list")
    github["referrers"] = referrers
    snapshot: dict[str, Any] = {
        "collected_at": values["COLLECTED_AT"], "github": github,
        "pypi": {key: _count(values, name) for key, name in {
            "last_day": "PYPI_DAY", "last_week": "PYPI_WEEK", "last_month": "PYPI_MONTH",
        }.items()},
        "npm": {"last_month": _count(values, "NPM_MONTH")},
    }
    for family in ("pypi", "npm"):
        previous = existing.get(family, {})
        previous_month = previous.get("last_month", 0)
        if snapshot[family]["last_month"] == 0 and type(previous_month) is int and previous_month > 0:
            snapshot[family] = previous
    today = values["TODAY"]
    history = [item for item in existing.get("history", []) if item.get("date") != today]
    history.append({
        "date": today, "stars": github["stars"], "forks": github["forks"],
        "pypi_month": snapshot["pypi"]["last_month"], "npm_month": snapshot["npm"]["last_month"],
        "views_unique": github["views_14d_unique"], "clones_unique": github["clones_14d_unique"],
    })
    snapshot["history"] = sorted(history, key=lambda item: item["date"])
    return snapshot


def main() -> None:
    output = Path(os.environ["DATA_FILE"])
    existing = json.loads(output.read_text(encoding="utf-8")) if output.exists() else {"history": []}
    if not isinstance(existing, dict):
        raise ValueError("Expected an impact snapshot object")
    snapshot = build_snapshot(os.environ, existing)
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=output.parent, delete=False) as temporary:
        json.dump(snapshot, temporary, indent=2)
        path = Path(temporary.name)
    try:
        os.replace(path, output)
    finally:
        path.unlink(missing_ok=True)
    print("Updated impact snapshot.")


if __name__ == "__main__":
    main()
