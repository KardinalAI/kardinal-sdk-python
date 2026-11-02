"""Dev-time check for the PlanId patch in kardinal/routing/_annotations.py.

This is deliberately a test, not a runtime assertion in the SDK itself: if
openapi.yaml is ever fixed upstream so PlanId parses on its own, the patch
finding nothing to do is the correct, desired outcome for every installed
copy of the SDK out in the wild — it should never raise at import time for
an end user. Here, in CI, it means the patch (and this test) can be removed.
"""

from kardinal.routing._annotations import PLAN_ID_PATCH_APPLIED


def test_plan_id_patch_still_applies() -> None:
    assert PLAN_ID_PATCH_APPLIED, (
        "The PlanId patch found nothing to patch. If openapi.yaml's "
        "double-allOf chain (Plan.id -> PlanId -> UUID) was fixed upstream, "
        "this is expected — remove _patch_broken_plan_id() and this test, "
        "and drop the corresponding note from the README's known gaps."
    )

