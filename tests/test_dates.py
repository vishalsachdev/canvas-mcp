"""Unit tests for date formatting utilities."""

import datetime
from unittest.mock import patch

from canvas_mcp.core.dates import format_date_smart, format_datetime_compact


class TestFormatDateSmartRelative:
    """Test format_date_smart with relative mode.

    These tests verify the fix for the timedelta.days bug where negative
    deltas < 24h were incorrectly returning "yesterday" instead of "Xh ago".
    """

    def _make_datetime(self, hours_offset: int = 0, minutes_offset: int = 0) -> str:
        """Create an ISO datetime string relative to a fixed 'now' time."""
        base = datetime.datetime(2026, 1, 21, 12, 0, 0, tzinfo=datetime.timezone.utc)
        dt = base + datetime.timedelta(hours=hours_offset, minutes=minutes_offset)
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    @patch("canvas_mcp.core.dates.datetime")
    def test_2_hours_ago_returns_2h_ago(self, mock_datetime):
        """2 hours ago should return '2h ago', not 'yesterday'."""
        # Fix datetime.now() to a known time
        fixed_now = datetime.datetime(2026, 1, 21, 12, 0, 0, tzinfo=datetime.timezone.utc)
        mock_datetime.datetime.now.return_value = fixed_now
        mock_datetime.datetime.strptime = datetime.datetime.strptime
        mock_datetime.timezone = datetime.timezone

        # Time 2 hours before "now"
        past_time = "2026-01-21T10:00:00Z"

        result = format_date_smart(past_time, "relative")
        assert result == "2h ago", f"Expected '2h ago', got '{result}'"

    @patch("canvas_mcp.core.dates.datetime")
    def test_30_minutes_ago_returns_30m_ago(self, mock_datetime):
        """30 minutes ago should return '30m ago'."""
        fixed_now = datetime.datetime(2026, 1, 21, 12, 0, 0, tzinfo=datetime.timezone.utc)
        mock_datetime.datetime.now.return_value = fixed_now
        mock_datetime.datetime.strptime = datetime.datetime.strptime
        mock_datetime.timezone = datetime.timezone

        past_time = "2026-01-21T11:30:00Z"

        result = format_date_smart(past_time, "relative")
        assert result == "30m ago", f"Expected '30m ago', got '{result}'"

    @patch("canvas_mcp.core.dates.datetime")
    def test_23_hours_ago_returns_23h_ago(self, mock_datetime):
        """23 hours ago should return '23h ago', not 'yesterday'."""
        fixed_now = datetime.datetime(2026, 1, 21, 12, 0, 0, tzinfo=datetime.timezone.utc)
        mock_datetime.datetime.now.return_value = fixed_now
        mock_datetime.datetime.strptime = datetime.datetime.strptime
        mock_datetime.timezone = datetime.timezone

        # 23 hours before noon = 1pm previous day
        past_time = "2026-01-20T13:00:00Z"

        result = format_date_smart(past_time, "relative")
        assert result == "23h ago", f"Expected '23h ago', got '{result}'"

    @patch("canvas_mcp.core.dates.datetime")
    def test_25_hours_ago_returns_yesterday(self, mock_datetime):
        """25 hours ago (>24h) should return 'yesterday'."""
        fixed_now = datetime.datetime(2026, 1, 21, 12, 0, 0, tzinfo=datetime.timezone.utc)
        mock_datetime.datetime.now.return_value = fixed_now
        mock_datetime.datetime.strptime = datetime.datetime.strptime
        mock_datetime.timezone = datetime.timezone

        # 25 hours before noon = 11am two days ago... wait that's 25 hours
        past_time = "2026-01-20T11:00:00Z"

        result = format_date_smart(past_time, "relative")
        assert result == "yesterday", f"Expected 'yesterday', got '{result}'"

    @patch("canvas_mcp.core.dates.datetime")
    def test_in_2_hours_returns_in_2h(self, mock_datetime):
        """2 hours from now should return 'in 2h'."""
        fixed_now = datetime.datetime(2026, 1, 21, 12, 0, 0, tzinfo=datetime.timezone.utc)
        mock_datetime.datetime.now.return_value = fixed_now
        mock_datetime.datetime.strptime = datetime.datetime.strptime
        mock_datetime.timezone = datetime.timezone

        future_time = "2026-01-21T14:00:00Z"

        result = format_date_smart(future_time, "relative")
        assert result == "in 2h", f"Expected 'in 2h', got '{result}'"

    @patch("canvas_mcp.core.dates.datetime")
    def test_in_30_minutes_returns_in_30m(self, mock_datetime):
        """30 minutes from now should return 'in 30m'."""
        fixed_now = datetime.datetime(2026, 1, 21, 12, 0, 0, tzinfo=datetime.timezone.utc)
        mock_datetime.datetime.now.return_value = fixed_now
        mock_datetime.datetime.strptime = datetime.datetime.strptime
        mock_datetime.timezone = datetime.timezone

        future_time = "2026-01-21T12:30:00Z"

        result = format_date_smart(future_time, "relative")
        assert result == "in 30m", f"Expected 'in 30m', got '{result}'"

    @patch("canvas_mcp.core.dates.datetime")
    def test_now_returns_now(self, mock_datetime):
        """Time within 60 seconds should return 'now'."""
        fixed_now = datetime.datetime(2026, 1, 21, 12, 0, 0, tzinfo=datetime.timezone.utc)
        mock_datetime.datetime.now.return_value = fixed_now
        mock_datetime.datetime.strptime = datetime.datetime.strptime
        mock_datetime.timezone = datetime.timezone

        # 30 seconds ago
        near_time = "2026-01-21T11:59:30Z"

        result = format_date_smart(near_time, "relative")
        assert result == "now", f"Expected 'now', got '{result}'"

    @patch("canvas_mcp.core.dates.datetime")
    def test_tomorrow_returns_tomorrow(self, mock_datetime):
        """25 hours from now should return 'tomorrow'."""
        fixed_now = datetime.datetime(2026, 1, 21, 12, 0, 0, tzinfo=datetime.timezone.utc)
        mock_datetime.datetime.now.return_value = fixed_now
        mock_datetime.datetime.strptime = datetime.datetime.strptime
        mock_datetime.timezone = datetime.timezone

        future_time = "2026-01-22T13:00:00Z"

        result = format_date_smart(future_time, "relative")
        assert result == "tomorrow", f"Expected 'tomorrow', got '{result}'"

    @patch("canvas_mcp.core.dates.datetime")
    def test_3_days_ago_returns_3_days_ago(self, mock_datetime):
        """3 days ago should return '3 days ago'."""
        fixed_now = datetime.datetime(2026, 1, 21, 12, 0, 0, tzinfo=datetime.timezone.utc)
        mock_datetime.datetime.now.return_value = fixed_now
        mock_datetime.datetime.strptime = datetime.datetime.strptime
        mock_datetime.timezone = datetime.timezone

        # 72+ hours ago
        past_time = "2026-01-18T10:00:00Z"

        result = format_date_smart(past_time, "relative")
        assert result == "3 days ago", f"Expected '3 days ago', got '{result}'"

    @patch("canvas_mcp.core.dates.datetime")
    def test_in_3_days_returns_in_3_days(self, mock_datetime):
        """3 days from now should return 'in 3 days'."""
        fixed_now = datetime.datetime(2026, 1, 21, 12, 0, 0, tzinfo=datetime.timezone.utc)
        mock_datetime.datetime.now.return_value = fixed_now
        mock_datetime.datetime.strptime = datetime.datetime.strptime
        mock_datetime.timezone = datetime.timezone

        # 72+ hours from now
        future_time = "2026-01-24T14:00:00Z"

        result = format_date_smart(future_time, "relative")
        assert result == "in 3 days", f"Expected 'in 3 days', got '{result}'"


class TestFormatDateSmartOtherModes:
    """Test format_date_smart with standard and compact modes."""

    def test_standard_mode_returns_iso8601(self):
        """Standard mode should return full ISO 8601 format."""
        date_str = "2026-01-21T14:30:00Z"
        result = format_date_smart(date_str, "standard")
        assert result == "2026-01-21T14:30:00Z"

    def test_compact_mode_returns_short_format(self):
        """Compact mode should return short month-day format."""
        date_str = "2026-01-21T14:30:00Z"
        result = format_date_smart(date_str, "compact")
        # Result depends on current year
        assert result.startswith("Jan 21")

    def test_none_input_returns_dash_for_compact(self):
        """None input should return '-' for compact mode."""
        result = format_date_smart(None, "compact")
        assert result == "-"

    def test_none_input_returns_na_for_standard(self):
        """None input should return 'N/A' for standard mode."""
        result = format_date_smart(None, "standard")
        assert result == "N/A"


class TestFormatDatetimeCompact:
    """Test format_datetime_compact function."""

    def test_includes_time(self):
        """Compact datetime should include time component."""
        date_str = "2026-01-21T14:30:00Z"
        result = format_datetime_compact(date_str)
        assert "14:30" in result

    def test_none_returns_dash(self):
        """None input should return '-'."""
        result = format_datetime_compact(None)
        assert result == "-"
