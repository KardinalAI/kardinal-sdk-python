"""Every ```python block of the README, run in order in one namespace (as a
reader chaining the examples would) against a mocked API. A block added to
the README is run too, so a published example can't silently break.
"""

import json
import re
from pathlib import Path

import httpx
import respx

from kardinal._core.transport import DEFAULT_BASE_URL

_README = Path(__file__).resolve().parent.parent / "README.md"
_PLAN_ID = "4cbd0ab8-282c-4b30-b981-29e1ed8a2016"
_PLAN_URL = f"{DEFAULT_BASE_URL}/plans/{_PLAN_ID}"
_CLAMPED = {
    "code": "INVALID_VALUE",
    "message": "The field value is not valid.",
    "properties": {"path": "maxOptimizationDuration", "details": "clamped to 5s"},
}
_PLAN_SIZE_LIMIT = [
    {
        "code": "INVALID_VALUE",
        "message": "The field value is not valid.",
        "properties": {"path": "resources", "details": "251 is greater than the allowed value (250)"},
    },
    {
        "code": "NOT_ALLOWED",
        "message": "The requested action is not allowed.",
        "properties": {"details": "The resulting plan violates the quotas configuration of the agency"},
    },
]


def _python_blocks():
    return re.findall(r"^```python\n(.*?)^```", _README.read_text(), re.MULTILINE | re.DOTALL)


class _FakeApi:
    """Echoes submitted plans back with an id and a version, like the API,
    and reports every plan as optimized with a one-tour solution.
    """

    def __init__(self):
        self.plan = None
        self.reject_submit = False

    def submit(self, request):
        if self.reject_submit:
            return httpx.Response(403, json={"errors": _PLAN_SIZE_LIMIT})
        self.plan = {**json.loads(request.content), "id": _PLAN_ID, "version": 1}
        return httpx.Response(201, json={"item": self.plan, "warnings": [_CLAMPED]})

    def update(self, request):
        self.plan = {**json.loads(request.content), "id": _PLAN_ID, "version": self.plan["version"] + 1}
        return httpx.Response(200, json={"item": self.plan})

    def get(self, request):
        return httpx.Response(200, json={"item": self.plan})

    def state(self, request):
        return httpx.Response(
            200, json={"item": {"state": "optimized", "planVersion": self.plan["version"]}}
        )

    def solution(self, request):
        tour = {"resourceId": self.plan["resources"][0]["id"], "wayPoints": []}
        return httpx.Response(
            200,
            json={"item": {"planId": _PLAN_ID, "planVersion": self.plan["version"], "tours": [tour]}},
        )


@respx.mock
def test_every_readme_python_block_runs(monkeypatch) -> None:
    monkeypatch.setattr("time.sleep", lambda _seconds: None)
    api = _FakeApi()
    respx.post(f"{DEFAULT_BASE_URL}/plans").mock(side_effect=api.submit)
    respx.get(_PLAN_URL).mock(side_effect=api.get)
    respx.put(_PLAN_URL).mock(side_effect=api.update)
    respx.get(f"{_PLAN_URL}/state").mock(side_effect=api.state)
    respx.get(f"{_PLAN_URL}/solution").mock(side_effect=api.solution)
    respx.get(f"{_PLAN_URL}/solution/objectives").mock(
        return_value=httpx.Response(200, json={"items": [{"name": "minimizeDelay", "value": 0}]})
    )

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
