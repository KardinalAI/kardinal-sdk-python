"""`k.routing.plans`: submit, get, update, delete, list/iter_all, start,
stop, get_status — plus the hand-written `PlanCreate`/`Plan`/`Order` that
the single generated `Plan` schema can't provide on its own.
"""

from __future__ import annotations

from typing import Dict, Iterator, List, Literal, Optional, Tuple, Union

from pydantic import BaseModel, ConfigDict

from .._core.pagination import Page, iter_all as _iter_all
from .._core.transport import Transport
from . import _annotations  # import side effect: patches models.PlanId
from ._annotations import validate_response
from . import models


class Order(BaseModel):
    """Same shape as the generated `Order`, but `stops` takes a `SingleStop`
    or `AlternativesStop` directly.

    The generated `Order.stops: List[Stop1]` forces wrapping each item in a
    `Stop1`/`Stop12`/`Stop13` RootModel that exists only because openapi.yaml
    writes `items: allOf: [$ref: Stop]` (a single-$ref `allOf`, which
    datamodel-codegen wraps rather than aliases). Those wrapper classes add
    no fields of their own, so the JSON this produces is identical.
    """

    model_config = ConfigDict(extra="forbid")

    id: models.RegexIdValidation
    properties: Optional[models.Properties] = None
    priority: int = 0
    optional: Optional[bool] = None
    requiredSkills: Optional[List[models.RegexIdValidation]] = None
    stops: List[Union[models.SingleStop, models.AlternativesStop]]
    successiveStops: Optional[bool] = None
    maxStopSpan: Optional[models.Duration] = None


class PlanCreate(BaseModel):
    """Request body for `submit()`.

    openapi.yaml has only one `Plan` schema, shared by requests and
    responses — this is `Plan` minus every server-assigned (`readOnly`)
    field. Sending an `id` is rejected by the API with a 400.
    """

    model_config = ConfigDict(extra="forbid")

    properties: Optional[models.Properties] = None
    resources: List[models.Resource]
    orders: Optional[List[Order]] = None
    additionalOperationDurations: Optional[List[models.AdditionalOperationDuration]] = None
    operationDurationPoliciesByResourceTag: Optional[
        Dict[str, List[models.OperationDurationPolicy]]
    ] = None
    additionalConstraints: Optional[List[models.AdditionalConstraints]] = None
    globalConstraints: Optional[List[models.GlobalConstraints]] = None
    accessDurationsByStopTag: Optional[Dict[str, models.Duration]] = None
    overlappingCapacitiesByStopTag: Optional[Dict[str, int]] = None
    setupDurations: Optional[List[models.SetupDuration]] = None
    objectives: Optional[models.PlanObjectives] = None
    maxOptimizationDuration: Optional[models.Duration] = None
    tz: Optional[models.TimeZone] = None
    lateDeparture: bool = False
    sharedCapacities: bool = False
    emptyThresholdByCapacityByResourceTag: Optional[Dict[str, models.Capacities]] = None
    avoidEarlyLoadingsByResourceTag: Optional[Dict[str, List[models.AvoidEarlyLoading]]] = None
    CO2EmissionCalculationByResourceTag: Optional[Dict[str, models.Cost]] = None


class PlanOrder(Order):
    """`Order` as read back in a `Plan` from the server: same fields, but
    unknown ones are kept instead of rejected (see `Plan` below).
    """

    model_config = ConfigDict(extra="allow")


class Plan(models.Plan):
    """The generated `Plan`, with three overrides:

    - `id` is narrowed to required: every `Plan` this SDK hands back came
      from the server and always has one. Forgetting it on `update()` fails
      at the type-checking stage, not at the server.
    - `orders` is retyped to `PlanOrder`, a subclass of this module's
      `Order` (see above), instead of the generated one, so a `Plan` fetched
      with `get()` and a `PlanCreate` built by hand use the same `stops`
      shape — `plan.orders.append(Order(...))` ahead of `update()` works.
    - `warnings` doesn't exist on the generated `Plan` at all: it's a sibling
      of `item` on the `EnvelopedPlan` envelope, not a field of the plan
      itself. `submit`/`get`/`update` below copy it across after validating
      `item`, so callers get amendments (traffic turned off, a value
      clamped, ...) on the object they already have instead of a separate
      envelope type to unwrap.

    Unlike `Order`/`PlanCreate` (pure request types, `extra="forbid"`),
    `Plan` and `PlanOrder` are `extra="allow"` on purpose: they're also the
    types `get()`/`submit()`/`update()` deserialize the server's *response*
    into. Forbidding unknown fields would make this SDK fail to parse a
    legitimate response the day the API adds a field this version of the
    SDK doesn't know about yet; ignoring them would make `update()`, which
    replaces the whole plan, delete that field on the server. Kept, they're
    sent back unchanged. Nested generated models (resources, stops) still
    drop unknown fields.
    """

    model_config = ConfigDict(extra="allow")

    id: str
    orders: Optional[List[PlanOrder]] = None
    warnings: List[models.Warning] = []


# Server-computed fields update() must not echo back on PUT — POST already
# actively rejects an unexpected `id`, so nothing guarantees a future PUT
# stays lenient about these just because it is today. `id` included: it's
# `readOnly` in the spec and travels in the URL; today's PUT only tolerates
# a body `id` that matches the URL.
_PLAN_READ_ONLY_FIELDS = frozenset(
    {
        "id",
        "agencyId",
        "version",
        "running",
        "status",
        "state",
        "nbResources",
        "nbOrders",
        "createdAt",
        "createdBy",
        "updatedAt",
        "updatedBy",
        "archivedAt",
    }
)


def _plan_from_envelope(response: Dict[str, object]) -> Plan:
    """`EnvelopedPlan.item`, plus `EnvelopedPlan.warnings` copied onto the
    returned `Plan` — `warnings` is a sibling of `item` in the response
    body, not a field `Plan.model_validate(item)` would ever see on its own.
    """
    plan = validate_response(Plan, response["item"])
    plan.warnings = [validate_response(models.Warning, w) for w in response.get("warnings") or []]
    return plan


class PlansAPI:
    """`k.routing.plans`: submit, get, update, delete, list/iter_all, start,
    stop, get_status.
    """

    def __init__(self, transport: Transport) -> None:
        self._transport = transport

    def submit(self, plan: PlanCreate) -> Plan:
        """`POST /plans`. Creates a new plan and starts optimization —
        billed in full. The server assigns `id`.
        """
        body = plan.model_dump(mode="json", exclude_none=True)
        response = self._transport.request("POST", "/plans", json=body)
        return _plan_from_envelope(response)

    def get(self, plan_id: str) -> Plan:
        """`GET /plans/{id}`. The plan as currently stored. Never carries
        warnings: they're only returned by `submit()`/`update()`.
        """
        response = self._transport.request("GET", f"/plans/{plan_id}")
        return _plan_from_envelope(response)

    def update(self, plan: Plan, *, force: bool = False) -> Plan:
        """`PUT /plans/{id}`. Sends the complete plan, replacing the stored one
        (anything left out is removed; fields this SDK version doesn't know,
        read by `get()`, are kept and sent back). The version increments, and the plan
        is re-optimized, only if the plan actually changed: an identical PUT
        is a free no-op, returning the same version. Only newly added unique
        stops are billed.

        `force` unarchives the plan first if it's archived; ignored otherwise.
        """
        # `warnings` is this SDK's own field (see `Plan`), not the plan's.
        body = plan.model_dump(
            mode="json", exclude_none=True, exclude=_PLAN_READ_ONLY_FIELDS | {"warnings"}
        )
        response = self._transport.request(
            "PUT", f"/plans/{plan.id}", json=body, params={"force": force}
        )
        return _plan_from_envelope(response)

    def delete(self, plan_id: str) -> None:
        """`DELETE /plans/{id}`. Permanently deletes the plan and its
        solution; any optimization in progress is stopped.
        """
        self._transport.request("DELETE", f"/plans/{plan_id}")

    def list(
        self,
        *,
        page: int = 1,
        items_per_page: int = 20,
        archived: Literal["excluded", "included", "only"] = "excluded",
    ) -> Page[models.PlanLight]:
        """`GET /plans`. Retrieving a collection of plans is always
        paginated — sending `page`/`itemsPerPage` explicitly (rather than
        relying on the API's own defaults) just makes the page this SDK
        asked for visible in the call itself.
        """
        response = self._transport.request(
            "GET",
            "/plans",
            params={"page": page, "itemsPerPage": items_per_page, "archived": archived},
        )
        paging = response["paging"]
        return Page(
            items=[validate_response(models.PlanLight, item) for item in response.get("items") or []],
            page=paging["page"],
            total_pages=paging["totalPages"],
            total=paging["total"],
            next_page=paging.get("nextPage"),
            previous_page=paging.get("previousPage"),
            items_per_page=paging.get("itemsPerPage"),
        )

    def iter_all(
        self, *, archived: Literal["excluded", "included", "only"] = "excluded"
    ) -> Iterator[models.PlanLight]:
        """Chains `list()` across every page."""
        return _iter_all(lambda page: self.list(page=page, archived=archived))

    def start(self, plan_id: str, *, force: bool = False) -> models.EnvelopedPlanReference:
        """`PUT /plans/{id}/running` with `true`. Restarts optimization on
        the current version of the plan, without changing its data or
        `version` — the returned reference's `planVersion` is that same,
        unchanged version, not a new one.

        `force` unarchives the plan first if it's archived; ignored otherwise.
        """
        response = self._transport.request(
            "PUT", f"/plans/{plan_id}/running", json=True, params={"force": force}
        )
        return validate_response(models.EnvelopedPlanReference, response)

    def stop(self, plan_id: str, *, force: bool = False) -> models.EnvelopedPlanReference:
        """`PUT /plans/{id}/running` with `false`. Stops optimization on
        the current version of the plan, without changing its data or
        `version`.

        `force` unarchives the plan first if it's archived; ignored otherwise.
        """
        response = self._transport.request(
            "PUT", f"/plans/{plan_id}/running", json=False, params={"force": force}
        )
        return validate_response(models.EnvelopedPlanReference, response)

    def get_status(self, plan_id: str) -> Union[models.PlanState, str]:
        """`GET /plans/{id}/state`. Returns the plan's current `PlanState`
        (`waiting`, `processing`, ..., `optimized`, `stopped`, ...), or the
        raw string for a state this version of the SDK doesn't know yet.

        The type returned is `PlanState` (the enum this endpoint's `state`
        field actually carries), not the unrelated `PlanStatus` object
        embedded in `Plan.status` — the spec uses both names for different
        things (see the README's "Good to know" section).
        """
        return self._get_state(plan_id)[0]

    def _get_state(self, plan_id: str) -> Tuple[Union[models.PlanState, str], Optional[int]]:
        """`get_status()` plus the `planVersion` that state belongs to —
        `solutions.wait()` needs both, since right after `update()` this
        endpoint can still report the previous version's state.
        """
        response = self._transport.request("GET", f"/plans/{plan_id}/state")
        item = response["item"]
        try:
            state: Union[models.PlanState, str] = models.PlanState(item["state"])
        except ValueError:
            state = item["state"]
        return state, item.get("planVersion")
