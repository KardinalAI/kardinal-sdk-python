import json

import httpx
import pytest
import respx

from kardinal._core.errors import KardinalConnectionError, KardinalNotFoundError
from kardinal._core.transport import DEFAULT_BASE_URL, Transport
from kardinal.routing import models
from kardinal.routing.plans import Plan, PlanCreate, PlansAPI

_PLAN_ID = "4cbd0ab8-282c-4b30-b981-29e1ed8a2016"


def _plans() -> PlansAPI:
    return PlansAPI(Transport(api_key="test-key"))


@respx.mock
def test_submit_returns_plan_with_id() -> None:
    respx.post(f"{DEFAULT_BASE_URL}/plans").mock(
        return_value=httpx.Response(
            201, json={"item": {"id": _PLAN_ID, "resources": []}}
        )
    )
    plan = _plans().submit(PlanCreate(resources=[]))
    assert plan.id == _PLAN_ID


@respx.mock
def test_get_status_returns_plan_state() -> None:
    respx.get(f"{DEFAULT_BASE_URL}/plans/p1/state").mock(
        return_value=httpx.Response(200, json={"item": {"state": "optimized"}})
    )
    assert _plans().get_status("p1") == models.PlanState.optimized


@respx.mock
def test_list_sends_pagination_params_and_parses_paging() -> None:
    route = respx.get(f"{DEFAULT_BASE_URL}/plans").mock(
        return_value=httpx.Response(
            200,
            json={
                "items": [{"id": _PLAN_ID}],
                "paging": {"total": 1, "totalPages": 1, "page": 1, "itemsPerPage": 20},
            },
        )
    )
    page = _plans().list()
    sent_params = route.calls.last.request.url.params
    assert sent_params["page"] == "1"
    assert sent_params["itemsPerPage"] == "20"
    assert sent_params["archived"] == "excluded"
    assert page.total == 1
    assert page.items[0].id == _PLAN_ID
    assert page.next_page is None
    assert page.previous_page is None  # absent on the first page
    assert page.items_per_page == 20


@respx.mock
def test_list_parses_previous_and_next_page_on_a_middle_page() -> None:
    """Shape observed live: a middle page carries both `nextPage` and
    `previousPage`, and `itemsPerPage` echoes the requested page size.
    """
    respx.get(f"{DEFAULT_BASE_URL}/plans").mock(
        return_value=httpx.Response(
            200,
            json={
                "items": [{"id": _PLAN_ID}],
                "paging": {
                    "total": 21,
                    "totalPages": 5,
                    "page": 2,
                    "nextPage": 3,
                    "previousPage": 1,
                    "itemsPerPage": 5,
                },
            },
        )
    )
    page = _plans().list(page=2, items_per_page=5)
    assert (page.page, page.total_pages, page.total) == (2, 5, 21)
    assert page.next_page == 3
    assert page.previous_page == 1
    assert page.items_per_page == 5


@respx.mock
def test_404_raises_not_found_with_required_attributes() -> None:
    respx.get(f"{DEFAULT_BASE_URL}/plans/missing").mock(
        return_value=httpx.Response(
            404, json={"errors": [{"code": "NOT_FOUND", "message": "not found"}]}
        )
    )
    with pytest.raises(KardinalNotFoundError) as exc_info:
        _plans().get("missing")
    assert exc_info.value.code == "NOT_FOUND"
    assert exc_info.value.status == 404
    assert exc_info.value.retryable is False


@respx.mock
def test_network_failure_raises_connection_error_not_raw_httpx() -> None:
    respx.get(f"{DEFAULT_BASE_URL}/plans/p1").mock(
        side_effect=httpx.ConnectError("connection refused")
    )
    with pytest.raises(KardinalConnectionError) as exc_info:
        _plans().get("p1")
    assert exc_info.value.code == "CONNECTION_ERROR"
    assert exc_info.value.retryable is False
    assert isinstance(exc_info.value.__cause__, httpx.ConnectError)


@respx.mock
def test_start_and_stop_send_boolean_body_and_return_the_plan_reference() -> None:
    route = respx.put(f"{DEFAULT_BASE_URL}/plans/p1/running").mock(
        return_value=httpx.Response(200, json={"planId": "p1", "planVersion": 3})
    )
    plans = _plans()
    reference = plans.start("p1")
    assert route.calls.last.request.content == b"true"
    assert reference.planId == "p1"
    assert reference.planVersion.root == 3
    reference = plans.stop("p1")
    assert route.calls.last.request.content == b"false"
    assert reference.planId == "p1"


@respx.mock
def test_submit_copies_envelope_warnings_onto_the_plan() -> None:
    respx.post(f"{DEFAULT_BASE_URL}/plans").mock(
        return_value=httpx.Response(
            201,
            json={
                "item": {"id": _PLAN_ID, "resources": []},
                "warnings": [{"code": "INVALID_VALUE", "message": "clamped"}],
            },
        )
    )
    plan = _plans().submit(PlanCreate(resources=[]))
    assert plan.warnings[0].code.value == "INVALID_VALUE"


@respx.mock
def test_submit_defaults_warnings_to_empty_list() -> None:
    respx.post(f"{DEFAULT_BASE_URL}/plans").mock(
        return_value=httpx.Response(201, json={"item": {"id": _PLAN_ID, "resources": []}})
    )
    plan = _plans().submit(PlanCreate(resources=[]))
    assert plan.warnings == []


@respx.mock
def test_update_excludes_read_only_fields_from_the_request_body() -> None:
    route = respx.put(f"{DEFAULT_BASE_URL}/plans/{_PLAN_ID}").mock(
        return_value=httpx.Response(200, json={"item": {"id": _PLAN_ID, "resources": [], "version": 2}})
    )
    plan = Plan(
        id=_PLAN_ID, resources=[], version=1, agencyId="BLD1234567_production", running=True
    )
    updated = _plans().update(plan)
    sent = json.loads(route.calls.last.request.content)
    assert "version" not in sent
    assert "agencyId" not in sent
    assert "running" not in sent
    # `id` is `readOnly` in the spec: it only travels in the URL (the route
    # above matched on it). The server rejects a body `id` that doesn't
    # match the URL, and POST already rejects any body `id`.
    assert "id" not in sent
    assert updated.id == _PLAN_ID


@respx.mock
def test_update_sends_force_as_a_query_param() -> None:
    route = respx.put(f"{DEFAULT_BASE_URL}/plans/{_PLAN_ID}").mock(
        return_value=httpx.Response(200, json={"item": {"id": _PLAN_ID, "resources": []}})
    )
    _plans().update(Plan(id=_PLAN_ID, resources=[]), force=True)
    assert route.calls.last.request.url.params["force"] == "true"


@respx.mock
def test_start_and_stop_send_force_as_a_query_param() -> None:
    route = respx.put(f"{DEFAULT_BASE_URL}/plans/p1/running").mock(
        return_value=httpx.Response(200, json={"planId": "p1", "planVersion": 1})
    )
    plans = _plans()
    plans.start("p1", force=True)
    assert route.calls.last.request.url.params["force"] == "true"
    plans.stop("p1", force=False)
    assert route.calls.last.request.url.params["force"] == "false"


@respx.mock
def test_delete_sends_a_delete_request() -> None:
    route = respx.delete(f"{DEFAULT_BASE_URL}/plans/{_PLAN_ID}").mock(
        return_value=httpx.Response(204)
    )
    assert _plans().delete(_PLAN_ID) is None
    assert route.calls.last.request.method == "DELETE"


@respx.mock
def test_iter_all_chains_across_pages() -> None:
    respx.get(f"{DEFAULT_BASE_URL}/plans", params={"page": "1"}).mock(
        return_value=httpx.Response(
            200,
            json={
                "items": [{"id": "p1"}],
                "paging": {"total": 2, "totalPages": 2, "page": 1, "nextPage": 2},
            },
        )
    )
    respx.get(f"{DEFAULT_BASE_URL}/plans", params={"page": "2"}).mock(
        return_value=httpx.Response(
            200,
            json={
                "items": [{"id": "p2"}],
                "paging": {"total": 2, "totalPages": 2, "page": 2},
            },
        )
    )
    ids = [item.id for item in _plans().iter_all()]
    assert ids == ["p1", "p2"]


@respx.mock
def test_list_with_archived_only() -> None:
    route = respx.get(f"{DEFAULT_BASE_URL}/plans").mock(
        return_value=httpx.Response(
            200, json={"items": [], "paging": {"total": 0, "totalPages": 0, "page": 1}}
        )
    )
    _plans().list(archived="only")
    assert route.calls.last.request.url.params["archived"] == "only"
