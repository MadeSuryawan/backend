# tests/utils/test_helpers.py
"""Tests for app/utils/helpers.py module."""

import re
from time import perf_counter, sleep

from app.utils.helpers import time_taken, today_str


class TestTodayStr:
    """Tests for today_str function."""

    def test_returns_string(self) -> None:
        """Test that today_str returns a string."""
        result = today_str()
        assert isinstance(result, str)

    def test_format_matches_expected_pattern(self) -> None:
        """Test that the date format matches YYYY-MM-DD HH:MM:SS."""
        result = today_str()
        pattern = r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$"
        assert re.match(pattern, result), f"Date format mismatch: {result}"

    def test_contains_valid_date_components(self) -> None:
        """Test that the date components are valid."""
        result = today_str()
        parts = result.split(" ")
        assert len(parts) == 2

        date_part = parts[0]
        time_part = parts[1]

        year, month, day = date_part.split("-")
        assert 2020 <= int(year) <= 2100
        assert 1 <= int(month) <= 12
        assert 1 <= int(day) <= 31

        hour, minute, second = time_part.split(":")
        assert 0 <= int(hour) <= 23
        assert 0 <= int(minute) <= 59
        assert 0 <= int(second) <= 59


class TestTimeTaken:
    """Tests for time_taken function."""

    def test_returns_formatted_string(self) -> None:
        """Test that time_taken returns a formatted string."""

        start = perf_counter()
        result = time_taken(start)
        assert isinstance(result, str)
        assert "m" in result
        assert "s" in result

    def test_format_pattern(self) -> None:
        """Test the format is Xm Y.ZZs."""

        start = perf_counter()
        result = time_taken(start)
        pattern = r"^\d+m \d+\.\d{2}s$"
        assert re.match(pattern, result), f"Format mismatch: {result}"

    def test_elapsed_time_calculation(self) -> None:
        """Test that elapsed time is calculated correctly."""

        start = perf_counter()
        sleep(0.1)  # Sleep for 100ms
        result = time_taken(start)
        assert result.startswith("0m 0.1")

    def test_with_longer_duration(self) -> None:
        """Test with a mock start time that results in longer duration."""

        # Mock a start time that was 65 seconds ago
        start = perf_counter() - 65
        result = time_taken(start)
        assert result == "1m 5.00s"

    def test_with_hours_worth_of_time(self) -> None:
        """Test with duration exceeding 60 minutes."""

        # 3665 seconds = 61 minutes and 5 seconds
        start = perf_counter() - 3665
        result = time_taken(start)
        # divmod gives 61m 5.00s (not handling hours)
        assert result == "61m 5.00s"
