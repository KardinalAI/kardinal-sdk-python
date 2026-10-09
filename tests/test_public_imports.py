"""Everything user code needs is importable from `kardinal` itself — no
`kardinal._core` in anything shown to users (P2).
"""

import subprocess
import sys
from pathlib import Path

import kardinal
from kardinal import routing
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


def test_the_pre_submit_check_is_reachable_without_a_private_module() -> None:
    """`submit()` raises on an unknown key, so a caller needs a way to ask
    first. It lived in `_annotations`, which no user should have to import.
    """
    from kardinal.routing import UnknownField, unknown_fields
    from kardinal.routing._annotations import unknown_fields as private

    assert unknown_fields is private
    assert UnknownField is not None
    assert {"unknown_fields", "UnknownField"} <= set(dir(routing))


def test_exposing_it_did_not_make_help_load_the_models() -> None:
    """The CLI imports the models only inside command bodies, so `--help`
    answers without building every generated class. Re-exporting eagerly
    from `kardinal.routing` would have undone that silently.
    """
    code = "import sys; from kardinal import cli; print('kardinal.routing.models' in sys.modules)"
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=True
    )
    assert result.stdout.strip() == "False"
