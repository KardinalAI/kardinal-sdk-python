import httpx
import respx

from kardinal import Kardinal, Whoami
from kardinal._core.transport import DEFAULT_BASE_URL

_PAGING = {"page": 1, "itemsPerPage": 1, "totalItems": 0}


@respx.mock
def test_whoami_returns_the_host_and_the_agency() -> None:
    route = respx.get(f"{DEFAULT_BASE_URL}/plans").mock(
        return_value=httpx.Response(
            200, json={"agencyId": "A_sandbox", "items": [], "paging": _PAGING}
        )
    )
    with Kardinal(api_key="k") as client:
        who = client.whoami()
    assert who == Whoami(baseUrl=DEFAULT_BASE_URL, agencyId="A_sandbox")
    params = dict(route.calls.last.request.url.params)
    assert params == {"page": "1", "itemsPerPage": "1", "archived": "excluded"}


@respx.mock
def test_whoami_without_agency_id_gives_none() -> None:
    respx.get(f"{DEFAULT_BASE_URL}/plans").mock(
        return_value=httpx.Response(200, json={"items": [], "paging": _PAGING})
    )
    with Kardinal(api_key="k") as client:
        assert client.whoami().agencyId is None
