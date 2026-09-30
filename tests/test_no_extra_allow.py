import re
from pathlib import Path

from kardinal.routing.plans import Order, Plan, PlanCreate, PlanOrder

_MODELS = Path(__file__).resolve().parent.parent / "kardinal" / "routing" / "models" / "__init__.py"


def test_no_generated_model_uses_extra_allow() -> None:
    pattern = re.compile(r"""extra\s*=\s*['"]allow['"]""")
    assert not pattern.search(_MODELS.read_text()), f"{_MODELS} uses extra='allow'"


def test_request_models_forbid_unknown_fields() -> None:
    assert Order.model_config["extra"] == "forbid"
    assert PlanCreate.model_config["extra"] == "forbid"


def test_models_read_from_the_server_keep_unknown_fields() -> None:
    # update() sends a fetched Plan back as a full replacement: dropping a
    # field this SDK doesn't know would delete it on the server.
    assert Plan.model_config["extra"] == "allow"
    assert PlanOrder.model_config["extra"] == "allow"
