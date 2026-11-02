from datetime import UTC
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from canvas_mcp.core.access.store import AccessStore, InMemoryBackend, Requester
from canvas_mcp.server import _cmd_list_grants, _cmd_revoke


def _store_with_one():
    s = AccessStore(InMemoryBackend(), cache_ttl_seconds=0)
    s.grant(Requester("oid-1", "j@x.edu", "Jane Doe"), jti="j1")
    return s


def test_list_grants_prints_rows(capsys):
    with patch("canvas_mcp.server._access_store", return_value=_store_with_one()):
        rc = _cmd_list_grants(SimpleNamespace())
    out = capsys.readouterr().out
    assert rc == 0 and "oid-1" in out and "Jane Doe" in out


def test_revoke_removes_and_reports(capsys):
    store = _store_with_one()
    with patch("canvas_mcp.server._access_store", return_value=store):
        rc = _cmd_revoke(SimpleNamespace(revoke="oid-1"))
    assert rc == 0 and store.is_granted("oid-1") is False
    assert "revoked" in capsys.readouterr().out.lower()


def test_revoke_unknown_oid_reports_not_found(capsys):
    with patch("canvas_mcp.server._access_store", return_value=_store_with_one()):
        rc = _cmd_revoke(SimpleNamespace(revoke="nope"))
    assert rc == 1 and "not found" in capsys.readouterr().out.lower()


def test_server_config_output_stdio_pat_and_oauth(tmp_path, monkeypatch, capsys):
    from datetime import datetime

    from pydantic import SecretStr

    from canvas_mcp import server
    from canvas_mcp.auth.models import OAuthUser, StoredTokens
    from canvas_mcp.auth.store import TokenStore
    from canvas_mcp.core import config as config_module

    # 1. With PAT
    monkeypatch.setenv("CANVAS_API_TOKEN", "pat-tok")
    monkeypatch.setenv("CANVAS_API_URL", "https://canvas.example.edu/api/v1")
    config_module.reset_config()

    with pytest.raises(SystemExit) as exc:
        server.main(["--config"])
    assert exc.value.code == 0
    err = capsys.readouterr().err
    assert "Authentication: PAT" in err

    # 2. With mobile OAuth (PAT empty)
    monkeypatch.delenv("CANVAS_API_TOKEN", raising=False)
    config_module.reset_config()

    store_file = tmp_path / "tokens.json"
    now = datetime.now(UTC)
    store = TokenStore(store_file)
    store.save(
        StoredTokens(
            canvas_domain="canvas.example.edu",
            access_token=SecretStr("acc"),
            refresh_token=SecretStr("ref"),
            client_id="cid",
            client_secret=SecretStr("sec"),
            obtained_at=now,
            last_refreshed_at=now,
            user=OAuthUser(id=1, name="Test User"),
        )
    )

    with patch("canvas_mcp.auth.session.TokenStore", return_value=store):
        with pytest.raises(SystemExit) as exc:
            server.main(["--config"])
        assert exc.value.code == 0
        err = capsys.readouterr().err
        assert "Authentication: mobile OAuth" in err
        assert "acc" not in err
        assert "ref" not in err
        assert "sec" not in err


def test_server_test_flag_with_oauth(tmp_path, monkeypatch):
    from datetime import datetime

    import httpx
    from pydantic import SecretStr

    from canvas_mcp import server
    from canvas_mcp.auth.models import OAuthUser, StoredTokens
    from canvas_mcp.auth.store import TokenStore
    from canvas_mcp.core import config as config_module

    monkeypatch.delenv("CANVAS_API_TOKEN", raising=False)
    monkeypatch.setenv("CANVAS_API_URL", "https://canvas.example.edu/api/v1")
    config_module.reset_config()

    store_file = tmp_path / "tokens.json"
    now = datetime.now(UTC)
    store = TokenStore(store_file)
    store.save(
        StoredTokens(
            canvas_domain="canvas.example.edu",
            access_token=SecretStr("acc"),
            refresh_token=SecretStr("ref"),
            client_id="cid",
            client_secret=SecretStr("sec"),
            obtained_at=now,
            last_refreshed_at=now,
            user=OAuthUser(id=1, name="Test User"),
        )
    )

    def mock_handler(request: httpx.Request) -> httpx.Response:
        assert request.headers.get("Authorization") == "Bearer acc"
        return httpx.Response(200, json={"id": 1, "name": "Test User"})

    transport = httpx.MockTransport(mock_handler)

    with patch("canvas_mcp.auth.session.TokenStore", return_value=store):
        with patch(
            "canvas_mcp.core.client._get_http_client",
            return_value=httpx.AsyncClient(
                transport=transport, headers={"Authorization": "Bearer acc"}
            ),
        ):
            with pytest.raises(SystemExit) as exc:
                server.main(["--test"])
            assert exc.value.code == 0
