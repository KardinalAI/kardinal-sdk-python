"""Local validation of the request models: what `PlanCreate`/`Order`
reject or fill in before anything is sent (or billed).
"""

import pytest
from pydantic import ValidationError

from kardinal.routing import models
from kardinal.routing._annotations import unknown_fields
from kardinal.routing.plans import Order, PlanCreate

_RESOURCE = {
    "id": "r1",
    "vehicleProfile": {"type": "car"},
    "workingTimeWindow": {"begin": "2026-10-01T08:00:00Z", "end": "2026-10-01T18:00:00Z"},
}
_STOP = {"type": "single", "id": "s1", "position": {"lat": 48.85, "lon": 2.35}}


def _order(**fields) -> dict:
    return {"id": "o1", "stops": [_STOP], **fields}


def test_an_empty_plan_is_rejected() -> None:
    with pytest.raises(ValidationError):
        PlanCreate.model_validate({})


def test_an_unknown_field_is_rejected() -> None:
    with pytest.raises(ValidationError):
        PlanCreate.model_validate({"resources": [_RESOURCE], "bogusField": 123})


def test_a_client_supplied_id_is_rejected_like_the_api_would() -> None:
    # PlanCreate has no `id` field at all: extra="forbid" rejects it.
    with pytest.raises(ValidationError):
        PlanCreate.model_validate({"id": "should-not-exist", "resources": [_RESOURCE]})


def test_a_minimal_valid_plan_is_accepted_with_its_defaults() -> None:
    plan = PlanCreate.model_validate({"resources": [_RESOURCE]})
    assert len(plan.resources) == 1
    assert plan.lateDeparture is False


def test_empty_resources_and_stops_are_accepted_like_openapi_yaml() -> None:
    PlanCreate.model_validate({"resources": [], "orders": [_order(stops=[])]})


def test_an_id_outside_the_allowed_characters_is_rejected() -> None:
    with pytest.raises(ValidationError):
        PlanCreate.model_validate({"resources": [{**_RESOURCE, "id": "r 1"}]})
    with pytest.raises(ValidationError):
        PlanCreate.model_validate({"resources": [], "orders": [_order(id="é")]})


def test_a_malformed_iso_8601_duration_is_rejected() -> None:
    with pytest.raises(ValidationError):
        PlanCreate.model_validate({"resources": [], "maxOptimizationDuration": "10s"})
    with pytest.raises(ValidationError):
        PlanCreate.model_validate({"resources": [], "orders": [_order(maxStopSpan="1h")]})


def test_a_non_integer_priority_is_rejected() -> None:
    with pytest.raises(ValidationError):
        PlanCreate.model_validate({"resources": [], "orders": [_order(priority=1.5)]})
    with pytest.raises(ValidationError):
        PlanCreate.model_validate({"resources": [{**_RESOURCE, "priority": 0.5}]})


def test_an_unknown_vehicle_profile_type_is_rejected() -> None:
    with pytest.raises(ValidationError):
        PlanCreate.model_validate({"resources": [{**_RESOURCE, "vehicleProfile": {"type": "boat"}}]})


def test_an_unknown_resource_field_is_kept_so_submit_can_report_it() -> None:
    # Dropping it here is what used to make a misspelled optional field
    # undetectable: `submit()` raises on what `unknown_fields()` finds.
    plan = PlanCreate.model_validate({"resources": [{**_RESOURCE, "bogus": 1}]})
    assert unknown_fields(plan) == ["plan.resources[0].bogus"]
    assert plan.resources[0].priority == 0


def test_a_stop_keeps_its_type_discriminator() -> None:
    order = Order.model_validate(_order())
    assert isinstance(order.stops[0], models.SingleStop)
    assert order.model_dump(mode="json")["stops"][0]["type"] == "single"


def test_a_stop_without_its_type_discriminator_is_rejected() -> None:
    stop = {k: v for k, v in _STOP.items() if k != "type"}
    with pytest.raises(ValidationError):
        Order.model_validate(_order(stops=[stop]))
