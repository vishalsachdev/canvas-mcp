import pytest
from canvas_mcp.core.config import get_config, reset_config


@pytest.fixture(autouse=True)
def _clean_config():
    reset_config()
    yield
    reset_config()


def test_access_defaults_are_disabled(monkeypatch):
    for var in ("ACCESS_REQUEST_ENABLED", "ACCESS_TABLE_ACCOUNT", "ACS_ENDPOINT",
                "ACS_SENDER", "ACCESS_ADMIN_EMAILS", "ACCESS_APPROVE_BASE_URL",
                "ACCESS_TOKEN_SECRET"):
        monkeypatch.delenv(var, raising=False)
    cfg = get_config()
    assert cfg.access_request_enabled is False
    assert cfg.access_admin_emails == []
    assert cfg.access_table_name == "accessoverlay"
    assert cfg.access_notify_cooldown_hours == 24


def test_access_settings_parse_from_env(monkeypatch):
    monkeypatch.setenv("ACCESS_REQUEST_ENABLED", "true")
    monkeypatch.setenv("ACCESS_ADMIN_EMAILS", "a@x.edu, b@x.edu")
    monkeypatch.setenv("ACCESS_APPROVE_BASE_URL", "https://h.edu/")
    monkeypatch.setenv("ACCESS_NOTIFY_COOLDOWN_HOURS", "6")
    cfg = get_config()
    assert cfg.access_request_enabled is True
    assert cfg.access_admin_emails == ["a@x.edu", "b@x.edu"]
    assert cfg.access_approve_base_url == "https://h.edu"  # trailing slash stripped
    assert cfg.access_notify_cooldown_hours == 6


def test_admin_emails_blank_yields_empty_list(monkeypatch):
    monkeypatch.setenv("ACCESS_ADMIN_EMAILS", "   ")
    assert get_config().access_admin_emails == []
