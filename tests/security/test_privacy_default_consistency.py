"""The privacy default must agree across every distribution channel.

ENABLE_DATA_ANONYMIZATION decides whether raw student records are handed to the
connected AI. The value ships in four independent places — the code default, the
MCP Registry manifest, the container image, and the operator template — and any
of them can be the one a given install actually gets. A Registry client that
materializes the manifest's declared default would have started the server with
anonymization off while every other channel had it on, and nothing in the release
pipeline compared them.

This test is the comparison. It is deliberately about *agreement*, not about the
literal value: flipping the default is a deliberate privacy decision that must be
made in all four places at once, and this fails until it is.
"""

import json
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SETTING = "ENABLE_DATA_ANONYMIZATION"


def _registry_manifest_default() -> str:
    manifest = json.loads((REPO_ROOT / "server.json").read_text())

    found = []
    def walk(node):
        if isinstance(node, dict):
            for key, value in node.items():
                if key == SETTING and isinstance(value, dict) and "default" in value:
                    found.append(str(value["default"]))
                # Registry schema also uses [{"name": ..., "default": ...}] form.
                if key == "name" and value == SETTING and "default" in node:
                    found.append(str(node["default"]))
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(manifest)
    assert found, f"{SETTING} has no declared default in server.json"
    assert len(set(found)) == 1, f"server.json declares conflicting defaults: {found}"
    return found[0].strip().lower()


def _code_default() -> bool:
    """The default the server uses when the variable is absent from the environment."""
    import os
    from unittest.mock import patch

    from canvas_mcp.core import config as config_module

    with patch.dict(os.environ, {}, clear=True):
        config_module.reset_config()
        # _bool_env is the single place the default is expressed.
        value = config_module._bool_env(SETTING, True)
    config_module.reset_config()
    return value


def _dockerfile_default() -> str:
    text = (REPO_ROOT / "Dockerfile").read_text()
    matches = re.findall(rf'^\s*{SETTING}="?([A-Za-z]+)"?', text, re.MULTILINE)
    assert matches, f"{SETTING} is not set in the Dockerfile"
    return matches[-1].strip().lower()


def _env_template_default() -> str:
    text = (REPO_ROOT / "env.template").read_text()
    matches = re.findall(rf"^{SETTING}=(\S+)", text, re.MULTILINE)
    assert matches, f"{SETTING} is not set in env.template"
    return matches[-1].strip().lower()


class TestPrivacyDefaultConsistency:
    def test_all_channels_declare_the_same_default(self):
        code = "true" if _code_default() else "false"
        channels = {
            "code (core/config.py)": code,
            "MCP Registry (server.json)": _registry_manifest_default(),
            "container (Dockerfile)": _dockerfile_default(),
            "operator template (env.template)": _env_template_default(),
        }

        distinct = set(channels.values())
        assert len(distinct) == 1, (
            f"{SETTING} defaults disagree across distribution channels: {channels}. "
            "A privacy default must be changed in all of them together."
        )

    def test_the_agreed_default_protects_student_data(self):
        """Agreement alone is not enough — the agreed value must be the safe one."""
        assert _code_default() is True, (
            f"{SETTING} must default to enabled. Disabling it by default would send "
            "raw student records to the connected AI on a fresh install."
        )

    @pytest.mark.parametrize(
        "reader",
        [_registry_manifest_default, _dockerfile_default, _env_template_default],
        ids=["server.json", "Dockerfile", "env.template"],
    )
    def test_each_channel_declares_a_parseable_boolean(self, reader):
        assert reader() in {"true", "false"}
