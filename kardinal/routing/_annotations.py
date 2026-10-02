"""Pydantic-only fixes on top of the generated models, reapplied after
every regeneration. Kept separate from `kardinal/routing/models/` — never
hand-edited — precisely so it survives regeneration; only patches that are
about pydantic's own behavior belong here, not anything that describes the
API itself (that belongs in the spec).

Importing this module patches `kardinal.routing.models` in place. `plans.py`
imports it for that side effect before constructing anything, and every
documented entry point (`Kardinal`, `routing.plans`, `routing.solutions`,
`routing.examples`, the CLI) goes through `plans.py` first, so the patch is
always in place by the time a user's code runs.

**Known gap**: this is *not* guaranteed if a caller does
`from kardinal.routing import models` on its own, bypassing every documented
entry point — the patch would not have run yet. It isn't applied at the
`kardinal.routing` package level instead, because that would run on every
import of any submodule, including `kardinal.routing.cli`, which would
reintroduce the exact "`--help` loads the models" problem this file's
sibling fix (routing/cli.py's lazy imports) exists to avoid. Trade-off kept
in favor of `--help` staying fast and connection-free.
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from enum import Enum
from typing import Any, Iterator, Optional, Type, TypeVar
from uuid import UUID

from pydantic import BaseModel, RootModel

from . import models

_SCALAR_ROOT_TYPES = (str, int, float, bool, UUID, Enum)


def _generated_models() -> list[type[BaseModel]]:
    return [
        obj
        for obj in vars(models).values()
        if isinstance(obj, type)
        and issubclass(obj, BaseModel)
        and obj.__module__ == models.__name__
    ]


def _patch_keep_unknown_fields() -> bool:
    """Generated models default to dropping an unknown key, which makes a
    misspelled optional field impossible to detect: the value disappears
    before anything can look at it, the plan is accepted, and the field it
    was meant to set stays unset. 155 of the 231 fields on the request path
    are optional, so most of a plan can be silently lost this way.

    Keep those keys instead of dropping them. Nothing is rejected here —
    `unknown_fields()` reports them, and `submit()`/`update()` raise on what
    it finds. Responses keep parsing: an unknown key the server adds is
    retained rather than refused, which is the same tolerance
    `_patch_lenient_enums` gives enum values.

    Rebuilding is done in several passes on purpose. A model compiles its
    fields' validators into itself, so a model rebuilt before its members
    keeps their stale version: `Order` rebuilt before `Stop` would still
    drop what `Stop` now keeps. Repeating lets the change reach every
    dependant whatever the declaration order.
    """
    plain = [c for c in _generated_models() if not issubclass(c, RootModel)]
    for cls in plain:
        cls.model_config["extra"] = "allow"
    for _ in range(3):
        for cls in _generated_models():
            cls.model_rebuild(force=True)
    return bool(plain)


KEEP_UNKNOWN_FIELDS_PATCH_APPLIED = _patch_keep_unknown_fields()


def unknown_fields(obj: Any, path: str = "plan") -> list[str]:
    """Paths of every key no model declared, e.g.
    `plan.resources[0].maxWorkingDurationn`. Empty when the payload is clean.
    """
    found: list[str] = []
    if isinstance(obj, RootModel):
        return unknown_fields(obj.root, path)
    if isinstance(obj, BaseModel):
        found += [f"{path}.{key}" for key in sorted(obj.model_extra or {})]
        for name in type(obj).model_fields:
            found += unknown_fields(getattr(obj, name, None), f"{path}.{name}")
    elif isinstance(obj, list):
        for index, item in enumerate(obj):
            found += unknown_fields(item, f"{path}[{index}]")
    elif isinstance(obj, dict):
        for key, value in obj.items():
            found += unknown_fields(value, f"{path}.{key}")
    return found


def _patch_broken_plan_id() -> bool:
    """openapi.yaml chains `Plan.id -> allOf [PlanId] -> allOf [UUID]`: two
    nested single-$ref `allOf`s. datamodel-codegen only resolves one hop, so
    the generated `PlanId` ends up an empty `BaseModel` with no fields at
    all — every one of the 13 fields typed `Optional[PlanId]` (`Plan.id`,
    `PlanLight.id`, and every response envelope's `planId`) fails to parse
    the UUID string the API actually sends.

    Point those fields at a plain string instead and rebuild the affected
    models. This is a codegen defect on a double-`allOf` chain in the spec,
    not fixed there this pass.

    Returns whether anything was patched. Deliberately not an `assert`: if
    the spec is ever fixed upstream so `PlanId` parses correctly on its own,
    this finding nothing to patch is the *correct*, desired outcome, not an
    error — a bare `assert` here would instead raise at import time for
    every installed copy of this SDK the moment that unrelated, beneficial
    server-side fix ships, which would look like the SDK itself broke. The
    test suite (not runtime) is where this gets checked — see
    tests/test_annotations.py.
    """
    broken = Optional[models.PlanId]
    fixed = Optional[str]
    patched_any = False
    for name in dir(models):
        cls = getattr(models, name)
        if not (isinstance(cls, type) and issubclass(cls, models.BaseModel)):
            continue
        changed = False
        for field_name in ("id", "planId"):
            field = cls.model_fields.get(field_name)
            if field is not None and field.annotation == broken:
                field.annotation = fixed  # type: ignore[assignment]
                changed = True
        if changed:
            cls.model_rebuild(force=True)
            patched_any = True
    return patched_any


PLAN_ID_PATCH_APPLIED = _patch_broken_plan_id()


def _patch_scalar_root_equality() -> bool:
    """A generated `RootModel[str]`/`[int]`/`[UUID]`/`[Enum]` (`RegexIdValidation`,
    `PlanVersion`, `Duration`, `TimeZone`, `AgencyId`, `DateTime`, `CountryCode`,
    `UUIDModel`, ...) wraps its value instead of being it: pydantic's default
    `BaseModel.__eq__` only considers two instances equal if they're the same
    model class with equal fields, so `tour.resourceId == "truck-1"` is always
    `False` even though `resourceId` is conceptually a plain string, and
    `str(tour.resourceId)` prints `"root='truck-1'"` instead of `"truck-1"`.
    `RootModel` also inherits `BaseModel`'s unhashable-by-default `__hash__`.

    Scoped to *scalar* root types only (via `dir(models)` introspection, same
    pattern as `_patch_broken_plan_id` above, so it stays correct across
    regeneration without a hand-maintained class list). Composite root models
    (`RootModel[List[...]]`, `RootModel[Dict[...]]`, `RootModel[Union[...]]`,
    e.g. `StopTagPair`, `CountryCodes`) are deliberately left untouched: a
    transparent `__eq__`/`__str__` is unambiguous for a scalar but not for a
    collection, where it could hide accidental comparisons against the wrong
    shape.

    Network (de)serialization is unaffected either way: `model_dump(mode="json")`
    already unwraps `.root` regardless of these dunder methods.
    """
    patched_any = False
    for name in dir(models):
        cls = getattr(models, name)
        if not (isinstance(cls, type) and issubclass(cls, models.RootModel)):
            continue
        if cls is models.RootModel:
            continue
        field = cls.model_fields.get("root")
        if field is None or not (
            isinstance(field.annotation, type)
            and issubclass(field.annotation, _SCALAR_ROOT_TYPES)
        ):
            continue

        def _eq(self: Any, other: object, _cls: type = cls) -> bool:
            if isinstance(other, _cls):
                return bool(self.root == other.root)  # type: ignore[attr-defined]
            return bool(self.root == other)

        def _hash(self: Any) -> int:
            return hash(self.root)

        def _str(self: Any) -> str:
            return str(self.root)

        def _format(self: Any, format_spec: str) -> str:
            return format(self.root, format_spec)

        # setattr: these replace methods on a class generated elsewhere.
        setattr(cls, "__eq__", _eq)
        setattr(cls, "__hash__", _hash)
        setattr(cls, "__str__", _str)
        setattr(cls, "__format__", _format)
        patched_any = True
    return patched_any


SCALAR_ROOT_EQUALITY_PATCH_APPLIED = _patch_scalar_root_equality()


# Set while parsing a response from the server, never while validating what
# a user builds (see `validate_response` below).
_LENIENT_ENUMS: ContextVar[bool] = ContextVar("kardinal_lenient_enums", default=False)


def _lenient_missing(cls: Type[Enum], value: object) -> Optional[Enum]:
    """`Enum._missing_`: in a server response, a value this SDK version
    doesn't know becomes a pseudo-member carrying it (`.value` is the raw
    string), instead of failing the whole response."""
    if not (_LENIENT_ENUMS.get() and isinstance(value, str)):
        return None
    member = object.__new__(cls)
    member._value_ = value
    member._name_ = value
    return member


def _patch_lenient_enums() -> bool:
    """The API may add a value to any enum in a non-breaking release (a new
    plan state, warning code, ...): openapi.yaml says so for codes. Strict
    enum validation would make `get()`, `list()`, `submit()` ... fail on a
    legitimate response with a `pydantic.ValidationError` the day that
    happens — after `submit()` already created and billed the plan. The
    TypeScript SDK passes such values through; so does this, but only for
    responses: a plan built by hand is still validated strictly.
    """
    patched_any = False
    for name in dir(models):
        cls = getattr(models, name)
        if isinstance(cls, type) and issubclass(cls, Enum) and cls is not Enum:
            cls._missing_ = classmethod(_lenient_missing)  # type: ignore[assignment]
            patched_any = True
    return patched_any


LENIENT_ENUMS_PATCH_APPLIED = _patch_lenient_enums()

_M = TypeVar("_M", bound=BaseModel)


@contextmanager
def _lenient_enums() -> Iterator[None]:
    token = _LENIENT_ENUMS.set(True)
    try:
        yield
    finally:
        _LENIENT_ENUMS.reset(token)


def validate_response(model: Type[_M], data: Any) -> _M:
    """`model.model_validate(data)` for data the server sent: enum values
    this SDK version doesn't know are kept instead of rejected."""
    with _lenient_enums():
        return model.model_validate(data)
