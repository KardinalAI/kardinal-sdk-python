"""A misspelled optional field used to vanish without a trace: neither the
SDK nor the API complains, and the plan is optimized as if the field had
never been written. These cover keeping such a key and reporting it.
"""

import pytest

from kardinal import UnknownFieldError
from kardinal.routing import models
from kardinal.routing._annotations import unknown_fields, validate_response
from kardinal.routing.plans import Order, Plan, PlanCreate

_TW = {"begin": "2026-10-01T08:00:00Z", "end": "2026-10-01T18:00:00Z"}
_RESOURCE = {"id": "r1", "vehicleProfile": {"type": "car"}, "workingTimeWindow": _TW}
_STOP = {"type": "single", "id": "s1", "position": {"lat": 48.85, "lon": 2.35}}


def test_a_clean_plan_reports_nothing() -> None:
    plan = PlanCreate.model_validate({"resources": [_RESOURCE], "orders": [{"id": "o1", "stops": [_STOP]}]})
    assert [f.path for f in unknown_fields(plan)] == []


def test_a_misspelled_field_on_a_resource_is_reported() -> None:
    plan = PlanCreate.model_validate({"resources": [{**_RESOURCE, "maxWorkingDurationn": "PT8H"}]})
    assert [f.path for f in unknown_fields(plan)] == ["plan.resources[0].maxWorkingDurationn"]


def test_a_misspelled_field_nested_under_a_union_is_reported() -> None:
    # `stops` and `breaks` hold their items in a RootModel union. A model
    # compiles its members' validators into itself, so this only works if
    # every dependant was rebuilt after the members — the case most likely
    # to regress silently.
    plan = PlanCreate.model_validate(
        {
            "resources": [
                {
                    **_RESOURCE,
                    "breaks": [
                        {"type": "timeWindowBreak", "duration": "PT45M", "timeWindow": _TW, "oops": 1}
                    ],
                }
            ],
            "orders": [{"id": "o1", "stops": [{**_STOP, "operationDurationn": "PT5M"}]}],
        }
    )
    assert sorted(f.path for f in unknown_fields(plan)) == [
        "plan.orders[0].stops[0].operationDurationn",
        "plan.resources[0].breaks[0].oops",
    ]


def test_every_unknown_field_is_reported_at_once() -> None:
    plan = PlanCreate.model_validate(
        {
            "resources": [{**_RESOURCE, "a": 1}, {**_RESOURCE, "id": "r2", "b": 2}],
            "orders": [{"id": "o1", "stops": [_STOP]}],
        }
    )
    assert len(unknown_fields(plan)) == 2


def test_submit_refuses_to_send_a_plan_with_an_unknown_field() -> None:
    class _NeverCalled:
        def request(self, *args, **kwargs):
            raise AssertionError("submit() sent the plan instead of raising")

    from kardinal.routing.plans import PlansAPI

    plan = PlanCreate.model_validate({"resources": [{**_RESOURCE, "bogus": 1}]})
    with pytest.raises(UnknownFieldError) as excinfo:
        PlansAPI(_NeverCalled()).submit(plan)
    assert excinfo.value.paths == ["plan.resources[0].bogus"]
    assert "bogus" in str(excinfo.value)


def test_a_response_carrying_an_unknown_field_still_parses() -> None:
    # The same classes read responses. Refusing a key the server added
    # would break every installed client the day the API gains a field.
    item = {
        "id": "4cbd0ab8-282c-4b30-b981-29e1ed8a2016",
        "resources": [{**_RESOURCE, "fieldAddedByAFutureApi": "x"}],
        "aPlanLevelFieldAddedLater": 1,
    }
    plan = validate_response(Plan, item)
    assert plan.resources[0].model_extra == {"fieldAddedByAFutureApi": "x"}


def test_a_kept_key_round_trips_on_update_instead_of_being_deleted() -> None:
    # Keeping the key is also what `update()` needs: it replaces the whole
    # plan, so a field read by `get()` that this SDK version doesn't know
    # would be deleted server-side if it were dropped on the way back.
    # `submit()` never reaches serialization — it raises first.
    item = {
        "id": "4cbd0ab8-282c-4b30-b981-29e1ed8a2016",
        "resources": [{**_RESOURCE, "fieldAddedByAFutureApi": "x"}],
    }
    plan = validate_response(Plan, item)
    assert "fieldAddedByAFutureApi" in plan.model_dump_json()


def test_the_generated_models_still_build_normally() -> None:
    resource = models.Resource.model_validate(_RESOURCE)
    order = Order.model_validate({"id": "o1", "stops": [_STOP]})
    assert resource.priority == 0
    assert isinstance(order.stops[0], models.SingleStop)


def test_update_warns_on_a_near_miss_but_not_on_an_unknown_api_field() -> None:
    # update() can't raise: the plan usually came from get(), so an unknown
    # key may be a field the API added, which must be sent back untouched.
    # A key one edit away from a declared one is the case that can't be.
    import warnings as _warnings

    from kardinal.routing.plans import PlansAPI

    base = {"id": "4cbd0ab8-282c-4b30-b981-29e1ed8a2016", "resources": [_RESOURCE]}

    class _Echo:
        def request(self, *args, **kwargs):
            return {"item": base}

    def _warnings_for(resource_extra: dict) -> list:
        plan = validate_response(Plan, {**base, "resources": [{**_RESOURCE, **resource_extra}]})
        with _warnings.catch_warnings(record=True) as caught:
            _warnings.simplefilter("always")
            PlansAPI(_Echo()).update(plan)
        return caught

    assert _warnings_for({"fieldAddedByAFutureApi": "x"}) == []
    near_miss = _warnings_for({"maxWorkingDurationn": "PT8H"})
    assert len(near_miss) == 1
    assert "maxWorkingDuration" in str(near_miss[0].message)


def test_a_server_assigned_key_is_not_reported_as_a_spelling_mistake() -> None:
    plan = PlanCreate.model_validate({"id": "deadbeef", "resources": [_RESOURCE]})
    field = unknown_fields(plan)[0]
    assert field.path == "plan.id"
    assert field.suggestion is None
    assert field.server_assigned
    assert "server assigns it" in str(field)


def test_a_plausible_future_api_field_gets_no_suggestion() -> None:
    # The reason this uses edit distance and not difflib's similarity
    # ratio: `maxDrivingDuration` scores above 0.6 against
    # `maxWorkingDuration` while being four edits away, so `update()` would
    # have warned on every call once the API grew such a field.
    from kardinal.routing._annotations import _describe

    for plausible in ("maxDrivingDuration", "maxLoadingDuration", "maxRestDuration"):
        field = _describe(plausible, models.Resource, f"plan.resources[0].{plausible}")
        assert field.suggestion is None, plausible


def test_a_real_typo_still_gets_its_suggestion() -> None:
    from kardinal.routing._annotations import _describe

    for typo in ("maxWorkingDurationn", "maxworkingduration", "MaxWorkingDuration"):
        field = _describe(typo, models.Resource, f"plan.resources[0].{typo}")
        assert field.suggestion == "maxWorkingDuration", typo


def test_server_assigned_only_applies_to_the_plan_itself() -> None:
    from kardinal.routing._annotations import _describe

    assert _describe("version", models.Plan, "plan.version").server_assigned
    # An order has no server-assigned `version`; claiming otherwise would
    # send the caller looking for something that doesn't exist.
    assert not _describe("version", models.Order, "plan.orders[0].version").server_assigned


def test_a_short_name_is_not_matched_to_an_unrelated_short_field() -> None:
    # Two edits on a two-letter name is a different word, not a typo.
    from kardinal.routing._annotations import _describe

    assert _describe("id", PlanCreate, "plan.id").suggestion is None
