"""Dev-time check for the PlanId patch in kardinal/routing/_annotations.py.

This is deliberately a test, not a runtime assertion in the SDK itself: if
openapi.yaml is ever fixed upstream so PlanId parses on its own, the patch
finding nothing to do is the correct, desired outcome for every installed
copy of the SDK out in the wild — it should never raise at import time for
an end user. Here, in CI, it means the patch (and this test) can be removed.
"""

from kardinal.routing import models
from kardinal.routing._annotations import (
    PLAN_ID_PATCH_APPLIED,
    SCALAR_ROOT_EQUALITY_PATCH_APPLIED,
)


def test_plan_id_patch_still_applies() -> None:
    assert PLAN_ID_PATCH_APPLIED, (
        "The PlanId patch found nothing to patch. If openapi.yaml's "
        "double-allOf chain (Plan.id -> PlanId -> UUID) was fixed upstream, "
        "this is expected — remove _patch_broken_plan_id() and this test, "
        "and drop the corresponding note from the README's known gaps."
    )


def test_scalar_root_equality_patch_still_applies() -> None:
    assert SCALAR_ROOT_EQUALITY_PATCH_APPLIED


def test_regex_id_validation_compares_equal_to_plain_string() -> None:
    value = models.RegexIdValidation("truck-2")
    assert value == "truck-2"
    assert "truck-2" == value
    assert value != "truck-3"
    assert str(value) == "truck-2"
    assert f"{value}" == "truck-2"
    assert hash(value) == hash("truck-2")


def test_scalar_root_equality_on_a_model_field() -> None:
    from kardinal.routing.plans import Order

    order = Order(id="order-1", stops=[])
    assert order.id == "order-1"
    assert str(order.id) == "order-1"


def test_plan_version_root_model_compares_equal_to_plain_int() -> None:
    version = models.PlanVersion(3)
    assert version == 3
    assert str(version) == "3"


def test_two_instances_of_the_same_scalar_root_model_compare_by_value() -> None:
    assert models.RegexIdValidation("truck-1") == models.RegexIdValidation("truck-1")
    assert models.RegexIdValidation("truck-1") != models.RegexIdValidation("truck-2")


def test_composite_root_models_are_not_patched() -> None:
    """List/Dict/Union root models are deliberately excluded — a transparent
    __eq__/__str__ is unambiguous for a scalar but not for a collection.
    """
    pair = models.StopTagPair(["goat", "cabbage"])
    assert pair != ["goat", "cabbage"]


def test_scalar_root_model_still_round_trips_through_json() -> None:
    """The patch only adds dunder methods; (de)serialization must stay
    exactly what it was before the patch — .root is unwrapped either way.
    """
    from kardinal.routing.plans import Order

    order = Order(id="order-1", stops=[])
    assert order.model_dump(mode="json", exclude_none=True)["id"] == "order-1"
