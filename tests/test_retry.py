"""The server says when its limit lifts; the SDK used to ignore it and back
off on a schedule of its own, which is how a client stays throttled longer
than it had to be. And an unjittered backoff makes every client throttled by
the same 429 retry at the same moment, rebuilding the burst that caused it.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from email.utils import format_datetime

import pytest

from kardinal._core.retry import (
    backoff_seconds,
    delay_seconds,
    is_retryable,
    retry_after_seconds,
)


def _http_date(offset_seconds: float) -> str:
    return format_datetime(
        datetime.now(timezone.utc) + timedelta(seconds=offset_seconds), usegmt=True
    )


class TestRetryAfter:
    def test_reads_the_delay_seconds_form(self) -> None:
        assert retry_after_seconds("3") == 3.0
        assert retry_after_seconds("  3  ") == 3.0
        assert retry_after_seconds("0") == 0.0

    def test_reads_the_http_date_form(self) -> None:
        read = retry_after_seconds(_http_date(2))
        assert read is not None
        assert 0.5 < read <= 2.0

    def test_treats_a_date_already_past_as_now(self) -> None:
        assert retry_after_seconds(_http_date(-5)) == 0.0

    def test_caps_an_absurd_value_instead_of_trusting_it(self) -> None:
        # A bad header must not park a caller for a day.
        assert retry_after_seconds("99999") == 60.0

    @pytest.mark.parametrize("header", [None, "", "soon", "-5"])
    def test_ignores_a_header_it_cannot_read(self, header: str | None) -> None:
        assert retry_after_seconds(header) is None

    def test_wins_over_the_sdks_own_backoff(self) -> None:
        assert delay_seconds(1, "3") == 3.0
        assert delay_seconds(4, "1") == 1.0

    def test_falls_back_to_backoff_when_the_server_said_nothing(self) -> None:
        assert 0.25 <= delay_seconds(1, None) <= 0.5


class TestBackoff:
    def test_is_jittered_so_throttled_clients_do_not_retry_in_lockstep(self) -> None:
        assert len({backoff_seconds(3) for _ in range(50)}) > 1

    @pytest.mark.parametrize(
        ("attempt", "ceiling"),
        [(1, 0.5), (2, 1.0), (3, 2.0), (9, 8.0)],  # 9: capped
    )
    def test_keeps_a_floor_and_a_ceiling_at_every_attempt(
        self, attempt: int, ceiling: float
    ) -> None:
        for _ in range(20):
            assert ceiling / 2 <= backoff_seconds(attempt) <= ceiling


class TestWhatGetsRetried:
    def test_never_retries_post_which_has_no_idempotency_key(self) -> None:
        assert not is_retryable("POST", status=503, network_error=False)
        assert not is_retryable("POST", status=None, network_error=True)

    @pytest.mark.parametrize("method", ["GET", "PUT", "DELETE"])
    def test_retries_a_read_a_replace_or_a_delete_on_429_and_5xx(self, method: str) -> None:
        assert is_retryable(method, status=429, network_error=False)
        assert is_retryable(method, status=503, network_error=False)
        assert not is_retryable(method, status=404, network_error=False)
