"""Retry policy.

openapi.yaml defines no `Idempotency-Key`, so retrying `POST /plans`
(`submit`) after a network error or a 5xx could double-create a plan.
Only GET/PUT/DELETE are retried automatically; POST is not.
"""

from __future__ import annotations

import random
import re
import time
from email.utils import parsedate_to_datetime
from typing import Optional

_RETRYABLE_METHODS = frozenset({"GET", "PUT", "DELETE"})
_RETRYABLE_STATUSES = frozenset({429, 500, 502, 503, 504})

_BACKOFF_CAP = 8.0
_RETRY_AFTER_CAP = 60.0
_DIGITS = re.compile(r"^\d+$")
_HAS_LETTER = re.compile(r"[A-Za-z]")


def is_retryable(method: str, *, status: Optional[int], network_error: bool) -> bool:
    if method.upper() not in _RETRYABLE_METHODS:
        return False
    if network_error:
        return True
    return status is not None and status in _RETRYABLE_STATUSES


def retry_after_seconds(header: Optional[str]) -> Optional[float]:
    """`Retry-After` as seconds, or `None` when absent or unusable. Both
    forms the HTTP spec allows are accepted: a number of seconds, and an
    HTTP date. A date already past gives 0 — the server is saying "now" —
    and anything beyond a minute is capped rather than trusted, so a bad
    header can't park a caller indefinitely.
    """
    if header is None:
        return None
    value = header.strip()
    if not value:
        return None

    if _DIGITS.match(value):
        return min(float(value), _RETRY_AFTER_CAP)
    # An HTTP-date always carries a day or month name, so requiring a letter
    # keeps the date parser from reading something like "-5" as a year and
    # reporting a date in the past, i.e. "retry now".
    if not _HAS_LETTER.search(value):
        return None
    try:
        when = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if when is None:
        return None
    delay = when.timestamp() - time.time()
    return min(max(0.0, delay), _RETRY_AFTER_CAP)


def backoff_seconds(attempt: int) -> float:
    """Exponential backoff. `attempt` is 1-indexed (first retry is attempt 1).

    Jittered: without it, every client throttled by the same 429 retries at
    the same moment and rebuilds the burst that caused it. The delay keeps
    its floor and spreads over the window above it.
    """
    ceiling = min(0.5 * (2 ** (attempt - 1)), _BACKOFF_CAP)
    return ceiling / 2 + random.random() * (ceiling / 2)


def delay_seconds(attempt: int, retry_after: Optional[str] = None) -> float:
    """How long to wait before the next attempt.

    The server's own `Retry-After` wins when it sent one: it knows when the
    limit lifts, and backing off on a schedule of our own against a rate
    limiter is how a client gets throttled for longer than it had to be.
    """
    from_server = retry_after_seconds(retry_after)
    return from_server if from_server is not None else backoff_seconds(attempt)


def sleep(attempt: int, retry_after: Optional[str] = None) -> None:
    time.sleep(delay_seconds(attempt, retry_after))
