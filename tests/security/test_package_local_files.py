"""Allowing operator briefs, credential files or agent scratch into a package must fail."""

import io
import runpy
import tarfile
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("name", ["BRIEF.md", ".env", ".superpowers/sdd/PLAN/progress.md", "internal/ops.local.md"])
@pytest.mark.parametrize("kind", ["wheel", "sdist"])
def test_packages_refuse_local_only_files(tmp_path, name, kind):
    script = ROOT / "scripts/check_package_contents.py"
    assert script.exists(), "Missing package publication privacy gate"
    check = runpy.run_path(str(script))["check_package"]
    if kind == "wheel":
        path = tmp_path / "synthetic.whl"
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr(name, "synthetic operator data")
    else:
        path = tmp_path / "synthetic.tar.gz"
        with tarfile.open(path, "w:gz", encoding="utf-8") as archive:
            member = tarfile.TarInfo("synthetic/" + name)
            body = b"synthetic operator data"
            member.size = len(body)
            archive.addfile(member, io.BytesIO(body))
    with pytest.raises(ValueError, match="local-only"):
        check(path)


def test_wheel_with_bundled_code_api_is_accepted(tmp_path):
    script = ROOT / "scripts/check_package_contents.py"
    assert script.exists(), "Missing package publication privacy gate"
    path = tmp_path / "synthetic.whl"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("canvas_mcp/core/html.py", "synthetic source")
        archive.writestr("canvas_mcp/code_api/client.ts", "synthetic source")
    runpy.run_path(str(script))["check_package"](path)
