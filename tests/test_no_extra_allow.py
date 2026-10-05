"""Unknown keys must be kept, not dropped — that is what makes a misspelled
optional field detectable at all. `extra=allow` now comes from the
generator (`--extra-fields=allow`), so the risk is no longer a patch that
stops converging; it is a regeneration run without the flag.
"""

from pydantic import RootModel

from kardinal.routing import _annotations
from kardinal.routing.plans import Order, Plan, PlanCreate, PlanOrder


def _walk(schema, seen=None):
    """Every node of a compiled core schema, following refs once."""
    seen = seen if seen is not None else set()
    if isinstance(schema, dict):
        if id(schema) in seen:
            return
        seen.add(id(schema))
        yield schema
        for value in schema.values():
            yield from _walk(value, seen)
    elif isinstance(schema, (list, tuple)):
        for item in schema:
            yield from _walk(item, seen)


def test_every_compiled_schema_keeps_unknown_fields() -> None:
    # The compiled schema, not model_config: the config is the input to the
    # build, and only the result decides what happens at runtime.
    bad = set()
    for cls in _annotations._generated_models():
        for node in _walk(cls.__pydantic_core_schema__):
            if node.get("type") == "model" and not node.get("root_model"):
                config = node.get("config") or {}
                if config.get("extra_fields_behavior") != "allow":
                    bad.add(config.get("title") or node.get("cls", "?"))
    assert bad == set()


def test_every_generated_model_declares_extra_allow() -> None:
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
