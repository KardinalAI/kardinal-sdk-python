"""Retry policy.

openapi.yaml defines no `Idempotency-Key`, so retrying `POST /plans`
(`submit`) after a network error or a 5xx could double-create a plan.
Only GET/PUT/DELETE are retried automatically; POST is not.
"""

from __future__ import annotations

import time
from typing import Optional

_RETRYABLE_METHODS = frozenset({"GET", "PUT", "DELETE"})
_RETRYABLE_STATUSES = frozenset({429, 500, 502, 503, 504})


def is_retryable(method: str, *, status: Optional[int], network_error: bool) -> bool:
    if method.upper() not in _RETRYABLE_METHODS:
        return False
    if network_error:
        return True
    return status is not None and status in _RETRYABLE_STATUSES


def backoff_seconds(attempt: int) -> float:
    """Exponential backoff. `attempt` is 1-indexed (first retry is attempt 1)."""
    return min(0.5 * (2 ** (attempt - 1)), 8.0)


def sleep(attempt: int) -> None:
    time.sleep(backoff_seconds(attempt))
