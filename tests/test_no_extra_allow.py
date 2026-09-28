import re
from pathlib import Path

_MODELS = Path(__file__).resolve().parent.parent / "kardinal" / "routing" / "models" / "__init__.py"
_ROUTING_SOURCE = [
    Path(__file__).resolve().parent.parent / "kardinal" / "routing" / "plans.py",
]


def test_no_request_model_uses_extra_allow() -> None:
    pattern = re.compile(r"""extra\s*=\s*['"]allow['"]""")
    for path in [_MODELS, *_ROUTING_SOURCE]:
        assert not pattern.search(path.read_text()), f"{path} uses extra='allow'"
