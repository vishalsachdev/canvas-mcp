"""Least-privilege policy for AI-driven GitHub workflows.

The weekly maintenance job feeds untrusted input — public issue text and web
search results, both writable by anyone — into a model that simultaneously
holds a GITHUB_TOKEN. Prompt injection in that input is not reliably
preventable, so the control is the token: it must not be able to do more than
the job's one legitimate output, filing a maintenance issue.

These are policy assertions, not behavior tests. They exist so a future edit
that re-broadens the token or the tool allowlist fails here rather than in
production.
"""

from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

WORKFLOWS = Path(__file__).resolve().parents[2] / ".github" / "workflows"
AI_WORKFLOW = WORKFLOWS / "weekly-maintenance.yml"

# Permissions that let a hijacked run alter code or merge state.
FORBIDDEN_WRITE_SCOPES = {"contents", "pull-requests", "packages", "actions",
                          "deployments", "security-events"}


def _load(path: Path) -> dict:
    return yaml.safe_load(path.read_text())


@pytest.mark.skipif(not AI_WORKFLOW.exists(), reason="workflow not present")
class TestWeeklyMaintenancePermissions:
    def test_no_write_scope_beyond_issues(self):
        job = _load(AI_WORKFLOW)["jobs"]["maintenance"]
        permissions = job.get("permissions", {})

        granted_writes = {
            scope
            for scope, level in permissions.items()
            if level == "write" and scope in FORBIDDEN_WRITE_SCOPES
        }
        assert not granted_writes, (
            f"weekly-maintenance grants write on {sorted(granted_writes)}. It "
            "reads untrusted issue and web content, and only needs to file an issue."
        )

    def test_issues_write_is_still_granted(self):
        """The job must remain able to do its one job."""
        job = _load(AI_WORKFLOW)["jobs"]["maintenance"]
        assert job.get("permissions", {}).get("issues") == "write"

    def test_gh_is_not_unrestricted(self):
        job = _load(AI_WORKFLOW)["jobs"]["maintenance"]
        args = " ".join(
            str(step.get("with", {}).get("claude_args", "")) for step in job["steps"]
        )

        assert "Bash(gh:*)" not in args, (
            "Bash(gh:*) permits any GitHub mutation the token allows, including "
            "`gh api` against arbitrary endpoints"
        )
        assert "gh issue create" in args, "the job still needs to file its report"

    def test_untrusted_input_is_framed_as_data(self):
        """The prompt should tell the model that fetched content is not instructions."""
        text = AI_WORKFLOW.read_text().lower()
        assert "untrusted" in text, (
            "the prompt does not mark issue/web content as untrusted data"
        )


def _tool_args_in(path: Path) -> list[str]:
    """Collect every step's tool-permission argument from a workflow.

    Parsed from the YAML rather than grepped from the raw text: a comment that
    merely *names* an unsafe setting is documentation, not configuration, and a
    policy gate that cannot tell those apart trains people to ignore it.
    """
    try:
        doc = _load(path) or {}
    except yaml.YAMLError:
        return []

    found: list[str] = []
    for job in (doc.get("jobs") or {}).values():
        for step in (job or {}).get("steps") or []:
            with_block = (step or {}).get("with") or {}
            for key in ("claude_args", "args", "allowed_tools", "allowed-tools"):
                if key in with_block:
                    found.append(str(with_block[key]))
    return found


class TestNoWorkflowReintroducesUnrestrictedGh:
    """A repo-wide sweep, so a new AI workflow inherits the same rule."""

    def test_no_workflow_grants_unrestricted_gh(self):
        offenders = [
            path.name
            for path in sorted(WORKFLOWS.glob("*.yml"))
            if any("Bash(gh:*)" in arg for arg in _tool_args_in(path))
        ]
        assert not offenders, f"unrestricted gh access in: {offenders}"

    def test_the_sweep_would_actually_catch_it(self, tmp_path):
        """Guard against a sweep that passes because it inspects nothing."""
        sample = tmp_path / "bad.yml"
        sample.write_text(
            "jobs:\n"
            "  j:\n"
            "    steps:\n"
            "      - with:\n"
            '          claude_args: \'--allowed-tools "Bash(gh:*),Read"\'\n'
        )
        assert any("Bash(gh:*)" in arg for arg in _tool_args_in(sample))
