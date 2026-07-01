import pytest
from unittest.mock import AsyncMock
import canvas_mcp.core.audit as audit
from canvas_mcp.core.access import routes
from canvas_mcp.core.access.store import AccessStore, InMemoryBackend, Requester
from canvas_mcp.core.access.tokens import mint_token

REQ = Requester(oid="oid-1", upn="j@x.edu", display_name="Jane Doe")
SECRET = "s"


def _seeded_store():
    s = AccessStore(InMemoryBackend(), cache_ttl_seconds=0)
    s.note_request(REQ, jti="j1", exp=1000, now_iso="2026-06-29T00:00:00Z", cooldown_hours=24)
    return s


async def _collect(send):
    # send is an AsyncMock; return concatenated body bytes + first status
    status = send.call_args_list[0][0][0]["status"]
    body = b"".join(c[0][0].get("body", b"") for c in send.call_args_list if "body" in c[0][0])
    return status, body.decode()


@pytest.mark.asyncio
async def test_approve_get_renders_confirm_for_valid_token():
    store = _seeded_store()
    token = mint_token(oid="oid-1", jti="j1", exp=1000, secret=SECRET)
    send = AsyncMock()
    await routes.handle_approve(f"token={token}".encode(), send, store=store, secret=SECRET, now=1)
    status, html = await _collect(send)
    assert status == 200 and "Jane Doe" in html and "Confirm" in html
    assert store.is_granted("oid-1") is False  # GET must NOT grant


@pytest.mark.asyncio
async def test_approve_get_invalid_token_is_generic():
    store = _seeded_store()
    send = AsyncMock()
    await routes.handle_approve(b"token=garbage", send, store=store, secret=SECRET, now=1)
    status, html = await _collect(send)
    assert status == 200 and "no longer valid" in html and "Jane Doe" not in html


@pytest.mark.asyncio
async def test_confirm_post_grants_and_audits(monkeypatch):
    store = _seeded_store()
    events = []
    monkeypatch.setattr(audit, "_access_events_enabled", True)
    monkeypatch.setattr(audit, "_emit", lambda e: events.append(e))
    token = mint_token(oid="oid-1", jti="j1", exp=1000, secret=SECRET)
    send = AsyncMock()
    await routes.handle_confirm(f"token={token}".encode(), send, store=store, secret=SECRET, now=1)
    status, html = await _collect(send)
    assert status == 200 and "granted" in html.lower()
    assert store.is_granted("oid-1") is True
    assert events and events[0]["action"] == "grant" and events[0]["entra_oid"] == "oid-1"


@pytest.mark.asyncio
async def test_confirm_post_rejects_replayed_token():
    store = _seeded_store()
    token = mint_token(oid="oid-1", jti="j1", exp=1000, secret=SECRET)
    await routes.handle_confirm(f"token={token}".encode(), AsyncMock(), store=store, secret=SECRET, now=1)
    send2 = AsyncMock()
    await routes.handle_confirm(f"token={token}".encode(), send2, store=store, secret=SECRET, now=1)
    _, html = await _collect(send2)
    assert "no longer valid" in html  # single-use enforced


@pytest.mark.asyncio
async def test_confirm_grant_failure_is_retriable(monkeypatch):
    """A transient grant-write failure must NOT consume the token: the admin
    gets a retry page (not a 500, not a spent token), and the SAME link then
    works on retry once the write succeeds."""
    store = _seeded_store()
    token = mint_token(oid="oid-1", jti="j1", exp=1000, secret=SECRET)

    calls = {"n": 0}
    real_grant = store.grant

    def flaky_grant(req, *, jti):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("azure write failed")
        return real_grant(req, jti=jti)

    monkeypatch.setattr(store, "grant", flaky_grant)

    # First Confirm: grant throws -> retry page, nothing granted, token NOT consumed
    send1 = AsyncMock()
    await routes.handle_confirm(f"token={token}".encode(), send1, store=store, secret=SECRET, now=1)
    status1, html1 = await _collect(send1)
    assert status1 == 200 and "temporary error" in html1.lower()   # retry page, no 500
    assert store.is_granted("oid-1") is False                       # not granted
    assert store.get_pending("oid-1")["status"] == "pending"        # token retriable

    # Second Confirm with the SAME token: grant now succeeds -> granted + success
    send2 = AsyncMock()
    await routes.handle_confirm(f"token={token}".encode(), send2, store=store, secret=SECRET, now=1)
    status2, html2 = await _collect(send2)
    assert status2 == 200 and "granted" in html2.lower()
    assert store.is_granted("oid-1") is True
