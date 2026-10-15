import pytest

from kardinal._core.errors import (
    KardinalAuthError,
    KardinalConnectionError,
    KardinalLimitError,
    KardinalNotFoundError,
    KardinalRateLimitError,
    KardinalServerError,
    KardinalValidationError,
    from_response,
)


def _error(code: str) -> list:
    return [{"code": code, "message": "boom"}]


def test_not_authenticated_maps_to_kardinal_auth_error() -> None:
    exc = from_response(status=401, request_id=None, errors=_error("NOT_AUTHENTICATED"))
    assert isinstance(exc, KardinalAuthError)
    assert exc.code == "NOT_AUTHENTICATED"


def test_not_allowed_maps_to_kardinal_limit_error() -> None:
    """A NOT_ALLOWED with no recognised `details` is a limit (plan size,
    optimization quota, exhausted credits): the fallback for every 403 that
    is not one of the two exact messages tested at the end of this file.
    """
    exc = from_response(status=403, request_id=None, errors=_error("NOT_ALLOWED"))
    assert isinstance(exc, KardinalLimitError)
    assert not isinstance(exc, KardinalAuthError)
    assert exc.code == "NOT_ALLOWED"


def test_plan_size_limit_is_a_limit_error_whatever_the_first_error_code() -> None:
    """Observed live: exceeding a plan-size limit returns a 403 whose FIRST
    error is INVALID_VALUE (the field and the limit), followed by the
    NOT_ALLOWED that makes it a 403. The status decides the family, and
    `.code`/`.details` come from the error that explains the 403.
    """
    errors = [
        {
            "code": "INVALID_VALUE",
            "message": "The field value is not valid.",
            "properties": {
                "details": "The plan's number of resources (251) is greater than the allowed value (250)",
                "path": "resources",
            },
        },
        {
            "code": "NOT_ALLOWED",
            "message": "The requested action is not allowed.",
            "properties": {"details": "The resulting plan violates the quotas configuration of the agency"},
        },
    ]
    exc = from_response(status=403, request_id=None, errors=errors)
    assert isinstance(exc, KardinalLimitError)
    assert exc.code == "NOT_ALLOWED"
    assert str(exc) == "The requested action is not allowed."
    assert exc.details == "The resulting plan violates the quotas configuration of the agency"
    assert exc.errors == errors


def test_a_future_403_code_is_still_a_limit_error_and_becomes_the_code() -> None:
    """The backend may add finer codes, still under 403 (e.g. for quotas or
    credits): they must land in KardinalLimitError without an SDK change.
    """
    errors = [
        {"code": "INVALID_VALUE", "message": "bad", "properties": {"path": "resources"}},
        {"code": "QUOTA_EXCEEDED", "message": "quota"},
    ]
    exc = from_response(status=403, request_id=None, errors=errors)
    assert isinstance(exc, KardinalLimitError)
    assert exc.code == "QUOTA_EXCEEDED"


@pytest.mark.parametrize(
    "code",
    [
        "INVALID_INPUT",
        "ID_NOT_UNIQUE",
        "KEYS_NOT_UNIQUE",
        "INVALID_ID_REFERENCE",
        "INVALID_VALUE",
        "PRECONDITION_FAILED",
        "NOT_IMPLEMENTED",
    ],
)
def test_business_validation_codes_map_to_kardinal_validation_error(code) -> None:
    exc = from_response(status=400, request_id=None, errors=_error(code))
    assert isinstance(exc, KardinalValidationError)
    assert exc.errors == _error(code)


def test_internal_server_error_code_maps_to_kardinal_server_error() -> None:
    exc = from_response(status=500, request_id=None, errors=_error("INTERNAL_SERVER_ERROR"))
    assert isinstance(exc, KardinalServerError)


def test_unrecognized_code_falls_back_to_the_family_matching_http_status() -> None:
    """openapi.yaml documents that new business codes may be added in a
    future non-breaking release — an unrecognized code must not disappear,
    it should fall back to the family its HTTP status implies.
    """
    exc = from_response(status=404, request_id=None, errors=_error("SOME_FUTURE_CODE"))
    assert isinstance(exc, KardinalNotFoundError)
    assert exc.code == "SOME_FUTURE_CODE"


@pytest.mark.parametrize(
    ("status", "expected_family"),
    [
        (401, KardinalAuthError),
        (403, KardinalLimitError),
        (404, KardinalNotFoundError),
        (429, KardinalRateLimitError),
        (500, KardinalServerError),
        (502, KardinalServerError),
        (418, KardinalValidationError),  # anything else defaults to validation
    ],
)
def test_family_for_status_covers_every_status_bucket(status, expected_family) -> None:
    exc = from_response(status=status, request_id=None, errors=_error("SOME_FUTURE_CODE"))
    assert isinstance(exc, expected_family)


@pytest.mark.parametrize(
    ("status", "expected_code"),
    [
        (401, "NOT_AUTHENTICATED"),
        (403, "NOT_ALLOWED"),
        (404, "NOT_FOUND"),
        (429, "RATE_LIMITED"),
        (500, "INTERNAL_SERVER_ERROR"),
        (418, "INVALID_INPUT"),
    ],
)
def test_synthetic_code_used_when_response_carries_no_error_envelope(
    status, expected_code
) -> None:
    """A 429, in particular, is documented as carrying no error envelope at
    all — `.code` must still be set to something meaningful.
    """
    exc = from_response(status=status, request_id=None, errors=[])
    assert exc.code == expected_code
    assert exc.status == status


@pytest.mark.parametrize("status", [429, 500, 502, 503])
def test_retryable_is_true_for_429_and_5xx(status) -> None:
    exc = from_response(status=status, request_id=None, errors=[])
    assert exc.retryable is True


@pytest.mark.parametrize("status", [400, 401, 403, 404])
def test_retryable_is_false_below_429(status) -> None:
    exc = from_response(status=status, request_id=None, errors=[])
    assert exc.retryable is False


def test_connection_error_is_not_constructed_by_from_response() -> None:
    # KardinalConnectionError is client-side only (no HTTP response backs
    # it) — Transport raises it directly, never through from_response().
    assert KardinalConnectionError not in (
        type(from_response(status=s, request_id=None, errors=[])) for s in (401, 404, 429, 500)
    )


def test_every_family_carries_the_full_errors_list_and_details() -> None:
    """Every limit (plan size, daily quota, credits) is `403 NOT_ALLOWED`:
    only `properties.details` tells them apart, so it must reach every
    exception, not just `KardinalValidationError`.
    """
    errors = [
        {
            "code": "NOT_ALLOWED",
            "message": "The requested action is not allowed.",
            "properties": {"details": "Monthly credit quota exhausted"},
        }
    ]
    exc = from_response(status=403, request_id=None, errors=errors)
    assert isinstance(exc, KardinalLimitError)
    assert exc.errors == errors
    assert exc.details == "Monthly credit quota exhausted"


def test_details_is_none_without_an_error_envelope() -> None:
    exc = from_response(status=429, request_id=None, errors=[])
    assert exc.errors == []
    assert exc.details is None


def test_details_is_none_when_the_first_error_has_no_properties() -> None:
    exc = from_response(status=404, request_id=None, errors=_error("NOT_FOUND"))
    assert exc.details is None


def test_a_5xx_on_post_is_not_retryable() -> None:
    """The plan may have been created before the server failed: resubmitting
    could create (and bill) it twice. `retryable` means "safe to retry".
    """
    exc = from_response(status=500, request_id=None, errors=[], method="POST")
    assert isinstance(exc, KardinalServerError)
    assert exc.retryable is False


def test_a_5xx_on_get_put_delete_is_retryable() -> None:
    for method in ("GET", "PUT", "DELETE"):
        assert from_response(status=503, request_id=None, errors=[], method=method).retryable is True


def test_a_429_is_retryable_even_on_post() -> None:
    """The 429 comes from the cluster before any processing: nothing was created."""
    exc = from_response(status=429, request_id=None, errors=[], method="POST")
    assert exc.retryable is True


def test_an_error_entry_without_code_or_message_falls_back_to_synthetic_values() -> None:
    exc = from_response(status=404, request_id=None, errors=[{"properties": {}}])
    assert isinstance(exc, KardinalNotFoundError)
    assert exc.code == "NOT_FOUND"
    assert str(exc) == "HTTP 404"


def test_details_tell_two_404s_apart() -> None:
    """A plan that doesn't exist and a plan with no solution yet are both
    `404 NOT_FOUND`: only `details` tells them apart.
    """
    missing = from_response(
        status=404, request_id=None,
        errors=[{"code": "NOT_FOUND", "message": "m", "properties": {"details": "Plan not found"}}],
    )
    no_solution = from_response(
        status=404, request_id=None,
        errors=[{"code": "NOT_FOUND", "message": "m", "properties": {"details": "Solution not found"}}],
    )
    assert isinstance(missing, KardinalNotFoundError)
    assert missing.details != no_solution.details


def test_the_envelope_warnings_reach_the_error() -> None:
    warnings = [{"code": "INVALID_VALUE", "message": "amended"}]
    exc = from_response(status=400, request_id=None, errors=_error("INVALID_VALUE"), warnings=warnings)
    assert exc.warnings == warnings



def _not_allowed(details: str) -> list:
    return [{"code": "NOT_ALLOWED", "message": "boom", "properties": {"details": details}}]


def test_a_revoked_key_is_an_auth_error_not_a_limit_error() -> None:
    """The backend answers a revoked or regenerated token with 403
    NOT_ALLOWED and this exact `details`: it is a key problem, not a limit.
    """
    exc = from_response(status=403, request_id=None, errors=_not_allowed("the token is invalid"))
    assert isinstance(exc, KardinalAuthError)
    assert not isinstance(exc, KardinalLimitError)
    assert exc.status == 403
    assert exc.code == "NOT_ALLOWED"
    assert exc.details == "the token is invalid"


def test_an_archived_plan_without_force_is_a_validation_error() -> None:
    """The fix is in the request (add `force=true`), not a wait or a top-up."""
    details = "Cannot update an archived plan, except with the 'force' query param"
    exc = from_response(status=403, request_id=None, errors=_not_allowed(details))
    assert isinstance(exc, KardinalValidationError)
    assert not isinstance(exc, KardinalLimitError)
    assert exc.status == 403
    assert exc.code == "NOT_ALLOWED"
    assert exc.details == details


@pytest.mark.parametrize(
    "details",
    [
        "Insufficient credits",
        "The maximum number of optimizations per day (1500) has been reached for agency x",
        "the token is invalid, really",  # exact match only, never "contains"
        "Cannot update an archived plan",
    ],
)
def test_other_403_details_are_still_limit_errors(details: str) -> None:
    exc = from_response(status=403, request_id=None, errors=_not_allowed(details))
    assert isinstance(exc, KardinalLimitError)


def test_a_plan_size_limit_is_still_a_limit_error() -> None:
    errors = [
        {"code": "INVALID_VALUE", "message": "x", "properties": {"path": "a", "details": "too many"}},
        {"code": "NOT_ALLOWED", "message": "x", "properties": {"details": "plan size"}},
    ]
    exc = from_response(status=403, request_id=None, errors=errors)
    assert isinstance(exc, KardinalLimitError)
