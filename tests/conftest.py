import pytest


@pytest.fixture(autouse=True)
def api_key_env(monkeypatch):
    monkeypatch.setenv("KARDINAL_API_KEY", "test-key")
