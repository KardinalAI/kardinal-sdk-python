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

from enum import Enum
from typing import Optional
from uuid import UUID

from . import models

_SCALAR_ROOT_TYPES = (str, int, float, bool, UUID, Enum)


def _patch_broken_plan_id() -> bool:
    """openapi.yaml chains `Plan.id -> allOf [PlanId] -> allOf [UUID]`: two
    nested single-$ref `allOf`s. datamodel-codegen only resolves one hop, so
    the generated `PlanId` ends up an empty `BaseModel` with no fields at
    all — every one of the 13 fields typed `Optional[PlanId]` (`Plan.id`,
    `PlanLight.id`, and every response envelope's `planId`) fails to parse
    the UUID string the API actually sends.

    Point those fields at a plain string instead and rebuild the affected
    models. This is a codegen defect on a double-`allOf` chain in the spec,
    not fixed there this pass — see the README's "known gaps" section.

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
                field.annotation = fixed
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

        def _eq(self, other: object, _cls: type = cls) -> bool:
            if isinstance(other, _cls):
                return self.root == other.root
            return self.root == other

        def _hash(self: object) -> int:
            return hash(self.root)  # type: ignore[attr-defined]

        def _str(self: object) -> str:
            return str(self.root)  # type: ignore[attr-defined]

        def _format(self: object, format_spec: str) -> str:
            return format(self.root, format_spec)  # type: ignore[attr-defined]

        cls.__eq__ = _eq
        cls.__hash__ = _hash
        cls.__str__ = _str
        cls.__format__ = _format
        patched_any = True
    return patched_any


SCALAR_ROOT_EQUALITY_PATCH_APPLIED = _patch_scalar_root_equality()
