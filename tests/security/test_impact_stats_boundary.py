"""Remote statistics interpolated into Python source must fail these cases."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _run_build(tmp_path, changes):
    source = (ROOT / "scripts/collect-impact-stats.sh").read_text(encoding="utf-8")
    # Run the actual shell-to-Python boundary; collection, deployment and the
    # production heartbeat are outside this block and never run in these tests.
    block = source.split("# --- Build JSON ---", 1)[1].split('log "Done collecting stats"', 1)[0]
    block = "log() { :; }\n" + block
    output = tmp_path / "impact.json"
    existing = {"pypi": {"last_day": 1, "last_week": 2, "last_month": 9},
                "npm": {"last_month": 8}, "history": []}
    output.write_text(json.dumps(existing), encoding="utf-8")
    env = {**os.environ, "PYTHON": sys.executable, "SCRIPT_DIR": str(ROOT / "scripts"),
           "DATA_FILE": str(output), "GH_REFERRERS": "[]"}
    for field in ["GH_STARS", "GH_FORKS", "GH_CONTRIBUTORS", "GH_OPEN_ISSUES",
                  "GH_VIEWS_TOTAL", "GH_VIEWS_UNIQUE", "GH_CLONES_TOTAL", "GH_CLONES_UNIQUE",
                  "PYPI_DAY", "PYPI_WEEK", "PYPI_MONTH", "NPM_MONTH"]:
        env[field] = "3"
    env.update(changes)
    result = subprocess.run(["bash", "-eu", "-c", block], cwd=tmp_path, env=env,
                            capture_output=True, text=True, encoding="utf-8", timeout=10)
    return result, json.loads(output.read_text(encoding="utf-8")), existing


@pytest.mark.parametrize("field", ["PYPI_WEEK", "NPM_MONTH", "GH_STARS"])
def test_remote_counter_cannot_execute_python(tmp_path, field):
    marker = tmp_path / "forbidden"
    attack = f"__import__('pathlib').Path({str(marker)!r}).write_text('executed')"
    result, stored, existing = _run_build(tmp_path, {field: attack})
    assert not marker.exists(), "Remote count was executed as Python"
    assert result.returncode != 0
    assert stored == existing


def test_valid_statistics_are_numeric_and_keep_last_good_values(tmp_path):
    result, stored, _ = _run_build(tmp_path, {"PYPI_MONTH": "0", "NPM_MONTH": "0"})
    assert result.returncode == 0, result.stderr
    assert stored["github"]["stars"] == 3
    assert stored["pypi"] == {"last_day": 1, "last_week": 2, "last_month": 9}
    assert stored["npm"]["last_month"] == 8
    assert stored["history"][0]["pypi_month"] == 9


@pytest.mark.parametrize("value", ["-1", "True", "3.5", "null", "3\n4"])
def test_invalid_counter_does_not_replace_previous_snapshot(tmp_path, value):
    result, stored, existing = _run_build(tmp_path, {"PYPI_WEEK": value})
    assert result.returncode != 0
    assert stored == existing
