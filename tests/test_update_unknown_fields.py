"""`update()` sorts an unknown key by where it came from.

The API drops any key it doesn't know — verified on both POST and PUT
against the sandbox — so a key it sends back is a real field by
construction, and a key only the caller added is a typo that would vanish
in silence. `get()` records the first kind; `update()` raises on the rest.
"""

import warnings

import pytest

from kardinal import UnknownFieldError
from kardinal.routing.plans import Plan, PlansAPI

_PID = "4cbd0ab8-282c-4b30-b981-29e1ed8a2016"
_TW = {"begin": "2026-10-07T08:00:00Z", "end": "2026-10-07T18:00:00Z"}
_RESOURCE = {"id": "r1", "vehicleProfile": {"type": "car"}, "workingTimeWindow": _TW}


class _Server:
    """Returns the plan it was built with, and records what was PUT."""

    def __init__(self, resources):
        self.item = {"id": _PID, "resources": resources}
        self.sent = None

    def request(self, method, path, **kwargs):
        if method == "PUT":
            self.sent = kwargs.get("json")
        return {"item": self.item}


def _fetched(resources):
    server = _Server(resources)
    api = PlansAPI(server)
    return api, api.get(_PID), server


def _resource_cls(plan):
    return type(plan.resources[0])


def test_a_field_the_api_added_is_sent_back_untouched() -> None:
    api, plan, server = _fetched([{**_RESOURCE, "modeAddedByApi": "standard"}])
    api.update(plan)
    assert server.sent["resources"][0]["modeAddedByApi"] == "standard"


def test_a_key_the_caller_added_is_refused() -> None:
    api, plan, _ = _fetched([{**_RESOURCE, "modeAddedByApi": "standard"}])
    plan.resources[0].maxWorkingDurationn = "PT8H"
    with pytest.raises(UnknownFieldError) as excinfo:
        api.update(plan)
    assert excinfo.value.paths == ["plan.resources[0].maxWorkingDurationn"]


def test_the_api_field_is_recognised_on_a_resource_added_afterwards() -> None:
    # Provenance is keyed by model type, not by path: a field the API added
    # has the same name on every object of that type, while `resources[3]`
    # moves as soon as the caller inserts or drops one.
    api, plan, _ = _fetched([{**_RESOURCE, "modeAddedByApi": "standard"}])
    plan.resources.append(
        _resource_cls(plan).model_validate({**_RESOURCE, "id": "r2", "modeAddedByApi": "x"})
    )
    api.update(plan)  # no exception


def test_reordering_resources_is_not_a_false_positive() -> None:
    api, plan, _ = _fetched(
        [{**_RESOURCE, "modeAddedByApi": "s"}, {**_RESOURCE, "id": "r2"}]
    )
    plan.resources.reverse()
    api.update(plan)  # no exception


def test_a_typo_on_a_resource_the_caller_added_is_refused() -> None:
    api, plan, _ = _fetched([_RESOURCE])
    plan.resources.append(
        _resource_cls(plan).model_validate({**_RESOURCE, "id": "r2", "oops": 1})
    )
    with pytest.raises(UnknownFieldError) as excinfo:
        api.update(plan)
    assert excinfo.value.paths == ["plan.resources[1].oops"]


def test_two_updates_in_a_row_still_accept_the_api_field() -> None:
    api, plan, _ = _fetched([{**_RESOURCE, "modeAddedByApi": "standard"}])
    again = api.update(plan)
    api.update(again)  # no exception


def test_model_copy_keeps_the_provenance() -> None:
    api, plan, _ = _fetched([{**_RESOURCE, "modeAddedByApi": "standard"}])
    api.update(plan.model_copy(deep=True))  # no exception


def test_a_hand_built_plan_falls_back_to_warning() -> None:
    # Nothing to sort by, so resemblance is all that's left. Warning, never
    # refusal: refusing would break the day the API adds a field, on a plan
    # this SDK never read and cannot vouch for.
    api, fetched, _ = _fetched([_RESOURCE])
    hand = Plan(id=_PID, resources=[])
    hand.resources.append(
        _resource_cls(fetched).model_validate({**_RESOURCE, "maxWorkingDurationn": "PT8H"})
    )
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        PlansAPI(_Server([])).update(hand)
    assert len(caught) == 1
    assert "maxWorkingDuration" in str(caught[0].message)


def test_a_hand_built_plan_says_nothing_about_an_unrecognisable_key() -> None:
    api, fetched, _ = _fetched([_RESOURCE])
    hand = Plan(id=_PID, resources=[])
    hand.resources.append(
        _resource_cls(fetched).model_validate({**_RESOURCE, "somethingEntirelyNew": 1})
    )
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        PlansAPI(_Server([])).update(hand)
    assert caught == []


def test_a_json_round_trip_degrades_to_the_hand_built_rules() -> None:
    # Documented limitation: private attributes don't survive
    # model_dump() -> model_validate(). The plan is then treated as
    # hand-built, which costs the exact check but never a false refusal.
    api, plan, _ = _fetched([{**_RESOURCE, "modeAddedByApi": "standard"}])
    reloaded = Plan.model_validate(plan.model_dump(mode="json", exclude_none=True))
    assert reloaded._from_server is False
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        PlansAPI(_Server([])).update(reloaded)
    assert caught == []  # no resemblance, so nothing to say


def test_allow_unknown_lets_a_caller_use_a_field_the_sdk_does_not_know() -> None:
    # A field the API gained since this SDK was released, not present on
    # the fetched plan, so provenance can't vouch for it. Without this the
    # caller would be blocked until the SDK ships a version that knows it.
    api, plan, server = _fetched([_RESOURCE])
    plan.resources[0].aFieldThisSdkDoesNotKnow = "x"
    with pytest.raises(UnknownFieldError):
        api.update(plan)
    api.update(plan, allow_unknown=["aFieldThisSdkDoesNotKnow"])
    assert server.sent["resources"][0]["aFieldThisSdkDoesNotKnow"] == "x"


def test_allow_unknown_still_catches_a_typo_elsewhere() -> None:
    # Named fields, not a blanket switch: the point is to keep checking
    # everything the caller didn't explicitly vouch for.
    api, plan, _ = _fetched([_RESOURCE])
    plan.resources[0].aFieldThisSdkDoesNotKnow = "x"
    plan.resources[0].maxWorkingDurationn = "PT8H"
    with pytest.raises(UnknownFieldError) as excinfo:
        api.update(plan, allow_unknown=["aFieldThisSdkDoesNotKnow"])
    assert excinfo.value.paths == ["plan.resources[0].maxWorkingDurationn"]
