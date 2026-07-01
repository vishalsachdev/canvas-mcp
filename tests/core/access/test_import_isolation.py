"""Regression guard: the base install must import the access package and the
server WITHOUT the optional ``[hosted]`` Azure dependencies.

This runs in a SUBPROCESS with a fresh interpreter rather than reloading
modules in-process. Reloading (`importlib.reload`) mutates the already-imported
modules' globals in place, which rebinds shared classes (e.g. ``TokenClaims``,
``ConcurrencyConflict``) and pollutes class identity for every other test in the
session. A subprocess isolates that completely — and is a stronger check, since
it exercises a genuine cold import with ``azure`` blocked, not a reload of
modules that were already imported normally.
"""

import subprocess
import sys
import textwrap


def _run(script: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-c", textwrap.dedent(script)],
        capture_output=True,
        text=True,
    )


def test_core_modules_import_without_azure():
    """All access modules + the server import cold with azure unavailable."""
    result = _run(
        """
        import builtins
        _real = builtins.__import__

        def _blocked(name, globals=None, locals=None, fromlist=(), level=0):
            # Block only ABSOLUTE azure-SDK imports (level 0), faithfully
            # simulating "the [hosted] azure libs are not installed". Relative
            # imports (level > 0) like pydantic_settings' own `.azure` submodule
            # must pass through untouched.
            if level == 0 and (name == "azure" or name.startswith("azure.")):
                raise ImportError("simulated missing dependency: " + name)
            return _real(name, globals, locals, fromlist, level)

        builtins.__import__ = _blocked

        import canvas_mcp.core.access.tokens          # noqa: F401
        import canvas_mcp.core.access.store           # noqa: F401
        import canvas_mcp.core.access.notify          # noqa: F401
        import canvas_mcp.core.access.routes          # noqa: F401
        import canvas_mcp.core.access.factory         # noqa: F401
        import canvas_mcp.server                      # noqa: F401
        print("IMPORTS-OK")
        """
    )
    assert result.returncode == 0, f"stdout={result.stdout!r}\nstderr={result.stderr!r}"
    assert "IMPORTS-OK" in result.stdout


def test_factory_build_store_returns_none_without_azure():
    """build_store degrades to None (never raises) when azure is absent."""
    result = _run(
        """
        import builtins
        _real = builtins.__import__

        def _blocked(name, globals=None, locals=None, fromlist=(), level=0):
            if level == 0 and (name == "azure" or name.startswith("azure.")):
                raise ImportError("no azure")
            return _real(name, globals, locals, fromlist, level)

        builtins.__import__ = _blocked

        from types import SimpleNamespace
        from canvas_mcp.core.access import factory
        cfg = SimpleNamespace(
            access_request_enabled=True, access_token_secret="s",
            access_table_account="acct", access_table_name="t",
        )
        assert factory.build_store(cfg) is None
        print("DEGRADES-OK")
        """
    )
    assert result.returncode == 0, f"stdout={result.stdout!r}\nstderr={result.stderr!r}"
    assert "DEGRADES-OK" in result.stdout
