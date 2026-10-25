"""Importing package metadata or policy data must not start the server stack."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

import canvas_mcp


@pytest.mark.parametrize("code", [
    "import canvas_mcp; assert isinstance(canvas_mcp.__version__, str)",
    (
        "from canvas_mcp.core.tool_policy import resolve_tool_policy; "
        "assert resolve_tool_policy('none', 'http').allowed == frozenset()"
    ),
    (
        "from canvas_mcp.core.config import STUDENT_WRITE_TOOL_NAMES; "
        "assert 'submit_assignment' in STUDENT_WRITE_TOOL_NAMES"
    ),
])
def test_data_imports_do_not_load_the_server_framework(code: str) -> None:
    program = '''
import importlib.abc
import sys
class BlockServer(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] == 'fastmcp':
            raise ImportError('server framework must not load for a data import')
sys.meta_path.insert(0, BlockServer())
''' + code + "\nassert 'canvas_mcp.server' not in sys.modules"
    result = subprocess.run(
        [sys.executable, "-c", program], capture_output=True, text=True,
        encoding="utf-8", timeout=15,
        env={**os.environ, "PYTHON_DOTENV_DISABLED": "1",
             "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src")},
    )
    assert result.returncode == 0, result.stderr


def test_public_main_keeps_the_server_entry_point() -> None:
    from canvas_mcp.server import main as server_main

    assert canvas_mcp.main is server_main


def test_unknown_package_attribute_raises_attribute_error() -> None:
    with pytest.raises(AttributeError, match="no_such_attribute"):
        _ = canvas_mcp.no_such_attribute
