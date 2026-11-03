#!/usr/bin/env bash
# Regenerate kardinal/routing/models/__init__.py from spec/openapi.yaml.
# datamodel-codegen with the options below, plus deterministic post-process
# fixes (see below) — never hand-edit the generated file itself.
set -euo pipefail

cd "$(dirname "$0")/.."

OUTPUT=kardinal/routing/models/__init__.py
mkdir -p "$(dirname "$OUTPUT")"

python3 -m datamodel_code_generator \
  --input spec/openapi.yaml --input-file-type openapi \
  --output-model-type pydantic_v2.BaseModel \
  --use-schema-description \
  --extra-fields=allow \
  --field-constraints \
  --use-subclass-enum \
  --collapse-root-models \
  --set-default-enum-member \
  --disable-timestamp \
  --output "$OUTPUT"

# `--collapse-root-models` unwraps most single-value RootModels, so a stop id
# is a `str`, a plan version an `int`, and a tour's `wayPoints` a plain list
# of the four waypoint models: no `.root`, `json.dumps` accepts them. Two
# things are left undone, and this step finishes them without a hand-kept
# class list:
#  1. The spec attaches a description to a reference with `allOf: [$ref]`
#     (`Plan.state`, `WayPoint*.status`, `Tour.mode`, ...). The generator
#     keeps such a reference wrapped, so `plan.state` stays a RootModel that
#     `json.dumps` refuses and that needs `.root`. Every remaining RootModel
#     (around a scalar, an enum, an object or a list: a list with a single
#     kind of member, such as the global constraints, is wrapped the same
#     way, and would lose its wrapper by itself the day a second kind
#     appears) is replaced by its inner type. When it
#     carries a constraint (an id or duration pattern) the name stays, as an
#     `Annotated[...]` alias, so the constraint is still checked.
#  2. The collapse drops `discriminator='type'` from the unions of stops,
#     waypoints, breaks, violations and constraints. Without it pydantic
#     tries every variant and reports the errors of all of them, under the
#     class name instead of the API's `type` value. It is restored on every
#     union whose members all declare a `type` Literal.
python3 - "$OUTPUT" <<'PY'
import ast
import re
import sys

path = sys.argv[1]
CONSTRAINTS = {
    "pattern", "min_length", "max_length", "ge", "le", "gt", "lt", "multiple_of",
}


def offset(lines, lineno, col):
    # ast columns are UTF-8 byte offsets.
    return sum(len(l.encode()) for l in lines[: lineno - 1]) + col


def apply(src, edits):
    data = src.encode()
    for start, end, text in sorted(edits, reverse=True):
        data = data[:start] + text.encode() + data[end:]
    return data.decode()


src = open(path).read()
lines = src.splitlines(keepends=True)
tree = ast.parse(src)
classes = {n.name: n for n in tree.body if isinstance(n, ast.ClassDef)}

# 1. every RootModel wrapper (scalar, enum, object, list) -> inner type
inline = {}
aliases = {}
for name, cls in classes.items():
    if len(cls.bases) != 1:
        continue
    base = cls.bases[0]
    if not (isinstance(base, ast.Subscript) and ast.unparse(base.value) == "RootModel"):
        continue
    inner = ast.unparse(base.slice)
    root = next(
        (s for s in cls.body if isinstance(s, ast.AnnAssign) and s.target.id == "root"),
        None,
    )
    kept = []
    if root is not None and isinstance(root.value, ast.Call):
        kept = [
            f"{k.arg}={ast.get_source_segment(src, k.value)}"
            for k in root.value.keywords
            if k.arg in CONSTRAINTS
        ]
    if kept:
        # Keep the name as an alias that carries the constraints, so a
        # pattern is still checked wherever the type is used.
        aliases[name] = f"Annotated[{inner}, Field({', '.join(kept)})]"
    else:
        inline[name] = inner

edits = []
for name, cls in classes.items():
    start = offset(lines, cls.lineno, 0)
    end = offset(lines, cls.end_lineno + 1, 0)
    if name in aliases:
        edits.append((start, end, f"{name} = {aliases[name]}\n"))
        continue
    if name in inline:
        first = cls.lineno - 1
        while first > 0 and not lines[first - 1].strip():
            first -= 1
        edits.append((offset(lines, first + 1, 0), end, ""))
        continue
    spots = list(cls.bases)
    spots += [s.annotation for s in cls.body if isinstance(s, ast.AnnAssign)]
    for spot in spots:
        for node in ast.walk(spot):
            if isinstance(node, ast.Name) and node.id in inline:
                edits.append((
                    offset(lines, node.lineno, node.col_offset),
                    offset(lines, node.end_lineno, node.end_col_offset),
                    inline[node.id],
                ))
src = apply(src, edits)
for name in (*inline, *aliases):
    src = re.sub(rf"^{name}\.model_rebuild\(\)\n", "", src, flags=re.M)

# 2. discriminated unions
lines = src.splitlines(keepends=True)
tree = ast.parse(src)
classes = {n.name: n for n in tree.body if isinstance(n, ast.ClassDef)}


def has_type_literal(cls):
    return any(
        isinstance(s, ast.AnnAssign)
        and getattr(s.target, "id", "") == "type"
        and ast.unparse(s.annotation).startswith("Literal[")
        for s in cls.body
    )


def discriminable_unions(annotation):
    for node in ast.walk(annotation):
        if isinstance(node, ast.Subscript) and ast.unparse(node.value) == "Union":
            members = node.slice.elts if isinstance(node.slice, ast.Tuple) else [node.slice]
            if len(members) > 1 and all(
                isinstance(m, ast.Name) and m.id in classes and has_type_literal(classes[m.id])
                for m in members
            ):
                yield node


# pydantic wants the discriminator on the union itself, not on a list of it.
edits = []
for cls in classes.values():
    for s in cls.body:
        if not isinstance(s, ast.AnnAssign):
            continue
        if s.value is not None and "discriminator" in ast.unparse(s.value):
            continue
        for node in discriminable_unions(s.annotation):
            start = offset(lines, node.lineno, node.col_offset)
            end = offset(lines, node.end_lineno, node.end_col_offset)
            edits.append((end, end, ", Field(discriminator='type')]"))
            edits.append((start, start, "Annotated["))
src = apply(src, edits)
if "Annotated[" in src and "import Annotated" not in src and "Annotated," not in src:
    src = src.replace("from typing import Dict,", "from typing import Annotated, Dict,", 1)
open(path, "w").write(src)
PY

# datamodel-codegen appends a trailing block of `SomeModel.model_rebuild()`
# calls (to resolve forward references) whose ORDER isn't stable across
# Python versions/environments, even though the set of classes is — call
# order doesn't matter here (each call is independent), so sort the block
# to make the output byte-identical everywhere. Without this, the CI "no
# diff" check (tests/test_models_no_diff.py) can fail on a pipeline even when nothing meaningful
# changed, purely because it ran on a different Python build than whoever
# last committed the file.
python3 - "$OUTPUT" <<'PY'
import re
import sys

path = sys.argv[1]
lines = open(path).readlines()

i = len(lines)
while i > 0 and re.match(r"^[A-Za-z_][A-Za-z0-9_]*\.model_rebuild\(\)\n?$", lines[i - 1]):
    i -= 1

lines[i:] = sorted(lines[i:])
open(path, "w").writelines(lines)
PY


# Make the hand-written patches in _annotations.py impossible to bypass.
# They were applied by importing plans.py/solutions.py, so a caller who
# imported the models on their own — to build a payload before touching the
# client — got the unpatched versions: `PlanId` unparseable, and unknown
# keys dropped instead of kept, which silently disabled submit()'s spelling
# check. Importing the models is now enough, whatever the entry point.
# Appended last so it runs once every class above exists.
cat >> "$OUTPUT" <<'PY'


from .. import _annotations  # noqa: E402,F401
PY

echo "Generated $OUTPUT"
