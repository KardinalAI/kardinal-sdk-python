"""HTTP transport: base URL, bearer auth, timeout, retry-on-network/5xx for
GET/PUT/DELETE (see `_core.retry`), and translation of failed responses into
the `_core.errors` hierarchy.
"""

from __future__ import annotations

import os
import platform
from importlib.metadata import PackageNotFoundError, version as _package_version
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


def sdk_version() -> str:
    """The installed `kardinal-ai` version, or `unknown` when the code runs
    without being installed as a package.
    """
    try:
        return _package_version("kardinal-ai")
    except PackageNotFoundError:
        return "unknown"


def client_header() -> str:
    """`X-Kardinal-Client`: short and stable, for the backend to filter on."""
    return f"kardinal-sdk-python/{sdk_version()}"


def user_agent(*, cli: bool = False) -> str:
    """`User-Agent`: SDK name and version, then Python version, OS and
    architecture (for diagnosis; nothing personal: no hostname, user or key),
    then the HTTP library. `cli` marks calls made by the `kardinal` command.
    """
    details = ["cli"] if cli else []
    details += [f"Python/{platform.python_version()}", f"{platform.system()}/{platform.machine()}"]
    return f"{client_header()} ({'; '.join(details)}) httpx/{httpx.__version__}"


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
            headers={
                "Authorization": f"Bearer {api_key}",
                "User-Agent": user_agent(),
                "X-Kardinal-Client": client_header(),
            },
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
        json: Any = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> Any:
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
                # A connection that never opened didn't send anything: safe
                # to retry even for a POST. Otherwise, a POST may have been
                # processed and only its response lost.
                never_sent = isinstance(exc, (httpx.ConnectError, httpx.ConnectTimeout))
                raise KardinalConnectionError(
                    str(exc),
                    code="CONNECTION_ERROR",
                    status=0,
                    request_id=None,
                    retryable=never_sent or method.upper() != "POST",
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
                retry.sleep(attempt, response.headers.get("Retry-After"))
                continue
            raise self._error_for(response, method)

    def _error_for(self, response: httpx.Response, method: str) -> KardinalError:
        request_id = response.headers.get("X-Request-Id")
        errors: list = []
        warnings: list = []
        if response.content:
            try:
                body = response.json()
            except ValueError:
                body = None
            if isinstance(body, dict):
                errors = _objects(body.get("errors"))
                warnings = _objects(body.get("warnings"))
        return from_response(
            status=response.status_code,
            request_id=request_id,
            errors=errors,
            warnings=warnings,
            method=method,
        )


def _objects(value: Any) -> list:
    """The error (or warning) objects of an error body, ignoring anything
    that isn't a list of objects: a malformed body must not hide the
    HTTP error behind a crash."""
    return [entry for entry in value if isinstance(entry, dict)] if isinstance(value, list) else []

