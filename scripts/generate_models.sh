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
  --field-constraints \
  --disable-timestamp \
  --output "$OUTPUT"

# openapi.yaml has two `oneOf` unions with exactly one member
# (`GlobalViolationMaxCumulatedCost`, `GlobalConstraintMaxCumulatedCost`).
# datamodel-codegen still attaches `discriminator='type'` to their RootModel
# wrapper even though there is nothing to discriminate between, and pydantic
# v2 refuses that combination outright (`PydanticUserError: ... needs field
# 'type' to be of type Literal`) — the generated module fails to import at
# all otherwise. A one-choice union needs no discriminator, so this drops it;
# every real (multi-member) discriminated union in the spec is untouched.
sed -i.bak \
  -e "s/root: GlobalViolationMaxCumulatedCost = Field(\.\.\., discriminator='type')/root: GlobalViolationMaxCumulatedCost = Field(...)/" \
  -e "s/root: GlobalConstraintMaxCumulatedCost = Field(\.\.\., discriminator='type')/root: GlobalConstraintMaxCumulatedCost = Field(...)/" \
  "$OUTPUT"
rm -f "$OUTPUT.bak"

# datamodel-codegen appends a trailing block of `SomeModel.model_rebuild()`
# calls (to resolve forward references) whose ORDER isn't stable across
# Python versions/environments, even though the set of classes is — call
# order doesn't matter here (each call is independent), so sort the block
# to make the output byte-identical everywhere. Without this, the CI "no
# diff" check (§9) can fail on a pipeline even when nothing meaningful
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
