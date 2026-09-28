"""CLI plumbing shared by every product's `cli.py`: exit codes, output
formatting, and exception translation.
"""

from __future__ import annotations

import json
import sys
from enum import IntEnum
from typing import Any, NoReturn

import typer
from pydantic import BaseModel

from .errors import KardinalError


class Exit(IntEnum):
    OK = 0
    BUSINESS_ERROR = 1
    USAGE_ERROR = 2


def emit(payload: Any, *, force_json: bool = False) -> None:
    """JSON when stdout isn't a terminal or `--json` was passed, a readable
    table otherwise — serves both a human and a script without a flag in the
    common case, and keeps the CLI chainable.
    """
    if isinstance(payload, BaseModel):
        payload = payload.model_dump(mode="json", exclude_none=True)
    if force_json or not sys.stdout.isatty():
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        for row in payload if isinstance(payload, list) else [payload]:
            if isinstance(row, dict):
                for key, value in row.items():
                    typer.echo(f"{key:<24} {value}")
                typer.echo("")
            else:
                typer.echo(str(row))


def fail(exc: KardinalError) -> NoReturn:
    """Translate an SDK exception into CLI output and exit the process.
    The only place an exception gets formatted — no command formats one itself.

    Typed `NoReturn` so every `except ... : fail(exc)` call site is
    recognized by a type checker as exiting, not leaving a variable that
    only gets assigned on the success path possibly unbound.
    """
    emit(
        {"code": exc.code, "message": str(exc), "details": exc.details, "retryable": exc.retryable},
        force_json=True,
    )
    raise typer.Exit(Exit.BUSINESS_ERROR)
