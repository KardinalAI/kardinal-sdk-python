"""The three-line quickstart from the README, run end to end against a
mocked transport.
"""

import httpx
import respx

from kardinal import Kardinal
from kardinal._core.transport import DEFAULT_BASE_URL
from kardinal.routing import examples

_PLAN_ID = "4cbd0ab8-282c-4b30-b981-29e1ed8a2016"


@respx.mock
def test_quickstart_runs_end_to_end(monkeypatch) -> None:
    monkeypatch.setenv("KARDINAL_API_KEY", "test-key")
    monkeypatch.setattr("time.sleep", lambda _seconds: None)

    respx.post(f"{DEFAULT_BASE_URL}/plans").mock(
        return_value=httpx.Response(201, json={"item": {"id": _PLAN_ID, "resources": []}})
    )
    respx.get(f"{DEFAULT_BASE_URL}/plans/{_PLAN_ID}").mock(
        return_value=httpx.Response(
            200,
            json={
                "item": {
                    "id": _PLAN_ID,
                    "resources": [],
                    "maxOptimizationDuration": "PT10S",
                }
            },
        )
    )
    respx.get(f"{DEFAULT_BASE_URL}/plans/{_PLAN_ID}/state").mock(
        return_value=httpx.Response(200, json={"item": {"state": "optimized"}})
    )
    respx.get(f"{DEFAULT_BASE_URL}/plans/{_PLAN_ID}/solution").mock(
        return_value=httpx.Response(200, json={"item": {"planId": _PLAN_ID, "tours": []}})
    )

    k = Kardinal()
    plan = k.routing.plans.submit(examples.small_delivery_plan())
    solution = k.routing.solutions.wait(plan.id)

    assert plan.id == _PLAN_ID
    assert solution.tours == []
