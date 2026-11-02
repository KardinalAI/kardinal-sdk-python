# Copied from sdks/quickstart.mdx by scripts/sync_doc_examples.py: do not edit by hand.

# --- sdks/quickstart.mdx:45
from kardinal import Kardinal
from kardinal.routing import examples

k = Kardinal()  # reads KARDINAL_API_KEY
plan = k.routing.plans.submit(examples.small_delivery_plan())
solution = k.routing.solutions.wait(plan.id)  # returns in about 20 seconds


# --- sdks/quickstart.mdx:72
print(solution.final_state)  # optimized, or interrupted/stopped if cut short
for tour in solution.tours or []:  # tours is None when no stop could be planned
    print(tour.resourceId, len(tour.wayPoints))
