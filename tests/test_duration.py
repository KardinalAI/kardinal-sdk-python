from datetime import timedelta

import pytest

from kardinal._core.duration import parse_duration


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("PT5M", timedelta(minutes=5)),
        ("PT5M30S", timedelta(minutes=5, seconds=30)),
        ("P1D", timedelta(days=1)),
        ("P1DT2H", timedelta(days=1, hours=2)),
        ("P1Y", timedelta(days=365)),
        ("P1M", timedelta(days=30)),
        ("P1W", timedelta(weeks=1)),
    ],
)
def test_parses_valid_iso8601_durations(value, expected) -> None:
    assert parse_duration(value) == expected


@pytest.mark.parametrize("value", ["P", "PT", "garbage", "", "1D", "PT5X"])
def test_rejects_zero_length_and_malformed_durations(value) -> None:
    """"P" (no date or time part at all) and "PT" (a time part present but
    empty) are both zero-length durations that the pattern alone doesn't
    reject — both must raise, not silently parse as a zero timedelta.
    """
    with pytest.raises(ValueError):
        parse_duration(value)
