from canvas_mcp.core.access.store import (
    AccessStore, InMemoryBackend, Requester, ConcurrencyConflict,
)

REQ = Requester(oid="oid-1", upn="j@x.edu", display_name="Jane Doe")


def _store(ttl=0):
    # ttl=0 -> no caching, so tests see writes immediately
    return AccessStore(InMemoryBackend(), cache_ttl_seconds=ttl)


def test_grant_then_is_granted_and_listed():
    s = _store()
    assert s.is_granted("oid-1") is False
    s.grant(REQ, jti="j1")
    assert s.is_granted("oid-1") is True
    grants = s.list_grants()
    assert len(grants) == 1 and grants[0].oid == "oid-1" and grants[0].upn == "j@x.edu"


def test_revoke_removes_grant():
    s = _store()
    s.grant(REQ, jti="j1")
    assert s.revoke("oid-1") is True
    assert s.is_granted("oid-1") is False
    assert s.revoke("oid-1") is False  # already gone


def test_note_request_dedups_within_cooldown():
    s = _store()
    assert s.note_request(REQ, jti="j1", exp=1000, now_iso="2026-06-29T00:00:00Z",
                          cooldown_hours=24) is True   # first time -> notify
    assert s.note_request(REQ, jti="j2", exp=2000, now_iso="2026-06-29T01:00:00Z",
                          cooldown_hours=24) is False  # within cooldown -> suppress


def test_consume_pending_is_single_use():
    s = _store()
    s.note_request(REQ, jti="j1", exp=1000, now_iso="2026-06-29T00:00:00Z", cooldown_hours=24)
    assert s.consume_pending("oid-1", "j1") is True   # first consume wins
    assert s.consume_pending("oid-1", "j1") is False  # already consumed
    assert s.consume_pending("oid-1", "wrong-jti") is False  # jti mismatch


def test_consume_pending_loses_etag_race(monkeypatch):
    s = _store()
    s.note_request(REQ, jti="j1", exp=1000, now_iso="2026-06-29T00:00:00Z", cooldown_hours=24)
    # Force the backend replace to lose the race.
    def racing(entity, etag):
        raise ConcurrencyConflict("stale etag")
    monkeypatch.setattr(s._backend, "replace_if_unmodified", racing)
    assert s.consume_pending("oid-1", "j1") is False  # conflict -> not consumed
