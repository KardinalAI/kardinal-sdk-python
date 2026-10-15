"""Exception hierarchy, organized by family.

Every public exception carries `code`, `status`, `request_id`, `retryable`,
`warnings`, `errors`, `details`. `retryable` is computed here — the API doesn't provide it. An
unrecognized `code` falls back to the family deduced from the HTTP status
rather than disappearing, since `Error.code` in openapi.yaml documents that
new codes may be added in a future non-breaking release.

`request_id` is `None` more often than not: openapi.yaml documents no
request-id header or field anywhere, so this is best-effort — populated only
when the server happens to send a `X-Request-Id` response header.

`warnings` is `EnvelopedErrors.warnings`: on a rejected payload, amendments
the server applied before the rejecting error was found. Empty on most
failures — it's populated specifically for the case of "some fields were
silently amended, and *then* something else failed validation".

`errors` is every `Error` object of the response envelope, on every family,
and `details` the `properties.details` of the error that `code` came from:
the only way to tell apart errors sharing a code — every limit (plan size,
daily quota, exhausted credits) is `403 NOT_ALLOWED`, and so are a revoked
key and an archived plan updated without `force` (which `from_response`
tells apart by this very text), and two `404
NOT_FOUND` differ only by it ("Plan not found" vs. "Solution version not
found."). Both are empty for client-side errors and for a 429, which
carries no envelope.
"""

from __future__ import annotations

from typing import Any, List, Optional, Sequence, Type


class KardinalError(Exception):
    """Base of every exception this SDK raises for a failed API call."""

    def __init__(
        self,
        message: str,
        *,
        code: str,
        status: int,
        request_id: Optional[str],
        retryable: bool,
        warnings: Optional[List[dict]] = None,
        errors: Optional[List[dict]] = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.status = status
        self.request_id = request_id
        self.retryable = retryable
        self.warnings = warnings or []
        self.errors = errors or []

    @property
    def details(self) -> Optional[str]:
        """`properties.details` of the error `code` came from (the first
        one, unless a 403 put the reason for the 403 further down).
        """
        if not self.errors:
            return None
        source = next((e for e in self.errors if e.get("code") == self.code), self.errors[0])
        return (source.get("properties") or {}).get("details")


class KardinalAuthError(KardinalError):
    """The API key is missing, malformed, expired, revoked or regenerated, or
    was issued for another environment.

    Two statuses carry it: `NOT_AUTHENTICATED` (401) for a missing, malformed
    or expired key, and 403 `NOT_ALLOWED` with `.details` `the token is
    invalid` for a key that was revoked or regenerated.
    """


class KardinalLimitError(KardinalError):
    """A 403 (`NOT_ALLOWED`) that is a limit of the agency — a plan-size
    limit (resources, orders, stops, stops per order without
    `successiveStops`), the daily/monthly optimization quota, or exhausted
    credits — and, as a fallback, any 403 this SDK doesn't recognise.

    Two 403s that are not limits are recognised by their exact `.details`
    and raised as another family: a revoked key (`KardinalAuthError`) and an
    archived plan updated without `force` (`KardinalValidationError`). The
    fallback means other 403s, such as the two other paths of the
    authentication library (an invalid scope, failed claim checks), still
    land here: don't assume that every 403 left in this class is a limit.

    `.details` says which limit. For a plan-size limit, `.errors` also has
    an `INVALID_VALUE` entry, placed first by the API, whose
    `properties.path` and `properties.details` name the field and the
    allowed value. Classified on the 403 status rather than on a code, so
    finer codes the API may add under 403 land here too.
    """


class KardinalValidationError(KardinalError):
    """One of the 7 business codes returned under 400, or an archived plan
    updated, stopped or restarted without `force` (403 `NOT_ALLOWED`, with
    `.details` `Cannot update an archived plan, except with the 'force' query
    param`: add `force=True`).

    A single 400 can report several invalid fields at once: `.errors` has
    them all, not just the first. The archived-plan 403 is different: its
    `.errors` holds one `NOT_ALLOWED` error with no field path.
    """


class UnknownFieldWarning(UserWarning):
    """A key that looks like a typo, on a plan this SDK never read.

    Separate category so a caller — and the CLI — can tell it from any
    unrelated warning raised while the request is in flight.
    """


class UnknownFieldError(KardinalError):
    """A key no model declares was found in a plan being sent.

    Almost always a misspelled optional field. The API drops such a key
    without complaining, and so would this SDK, so the field it was meant
    to set stays unset and the plan is optimized without it: a stop with a
    misspelled `operationDuration` takes no time, an order with a
    misspelled `requiredSkills` can go on any resource. Raised by `submit()`
    on any such key, and by `update()` on one the server didn't send, before
    the request leaves — nothing downstream will report it.
    """

    def __init__(self, fields: Sequence[Any]) -> None:
        listed = "\n".join(f"  {field}" for field in fields)
        super().__init__(
            f"Unknown field(s) in the plan:\n{listed}",
            code="UNKNOWN_FIELD",
            status=0,
            request_id=None,
            retryable=False,
        )
        self.fields = list(fields)
        self.paths = [getattr(f, "path", str(f)) for f in fields]


class KardinalNotFoundError(KardinalError):
    """`NOT_FOUND` (404). Raised on every 404, including reads — no `get_or_none`."""


class KardinalRateLimitError(KardinalError):
    """429: a temporary overload, not a quota — retry after a pause, with an
    increasing delay. The response has an empty body (no envelope to parse
    a business `code`/`message` from): `.code` is set to the synthetic value
    `"RATE_LIMITED"`.
    """


class KardinalServerError(KardinalError):
    """`INTERNAL_SERVER_ERROR`, or any other 5xx."""


class KardinalTimeoutError(KardinalError):
    """The hard `timeout` guard on `solutions.wait()` elapsed before the plan
    reached a final state (checked one last time right at the deadline).
    Client-side only — no HTTP response backs it.
    """


class KardinalOptimizationError(KardinalError):
    """`solutions.wait()` can't return a solution for the plan version it
    was waiting on. Client-side only, like `KardinalTimeoutError`. `.code`:

    - `OPTIMIZATION_STALLED`: still optimizing well past its
      `maxOptimizationDuration` — the engine most likely crashed, and
      nothing will ever move the state again.
    - `NO_SOLUTION`: the plan ended (typically stopped before the engine
      started) without a solution for this version.
    - `PLAN_SUPERSEDED`: a newer version of the plan was pushed meanwhile.
    """

    def __init__(
        self,
        message: str,
        *,
        code: str,
        plan_id: str,
        plan_version: Optional[int],
        state: object,
    ) -> None:
        super().__init__(message, code=code, status=0, request_id=None, retryable=False)
        self.plan_id = plan_id
        self.plan_version = plan_version
        self.state = state


class KardinalConnectionError(KardinalError):
    """A network-level failure (DNS, connection refused, read timeout, ...)
    that never got an HTTP response at all, after retries were exhausted.
    `retryable` unless the request was a POST that may have reached the
    server: a connection that never opened is safe to retry, a response lost
    after sending a POST isn't (the plan may exist).
    Client-side only, same as `KardinalTimeoutError` — without this, a
    `except KardinalError:` written to catch "anything that can go wrong
    talking to the API" would miss what's arguably the most common real
    failure mode, since the raw `httpx` exception would propagate instead.
    """


_VALIDATION_CODES = frozenset(
    {
        "INVALID_INPUT",
        "ID_NOT_UNIQUE",
        "KEYS_NOT_UNIQUE",
        "INVALID_ID_REFERENCE",
        "INVALID_VALUE",
        "PRECONDITION_FAILED",
        "NOT_IMPLEMENTED",
    }
)
_AUTH_CODES = frozenset({"NOT_AUTHENTICATED"})

# The two 403s that are not limits. The backend answers both with `NOT_ALLOWED`
# and tells them apart only by `properties.details`, so the match is on the
# exact text; if the backend rewords one, the error falls back to
# `KardinalLimitError`, as before.
# Revoked or regenerated token: coretech/go-jwt, client/base.go
# (`abortWithStatusForbidden`).
_REVOKED_TOKEN_DETAILS = "the token is invalid"
# Archived plan without `force`: coretech/phoebe, manager/plan_manager.go
# (`validateAndUpdatePlan` and `UpdateRunning`).
_ARCHIVED_PLAN_DETAILS = "Cannot update an archived plan, except with the 'force' query param"


def _family_for_status(status: int) -> type:
    if status == 401:
        return KardinalAuthError
    if status == 404:
        return KardinalNotFoundError
    if status == 429:
        return KardinalRateLimitError
    if status >= 500:
        return KardinalServerError
    return KardinalValidationError


def from_response(
    *,
    status: int,
    request_id: Optional[str],
    errors: List[dict],
    warnings: Optional[List[dict]] = None,
    method: str = "GET",
) -> KardinalError:
    """Build the right exception for a failed HTTP response.

    `errors` is the parsed `EnvelopedErrors.errors` list (empty for a 429,
    which carries no envelope at all). `warnings` is `EnvelopedErrors.warnings`.

    `retryable` means "retrying is safe and may succeed": a 429 always (the
    cluster refuses it before any processing), a 5xx except on POST, where
    the plan may have been created before the server failed and a retry
    could create it twice.
    """
    # A plan-size limit comes back as a 403 whose first error is the
    # INVALID_VALUE naming the field, followed by the error that explains
    # the 403 itself: for a 403, `code` comes from the first error that
    # isn't a validation code.
    primary = errors[0] if errors else None
    if status == 403:
        primary = next((e for e in errors if e.get("code") not in _VALIDATION_CODES), primary)
    code = (primary.get("code") if primary else None) or _synthetic_code(status)
    message = (primary.get("message") if primary else None) or f"HTTP {status}"
    retryable = status == 429 or (status >= 500 and method.upper() != "POST")

    family: Type[KardinalError]
    details = ((primary or {}).get("properties") or {}).get("details")
    if status == 403 and code == "NOT_ALLOWED" and details == _REVOKED_TOKEN_DETAILS:
        family = KardinalAuthError
    elif status == 403 and code == "NOT_ALLOWED" and details == _ARCHIVED_PLAN_DETAILS:
        family = KardinalValidationError
    elif status == 403:
        family = KardinalLimitError
    elif code in _AUTH_CODES:
        family = KardinalAuthError
    elif code in _VALIDATION_CODES:
        family = KardinalValidationError
    elif code == "NOT_FOUND":
        family = KardinalNotFoundError
    elif code == "INTERNAL_SERVER_ERROR":
        family = KardinalServerError
    else:
        family = _family_for_status(status)

    return family(
        message, code=code, status=status, request_id=request_id,
        retryable=retryable, warnings=warnings, errors=errors,
    )


def _synthetic_code(status: int) -> str:
    return {401: "NOT_AUTHENTICATED", 403: "NOT_ALLOWED", 404: "NOT_FOUND", 429: "RATE_LIMITED"}.get(
        status, "INTERNAL_SERVER_ERROR" if status >= 500 else "INVALID_INPUT"
    )
