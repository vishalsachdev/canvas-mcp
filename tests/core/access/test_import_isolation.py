import builtins
import importlib
import pytest


def test_core_modules_import_without_azure(monkeypatch):
    """Simulate azure not installed: importing access modules must still work."""
    real_import = builtins.__import__

    def blocked(name, *args, **kwargs):
        if name.startswith("azure"):
            raise ImportError(f"simulated missing dependency: {name}")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", blocked)
    for mod in ("canvas_mcp.core.access.tokens", "canvas_mcp.core.access.store",
                "canvas_mcp.core.access.notify", "canvas_mcp.core.access.routes",
                "canvas_mcp.core.access.factory", "canvas_mcp.server"):
        importlib.reload(importlib.import_module(mod))  # must not raise


def test_factory_build_store_returns_none_without_azure(monkeypatch):
    import builtins
    from types import SimpleNamespace
    from canvas_mcp.core.access import factory
    real_import = builtins.__import__

    def blocked(name, *args, **kwargs):
        if name.startswith("azure"):
            raise ImportError("no azure")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", blocked)
    cfg = SimpleNamespace(access_request_enabled=True, access_token_secret="s",
                          access_table_account="acct", access_table_name="t")
    assert factory.build_store(cfg) is None  # degrades, does not raise
