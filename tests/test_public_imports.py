"""Everything user code needs is importable from `kardinal` itself — no
`kardinal._core` in anything shown to users (P2).
"""

from pathlib import Path

import kardinal
from kardinal._core import auth, errors, pagination

_PUBLIC = {
    "KardinalError": errors.KardinalError,
    "KardinalAuthError": errors.KardinalAuthError,
    "KardinalLimitError": errors.KardinalLimitError,
    "KardinalValidationError": errors.KardinalValidationError,
    "KardinalNotFoundError": errors.KardinalNotFoundError,
    "KardinalRateLimitError": errors.KardinalRateLimitError,
    "KardinalServerError": errors.KardinalServerError,
    "KardinalTimeoutError": errors.KardinalTimeoutError,
    "KardinalOptimizationError": errors.KardinalOptimizationError,
    "KardinalConnectionError": errors.KardinalConnectionError,
    "MissingApiKeyError": auth.MissingApiKeyError,
    "EmptyApiKeyError": auth.EmptyApiKeyError,
    "Page": pagination.Page,
}


def test_public_names_are_exported_from_the_package_root() -> None:
    for name, obj in _PUBLIC.items():
        assert getattr(kardinal, name) is obj
        assert name in kardinal.__all__


def test_every_exception_class_in_core_is_exported() -> None:
    defined = {
        name
        for module in (errors, auth)
        for name, obj in vars(module).items()
        if isinstance(obj, type) and issubclass(obj, errors.KardinalError)
    }
    assert defined <= set(kardinal.__all__)


def test_readme_never_shows_a_private_import() -> None:
    readme = Path(__file__).resolve().parent.parent / "README.md"
    assert "_core" not in readme.read_text()
