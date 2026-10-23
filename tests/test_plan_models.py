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


def test_an_unknown_plan_level_field_is_reported_like_any_other() -> None:
    plan = PlanCreate.model_validate({"resources": [_RESOURCE], "bogusField": 123})
    assert [f.path for f in unknown_fields(plan)] == ["plan.bogusField"]


def test_a_client_supplied_id_is_reported_rather_than_silently_lost() -> None:
    # PlanCreate has no `id` field: the server assigns one. Sending an `id`
    # anyway is not refused by the API — it answers 201 with a different id
    # — so a caller reusing the one they sent would address a plan that
    # doesn't exist. Reported here instead.
    plan = PlanCreate.model_validate({"id": "should-not-exist", "resources": [_RESOURCE]})
    assert [f.path for f in unknown_fields(plan)] == ["plan.id"]


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
    assert [f.path for f in unknown_fields(plan)] == ["plan.resources[0].bogus"]
    assert plan.resources[0].priority == 0


def test_a_stop_keeps_its_type_discriminator() -> None:
    order = Order.model_validate(_order())
    assert isinstance(order.stops[0], models.SingleStop)
    assert order.model_dump(mode="json")["stops"][0]["type"] == "single"


def test_a_stop_without_its_type_discriminator_is_rejected() -> None:
    stop = {k: v for k, v in _STOP.items() if k != "type"}
    with pytest.raises(ValidationError):
        Order.model_validate(_order(stops=[stop]))


@pytest.mark.parametrize("field", ["height", "width", "length"])
def test_a_truck_dimension_is_a_whole_number_of_centimetres(field: str) -> None:
    for accepted in (380, 380.0):
        truck = models.VehicleProfileTruck.model_validate({"type": "truck", field: accepted})
        dumped = truck.model_dump(mode="json", exclude_none=True)[field]
        assert dumped == 380
        assert isinstance(dumped, int)

    # 2.55 * 100 is 254.99999999999997: a size computed from metres must be
    # rounded, round(width_m * 100).
    for refused in (4.2, 2.55 * 100):
        with pytest.raises(ValidationError) as error:
            models.VehicleProfileTruck.model_validate({"type": "truck", field: refused})
        assert error.value.errors()[0]["type"] == "int_from_float"


def test_a_max_cumulated_cost_constraint_needs_its_maximum() -> None:
    # The API refuses a constraint without `maximum` with a 400: it is
    # refused here instead, before anything is sent.
    constraint = {"type": "maxCumulatedCost", "costsByResourceTag": {"rented": {"using": 100}}}
    with pytest.raises(ValidationError) as error:
        PlanCreate.model_validate({"resources": [_RESOURCE], "globalConstraints": [constraint]})
    assert [(e["type"], e["loc"][-1]) for e in error.value.errors()] == [("missing", "maximum")]

    plan = PlanCreate.model_validate(
        {"resources": [_RESOURCE], "globalConstraints": [{**constraint, "maximum": 1000}]}
    )
    assert plan.model_dump(mode="json", exclude_none=True)["globalConstraints"][0]["maximum"] == 1000
