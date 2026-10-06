"""Kardinal Python SDK."""

from __future__ import annotations

from types import TracebackType
from typing import TYPE_CHECKING, Optional, Type

from ._core.auth import EmptyApiKeyError, MissingApiKeyError, resolve_api_key
from ._core.errors import (
    KardinalAuthError,
    KardinalConnectionError,
    KardinalError,
    KardinalLimitError,
    KardinalNotFoundError,
    KardinalOptimizationError,
    KardinalRateLimitError,
    KardinalServerError,
    KardinalTimeoutError,
    KardinalValidationError,
    UnknownFieldError,
    UnknownFieldWarning,
)
from ._core.pagination import Page
from ._core.transport import Transport

if TYPE_CHECKING:
    from .routing.plans import PlansAPI
    from .routing.solutions import SolutionsAPI

__all__ = [
    "Kardinal",
    "Page",
    "KardinalError",
    "KardinalAuthError",
    "KardinalLimitError",
    "KardinalValidationError",
    "UnknownFieldError",
    "UnknownFieldWarning",
    "KardinalNotFoundError",
    "KardinalRateLimitError",
    "KardinalServerError",
    "KardinalTimeoutError",
    "KardinalOptimizationError",
    "KardinalConnectionError",
    "MissingApiKeyError",
    "EmptyApiKeyError",
]


class _Routing:
    plans: "PlansAPI"
    solutions: "SolutionsAPI"

    def __init__(self, transport: Transport) -> None:
        # Imported here, not at module level: `kardinal.cli` is a submodule
        # of this package, so importing it for `--help` already runs this
        # file — keeping these lazy is what lets `--help` answer without
        # loading kardinal.routing.models or opening a connection.
        from .routing.plans import PlansAPI
        from .routing.solutions import SolutionsAPI

        self.plans = PlansAPI(transport)
        self.solutions = SolutionsAPI(transport, self.plans)


class Kardinal:
    """`Kardinal(api_key=None, base_url=None, timeout=30, max_retries=3)`

    `api_key` defaults to the `KARDINAL_API_KEY` environment variable.
    `base_url` defaults to `KARDINAL_BASE_URL`, then
    `https://app.kardinal.ai/api/v2`: sandbox and production share that host,
    and the API key determines which agency a call applies to.

    `timeout` (seconds) is each request's `httpx` timeout, applied to each
    phase (connect, read, write) separately. `max_retries` is how many times
    a read, `update()`, `delete()`, `start()` or `stop()` is retried after a
    network error, a 429 or a 5xx (`submit()` never is).

    Usable as a context manager, or call `close()` directly.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        *,
        base_url: Optional[str] = None,
        timeout: float = 30,
        max_retries: int = 3,
    ) -> None:
        resolved_key = resolve_api_key(api_key)
        self._transport = Transport(
            api_key=resolved_key,
            base_url=base_url,
            timeout=timeout,
            max_retries=max_retries,
        )
        self.routing = _Routing(self._transport)

    def close(self) -> None:
        """Closes the underlying `httpx` connection pool. Idempotent; any
        request made afterwards raises `KardinalError` (`CLIENT_CLOSED`).
        """
        self._transport.close()

    def __enter__(self) -> "Kardinal":
        return self

    def __exit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc: Optional[BaseException],
        traceback: Optional[TracebackType],
    ) -> None:
        self.close()
