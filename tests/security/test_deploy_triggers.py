"""Production deploys only on a release tag or a manual run from main.

deploy-prod.yml used to run on every push to main, so any merged pull request,
including an automated dependency bump, reached production with no deliberate
step. These are policy assertions: a future edit that restores the push-to-main
trigger, or drops the branch guard on manual runs, fails here instead of
shipping.
"""

from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

ROOT = Path(__file__).resolve().parents[2]
PROD_WORKFLOWS = [
    ROOT / ".github" / "workflows" / "deploy-prod.yml",
    # The template other deployments copy should teach the same policy.
    ROOT / "deploy" / "azure" / "deploy-prod.yml.sample",
]
BRANCH_GUARD = "github.ref == 'refs/heads/main' || startsWith(github.ref, 'refs/tags/v')"


def _triggers(workflow: dict) -> dict:
    # PyYAML follows YAML 1.1, which parses the bare key `on` as boolean True.
    return workflow.get("on", workflow.get(True)) or {}


def _policy_violations(workflow: dict) -> list[str]:
    problems = []
    triggers = _triggers(workflow)
    if triggers.get("push") != {"tags": ["v*"]}:
        problems.append(f"push trigger must be release tags only, got {triggers.get('push')!r}")
    if "workflow_dispatch" not in triggers:
        problems.append("manual runs (workflow_dispatch) must stay available")
    for name, job in workflow.get("jobs", {}).items():
        if job.get("if") != BRANCH_GUARD:
            problems.append(f"job {name!r} must guard manual runs with {BRANCH_GUARD!r}")
    return problems


@pytest.mark.parametrize("path", PROD_WORKFLOWS, ids=lambda p: p.name)
def test_production_deploys_only_on_release_or_manual_run(path):
    assert _policy_violations(yaml.safe_load(path.read_text(encoding="utf-8"))) == []


def test_the_policy_rejects_the_old_push_to_main_trigger():
    old = yaml.safe_load(
        """
on:
  push:
    branches: [main]
    paths-ignore: ['docs/**', '**.md', 'tools/**']
  workflow_dispatch: {}
jobs:
  build-and-deploy:
    runs-on: ubuntu-latest
"""
    )
    problems = _policy_violations(old)
    assert any("push trigger" in p for p in problems)
    assert any("guard manual runs" in p for p in problems)
