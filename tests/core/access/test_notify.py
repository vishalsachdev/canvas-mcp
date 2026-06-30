import pytest
from canvas_mcp.core.access.notify import build_request_email, notify_access_request
from canvas_mcp.core.access.store import AccessStore, InMemoryBackend, Requester

REQ = Requester(oid="oid-1", upn="j@x.edu", display_name="Jane Doe")


def test_email_contains_identity_and_link():
    msg = build_request_email(REQ, "https://h.edu/admin/access/approve?token=abc")
    assert "Jane Doe" in msg["html"] and "j@x.edu" in msg["html"]
    assert "token=abc" in msg["html"]
    assert "Jane Doe" in msg["subject"]
    assert "j@x.edu" in msg["plain"]


@pytest.mark.asyncio
async def test_notify_sends_once_and_dedups():
    store = AccessStore(InMemoryBackend(), cache_ttl_seconds=0)
    sent = []
    async def fake_send(recipients, subject, html, plain):
        sent.append((recipients, subject))
    kw = dict(store=store, requester=REQ, secret="s",
              approve_base_url="https://h.edu", admin_emails=["a@x.edu"],
              cooldown_hours=24, ttl_seconds=86400, send_email=fake_send)
    assert await notify_access_request(jti="j1", now=0, now_iso="2026-06-29T00:00:00Z", **kw) is True
    assert await notify_access_request(jti="j2", now=60, now_iso="2026-06-29T00:01:00Z", **kw) is False
    assert len(sent) == 1 and sent[0][0] == ["a@x.edu"]


@pytest.mark.asyncio
async def test_notify_swallows_send_failure():
    store = AccessStore(InMemoryBackend(), cache_ttl_seconds=0)
    async def boom(*a, **k):
        raise RuntimeError("ACS down")
    ok = await notify_access_request(
        jti="j1", now=0, now_iso="2026-06-29T00:00:00Z", store=store, requester=REQ,
        secret="s", approve_base_url="https://h.edu", admin_emails=["a@x.edu"],
        cooldown_hours=24, ttl_seconds=86400, send_email=boom)
    assert ok is False  # did not raise
