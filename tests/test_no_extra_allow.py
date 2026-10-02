from pydantic import RootModel

from kardinal.routing import _annotations
from kardinal.routing.plans import Order, Plan, PlanCreate, PlanOrder


def test_every_generated_model_keeps_unknown_fields() -> None:
    # The invariant the patch exists for. Checked at runtime, not by reading
    # the generated file: regeneration could add a kind of model the patch
    # walks past, and a text search would stay green while a misspelled
    # field went back to vanishing.
    plain = [c for c in _annotations._generated_models() if not issubclass(c, RootModel)]
    assert plain
    assert [c.__name__ for c in plain if c.model_config.get("extra") != "allow"] == []


def test_request_models_keep_unknown_fields_for_submit_to_report() -> None:
    # Not "forbid": a typo here would raise a different exception than the
    # same typo one level down. Both are reported by submit() instead.
    assert Order.model_config["extra"] == "allow"
    assert PlanCreate.model_config["extra"] == "allow"


def test_models_read_from_the_server_keep_unknown_fields() -> None:
    # update() sends a fetched Plan back as a full replacement: dropping a
    # field this SDK doesn't know would delete it on the server.
    assert Plan.model_config["extra"] == "allow"
    assert PlanOrder.model_config["extra"] == "allow"
