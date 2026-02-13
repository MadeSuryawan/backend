from datetime import UTC, datetime, timedelta

from app.utils.timezone import format_api_response, humanize_time


class TestFormatApiResponse:
    def test_utc_formatting(self) -> None:
        dt = datetime(2026, 2, 13, 15, 0, 0, tzinfo=UTC)
        user_tz = "America/New_York"
        result = format_api_response(dt, user_tz)

        assert result["utc"] == "2026-02-13T10:00:00-0500"

    def test_local_formatting(self) -> None:
        dt = datetime(2026, 2, 13, 15, 0, 0, tzinfo=UTC)
        user_tz = "America/New_York"  # UTC-5
        result = format_api_response(dt, user_tz)

        # 15:00 UTC = 10:00 EST
        assert result["local"] == "Friday, February 13, 2026 10:00:00"
        assert result["timezone"] == "America/New_York"

    def test_local_formatting_wita(self) -> None:
        dt = datetime(2026, 2, 13, 15, 0, 0, tzinfo=UTC)
        user_tz = "Asia/Makassar"  # WITA (UTC+8)
        result = format_api_response(dt, user_tz)

        # 15:00 UTC = 23:00 WITA
        assert result["local"] == "Friday, February 13, 2026 23:00:00"

    def test_timezone_conversion(self) -> None:
        dt = datetime(2026, 2, 13, 15, 0, 0, tzinfo=UTC)
        user_tz = "Asia/Tokyo"  # UTC+9
        result = format_api_response(dt, user_tz)

        # 15:00 UTC = 00:00 (+1 day) JST
        # Saturday, February 14, 2026 12:00 AM
        assert result["local"] == "Saturday, February 14, 2026 00:00:00"


class TestHumanizeTime:
    def test_just_now(self) -> None:
        dt = datetime.now(UTC)
        assert humanize_time(dt) == "Just now"

    def test_minutes_ago(self) -> None:
        dt = datetime.now(UTC) - timedelta(minutes=5)
        # Allow +/- 1 second drift although unlikely to affect "minutes" unless edge case
        assert humanize_time(dt) == "5 minutes ago"

    def test_single_minute_ago(self) -> None:
        dt = datetime.now(UTC) - timedelta(minutes=1)
        assert humanize_time(dt) == "1 minute ago"

    def test_hours_ago(self) -> None:
        dt = datetime.now(UTC) - timedelta(hours=2)
        assert humanize_time(dt) == "2 hours ago"

    def test_single_hour_ago(self) -> None:
        dt = datetime.now(UTC) - timedelta(minutes=65)  # 1 hour 5 min
        assert humanize_time(dt) == "1 hour ago"

    def test_yesterday(self) -> None:
        dt = datetime.now(UTC) - timedelta(days=1, hours=2)
        # logic: if diff < 2 days -> "Yesterday at ..."
        # humanize_time uses now - dt.
        # if dt is 1 day 2 hours ago, diff is 1 day 2 hours.
        # implementation: if diff < timedelta(days=2): return "Yesterday at ..."
        result = humanize_time(dt)
        assert result.startswith("Yesterday at")

    def test_days_ago(self) -> None:
        dt = datetime.now(UTC) - timedelta(days=3)
        assert humanize_time(dt) == "3 days ago"

    def test_date_format(self) -> None:
        dt = datetime.now(UTC) - timedelta(days=10)
        # Should return formatted date e.g. "Feb 07, 2026"
        # format: "%b %d, %Y"
        result = humanize_time(dt)
        assert len(result.split(",")) == 2
