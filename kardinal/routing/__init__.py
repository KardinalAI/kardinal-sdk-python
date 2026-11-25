"""Route optimization: plans, solutions, and their models.

Using a coding agent? Run `kardinal init` at the root of your repository
(it needs the `cli` extra). It writes a skill for this SDK to
`.claude/skills/kardinal-python/SKILL.md` (Claude Code) and to
`.agents/skills/kardinal-python/SKILL.md` (Codex, Mistral Vibe). The skill
lists the pitfalls of this SDK and links to the modeling rules in the docs.

`unknown_fields(plan)` is the check `submit()` makes, exposed so a caller
can run it before sending — the CLI has `validate`, and the library had no
equivalent once `submit()` started raising on an unknown key.

Resolved on first access rather than imported here: importing the models is
what applies the patches in `_annotations`, and doing that eagerly would
make `kardinal routing --help` load every generated model to print a usage
string.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ._annotations import UnknownField, unknown_fields

__all__ = ["UnknownField", "unknown_fields", "examples", "models", "plans", "solutions"]

_LAZY = {"UnknownField", "unknown_fields"}


def __getattr__(name: str) -> Any:
    if name in _LAZY:
        from . import _annotations

        return getattr(_annotations, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    return sorted(__all__)
