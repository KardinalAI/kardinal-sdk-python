"""HTTP transport: base URL, bearer auth, timeout, retry-on-network/5xx for
GET/PUT/DELETE (see `_core.retry`), and translation of failed responses into
the `_core.errors` hierarchy.
"""

from __future__ import annotations

import os
from typing import Any, Dict, Optional

import httpx

from . import retry
from .errors import KardinalConnectionError, KardinalError, from_response

DEFAULT_BASE_URL = "https://app.kardinal.ai/api/v2"
BASE_URL_ENV_VAR = "KARDINAL_BASE_URL"


def resolve_base_url(base_url: Optional[str]) -> str:
    """`base_url` argument, then `KARDINAL_BASE_URL`, then the default host.

    The environment variable is what lets the CLI (`kardinal ...`), which
    has no `--base-url` flag, target another host than the default.
    """
    return base_url or os.environ.get(BASE_URL_ENV_VAR) or DEFAULT_BASE_URL


class Transport:
    def __init__(
        self,
        *,
        api_key: str,
        base_url: Optional[str] = None,
        timeout: float = 30,
        max_retries: int = 3,
    ) -> None:
        self._max_retries = max_retries
        self.base_url = resolve_base_url(base_url)
        self._client = httpx.Client(
            base_url=self.base_url,
            timeout=timeout,
            headers={"Authorization": f"Bearer {api_key}"},
        )
        self._closed = False

    def close(self) -> None:
        self._closed = True
        self._client.close()

    def __enter__(self) -> "Transport":
        return self

    def __exit__(self, *exc_info: Any) -> None:
        self.close()

    def request(
        self,
        method: str,
        path: str,
        *,
        json: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """Send one request, retrying per `_core.retry`'s policy, and raise a
        `KardinalError` subclass on a failed response.
        """
        if self._closed:
            raise KardinalError(
                "This client was already closed; create a new Kardinal() "
                "instance instead of reusing one after close()/__exit__.",
                code="CLIENT_CLOSED",
                status=0,
                request_id=None,
                retryable=False,
            )
        attempt = 0
        while True:
            try:
                response = self._client.request(method, path, json=json, params=params)
            except httpx.TransportError as exc:
                if attempt < self._max_retries and retry.is_retryable(
                    method, status=None, network_error=True
                ):
                    attempt += 1
                    retry.sleep(attempt)
                    continue
                raise KardinalConnectionError(
                    str(exc),
                    code="CONNECTION_ERROR",
                    status=0,
                    request_id=None,
                    retryable=False,
                ) from exc

            if response.status_code < 300:
                if response.status_code == 204 or not response.content:
                    return None
                try:
                    return response.json()
                except ValueError as exc:
                    raise KardinalError(
                        f"Server returned a {response.status_code} with a "
                        f"non-JSON body: {exc}",
                        code="INVALID_RESPONSE_BODY",
                        status=response.status_code,
                        request_id=response.headers.get("X-Request-Id"),
                        retryable=False,
                    ) from exc

            if attempt < self._max_retries and retry.is_retryable(
                method, status=response.status_code, network_error=False
            ):
                attempt += 1
                retry.sleep(attempt)
                continue
            raise self._error_for(response)

    def _error_for(self, response: httpx.Response) -> KardinalError:
        request_id = response.headers.get("X-Request-Id")
        errors: list = []
        warnings: list = []
        if response.content:
            try:
                body = response.json()
                errors = body.get("errors") or []
                warnings = body.get("warnings") or []
            except ValueError:
                pass
        return from_response(
            status=response.status_code, request_id=request_id, errors=errors, warnings=warnings
        )
