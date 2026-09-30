import httpx
import pytest
import respx

from kardinal._core.errors import KardinalConnectionError, KardinalError, KardinalServerError
from kardinal._core.transport import DEFAULT_BASE_URL, Transport, resolve_base_url

_ENV_VAR_URL = "https://api.example.com/v2"
_EXPLICIT_URL = "https://api.example.org/v2"


def test_resolve_base_url_prefers_explicit_argument(monkeypatch) -> None:
    monkeypatch.setenv("KARDINAL_BASE_URL", _ENV_VAR_URL)
    assert resolve_base_url(_EXPLICIT_URL) == _EXPLICIT_URL


def test_resolve_base_url_falls_back_to_env_var(monkeypatch) -> None:
    monkeypatch.setenv("KARDINAL_BASE_URL", _ENV_VAR_URL)
    assert resolve_base_url(None) == _ENV_VAR_URL


def test_resolve_base_url_falls_back_to_production(monkeypatch) -> None:
    monkeypatch.delenv("KARDINAL_BASE_URL", raising=False)
    assert resolve_base_url(None) == DEFAULT_BASE_URL


def _transport() -> Transport:
    return Transport(api_key="test-key")


@respx.mock
def test_get_is_retried_and_succeeds_after_a_5xx(monkeypatch) -> None:
    monkeypatch.setattr("kardinal._core.retry.sleep", lambda attempt: None)
    route = respx.get(f"{DEFAULT_BASE_URL}/plans/p1").mock(
        side_effect=[
            httpx.Response(503),
            httpx.Response(200, json={"ok": True}),
        ]
    )
    result = _transport().request("GET", "/plans/p1")
    assert result == {"ok": True}
    assert route.call_count == 2


@respx.mock
def test_post_is_not_retried_on_a_5xx(monkeypatch) -> None:
    """No Idempotency-Key in the spec: retrying a POST after a 5xx could
    double-create a plan, so it must fail on the first 5xx, not retry.
    """
    monkeypatch.setattr("kardinal._core.retry.sleep", lambda attempt: None)
    route = respx.post(f"{DEFAULT_BASE_URL}/plans").mock(
        return_value=httpx.Response(503)
    )
    with pytest.raises(KardinalServerError):
        _transport().request("POST", "/plans", json={})
    assert route.call_count == 1


@respx.mock
def test_get_gives_up_after_max_retries(monkeypatch) -> None:
    monkeypatch.setattr("kardinal._core.retry.sleep", lambda attempt: None)
    route = respx.get(f"{DEFAULT_BASE_URL}/plans/p1").mock(
        return_value=httpx.Response(503)
    )
    with pytest.raises(KardinalServerError):
        Transport(api_key="test-key", max_retries=2).request("GET", "/plans/p1")
    assert route.call_count == 3  # initial attempt + 2 retries


@respx.mock
def test_network_error_is_retried_then_raises_connection_error(monkeypatch) -> None:
    monkeypatch.setattr("kardinal._core.retry.sleep", lambda attempt: None)
    route = respx.get(f"{DEFAULT_BASE_URL}/plans/p1").mock(
        side_effect=httpx.ConnectError("refused")
    )
    with pytest.raises(Exception):
        Transport(api_key="test-key", max_retries=1).request("GET", "/plans/p1")
    assert route.call_count == 2  # initial attempt + 1 retry


@respx.mock
def test_2xx_response_with_non_json_body_raises_kardinal_error() -> None:
    respx.get(f"{DEFAULT_BASE_URL}/plans/p1").mock(
        return_value=httpx.Response(200, content=b"not json", headers={"content-type": "text/plain"})
    )
    with pytest.raises(KardinalError) as exc_info:
        _transport().request("GET", "/plans/p1")
    assert exc_info.value.code == "INVALID_RESPONSE_BODY"
    assert exc_info.value.status == 200


@respx.mock
def test_204_response_returns_none() -> None:
    respx.delete(f"{DEFAULT_BASE_URL}/plans/p1").mock(return_value=httpx.Response(204))
    assert _transport().request("DELETE", "/plans/p1") is None


@respx.mock
def test_error_response_with_non_json_body_falls_back_to_empty_errors() -> None:
    respx.get(f"{DEFAULT_BASE_URL}/plans/p1").mock(
        return_value=httpx.Response(500, content=b"not json")
    )
    with pytest.raises(KardinalServerError) as exc_info:
        _transport().request("GET", "/plans/p1")
    assert exc_info.value.code == "INTERNAL_SERVER_ERROR"


def test_close_is_idempotent_and_usable_as_a_context_manager() -> None:
    with _transport() as transport:
        assert transport._closed is False
    assert transport._closed is True


def test_request_after_close_raises_client_closed_error() -> None:
    transport = _transport()
    transport.close()
    with pytest.raises(KardinalError) as exc_info:
        transport.request("GET", "/plans/p1")
    assert exc_info.value.code == "CLIENT_CLOSED"


def _installed_version() -> str:
    from importlib.metadata import version

    return version("kardinal-ai")


@respx.mock
def test_requests_identify_the_sdk_in_user_agent_and_x_kardinal_client() -> None:
    """The backend can only tell SDK traffic (and its version) apart from any
    other httpx client through these two headers.
    """
    route = respx.get(f"{DEFAULT_BASE_URL}/plans").mock(return_value=httpx.Response(200, json={}))
    Transport(api_key="test-key").request("GET", "/plans")
    headers = route.calls.last.request.headers
    product = f"kardinal-sdk-python/{_installed_version()}"
    assert headers["X-Kardinal-Client"] == product
    assert headers["User-Agent"].startswith(f"{product} (Python/")
    assert f" httpx/{httpx.__version__}" in headers["User-Agent"]
    assert "cli;" not in headers["User-Agent"]


@respx.mock
def test_a_5xx_on_submit_is_raised_as_not_retryable() -> None:
    route = respx.post(f"{DEFAULT_BASE_URL}/plans").mock(return_value=httpx.Response(500))
    with pytest.raises(KardinalServerError) as info:
        Transport(api_key="test-key").request("POST", "/plans", json={})
    assert info.value.retryable is False
    assert route.call_count == 1  # never retried automatically either


@respx.mock
def test_a_connection_that_never_opened_is_retryable_even_on_post() -> None:
    """ConnectError/ConnectTimeout: the request never reached the server."""
    respx.post(f"{DEFAULT_BASE_URL}/plans").mock(side_effect=httpx.ConnectTimeout("timed out"))
    with pytest.raises(KardinalConnectionError) as info:
        Transport(api_key="test-key").request("POST", "/plans", json={})
    assert info.value.retryable is True


@respx.mock
def test_a_read_failure_on_post_is_not_retryable() -> None:
    """The request may have been processed and only the response lost."""
    respx.post(f"{DEFAULT_BASE_URL}/plans").mock(side_effect=httpx.ReadTimeout("timed out"))
    with pytest.raises(KardinalConnectionError) as info:
        Transport(api_key="test-key").request("POST", "/plans", json={})
    assert info.value.retryable is False


@respx.mock
def test_a_read_failure_on_get_is_retryable(monkeypatch) -> None:
    monkeypatch.setattr("kardinal._core.retry.sleep", lambda attempt: None)
    respx.get(f"{DEFAULT_BASE_URL}/plans").mock(side_effect=httpx.ReadTimeout("timed out"))
    with pytest.raises(KardinalConnectionError) as info:
        Transport(api_key="test-key").request("GET", "/plans")
    assert info.value.retryable is True


@respx.mock
@pytest.mark.parametrize("body", [b"null", b"[1, 2]", b'"oops"'])
def test_error_response_whose_json_body_is_not_an_object_falls_back_to_empty_errors(body) -> None:
    respx.get(f"{DEFAULT_BASE_URL}/plans/p1").mock(
        return_value=httpx.Response(500, content=body)
    )
    with pytest.raises(KardinalServerError) as exc_info:
        _transport().request("GET", "/plans/p1")
    assert exc_info.value.code == "INTERNAL_SERVER_ERROR"
    assert exc_info.value.errors == []
