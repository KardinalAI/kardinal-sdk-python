# Copied from sdks/errors-and-warnings.mdx by scripts/sync_doc_examples.py: do not edit by hand.

# --- sdks/errors-and-warnings.mdx:28
from kardinal import KardinalLimitError, KardinalValidationError

try:
    plan = k.routing.plans.submit(plan_input)
except KardinalValidationError as e:
    print(e.code)    # INVALID_VALUE, ID_NOT_UNIQUE, ...
    print(e.errors)  # every error of the response, not only the first
    raise
except KardinalLimitError as e:
    print(e.details)  # which limit was hit
    raise


# --- sdks/errors-and-warnings.mdx:145
def stored_value(plan, path):
    value = plan.model_dump(mode="json", exclude_none=True)
    for key in path.split("."):
        value = value[int(key)] if isinstance(value, list) else (value or {}).get(key)
    return value

plan = k.routing.plans.submit(plan_input)
for warning in plan.warnings:
    path = (warning.properties or {}).get("path")
    if path:
        print(warning.code, path, stored_value(plan, path))  # for example, INVALID_VALUE maxOptimizationDuration PT6H


# --- sdks/errors-and-warnings.mdx:191
import logging

logging.getLogger("kardinal").setLevel(logging.ERROR)
