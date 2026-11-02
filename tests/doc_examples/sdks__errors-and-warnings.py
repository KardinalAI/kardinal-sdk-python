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
plan = k.routing.plans.submit(plan_input)
for warning in plan.warnings:
    print(warning.code, warning.properties)  # for example, maxOptimizationDuration clamped
