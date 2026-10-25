"""scripts/deploy_site.sh stages docs/ without the .assetsignore paths, which wrangler pages deploy does not read."""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

pytestmark = pytest.mark.skipif(
    os.name == "nt" or not shutil.which("bash") or not shutil.which("rsync"), reason="needs bash and rsync"
)


@pytest.fixture
def project(tmp_path: Path) -> Path:
    for name in ("scripts/deploy_site.sh", "scripts/sync_site_facts.py", "pyproject.toml", "tools/TOOL_MANIFEST.json",
                 "README.md"):
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(REPO_ROOT / name, tmp_path / name)
    shutil.copytree(REPO_ROOT / "skills", tmp_path / "skills")
    shutil.copytree(REPO_ROOT / "docs", tmp_path / "docs")
    for leak in ("docs/triage/2026-01-01.md", "docs/superpowers/plans/plan.md", "docs/ops.local.md"):
        (tmp_path / leak).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / leak).write_text("internal\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.com", "add", "-A"], cwd=tmp_path, check=True)
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-qm", "x"], cwd=tmp_path,
                   check=True)
    return tmp_path


def dry_run(project: Path, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["bash", str(project / "scripts/deploy_site.sh"), "--dry-run"], cwd=project,
                          capture_output=True, text=True, env={**os.environ, **(env or {})})


def test_staging_drops_every_ignored_path_and_keeps_the_site(project: Path):
    result = dry_run(project)
    assert result.returncode == 0, result.stderr
    staged = set(result.stdout.split("\n"))
    assert {"index.html", "llms.txt", "sitemap.xml", "robots.txt"} <= staged
    assert not [p for p in staged if p.startswith(("triage/", "audits/", "superpowers/")) or p.endswith(".local.md")]
    assert ".assetsignore" not in staged


def test_refuses_to_deploy_when_an_ignored_path_is_staged(project: Path, tmp_path_factory):
    # An rsync that ignores --exclude-from stands in for any staging step that lets a path through.
    fake = tmp_path_factory.mktemp("bin") / "rsync"
    fake.write_text('#!/bin/bash\nsrc="${@: -2:1}"; dst="${@: -1}"; cp -R "$src". "$dst"\n', encoding="utf-8")
    fake.chmod(0o755)
    result = dry_run(project, {"PATH": f"{fake.parent}{os.pathsep}{os.environ['PATH']}"})
    assert result.returncode != 0
    assert "Refusing to deploy" in result.stderr
    assert "superpowers" in result.stderr and "ops.local.md" in result.stderr


def test_unsupported_ignore_syntax_is_refused(project: Path):
    ignore = project / "docs/.assetsignore"
    ignore.write_text(ignore.read_text(encoding="utf-8") + "docs/**/drafts\n", encoding="utf-8")
    result = dry_run(project)
    assert result.returncode != 0
    assert "does not model" in result.stderr and "docs/**/drafts" in result.stderr


def test_dry_run_changes_no_tracked_file(project: Path):
    assert dry_run(project).returncode == 0
    status = subprocess.run(["git", "status", "--porcelain"], cwd=project, capture_output=True, text=True, check=True)
    assert status.stdout == ""


def test_deploys_when_home_env_has_no_cloudflare_token(project: Path, tmp_path_factory):
    # A ~/.env without CF_API_TOKEN must leave wrangler to its own login, not stop the script under set -e.
    home = tmp_path_factory.mktemp("home")
    (home / ".env").write_text("OTHER_KEY=1\n", encoding="utf-8")
    bin_dir = tmp_path_factory.mktemp("bin")
    calls = bin_dir / "npx-calls"
    npx = bin_dir / "npx"
    npx.write_text(f'#!/bin/bash\necho "token=${{CLOUDFLARE_API_TOKEN:-unset}} $*" > "{calls}"\n', encoding="utf-8")
    npx.chmod(0o755)
    env = {**os.environ, "HOME": str(home), "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}"}
    env.pop("CLOUDFLARE_API_TOKEN", None)
    result = subprocess.run(["bash", str(project / "scripts/deploy_site.sh")], cwd=project, capture_output=True,
                            text=True, env=env)
    assert result.returncode == 0, result.stderr
    call = calls.read_text(encoding="utf-8")
    assert call.startswith("token=unset ") and "wrangler pages deploy" in call and "--project-name=canvas-mcp" in call
