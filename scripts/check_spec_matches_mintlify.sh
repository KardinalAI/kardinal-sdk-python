#!/usr/bin/env bash
# Structural comparison of spec/openapi.yaml against the openapi.yaml of the
# Kardinal API docs repository (checked out next to this one, `../mintlify`
# by default), which is the source of truth this SDK's spec is copied from.
#
# A raw `diff` on these two YAML files is misleading: property reordering
# between regenerations produces large, unreadable hunks even when nothing
# meaningful changed (see the audit that added this script — spec/openapi.yaml
# had silently drifted for a week because nothing checked this). Comparing
# the parsed structure instead reports only real additions/removals.
#
# Not wired into CI: the CI runner has no access to the docs repository. Run this by hand before a release, or whenever mintlify's
# openapi.yaml changes.
set -euo pipefail
cd "$(dirname "$0")/.."

# By default, compare against mintlify's *published* spec (`origin/main`),
# read with `git show` — not the working-tree file, which reflects whatever
# branch happens to be checked out there (possibly unmerged, unpublished
# doc work). Nothing is checked out or fetched in the mintlify repo: run
# `git -C <mintlify> fetch` first to compare against the latest main.
# An explicit file path as first argument is compared as-is.
if [ $# -ge 1 ]; then
  MINTLIFY_SPEC="$1"
  if [ ! -f "$MINTLIFY_SPEC" ]; then
    echo "Can't find $MINTLIFY_SPEC." >&2
    exit 2
  fi
else
  MINTLIFY_REPO="${MINTLIFY_REPO_PATH:-../mintlify}"
  MINTLIFY_REF="${MINTLIFY_REF:-origin/main}"
  MINTLIFY_SPEC="$(mktemp)"
  trap 'rm -f "$MINTLIFY_SPEC"' EXIT
  if ! git -C "$MINTLIFY_REPO" show "$MINTLIFY_REF:openapi.yaml" > "$MINTLIFY_SPEC" 2>/dev/null; then
    echo "Can't read openapi.yaml at $MINTLIFY_REF in $MINTLIFY_REPO." >&2
    echo "Usage: $0 [path/to/openapi.yaml]" >&2
    echo "   or: MINTLIFY_REPO_PATH=/path/to/mintlify MINTLIFY_REF=origin/main $0" >&2
    exit 2
  fi
  echo "Comparing against $MINTLIFY_REPO at $MINTLIFY_REF." >&2
fi

python3 - "spec/openapi.yaml" "$MINTLIFY_SPEC" <<'PY'
import sys
import yaml

sdk_path, mintlify_path = sys.argv[1], sys.argv[2]
a = yaml.safe_load(open(sdk_path))
b = yaml.safe_load(open(mintlify_path))


def diff(a, b, path=""):
    diffs = []
    if type(a) is not type(b):
        return [(path, "type", a, b)]
    if isinstance(a, dict):
        for k in sorted(set(a) | set(b), key=str):
            p = f"{path}.{k}" if path else str(k)
            if k not in a:
                diffs.append((p, "only_in_mintlify", None, None))
            elif k not in b:
                diffs.append((p, "only_in_sdk", None, None))
            else:
                diffs.extend(diff(a[k], b[k], p))
    elif isinstance(a, list):
        if len(a) != len(b):
            diffs.append((path, "list_len", len(a), len(b)))
        for i, (x, y) in enumerate(zip(a, b)):
            diffs.extend(diff(x, y, f"{path}[{i}]"))
    elif a != b:
        diffs.append((path, "value", a, b))
    return diffs


findings = diff(a, b)
if not findings:
    print("spec/openapi.yaml matches the mintlify repo's openapi.yaml.")
    sys.exit(0)

print(f"spec/openapi.yaml has drifted from mintlify: {len(findings)} structural difference(s).")
for p, kind, av, bv in findings:
    if kind in ("only_in_sdk", "only_in_mintlify"):
        print(f"  {kind}: {p}")
    else:
        print(f"  {kind} at {p}: sdk={av!r} mintlify={bv!r}")
print()
print("Run: git -C <mintlify repo> show origin/main:openapi.yaml > spec/openapi.yaml && bash scripts/generate_models.sh")
sys.exit(1)
PY
