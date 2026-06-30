from types import SimpleNamespace
from unittest.mock import patch

from canvas_mcp.server import _cmd_list_grants, _cmd_revoke
from canvas_mcp.core.access.store import AccessStore, InMemoryBackend, Requester


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
