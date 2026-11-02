"""Ids, versions, states and waypoints are plain values: no `.root`, and
`json.dumps` (so a Flask `jsonify`) accepts them.
"""

import json
import typing
from enum import Enum

import httpx
import pytest
import respx
from pydantic import BaseModel, RootModel, ValidationError

from kardinal._core.transport import DEFAULT_BASE_URL, Transport
from kardinal.routing import models
from kardinal.routing.plans import Plan, PlanCreate, PlansAPI
from kardinal.routing.solutions import SolutionsAPI

_PLAN_ID = "4cbd0ab8-282c-4b30-b981-29e1ed8a2016"
_AGENCY = "BLD0000001_demo"
_SCALARS = (str, int, float, bool)


def _apis():
    transport = Transport(api_key="test-key")
    plans = PlansAPI(transport)
    return plans, SolutionsAPI(transport, plans)


def _tour():
    position = {"lat": 48.85, "lon": 2.35}
    return {
        "resourceId": "truck-1",
        "mode": "car",
        "wayPoints": [
            {"type": "begin", "position": position, "status": "optimized"},
            {"type": "stop", "stopId": "stop-1", "position": position, "status": "fixed"},
            {"type": "break", "position": position},
            {"type": "stop", "stopId": "stop-2", "position": position},
            {"type": "end", "position": position},
        ],
    }


@respx.mock
def test_a_stops_waypoint_ids_are_plain_strings() -> None:
    respx.get(f"{DEFAULT_BASE_URL}/plans/{_PLAN_ID}/solution").mock(
        return_value=httpx.Response(200, json={"item": {
            "planId": _PLAN_ID, "planVersion": 2, "tours": [_tour()],
        }})
    )
    solution = _apis()[1].get(_PLAN_ID)
    (tour,) = solution.tours

    stop_ids = [wp.stopId for wp in tour.wayPoints if wp.type == "stop"]

    assert stop_ids == ["stop-1", "stop-2"]
    assert all(type(stop_id) is str for stop_id in stop_ids)
    assert json.dumps(stop_ids) == '["stop-1", "stop-2"]'
    assert json.dumps(solution.planVersion) == "2"
    assert json.dumps(tour.mode) == '"car"'
    assert json.dumps([wp.status for wp in tour.wayPoints]) == (
        '["optimized", "fixed", null, null, null]'
    )


@respx.mock
def test_a_stored_plan_dumps_to_json_as_it_is() -> None:
    item = {"id": _PLAN_ID, "agencyId": _AGENCY, "version": 4, "resources": [], "state": "optimized"}
    respx.get(f"{DEFAULT_BASE_URL}/plans/{_PLAN_ID}").mock(
        return_value=httpx.Response(200, json={"item": item})
    )
    respx.get(f"{DEFAULT_BASE_URL}/plans").mock(
        return_value=httpx.Response(200, json={
            "items": [{"id": _PLAN_ID, "state": "optimized"}],
            "paging": {"total": 1, "totalPages": 1, "page": 1},
        })
    )
    plans = _apis()[0]

    stored = plans.get(_PLAN_ID)
    listed = plans.list().items[0]

    assert json.dumps([stored.version, stored.agencyId, stored.state]) == (
        f'[4, "{_AGENCY}", "optimized"]'
    )
    assert json.dumps(listed.state) == '"optimized"'
    assert listed.state == "optimized"


def _unwrapped(annotation) -> list:
    """Every class an annotation mentions, through Optional, List, Dict,
    Union and Annotated."""
    found = [annotation] if isinstance(annotation, type) else []
    for arg in typing.get_args(annotation):
        found += _unwrapped(arg)
    return found


def test_no_model_field_is_a_wrapper_around_a_scalar_or_an_enum() -> None:
    offenders = []
    for name, cls in vars(models).items():
        if not (isinstance(cls, type) and issubclass(cls, BaseModel)) or cls is BaseModel:
            continue
        for field_name, field in cls.model_fields.items():
            for inner in _unwrapped(field.annotation):
                if not (isinstance(inner, type) and issubclass(inner, RootModel)):
                    continue
                root = inner.model_fields["root"].annotation
                if isinstance(root, type) and issubclass(root, (*_SCALARS, Enum)):
                    offenders.append(f"{name}.{field_name}: {inner.__name__}")
    assert offenders == []


def test_the_unions_of_stops_and_waypoints_keep_their_discriminator() -> None:
    def discriminators(model, field_name):
        found = []
        for node in [model.model_fields[field_name].annotation]:
            stack = [node]
            while stack:
                current = stack.pop()
                stack += typing.get_args(current)
                found += [
                    getattr(meta, "discriminator", None)
                    for meta in getattr(current, "__metadata__", ())
                ]
        return [d for d in found if d]

    assert discriminators(models.Order, "stops") == ["type"]
    assert discriminators(models.Tour, "wayPoints") == ["type"]


def test_an_invalid_stop_id_is_reported_under_the_stops_type() -> None:
    stop = {"type": "single", "id": "s 1", "position": {"lat": "x", "lon": 2.35}}
    with pytest.raises(ValidationError) as caught:
        Plan.model_validate({
            "id": _PLAN_ID, "resources": [], "orders": [{"id": "o1", "stops": [stop]}],
        })
    errors = caught.value.errors()
    assert len(errors) == 2
    assert all(error["loc"][:4] == ("orders", 0, "stops", 0) for error in errors)
    assert all(error["loc"][4] == "single" for error in errors)
    assert [error["loc"][5:] for error in errors] == [("id",), ("position", "lat")]


def test_an_invalid_id_or_duration_is_still_refused() -> None:
    with pytest.raises(ValidationError):
        models.Order.model_validate({"id": "o 1", "stops": []})
    with pytest.raises(ValidationError):
        models.Order.model_validate({"id": "o1", "stops": [], "requiredSkills": ["a b"]})
    with pytest.raises(ValidationError):
        PlanCreate.model_validate({"resources": [], "accessDurationsByStopTag": {"t": "10s"}})


def test_no_scalar_root_model_is_left_for_the_equality_patch_to_cover() -> None:
    """`_annotations.py` no longer patches `==`/`hash`/`str` on scalar
    RootModels, because the generated models hold none. If one reappears,
    this fails, and the patch has to come back."""
    scalar_roots = [
        name
        for name, cls in vars(models).items()
        if isinstance(cls, type)
        and issubclass(cls, RootModel)
        and cls is not RootModel
        and isinstance(cls.model_fields["root"].annotation, type)
        and issubclass(cls.model_fields["root"].annotation, (*_SCALARS, Enum))
    ]
    assert scalar_roots == []
