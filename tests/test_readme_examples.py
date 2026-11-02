"""Every ```python block of the README, run in order in one namespace (as a
reader chaining the examples would) against a mocked API. A block added to
the README is run too, so a published example can't silently break.
"""

import re
from pathlib import Path

import respx
from fake_api import FakeApi, mock_routes

_README = Path(__file__).resolve().parent.parent / "README.md"


def _python_blocks():
    return re.findall(r"^```python\n(.*?)^```", _README.read_text(), re.MULTILINE | re.DOTALL)


@respx.mock
def test_every_readme_python_block_runs(monkeypatch) -> None:
    monkeypatch.setattr("time.sleep", lambda _seconds: None)
    api = FakeApi()
    mock_routes(api)

    blocks = _python_blocks()
    assert blocks, "no ```python block found in the README"
    namespace: dict = {}
    for number, block in enumerate(blocks, start=1):
        exec(compile(block, f"README.md python block {number}", "exec"), namespace)

    # The error-handling example must also work on the path it illustrates:
    # a rejected submission (a 403 plan-size limit).
    error_blocks = [block for block in blocks if "except KardinalLimitError" in block]
    assert error_blocks, "the README lost its KardinalLimitError example"
    api.reject_submit = True
    for block in error_blocks:
        exec(compile(block, "README.md KardinalLimitError example", "exec"), namespace)
