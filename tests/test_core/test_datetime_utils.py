"""Tests for timezone utilities in datetime_utils."""

from datetime import time
from unittest.mock import patch

from app.core.datetime_utils import (
    COMMON_TIMEZONES,
    has_delivery_window_passed,
    is_in_delivery_window,
    is_valid_timezone,
    parse_delivery_time,
    user_local_time,
)


class TestIsValidTimezone:
    """Tests for is_valid_timezone."""

    def test_valid_iana_timezone(self):
        """Should return True for valid IANA timezone."""
        assert is_valid_timezone("America/New_York") is True
        assert is_valid_timezone("Europe/Paris") is True
        assert is_valid_timezone("Asia/Tokyo") is True
        assert is_valid_timezone("UTC") is True

    def test_invalid_timezone(self):
        """Should return False for invalid timezone."""
        assert is_valid_timezone("Invalid/Timezone") is False
        assert is_valid_timezone("") is False
        assert is_valid_timezone("America/Atlantis") is False
        assert is_valid_timezone("Fake/City") is False

    def test_common_timezones_are_valid(self):
        """All timezones in COMMON_TIMEZONES should be valid."""
        for tz in COMMON_TIMEZONES:
            assert is_valid_timezone(tz), f"{tz} should be valid"


class TestUserLocalTime:
    """Tests for user_local_time."""

    def test_returns_aware_datetime(self):
        """Should return timezone-aware datetime."""
        local = user_local_time("America/New_York")
        assert local.tzinfo is not None

    def test_invalid_timezone_falls_back_to_utc(self):
        """Should fallback to UTC for invalid timezone."""
        local = user_local_time("Invalid/Zone")
        assert local.tzinfo is not None
        assert "UTC" in str(local.tzinfo)


class TestParseDeliveryTime:
    """Tests for parse_delivery_time."""

    def test_valid_time_format(self):
        """Should parse valid HH:MM format."""
        assert parse_delivery_time("08:00") == time(8, 0)
        assert parse_delivery_time("14:30") == time(14, 30)
        assert parse_delivery_time("00:00") == time(0, 0)
        assert parse_delivery_time("23:59") == time(23, 59)

    def test_invalid_time_format_returns_default(self):
        """Should return 08:00 for invalid formats."""
        assert parse_delivery_time("invalid") == time(8, 0)
        assert parse_delivery_time("25:00") == time(8, 0)  # Invalid hour
        assert parse_delivery_time("8:0") == time(8, 0)  # No leading zeros ok
        assert parse_delivery_time("") == time(8, 0)


class TestIsInDeliveryWindow:
    """Tests for is_in_delivery_window."""

    def test_in_window_exact_time(self):
        """Should return True when exactly at delivery time."""
        from datetime import datetime
        from zoneinfo import ZoneInfo

        # Mock current time to be exactly 08:00 in New York
        mock_time = datetime(2026, 1, 13, 8, 0, 0, tzinfo=ZoneInfo("America/New_York"))

        with patch("app.core.datetime_utils.datetime") as mock_datetime:
            mock_datetime.now.return_value = mock_time

            result = is_in_delivery_window("America/New_York", "08:00")
            assert result is True

    def test_in_window_within_range(self):
        """Should return True when within ±15 minutes of delivery time."""
        from datetime import datetime
        from zoneinfo import ZoneInfo

        # 08:10 is within ±15 minutes of 08:00
        mock_time = datetime(2026, 1, 13, 8, 10, 0, tzinfo=ZoneInfo("America/New_York"))

        with patch("app.core.datetime_utils.datetime") as mock_datetime:
            mock_datetime.now.return_value = mock_time

            result = is_in_delivery_window("America/New_York", "08:00")
            assert result is True

    def test_outside_window(self):
        """Should return False when outside delivery window."""
        from datetime import datetime
        from zoneinfo import ZoneInfo

        # 09:00 is outside ±15 minutes of 08:00
        mock_time = datetime(2026, 1, 13, 9, 0, 0, tzinfo=ZoneInfo("America/New_York"))

        with patch("app.core.datetime_utils.datetime") as mock_datetime:
            mock_datetime.now.return_value = mock_time

            result = is_in_delivery_window("America/New_York", "08:00")
            assert result is False


class TestHasDeliveryWindowPassed:
    """Tests for has_delivery_window_passed."""

    def test_window_passed(self):
        """Should return True when delivery time has passed."""
        from datetime import datetime
        from zoneinfo import ZoneInfo

        # 10:00 is after 08:00 + 15 min window
        mock_time = datetime(2026, 1, 13, 10, 0, 0, tzinfo=ZoneInfo("America/New_York"))

        with patch("app.core.datetime_utils.datetime") as mock_datetime:
            mock_datetime.now.return_value = mock_time

            result = has_delivery_window_passed("America/New_York", "08:00")
            assert result is True

    def test_window_not_passed(self):
        """Should return False when before delivery window."""
        from datetime import datetime
        from zoneinfo import ZoneInfo

        # 07:00 is before 08:00
        mock_time = datetime(2026, 1, 13, 7, 0, 0, tzinfo=ZoneInfo("America/New_York"))

        with patch("app.core.datetime_utils.datetime") as mock_datetime:
            mock_datetime.now.return_value = mock_time

            result = has_delivery_window_passed("America/New_York", "08:00")
            assert result is False

    def test_window_active_not_passed(self):
        """Should return False when in delivery window."""
        from datetime import datetime
        from zoneinfo import ZoneInfo

        # 08:10 is still in window
        mock_time = datetime(2026, 1, 13, 8, 10, 0, tzinfo=ZoneInfo("America/New_York"))

        with patch("app.core.datetime_utils.datetime") as mock_datetime:
            mock_datetime.now.return_value = mock_time

            result = has_delivery_window_passed("America/New_York", "08:00")
            assert result is False
