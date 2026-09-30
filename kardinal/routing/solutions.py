"""`k.routing.solutions`: get, get_objectives, wait."""

from __future__ import annotations

import time
from typing import List, Optional

from .._core.duration import parse_duration
from .._core.errors import (
    KardinalConnectionError,
    KardinalNotFoundError,
    KardinalOptimizationError,
    KardinalRateLimitError,
    KardinalServerError,
    KardinalTimeoutError,
)
from .._core.transport import Transport
from . import models
from .plans import PlansAPI

# Polling cadence agreed with the backend team: never more often than every
# 10s (each poll hits a shared backend), stretching to 10% of the time
# already waited, capped at 60s — a 6h optimization costs ~380 polls, not
# the ~2,200 a fixed 10s interval would.
_MIN_POLL_SECONDS = 10.0
_MAX_POLL_SECONDS = 60.0
_POLL_FRACTION = 0.1
# An engine that crashes never reports again: the state stays `optimizing`
# until the broker drops the plan 24h later. Past its own budget plus this
# margin, the optimization is presumed dead.
_STALL_MARGIN_SECONDS = 300.0
# `stopped` during `optimizing` is followed by `interrupted` once the engine
# has actually stopped — the solution can still improve in between.
_STOPPED_GRACE_SECONDS = 60.0
# 429 here comes from the cluster ("no backend available right now"), not
# the API: like 5xx and network failures, worth riding out, not surfacing.
_TRANSIENT_ERRORS = (KardinalRateLimitError, KardinalServerError, KardinalConnectionError)
_OPTIMIZING_STATES = frozenset({models.PlanState.optimizing, models.PlanState.preOptimizing})


def _poll_interval(elapsed: float) -> float:
    return min(max(elapsed * _POLL_FRACTION, _MIN_POLL_SECONDS), _MAX_POLL_SECONDS)


class Solution(models.Solution):
    """The generated `Solution`, plus `warnings` copied across from the
    `EnvelopedSolution` envelope it came back in — see `plans.Plan.warnings`
    for why this can't be a field of the generated model itself.
    """

    warnings: List[models.Warning] = []
    # Set by `wait()` only: the plan state it stopped on — `optimized`, or
    # `interrupted`/`stopped` when the optimization was cut short (stopped,
    # replaced, or the engine gave up) and this is the best it got to.
    final_state: Optional[models.PlanState] = None


class SolutionObjectives(List[models.SolutionObjective]):
    """A plain list of `SolutionObjective`, plus `warnings` copied across
    from the `EnvelopedSolutionObjectives` envelope — a list subclass so
    every existing use (`for o in ...`, indexing, `len()`) keeps working
    unchanged; there's no `SolutionObjectives` schema in openapi.yaml to
    model this as a `BaseModel` instead.
    """

    warnings: List[models.Warning]

    def __init__(self, items: List[models.SolutionObjective], warnings: List[models.Warning]):
        super().__init__(items)
        self.warnings = warnings


class SolutionsAPI:
    def __init__(self, transport: Transport, plans: PlansAPI) -> None:
        self._transport = transport
        self._plans = plans

    def get(self, plan_id: str) -> Solution:
        """`GET /plans/{id}/solution`. The current best solution, right away.

        Raises `KardinalNotFoundError` until a first solution exists (while
        the plan is `waiting` or `processing`). The first solutions can be
        empty or incomplete while the engine is still optimizing, and right
        after `update()` this can still be the previous version's solution
        (compare `planVersion`). `wait()` handles all of that.
        """
        response = self._transport.request("GET", f"/plans/{plan_id}/solution")
        solution = Solution.model_validate(response["item"])
        solution.warnings = [
            models.Warning.model_validate(w) for w in response.get("warnings") or []
        ]
        return solution

    def get_objectives(self, plan_id: str) -> SolutionObjectives:
        """`GET /plans/{id}/solution/objectives`. Only the value of each
        objective, without the tours. To track progress without waiting,
        poll no more than once every 10 seconds per plan.
        """
        response = self._transport.request("GET", f"/plans/{plan_id}/solution/objectives")
        return SolutionObjectives(
            [models.SolutionObjective.model_validate(item) for item in response.get("items") or []],
            [models.Warning.model_validate(w) for w in response.get("warnings") or []],
        )

    def wait(self, plan_id: str, timeout: Optional[float] = None) -> Solution:
        """Blocks until the plan's current version stops optimizing, then
        returns its solution, with `final_state` telling how it ended:
        `optimized`, or `interrupted`/`stopped` if it was cut short (check it
        before trusting the result as final).

        Polls `get_status` every 10s at first, stretching to every 60s on
        long optimizations; transient failures (429, 5xx, network) are
        ridden out. Meant for scripts and notebooks — a server tracking many
        plans should schedule its own `get_status` calls instead of blocking.

        Raises `KardinalOptimizationError` when there's no solution to return
        for this version (`NO_SOLUTION`), a newer version was pushed meanwhile
        (`PLAN_SUPERSEDED`), or the plan is still optimizing 5 minutes past its
        `maxOptimizationDuration` (`OPTIMIZATION_STALLED`: the engine most
        likely crashed); `KardinalNotFoundError` if the plan gets deleted.

        `timeout` is a hard guard that raises `KardinalTimeoutError`, not a
        target duration. It's the only guard against a plan stuck before
        optimization starts (`waiting`/`processing`), since how long those
        legitimately last isn't bounded.
        """
        start = time.monotonic()
        deadline = None if timeout is None else start + timeout
        plan = self._plans.get(plan_id)
        version = plan.version.root if plan.version is not None else None
        budget = (
            parse_duration(plan.maxOptimizationDuration.root).total_seconds()
            if plan.maxOptimizationDuration is not None
            else None
        )

        tracker = {"state": None, "since": None, "stopped_since": None}
        while True:
            now = time.monotonic()
            pause = _poll_interval(now - start)
            if deadline is not None:
                pause = min(pause, max(deadline - now, 0.0))
            time.sleep(pause)

            try:
                result = self._poll_once(plan_id, version, budget, tracker)
            except _TRANSIENT_ERRORS:
                result = None
            if result is not None:
                return result
            if deadline is not None and time.monotonic() >= deadline:
                last = tracker["state"]
                raise KardinalTimeoutError(
                    f"Timed out waiting for plan {plan_id!r} to finish optimizing "
                    f"(last state seen: {last.value if last else 'none'}).",
                    code="CLIENT_TIMEOUT",
                    status=0,
                    request_id=None,
                    retryable=False,
                )

    def _poll_once(
        self, plan_id: str, version: Optional[int], budget: Optional[float], tracker: dict
    ) -> Optional[Solution]:
        """One `wait()` poll: the solution if the plan is done, `None` to keep
        waiting, or raises. `tracker` carries what polls need to remember:
        the last state seen, since when, and since when it has been `stopped`.
        """
        state, state_version = self._plans._get_state(plan_id)
        if version is not None and state_version is not None:
            if state_version > version:
                raise KardinalOptimizationError(
                    f"Plan {plan_id!r} was replaced by version {state_version} "
                    f"while waiting for version {version}.",
                    code="PLAN_SUPERSEDED", plan_id=plan_id, plan_version=version, state=state,
                )
            if state_version < version:
                return None  # right after update(): /state hasn't caught up yet
        now = time.monotonic()
        if state != tracker["state"]:
            tracker["state"], tracker["since"] = state, now

        if state == models.PlanState.deleted:
            raise self._deleted(plan_id)
        if state in (models.PlanState.optimized, models.PlanState.interrupted):
            return self._final_solution(plan_id, version, state)
        if state == models.PlanState.stopped:
            if tracker["stopped_since"] is None:
                # Raises right away if there's no solution at all — stopped
                # before the engine was even called.
                self._final_solution(plan_id, version, state)
                tracker["stopped_since"] = now
            elif now - tracker["stopped_since"] >= _STOPPED_GRACE_SECONDS:
                return self._final_solution(plan_id, version, state)
            return None
        tracker["stopped_since"] = None
        if (
            state in _OPTIMIZING_STATES
            and budget is not None
            and now - tracker["since"] > budget + _STALL_MARGIN_SECONDS
        ):
            raise KardinalOptimizationError(
                f"Plan {plan_id!r} is still {state.value} more than "
                f"{_STALL_MARGIN_SECONDS / 60:.0f} minutes past its "
                "maxOptimizationDuration; the optimization most likely crashed.",
                code="OPTIMIZATION_STALLED", plan_id=plan_id, plan_version=version, state=state,
            )
        return None

    def _final_solution(
        self, plan_id: str, version: Optional[int], state: models.PlanState
    ) -> Solution:
        """The solution for exactly `version`, or why there isn't one. A 404
        is told apart (plan gone vs. no solution yet) by re-reading the plan,
        not by parsing the error's free-text `details`.
        """
        try:
            solution = self.get(plan_id)
        except KardinalNotFoundError:
            try:
                self._plans.get(plan_id)
            except KardinalNotFoundError:
                raise self._deleted(plan_id) from None
            solution = None
        if solution is None or (
            version is not None
            and solution.planVersion is not None
            and solution.planVersion.root != version
        ):
            raise KardinalOptimizationError(
                f"Plan {plan_id!r} ended ({state.value}) without a solution "
                f"for version {version}.",
                code="NO_SOLUTION", plan_id=plan_id, plan_version=version, state=state,
            )
        solution.final_state = state
        return solution

    @staticmethod
    def _deleted(plan_id: str) -> KardinalNotFoundError:
        return KardinalNotFoundError(
            f"Plan {plan_id!r} was deleted while waiting for its solution.",
            code="NOT_FOUND",
            status=404,
            request_id=None,
            retryable=False,
        )
