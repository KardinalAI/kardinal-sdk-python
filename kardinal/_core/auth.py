"""API key resolution. Environment variable only — no `--api-key` CLI flag,
it would land in shell history and the process list.
"""

from __future__ import annotations

import os
from typing import Optional

from .errors import KardinalError

API_KEY_ENV_VAR = "KARDINAL_API_KEY"


class MissingApiKeyError(KardinalError):
    def __init__(self) -> None:
        super().__init__(
            f"No API key provided. Pass api_key=... to Kardinal(), or set the "
            f"{API_KEY_ENV_VAR} environment variable.",
            code="MISSING_API_KEY",
            status=0,
            request_id=None,
            retryable=False,
        )


class EmptyApiKeyError(KardinalError):
    """`api_key=""` was passed explicitly — distinct from not passing one at
    all: falling back to the environment variable here would silently hide
    a configuration bug (e.g. an unset shell variable interpolated as "").
    """

    def __init__(self) -> None:
        super().__init__(
            "api_key was passed as an empty string. Pass a real key, or "
            "omit the argument entirely to read it from "
            f"{API_KEY_ENV_VAR}.",
            code="EMPTY_API_KEY",
            status=0,
            request_id=None,
            retryable=False,
        )


def resolve_api_key(api_key: Optional[str]) -> str:
    if api_key is not None:
        if not api_key:
            raise EmptyApiKeyError()
        return api_key
    from_env = os.environ.get(API_KEY_ENV_VAR)
    if from_env:
        return from_env
    raise MissingApiKeyError()
