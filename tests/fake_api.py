"""The simulated Kardinal API shared by the tests that run published
examples (the README, the doc pages): it echoes submitted plans back and
reports every plan as optimized with a one-tour, one-stop solution.
"""

import json

import httpx
import respx

from kardinal._core.transport import DEFAULT_BASE_URL

PLAN_ID = "4cbd0ab8-282c-4b30-b981-29e1ed8a2016"
PLAN_URL = f"{DEFAULT_BASE_URL}/plans/{PLAN_ID}"
CLAMPED = {
    "code": "INVALID_VALUE",
    "message": "The field value is not valid.",
    "properties": {"path": "maxOptimizationDuration", "details": "clamped to 5s"},
}
PLAN_SIZE_LIMIT = [
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


class FakeApi:
    """Echoes submitted plans back with an id and a version, like the API,
    and reports every plan as optimized with a one-tour, one-stop solution.
    """

    def __init__(self):
        self.plan = None
        self.reject_submit = False

    def submit(self, request):
        if self.reject_submit:
            return httpx.Response(403, json={"errors": PLAN_SIZE_LIMIT})
        self.plan = {**json.loads(request.content), "id": PLAN_ID, "version": 1}
        return httpx.Response(201, json={"item": self.plan, "warnings": [CLAMPED]})

    def update(self, request):
        self.plan = {**json.loads(request.content), "id": PLAN_ID, "version": self.plan["version"] + 1}
        return httpx.Response(200, json={"item": self.plan})

    def get(self, request):
        return httpx.Response(200, json={"item": self.plan})

    def state(self, request):
        return httpx.Response(
            200, json={"item": {"state": "optimized", "planVersion": self.plan["version"]}}
        )

    def solution(self, request):
        position = {"lat": 48.85, "lon": 2.35}
        stop = {
            "type": "stop",
            "stopId": "stop-1",
            "arrivalTime": "2026-10-29T09:50:00+01:00",
            "beginTime": "2026-10-29T10:00:00+01:00",
            "delay": "PT0S",
            "position": position,
        }
        tour = {
            "resourceId": self.plan["resources"][0]["id"],
            "wayPoints": [{"type": "begin", "position": position}, stop, {"type": "end", "position": position}],
        }
        return httpx.Response(
            200,
            json={"item": {"planId": PLAN_ID, "planVersion": self.plan["version"], "tours": [tour]}},
        )

    def running(self, request):
        return httpx.Response(200, json={"item": {"id": PLAN_ID}})

    def delete(self, request):
        return httpx.Response(204)

    def list(self, request):
        light = {"id": PLAN_ID, "version": (self.plan or {}).get("version", 1), "state": "optimized"}
        return httpx.Response(
            200, json={"items": [light], "paging": {"page": 1, "totalPages": 1, "total": 1}}
        )


def mock_routes(api: FakeApi) -> None:
    """Routes every call the examples make to `api`, on the active `respx` mock."""
    respx.post(f"{DEFAULT_BASE_URL}/plans").mock(side_effect=api.submit)
    respx.get(f"{DEFAULT_BASE_URL}/plans").mock(side_effect=api.list)
    respx.get(PLAN_URL).mock(side_effect=api.get)
    respx.put(PLAN_URL).mock(side_effect=api.update)
    respx.delete(PLAN_URL).mock(side_effect=api.delete)
    respx.put(f"{PLAN_URL}/running").mock(side_effect=api.running)
    respx.get(f"{PLAN_URL}/state").mock(side_effect=api.state)
    respx.get(f"{PLAN_URL}/solution").mock(side_effect=api.solution)
    respx.get(f"{PLAN_URL}/solution/objectives").mock(
        return_value=httpx.Response(200, json={"items": [{"name": "minimizeDelay", "value": 0}]})
    )
