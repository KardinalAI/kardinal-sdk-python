import pytest

from kardinal._core.auth import EmptyApiKeyError, MissingApiKeyError, resolve_api_key
from kardinal._core.errors import KardinalError


def test_explicit_argument_wins_over_env_var(monkeypatch) -> None:
    monkeypatch.setenv("KARDINAL_API_KEY", "from-env")
    assert resolve_api_key("from-arg") == "from-arg"


def test_falls_back_to_env_var_when_argument_is_none(monkeypatch) -> None:
    monkeypatch.setenv("KARDINAL_API_KEY", "from-env")
    assert resolve_api_key(None) == "from-env"


def test_raises_missing_api_key_error_when_neither_is_set(monkeypatch) -> None:
    monkeypatch.delenv("KARDINAL_API_KEY", raising=False)
    with pytest.raises(MissingApiKeyError) as exc_info:
        resolve_api_key(None)
    assert isinstance(exc_info.value, KardinalError)
    assert exc_info.value.code == "MISSING_API_KEY"
    assert exc_info.value.retryable is False


def test_empty_string_argument_raises_dedicated_error_instead_of_falling_back(
    monkeypatch,
) -> None:
    """api_key="" is a provided-but-empty value, not "nothing was passed" —
    silently falling back to the env var here would hide a config bug (e.g.
    an unset shell variable interpolated into an empty string).
    """
    monkeypatch.setenv("KARDINAL_API_KEY", "from-env")
    with pytest.raises(EmptyApiKeyError) as exc_info:
        resolve_api_key("")
    assert isinstance(exc_info.value, KardinalError)
    assert exc_info.value.code == "EMPTY_API_KEY"
