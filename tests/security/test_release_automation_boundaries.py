"""Unchecked publisher bytes and model-held publication authority must fail."""

import hashlib
import io
import json
import os
import runpy
import tarfile
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]


def _module(name):
    script = ROOT / "scripts" / name
    assert script.is_file(), f"Missing integrity boundary: {name}"
    return runpy.run_path(str(script))


def _archive(name="mcp-publisher", kind=tarfile.REGTYPE):
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w:gz", encoding="utf-8") as archive:
        member = tarfile.TarInfo(name)
        member.type = kind
        member.linkname = "/tmp/forbidden-synthetic-target" if kind == tarfile.SYMTYPE else ""
        payload = b"#!/bin/sh\nexit 0\n" if kind == tarfile.REGTYPE else b""
        member.size = len(payload)
        archive.addfile(member, io.BytesIO(payload))
    return stream.getvalue()


@pytest.mark.parametrize("corrupt", [False, True])
def test_publisher_checks_digest_before_replacing_executable(monkeypatch, tmp_path, corrupt):
    module = _module("install_mcp_publisher.py")
    archive = _archive()
    seen = []

    def download(url, **kwargs):
        seen.append(url)
        return io.BytesIO(archive)

    monkeypatch.setattr(module["urllib"].request, "urlopen", download)
    destination = tmp_path / "mcp-publisher"
    destination.write_bytes(b"previous executable")
    digest = "0" * 64 if corrupt else hashlib.sha256(archive).hexdigest()
    if corrupt:
        with pytest.raises(ValueError, match="checksum"):
            module["install_publisher"]("v1.8.1", digest, destination)
        assert destination.read_bytes() == b"previous executable"
    else:
        module["install_publisher"]("v1.8.1", digest, destination)
        assert destination.read_bytes() == b"#!/bin/sh\nexit 0\n"
        if os.name != "nt":  # Windows has no executable bit; the publisher installs on Linux runners.
            assert destination.stat().st_mode & 0o111
    assert seen == ["https://github.com/modelcontextprotocol/registry/releases/download/v1.8.1/mcp-publisher_linux_amd64.tar.gz"]


def test_publisher_archive_cannot_install_a_symlink(monkeypatch, tmp_path):
    module = _module("install_mcp_publisher.py")
    archive = _archive(kind=tarfile.SYMTYPE)
    monkeypatch.setattr(module["urllib"].request, "urlopen", lambda *a, **k: io.BytesIO(archive))
    with pytest.raises(ValueError, match="regular file"):
        module["install_publisher"]("v1.8.1", hashlib.sha256(archive).hexdigest(), tmp_path / "publisher")
    assert not (tmp_path / "publisher").exists()


@pytest.mark.parametrize("data", [
    {"report": {"path": "/proc/self/environ"}}, {"report": ""},
    {"report": "x" * 70_000}, {"report": "text\x00hidden"},
    {"report": "report", "path": "/proc/self/environ"},
])
def test_report_publication_rejects_paths_or_invalid_data(tmp_path, data):
    module = _module("prepare_maintenance_report.py")
    output = tmp_path / "maintenance-report.md"
    with pytest.raises(ValueError):
        module["write_report"](json.dumps(data), output)
    assert not output.exists()


def test_report_shell_syntax_stays_literal_data(tmp_path):
    module = _module("prepare_maintenance_report.py")
    text = "Synthetic report\n$(touch forbidden)\n`touch forbidden`"
    output = tmp_path / "maintenance-report.md"
    module["write_report"](json.dumps({"report": text}), output)
    assert output.read_text(encoding="utf-8") == text + "\n"
    assert not (tmp_path / "forbidden").exists()


def test_agent_analysis_cannot_mint_app_tokens_or_publish_issues():
    jobs = yaml.safe_load((ROOT / ".github/workflows/weekly-maintenance.yml").read_text(encoding="utf-8"))["jobs"]
    analysis = jobs["maintenance"]
    assert analysis["permissions"].get("id-token", "none") != "write"
    assert analysis["permissions"]["issues"] == "read"
    agent = next(s for s in analysis["steps"] if "claude-code-action@" in s.get("uses", ""))
    assert agent["with"]["github_token"] == "${{ github.token }}"
    assert "gh issue create" not in agent["with"]["claude_args"]
    publish = jobs["publish-report"]
    assert publish["needs"] == "maintenance"
    assert publish["permissions"]["issues"] == "write"
    assert not any("claude-code-action" in s.get("uses", "") for s in publish["steps"])


def test_interactive_agent_uses_only_job_scoped_credentials():
    job = yaml.safe_load((ROOT / ".github/workflows/claude.yml").read_text(encoding="utf-8"))["jobs"]["claude"]
    assert job["permissions"].get("id-token", "none") != "write"
    assert job["permissions"]["contents"] == "read"
    agent = next(s for s in job["steps"] if "claude-code-action@" in s.get("uses", ""))
    assert agent["with"]["github_token"] == "${{ github.token }}"


def test_release_installer_uses_an_immutable_version_and_checksum():
    workflow = yaml.safe_load((ROOT / ".github/workflows/publish-mcp.yml").read_text(encoding="utf-8"))
    assert workflow["permissions"].get("id-token", "none") != "write"
    job = workflow["jobs"]["publish-registry"]
    step = next(s for s in job["steps"] if s.get("name") == "Install MCP Publisher")
    assert step["env"]["MCP_PUBLISHER_VERSION"].startswith("v")
    assert len(step["env"]["MCP_PUBLISHER_SHA256"]) == 64
    assert "install_mcp_publisher.py" in step["run"]
    assert "releases/latest" not in step["run"]
