"""`k.routing.plans`: submit, get, update, replace, delete, list/iter_all,
start, stop, get_status — plus the hand-written `PlanCreate`/`Plan` that
the single generated `Plan` schema can't provide on its own.
"""

from __future__ import annotations

import logging
import sys
import warnings

from typing import Annotated, Any, Collection, Dict, Iterator, List, Literal, Optional, Tuple, Union

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr

from .._core.errors import UnknownFieldError, UnknownFieldWarning
from .._core.pagination import Page, iter_all as _iter_all
from .._core.transport import Transport
from . import _annotations  # import side effect: patches models.PlanId
# PLAN_READ_ONLY_FIELDS: server-computed fields update() must not echo
# back on PUT. It lives in _annotations.py because the message for an
# unknown key needs it too, to say "the server assigns it".
from ._annotations import PLAN_READ_ONLY_FIELDS as _PLAN_READ_ONLY_FIELDS
from ._annotations import _lenient_enums, validate_response
from . import models


# A hand-written `Order` subclass used to exist only to let `stops` take a
# `SingleStop` or an `AlternativesStop` directly. The generated `Order` now
# accepts both, so no subclass is needed: this alias keeps `Order` importable
# from this module.
Order = models.Order


class PlanCreate(BaseModel):
    """Request body for `submit()`.

    openapi.yaml has only one `Plan` schema, shared by requests and
    responses — this is `Plan` minus every server-assigned (`readOnly`)
    field. An `id` sent anyway is ignored by the API, which assigns its own
    and returns a 201; `submit()` reports it as `plan.id` rather than let a
    caller believe the id they sent is the plan's.

    `extra="allow"`, so a misspelled key is kept rather than dropped, and
    `submit()` reports it as one `UnknownFieldError` listing every level
    (the plan, its resources, orders, stops, ...) where one was found.
    """

    model_config = ConfigDict(extra="allow")

    properties: Optional[Dict[str, str]] = None
    resources: List[models.Resource]
    orders: Optional[List[Order]] = None
    additionalOperationDurations: Optional[List[models.AdditionalOperationDuration]] = None
    operationDurationPoliciesByResourceTag: Optional[
        Dict[str, List[models.OperationDurationPolicy]]
    ] = None
    additionalConstraints: Optional[
        List[
            Annotated[
                Union[
                    models.AdditionalConstraintAtLeastOneValidCapacity,
                    models.AdditionalConstraintForbiddenAssignment,
                    models.AdditionalConstraintIncompatibleStopTags,
                    models.AdditionalConstraintAtLeastOneConstraint,
                    models.AdditionalConstraintCapacities,
                    models.AdditionalConstraintMaxStopTagGroups,
                    models.AdditionalConstraintRemovalStrategy,
                ],
                Field(discriminator="type"),
            ]
        ]
    ] = None
    globalConstraints: Optional[List[models.GlobalConstraintMaxCumulatedCost]] = None
    accessDurationsByStopTag: Optional[Dict[str, models.Duration]] = None
    overlappingCapacitiesByStopTag: Optional[Dict[str, int]] = None
    setupDurations: Optional[List[models.SetupDuration]] = None
    objectives: Optional[
        List[Union[models.ObjectivesEnum, models.MaximizePrecedencesObjective, models.CustomObjective]]
    ] = None
    maxOptimizationDuration: Optional[models.Duration] = None
    tz: Optional[str] = None
    lateDeparture: bool = False
    sharedCapacities: bool = False
    emptyThresholdByCapacityByResourceTag: Optional[Dict[str, Dict[str, float]]] = None
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
    - `orders` is retyped to `PlanOrder`, a subclass of `Order` (the
      generated one, see above) that keeps unknown keys, so a `Plan` fetched
      with `get()` and a `PlanCreate` built by hand use the same `stops`
      shape — `plan.orders.append(Order(...))` ahead of `update()` works.
    - `warnings` doesn't exist on the generated `Plan` at all: it's a sibling
      of `item` on the `EnvelopedPlan` envelope, not a field of the plan
      itself. `submit`/`get`/`update` below copy it across after validating
      `item`, so callers get amendments (traffic turned off, a value
      clamped, ...) on the object they already have instead of a separate
      envelope type to unwrap.

    Every model here is `extra="allow"`, request and response alike. On the
    response side it is what lets this SDK parse a legitimate response the
    day the API adds a field this version doesn't know, and what lets
    `update()` — a full replacement — send that field back instead of
    deleting it server-side. On the request side the key is kept so
    `submit()` can report it; `update()` tells a key the server sent from
    one the caller added, using `_server_keys` below (see `update`).
    """

    model_config = ConfigDict(extra="allow")

    # Keys the server sent that no model declares. Filled by
    # `_plan_from_envelope`, so it is set on any plan that came from the
    # API and empty on one built by hand or read from a file. `update()`
    # uses it to tell a field the API added from a key the caller typed:
    # the API drops what it doesn't know (verified on both POST and PUT),
    # so anything it sends back is a real field by construction.
    #
    # A private attribute, so it survives `model_copy()` and `deepcopy`
    # without ever reaching the wire. It does not survive a round trip
    # through `model_dump()` / `model_validate()` — such a plan is treated
    # as hand-built and falls back to the weaker check: a warning on
    # near-misses only. It never refuses a real API field, but it no longer
    # catches a typo either.
    _server_keys: set[tuple[type, str]] = PrivateAttr(default_factory=set)
    _from_server: bool = PrivateAttr(default=False)

    # Narrowing the generated fields, on purpose (see above).
    id: str  # type: ignore[assignment]
    orders: Optional[List[PlanOrder]] = None  # type: ignore[assignment]
    warnings: List[models.Warning] = []


def _allowed(allow_unknown: Collection[str]) -> frozenset:
    """`allow_unknown` as a set of names.

    A bare `str` is refused rather than accepted: `str` satisfies
    `Collection[str]`, so `allow_unknown="someField"` type-checks, and `in`
    would then match any key that is a *substring* of it — dropping the
    brackets around one name would wave through a genuine typo, which is
    exactly what this check exists to catch.
    """
    if isinstance(allow_unknown, str):
        raise TypeError("allow_unknown takes a list of field names, not a single string")
    return frozenset(allow_unknown)


def _vouched_for(field, server_keys) -> bool:
    """Did the server send this key on this kind of object?

    Types are compared along the inheritance chain, not by identity:
    `Plan.orders` holds `PlanOrder`, while the docstring of `Plan` invites
    appending a plain `Order`, and both describe the same thing to the API.
    """
    return any(
        key == field.key and (issubclass(field.owner, cls) or issubclass(cls, field.owner))
        for cls, key in server_keys
    )


def _plan_from_envelope(response: Dict[str, Any]) -> Plan:
    """`EnvelopedPlan.item`, plus `EnvelopedPlan.warnings` copied onto the
    returned `Plan` — `warnings` is a sibling of `item` in the response
    body, not a field `Plan.model_validate(item)` would ever see on its own.
    """
    plan = validate_response(Plan, response["item"])
    plan.warnings = [validate_response(models.Warning, w) for w in response.get("warnings") or []]
    plan._server_keys = {f.origin for f in _annotations.unknown_fields(plan)}
    plan._from_server = True
    return plan


def _log_api_warnings(api_warnings: List[models.Warning]) -> None:
    """Logs the warnings of a `POST`/`PUT` response on the `kardinal` logger,
    one `WARNING` line per kind of warning (same `code` and `details`), with
    up to three of the paths it concerns. `plan.warnings` keeps them all.
    """
    groups: Dict[Tuple[str, str], List[str]] = {}
    for warning in api_warnings:
        properties = warning.properties or {}
        key = (warning.code.value, properties.get("details") or warning.message)
        paths = groups.setdefault(key, [])
        if properties.get("path"):
            paths.append(properties["path"])
    for (code, text), paths in groups.items():
        line = f"Kardinal API warning {code}: {text}"
        if paths:
            shown = paths[:3] + ([f"and {len(paths) - 3} more"] if len(paths) > 3 else [])
            line += f" ({', '.join(shown)})"
        # WHY: the logger is fetched here, at the moment of logging, and not
        # once at module level. A logger created when this module is imported
        # exists before the application configures logging, and
        # `logging.config.dictConfig` disables every existing logger it does
        # not name, so the line would vanish in a typical web application.
        # There is no `NullHandler` either: it would stop Python's fallback
        # handler from printing the line when nothing was configured.
        # The call is guarded because it runs after the API accepted the
        # plan: a handler or a filter that raises must not make `submit()`
        # fail once the plan exists and is billed.
        try:
            logging.getLogger("kardinal").warning(line)
        except Exception as error:
            print(f"Kardinal: logging the API warning failed: {error!r}", file=sys.stderr)


def _read_amended(response: Dict[str, Any]) -> Plan:
    """`_plan_from_envelope`, then logs the warnings of the response."""
    plan = _plan_from_envelope(response)
    _log_api_warnings(plan.warnings)
    return plan


def _create_body(plan: PlanCreate, allow_unknown: Collection[str]) -> Dict[str, Any]:
    """The request body of `submit()` and `replace()`. Refuses an unknown
    field that `allow_unknown` doesn't name.
    """
    allowed = _allowed(allow_unknown)
    unknown = [f for f in _annotations.unknown_fields(plan) if f.key not in allowed]
    if unknown:
        raise UnknownFieldError(unknown)
    return plan.model_dump(mode="json", exclude_none=True)


class PlansAPI:
    """`k.routing.plans`: submit, get, update, replace, delete, list/iter_all,
    start, stop, get_status.
    """

    def __init__(self, transport: Transport) -> None:
        self._transport = transport

    def submit(self, plan: PlanCreate, *, allow_unknown: Collection[str] = ()) -> Plan:
        """`POST /plans`. Creates a new plan and starts optimization —
        billed in full. The server assigns `id`.

        `allow_unknown` names fields to send that this SDK version doesn't
        declare — a field the API gained since it was released. Named one
        by one on purpose: a blanket switch would wave through a typo
        anywhere else in the plan, which is what this check exists to catch.

        A name given here is allowed on every object of the plan, not just
        the one you had in mind: unlike provenance, which is recorded per
        model type, this matches the key alone.
        """
        body = _create_body(plan, allow_unknown)
        response = self._transport.request("POST", "/plans", json=body)
        return _read_amended(response)

    def get(self, plan_id: str) -> Plan:
        """`GET /plans/{id}`. The plan as currently stored. Never carries
        warnings: they're only returned by `submit()`/`update()`.
        """
        response = self._transport.request("GET", f"/plans/{plan_id}")
        return _plan_from_envelope(response)

    def update(
        self, plan: Plan, *, force: bool = False, allow_unknown: Collection[str] = ()
    ) -> Plan:
        """`PUT /plans/{id}`. Sends the complete plan, replacing the stored one
        (anything left out is removed; fields this SDK version doesn't know,
        read by `get()`, are kept and sent back). The version increments, and the plan
        is re-optimized, only if the plan actually changed: an identical PUT
        is a free no-op, returning the same version. Only newly added unique
        stops are billed.

        Only the fields the plan was read or built with, plus the ones set
        on it since, are sent. A default this SDK fills in, such as
        `lateDeparture: false` or a `priority` of 0, is left out when the
        API didn't send it: the API compares the body with the stored plan
        as JSON, where an absent field and the same field at its default
        differ, so sending it would create a new version for no change.

        `force` unarchives the plan first if it's archived; ignored otherwise.

        Unknown keys are sorted by where they came from. One the server
        sent is a field the API added after this SDK version: it is sent
        back untouched, since a full replacement would otherwise delete it.
        One the caller added is a typo — the API drops what it doesn't
        know, so it would vanish in silence — and raises
        `UnknownFieldError`, exactly as in `submit()`.

        On a plan this SDK didn't read from the API (built by hand, or
        loaded from a file) there is nothing to sort by, so it falls back to
        warning on a key within two edits of a declared field, which is as
        far as resemblance alone can go.

        `allow_unknown` names fields to send that this SDK version doesn't
        declare, for a field the API gained since it was released and that
        isn't already on the fetched plan. A name given here is allowed on
        every object of the plan, not just the one you had in mind. See
        `submit` for why it names fields rather than switching the check off.
        """
        allowed = _allowed(allow_unknown)
        unknown = [f for f in _annotations.unknown_fields(plan) if f.key not in allowed]
        if plan._from_server:
            added_by_caller = [f for f in unknown if not _vouched_for(f, plan._server_keys)]
            if added_by_caller:
                raise UnknownFieldError(added_by_caller)
        else:
            likely_typos = [f for f in unknown if f.suggestion]
            if likely_typos:
                listed = ", ".join(str(f) for f in likely_typos)
                warnings.warn(
                    f"Possible typo(s) in the plan being sent: {listed}",
                    UnknownFieldWarning,
                    stacklevel=2,
                )
        # `warnings` is this SDK's own field (see `Plan`), not the plan's.
        # `exclude_unset`: see the docstring.
        body = plan.model_dump(
            mode="json",
            exclude_unset=True,
            exclude_none=True,
            exclude=set(_PLAN_READ_ONLY_FIELDS | {"warnings"}),
        )
        response = self._transport.request(
            "PUT", f"/plans/{plan.id}", json=body, params={"force": force}
        )
        return _read_amended(response)

    def replace(
        self,
        plan_id: str,
        plan: PlanCreate,
        *,
        force: bool = False,
        allow_unknown: Collection[str] = (),
    ) -> Plan:
        """`PUT /plans/{id}`. Replaces the stored plan with a new `PlanCreate`,
        without copying `id`, `agencyId` and `version` from a fetched plan.

        It is a full replacement, like `update()`. Anything you leave out is
        removed, including a field the API gained after this SDK version.
        To keep such a field, use `get()` and `update()` instead.

        It sends the same body as `submit()`. An identical plan is a free
        no-op that returns the same version, so a plan created by either SDK
        stays unchanged. A plan created from raw JSON, without the defaults
        this SDK fills in (`priority`, `lateDeparture`, `sharedCapacities`),
        gets one new version the first time, and then stays stable.

        There is no version check: the last write wins.

        `force` unarchives the plan first if it's archived; ignored otherwise.
        An unknown field raises `UnknownFieldError`, as in `submit()`.
        Retried like `update()`.
        """
        body = _create_body(plan, allow_unknown)
        response = self._transport.request(
            "PUT", f"/plans/{plan_id}", json=body, params={"force": force}
        )
        return _read_amended(response)

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

    def get_status(self, plan_id: str) -> models.PlanState:
        """`GET /plans/{id}/state`. Returns the plan's current `PlanState`
        (`waiting`, `processing`, ..., `optimized`, `stopped`, ...). It is a
        `str` enum: `== "optimized"` and `str(state)` work. A state this
        version of the SDK doesn't know yet is still a `PlanState`, equal to
        its raw string.

        The type returned is `PlanState` (the enum this endpoint's `state`
        field actually carries), not the unrelated `PlanStatus` object
        embedded in `Plan.status` — the spec uses both names for different
        things (see the README's "Good to know" section).
        """
        return self._get_state(plan_id)[0]

    def _get_state(self, plan_id: str) -> Tuple[models.PlanState, Optional[int]]:
        """`get_status()` plus the `planVersion` that state belongs to —
        `solutions.wait()` needs both, since right after `update()` this
        endpoint can still report the previous version's state.
        """
        response = self._transport.request("GET", f"/plans/{plan_id}/state")
        item = response["item"]
        with _lenient_enums():
            state = models.PlanState(item["state"])
        return state, item.get("planVersion")
