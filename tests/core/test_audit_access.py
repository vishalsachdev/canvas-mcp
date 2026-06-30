import pytest
import canvas_mcp.core.audit as audit


@pytest.fixture(autouse=True)
def _reset():
    audit.reset_audit_state()
    yield
    audit.reset_audit_state()


def test_grant_event_emitted_when_enabled(monkeypatch):
    events = []
    monkeypatch.setattr(audit, "_access_events_enabled", True)
    monkeypatch.setattr(audit, "_emit", lambda e: events.append(e))
    audit.log_access_change("grant", "oid-1", upn="j@x.edu")
    assert events == [{
        "event_type": "access_change", "action": "grant",
        "entra_oid": "oid-1", "upn": "j@x.edu", "source": "self-service",
    }]


def test_no_event_when_disabled(monkeypatch):
    events = []
    monkeypatch.setattr(audit, "_access_events_enabled", False)
    monkeypatch.setattr(audit, "_emit", lambda e: events.append(e))
    audit.log_access_change("grant", "oid-1")
    assert events == []


def test_upn_omitted_when_none(monkeypatch):
    events = []
    monkeypatch.setattr(audit, "_access_events_enabled", True)
    monkeypatch.setattr(audit, "_emit", lambda e: events.append(e))
    audit.log_access_change("revoke", "oid-2")
    assert "upn" not in events[0] and events[0]["action"] == "revoke"
