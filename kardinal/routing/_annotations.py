"""Pydantic-only fixes on top of the generated models, reapplied after
every regeneration. Kept separate from `kardinal/routing/models/` — never
hand-edited — precisely so it survives regeneration; only patches that are
about pydantic's own behavior belong here, not anything that describes the
API itself (that belongs in the spec).

Importing this module patches `kardinal.routing.models` in place. The
generated module imports it on its last line (appended by
`scripts/generate_models.sh`), so the patches are applied by importing the
models at all — no entry point can bypass them, and `--help` still doesn't
load them because the CLI imports the models only inside command bodies.
"""

from __future__ import annotations

import difflib
from contextlib import contextmanager
from contextvars import ContextVar
from enum import Enum
from typing import Any, Iterator, NamedTuple, Optional, Type, TypeVar
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


# Server-assigned, so never something a caller meant to send. Lives here
# rather than in plans.py because both the PUT body filter and the message
# for an unknown key need it.
PLAN_READ_ONLY_FIELDS = frozenset(
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


class UnknownField(NamedTuple):
    """A key no model declared, and what it was most likely meant to be.

    `suggestion` is a declared field of the same model one or two edits
    away — strong evidence of a typo, as opposed to a key the API may have
    added after this SDK version, which resembles nothing.
    """

    path: str
    suggestion: Optional[str]
    server_assigned: bool

    @property
    def hint(self) -> Optional[str]:
        if self.server_assigned:
            return "not a field you set: the server assigns it"
        return f"did you mean {self.suggestion}?" if self.suggestion else None

    def __str__(self) -> str:
        hint = self.hint
        return self.path if hint is None else f"{self.path}  ({hint})"


def _describe(key: str, owner: type[BaseModel], path: str) -> UnknownField:
    close = difflib.get_close_matches(key, owner.model_fields, n=1)
    return UnknownField(
        path=path,
        suggestion=close[0] if close else None,
        server_assigned=key in PLAN_READ_ONLY_FIELDS,
    )


def unknown_fields(obj: Any, path: str = "plan") -> list[UnknownField]:
    """Every key no model declared, with its path — e.g.
    `plan.resources[0].maxWorkingDurationn` — and a hint when the name is
    one edit away from a real field. Empty when the payload is clean.
    """
    found: list[UnknownField] = []
    if isinstance(obj, RootModel):
        return unknown_fields(obj.root, path)
    if isinstance(obj, BaseModel):
        owner = type(obj)
        found += [
            _describe(key, owner, f"{path}.{key}") for key in sorted(obj.model_extra or {})
        ]
        for name in owner.model_fields:
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
