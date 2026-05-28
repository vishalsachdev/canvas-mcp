"""Tests for canvas_mcp.core.dates.

Covers the TIMEZONE-aware behavior of format_date(): the function must
honor the configured output timezone while preserving ISO 8601 and
keeping the historical ``Z`` suffix when the resolved zone is UTC.
"""

import datetime

import pytest

from canvas_mcp.core import dates


@pytest.fixture(autouse=True)
def reset_tz_state(monkeypatch):
    """Clear the module-level tz cache and force a fresh Config each test."""
    monkeypatch.setattr(dates, "_tz_cache", {})
    monkeypatch.setattr(dates, "_tz_warned", set())
    # Force get_config() to rebuild from the (possibly monkeypatched) env
    from canvas_mcp.core import config as config_module
    monkeypatch.setattr(config_module, "_config", None)
    yield


def test_format_date_returns_na_for_none():
    assert dates.format_date(None) == "N/A"
    assert dates.format_date("") == "N/A"


def test_format_date_defaults_to_utc_with_z_suffix(monkeypatch):
    monkeypatch.delenv("TIMEZONE", raising=False)
    assert dates.format_date("2026-05-28T23:59:00Z") == "2026-05-28T23:59:00Z"


def test_format_date_uses_z_when_timezone_explicitly_utc(monkeypatch):
    monkeypatch.setenv("TIMEZONE", "UTC")
    assert dates.format_date("2026-05-28T23:59:00Z") == "2026-05-28T23:59:00Z"


def test_format_date_converts_to_configured_timezone(monkeypatch):
    pytest.importorskip("tzdata")  # Windows requires the tzdata package
    monkeypatch.setenv("TIMEZONE", "America/Chicago")
    # 23:59 UTC on 2026-05-28 == 18:59 CDT (UTC-5)
    result = dates.format_date("2026-05-28T23:59:00Z")
    assert result == "2026-05-28T18:59:00-0500"


def test_format_date_preserves_existing_offset_then_converts(monkeypatch):
    pytest.importorskip("tzdata")
    monkeypatch.setenv("TIMEZONE", "America/Chicago")
    # Same instant expressed with an explicit offset
    result = dates.format_date("2026-05-29T00:59:00+0100")
    assert result == "2026-05-28T18:59:00-0500"


def test_format_date_unknown_timezone_falls_back_to_utc(monkeypatch, capsys):
    monkeypatch.setenv("TIMEZONE", "Not/AZone")
    result = dates.format_date("2026-05-28T23:59:00Z")
    assert result == "2026-05-28T23:59:00Z"
    assert "Not/AZone" in capsys.readouterr().err


def test_format_date_returns_original_when_unparseable():
    assert dates.format_date("not-a-date") == "not-a-date"


def test_parse_date_assumes_utc_for_naive_strings():
    # The "%Y-%m-%d %H:%M:%S" format has no tzinfo; parser should backfill UTC
    dt = dates.parse_date("2026-05-28 23:59:00")
    assert dt is not None
    assert dt.tzinfo == datetime.timezone.utc


def test_parse_date_preserves_explicit_offset():
    dt = dates.parse_date("2026-05-28T18:59:00-0500")
    assert dt is not None
    assert dt.utcoffset() == datetime.timedelta(hours=-5)
