import httpx
import pytest
import respx

from kardinal._core.errors import (
    KardinalAuthError,
    KardinalNotFoundError,
    KardinalOptimizationError,
    KardinalTimeoutError,
)
from kardinal._core.transport import DEFAULT_BASE_URL, Transport
from kardinal.routing.models import PlanState
from kardinal.routing.plans import PlansAPI
from kardinal.routing.solutions import SolutionsAPI, _poll_interval

_PLAN_ID = "4cbd0ab8-282c-4b30-b981-29e1ed8a2016"


def _apis():
    transport = Transport(api_key="test-key")
    plans = PlansAPI(transport)
    return plans, SolutionsAPI(transport, plans)


_PLAN_URL = f"{DEFAULT_BASE_URL}/plans/{_PLAN_ID}"


@pytest.fixture
def clock(monkeypatch):
    """Fake clock: `time.sleep` advances `time.monotonic` instead of blocking,
    so a wait() that would take minutes runs instantly and deterministically.
    """
    now = [0.0]
    monkeypatch.setattr("time.monotonic", lambda: now[0])
    monkeypatch.setattr("time.sleep", lambda seconds: now.__setitem__(0, now[0] + seconds))
    return now


def _mock_plan(version=1, budget="PT6H"):
    item = {"id": _PLAN_ID, "resources": [], "version": version}
    if budget is not None:
        item["maxOptimizationDuration"] = budget
    return respx.get(_PLAN_URL).mock(return_value=httpx.Response(200, json={"item": item}))


def _mock_states(clock, timeline):
    """`timeline` is a list of `(from_second, state, version)`: `/state`
    answers with the last entry whose `from_second` has been reached.
    An entry may also be an `httpx.Response` (e.g. a 429) in place of the
    `(state, version)` pair.
    """

    def answer(request):
        current = [entry for entry in timeline if entry[0] <= clock[0]][-1]
        if isinstance(current[1], httpx.Response):
            return current[1]
        _, state, version = current
        return httpx.Response(200, json={"item": {"state": state, "planVersion": version}})

    return respx.get(f"{_PLAN_URL}/state").mock(side_effect=answer)


def _mock_solution(version=1):
    return respx.get(f"{_PLAN_URL}/solution").mock(
        return_value=httpx.Response(200, json={"item": {"planId": _PLAN_ID, "planVersion": version}})
    )


def _not_found(details):
    return httpx.Response(
        404,
        json={"errors": [{"code": "NOT_FOUND", "message": "not found", "properties": {"details": details}}]},
    )


@pytest.mark.parametrize(
    ("elapsed", "expected"),
    [(0, 10), (50, 10), (100, 10), (300, 30), (600, 60), (7200, 60)],
)
def test_poll_interval_is_ten_percent_of_elapsed_between_10_and_60_seconds(elapsed, expected) -> None:
    assert _poll_interval(elapsed) == expected


@respx.mock
def test_wait_returns_soon_after_the_plan_finishes_not_after_its_budget(clock) -> None:
    """A PT6H budget must not mean sleeping 6 hours: the engine usually
    finishes in seconds. /solution isn't touched before the final state.
    """
    _mock_plan(budget="PT6H")
    states = _mock_states(clock, [(0, "waiting", 1), (8, "optimizing", 1), (12, "optimized", 1)])
    solution_route = _mock_solution()
    _, solutions = _apis()

    solution = solutions.wait(_PLAN_ID)

    assert solution.planId == _PLAN_ID
    assert solution.final_state == PlanState.optimized
    assert clock[0] == 20
    assert states.call_count == 2
    assert solution_route.call_count == 1


@respx.mock
def test_wait_first_polls_after_ten_seconds_not_immediately(clock) -> None:
    """No poll at t=0: right after `start()` the state is briefly still the
    previous run's `optimized`, and polling then would return a stale result.
    """
    _mock_plan()
    _mock_states(clock, [(0, "optimized", 1)])
    _mock_solution()
    _, solutions = _apis()

    solutions.wait(_PLAN_ID)

    assert clock[0] == 10


@respx.mock
def test_wait_keeps_waiting_while_state_still_reports_the_previous_version(clock) -> None:
    _mock_plan(version=2)
    _mock_states(clock, [(0, "optimized", 1), (15, "processing", 2), (25, "optimized", 2)])
    _mock_solution(version=2)
    _, solutions = _apis()

    solution = solutions.wait(_PLAN_ID)

    assert solution.planVersion.root == 2
    assert clock[0] == 30


@respx.mock
def test_wait_raises_when_a_newer_version_was_pushed(clock) -> None:
    _mock_plan(version=2)
    _mock_states(clock, [(0, "waiting", 3)])
    _, solutions = _apis()

    with pytest.raises(KardinalOptimizationError) as info:
        solutions.wait(_PLAN_ID)

    assert info.value.code == "PLAN_SUPERSEDED"
    assert info.value.plan_version == 2


@respx.mock
def test_wait_rejects_a_solution_left_over_from_the_previous_version(clock) -> None:
    """v2 stopped during processing: /solution still serves v1's result."""
    _mock_plan(version=2)
    _mock_states(clock, [(0, "stopped", 2)])
    _mock_solution(version=1)
    _, solutions = _apis()

    with pytest.raises(KardinalOptimizationError) as info:
        solutions.wait(_PLAN_ID)

    assert info.value.code == "NO_SOLUTION"
    assert info.value.state == PlanState.stopped


@respx.mock
def test_wait_after_stopped_waits_for_interrupted_while_the_solution_improves(clock) -> None:
    """Stopped mid-optimization: Ebirah still has to stop, then reports
    `interrupted` — the solution can still improve in between.
    """
    _mock_plan()
    _mock_states(clock, [(0, "stopped", 1), (25, "interrupted", 1)])
    solution_route = _mock_solution()
    _, solutions = _apis()

    solution = solutions.wait(_PLAN_ID)

    assert solution.final_state == PlanState.interrupted
    assert clock[0] == 30
    assert solution_route.call_count == 2


@respx.mock
def test_wait_after_stopped_gives_up_waiting_for_interrupted_after_a_minute(clock) -> None:
    _mock_plan()
    _mock_states(clock, [(0, "stopped", 1)])
    _mock_solution()
    _, solutions = _apis()

    solution = solutions.wait(_PLAN_ID)

    assert solution.final_state == PlanState.stopped
    assert 70 <= clock[0] <= 90


@respx.mock
def test_wait_restarted_during_the_stopped_grace_period_follows_the_new_run(clock) -> None:
    _mock_plan()
    _mock_states(
        clock,
        [(0, "stopped", 1), (15, "processing", 1), (35, "stopped", 1), (45, "interrupted", 1)],
    )
    _mock_solution()
    _, solutions = _apis()

    solution = solutions.wait(_PLAN_ID)

    assert solution.final_state == PlanState.interrupted


@respx.mock
def test_wait_stopped_before_any_solution_raises_no_solution_right_away(clock) -> None:
    _mock_plan()
    _mock_states(clock, [(0, "stopped", 1)])
    respx.get(f"{_PLAN_URL}/solution").mock(return_value=_not_found("Solution version not found."))
    _, solutions = _apis()

    with pytest.raises(KardinalOptimizationError) as info:
        solutions.wait(_PLAN_ID)

    assert info.value.code == "NO_SOLUTION"
    assert clock[0] == 10


@respx.mock
def test_wait_detects_a_deleted_plan_without_reading_the_404_text(clock) -> None:
    """/state keeps answering after a DELETE (separate module, with
    retention): deletion shows up only on /solution and /plans/{id}.
    """
    respx.get(_PLAN_URL).mock(
        side_effect=[
            httpx.Response(200, json={"item": {"id": _PLAN_ID, "resources": [], "version": 1}}),
            _not_found("Plan not found"),
        ]
    )
    _mock_states(clock, [(0, "interrupted", 1)])
    respx.get(f"{_PLAN_URL}/solution").mock(return_value=_not_found("Plan not found"))
    _, solutions = _apis()

    with pytest.raises(KardinalNotFoundError, match="deleted"):
        solutions.wait(_PLAN_ID)


@respx.mock
def test_wait_raises_not_found_on_the_deleted_state(clock) -> None:
    _mock_plan()
    _mock_states(clock, [(0, "deleted", 1)])
    _, solutions = _apis()

    with pytest.raises(KardinalNotFoundError, match="deleted"):
        solutions.wait(_PLAN_ID)


@respx.mock
def test_wait_raises_stalled_when_optimizing_outlasts_its_budget_by_five_minutes(clock) -> None:
    """Ebirah crashed: nothing will ever move the state off `optimizing`."""
    _mock_plan(budget="PT5S")
    _mock_states(clock, [(0, "processing", 1), (20, "optimizing", 1)])
    _, solutions = _apis()

    with pytest.raises(KardinalOptimizationError) as info:
        solutions.wait(_PLAN_ID)

    assert info.value.code == "OPTIMIZATION_STALLED"
    assert info.value.state == PlanState.optimizing
    assert 305 < clock[0] - 20 < 305 + 60


@respx.mock
def test_wait_without_budget_has_no_stall_guard(clock) -> None:
    _mock_plan(budget=None)
    _mock_states(clock, [(0, "optimizing", 1), (5000, "optimized", 1)])
    _mock_solution()
    _, solutions = _apis()

    assert solutions.wait(_PLAN_ID).final_state == PlanState.optimized


@respx.mock
@pytest.mark.parametrize(
    "failure",
    [httpx.Response(429), httpx.Response(503), httpx.ConnectError("boom")],
    ids=["429", "503", "network"],
)
def test_wait_rides_out_transient_failures(clock, failure) -> None:
    _mock_plan()
    calls = {"n": 0}

    def answer(request):
        calls["n"] += 1
        if calls["n"] <= 5:
            if isinstance(failure, Exception):
                raise failure
            return failure
        return httpx.Response(200, json={"item": {"state": "optimized", "planVersion": 1}})

    respx.get(f"{_PLAN_URL}/state").mock(side_effect=answer)
    _mock_solution()
    _, solutions = _apis()

    assert solutions.wait(_PLAN_ID).final_state == PlanState.optimized


@respx.mock
def test_wait_does_not_swallow_auth_errors(clock) -> None:
    _mock_plan()
    respx.get(f"{_PLAN_URL}/state").mock(
        return_value=httpx.Response(401, json={"errors": [{"code": "NOT_AUTHENTICATED", "message": "no"}]})
    )
    _, solutions = _apis()

    with pytest.raises(KardinalAuthError):
        solutions.wait(_PLAN_ID)


@respx.mock
def test_wait_checks_the_state_once_more_before_timing_out(clock) -> None:
    """A timeout shorter than the poll interval must still look at the
    state — the old wait() raised without ever checking it.
    """
    _mock_plan()
    states = _mock_states(clock, [(0, "optimized", 1)])
    _mock_solution()
    _, solutions = _apis()

    solution = solutions.wait(_PLAN_ID, timeout=3)

    assert solution.final_state == PlanState.optimized
    assert states.call_count == 1
    assert clock[0] == 3


@respx.mock
def test_wait_raises_timeout_with_the_last_state_seen(clock) -> None:
    _mock_plan()
    states = _mock_states(clock, [(0, "processing", 1)])
    _, solutions = _apis()

    with pytest.raises(KardinalTimeoutError, match="processing"):
        solutions.wait(_PLAN_ID, timeout=25)

    assert clock[0] == 25
    assert states.call_count == 3


@respx.mock
def test_wait_timeout_zero_still_polls_once(clock) -> None:
    _mock_plan()
    states = _mock_states(clock, [(0, "waiting", 1)])
    _, solutions = _apis()

    with pytest.raises(KardinalTimeoutError):
        solutions.wait(_PLAN_ID, timeout=0)

    assert states.call_count == 1


@respx.mock
def test_get_objectives_returns_plain_list() -> None:
    respx.get(f"{DEFAULT_BASE_URL}/plans/{_PLAN_ID}/solution/objectives").mock(
        return_value=httpx.Response(
            200,
            json={"items": [{"name": "minimizeCosts", "priority": 0, "value": 12.5}]},
        )
    )
    _, solutions = _apis()
    objectives = solutions.get_objectives(_PLAN_ID)
    assert objectives[0].name.root == "minimizeCosts"
    assert objectives.warnings == []


@respx.mock
def test_get_copies_envelope_warnings_onto_the_solution() -> None:
    respx.get(f"{DEFAULT_BASE_URL}/plans/{_PLAN_ID}/solution").mock(
        return_value=httpx.Response(
            200,
            json={
                "item": {"planId": _PLAN_ID},
                "warnings": [{"code": "INVALID_VALUE", "message": "clamped"}],
            },
        )
    )
    _, solutions = _apis()
    solution = solutions.get(_PLAN_ID)
    assert solution.warnings[0].code.value == "INVALID_VALUE"


@respx.mock
def test_get_objectives_copies_envelope_warnings() -> None:
    respx.get(f"{DEFAULT_BASE_URL}/plans/{_PLAN_ID}/solution/objectives").mock(
        return_value=httpx.Response(
            200,
            json={
                "items": [],
                "warnings": [{"code": "INVALID_VALUE", "message": "clamped"}],
            },
        )
    )
    _, solutions = _apis()
    objectives = solutions.get_objectives(_PLAN_ID)
    assert objectives.warnings[0].code.value == "INVALID_VALUE"


@respx.mock
def test_wait_keeps_polling_through_a_state_this_sdk_does_not_know(clock) -> None:
    _mock_plan()
    _mock_states(clock, [(0, "someFutureState", 1), (30, "optimized", 1)])
    _mock_solution()
    plans, solutions = _apis()
    solution = solutions.wait(_PLAN_ID, timeout=600)
    assert solution.final_state == PlanState.optimized


@respx.mock
def test_wait_timeout_names_a_state_this_sdk_does_not_know(clock) -> None:
    _mock_plan()
    _mock_states(clock, [(0, "someFutureState", 1)])
    _, solutions = _apis()
    with pytest.raises(KardinalTimeoutError) as info:
        solutions.wait(_PLAN_ID, timeout=30)
    assert "someFutureState" in str(info.value)

