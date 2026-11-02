import json
import warnings
from enum import Enum

import httpx
import pytest
import respx

from kardinal._core.transport import DEFAULT_BASE_URL, Transport
from kardinal.routing import models
from kardinal.routing.plans import PlansAPI

_ENUMS = [
    obj
    for obj in vars(models).values()
    if isinstance(obj, type) and issubclass(obj, Enum) and obj.__module__ == models.__name__
]


def test_there_are_enums_to_check() -> None:
    assert len(_ENUMS) > 50


@pytest.mark.parametrize("cls", _ENUMS, ids=lambda c: c.__name__)
def test_every_enum_member_behaves_as_its_string_value(cls: type[Enum]) -> None:
    for m in cls:
        assert m == m.value
        assert str(m) == m.value
        assert f"{m}" == m.value
        assert json.dumps(m) == json.dumps(m.value)
        assert {m.value: 1}[m] == 1  # type: ignore[index]


def _plans() -> PlansAPI:
    return PlansAPI(Transport(api_key="test-key"))


@respx.mock
def test_get_status_compares_and_prints_as_a_string() -> None:
    respx.get(f"{DEFAULT_BASE_URL}/plans/p1/state").mock(
        return_value=httpx.Response(200, json={"item": {"state": "optimized"}})
    )
    status = _plans().get_status("p1")
    assert status == "optimized"
    assert status == models.PlanState.optimized
    assert str(status) == "optimized"
    assert isinstance(status, models.PlanState)


@respx.mock
def test_get_status_of_an_unknown_state_is_a_plan_state_equal_to_it() -> None:
    respx.get(f"{DEFAULT_BASE_URL}/plans/p1/state").mock(
        return_value=httpx.Response(200, json={"item": {"state": "someFutureState"}})
    )
    status = _plans().get_status("p1")
    assert isinstance(status, models.PlanState)
    assert status == "someFutureState"
    assert str(status) == "someFutureState"


def test_default_stop_kind_dumps_without_warning() -> None:
    stop = models.WayPointStop(type="stop", stopId="s1", position={"lat": 48.8, "lon": 2.3})
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        stop.model_dump()
        stop.model_dump(mode="json")
    assert stop.stopKind is models.StopKind.delivery
