#!/usr/bin/env bash
# CI check: regenerating the models must produce no diff. Regenerates in
# place and fails if the committed file changed.
set -euo pipefail
cd "$(dirname "$0")/.."

MODELS=kardinal/routing/models/__init__.py

bash scripts/generate_models.sh

if ! git diff --quiet -- "$MODELS"; then
  echo "$MODELS is out of date with spec/openapi.yaml." >&2
  echo "Run scripts/generate_models.sh and commit the result." >&2
  git diff -- "$MODELS" >&2
  exit 1
fi

echo "Models are up to date."
