from kardinal._core.errors import (
    KardinalAuthError,
    KardinalConnectionError,
    KardinalForbiddenError,
    KardinalLimitError,
    KardinalNotFoundError,
    KardinalRateLimitError,
    KardinalServerError,
    KardinalTimeoutError,
    KardinalValidationError,
)

_LEAF_CLASSES = [
    KardinalAuthError,
    KardinalLimitError,
    KardinalForbiddenError,
    KardinalNotFoundError,
    KardinalRateLimitError,
    KardinalServerError,
    KardinalTimeoutError,
    KardinalConnectionError,
]


def test_every_public_exception_carries_the_required_attributes() -> None:
    for cls in _LEAF_CLASSES:
        exc = cls("message", code="SOME_CODE", status=400, request_id="req-1", retryable=False)
        assert exc.code == "SOME_CODE"
        assert exc.status == 400
        assert exc.request_id == "req-1"
        assert exc.retryable is False
        assert exc.warnings == []


def test_validation_error_also_carries_the_full_errors_list() -> None:
    exc = KardinalValidationError(
        "message",
        code="INVALID_VALUE",
        status=400,
        request_id=None,
        retryable=False,
        errors=[{"code": "INVALID_VALUE", "message": "bad"}],
    )
    assert exc.errors == [{"code": "INVALID_VALUE", "message": "bad"}]


def test_validation_error_carries_amendments_applied_before_it_was_raised() -> None:
    exc = KardinalValidationError(
        "message",
        code="INVALID_VALUE",
        status=400,
        request_id=None,
        retryable=False,
        errors=[{"code": "INVALID_VALUE", "message": "bad"}],
        warnings=[{"code": "INVALID_VALUE", "message": "clamped"}],
    )
    assert exc.warnings == [{"code": "INVALID_VALUE", "message": "clamped"}]
