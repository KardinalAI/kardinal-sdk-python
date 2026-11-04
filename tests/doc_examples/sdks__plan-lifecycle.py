# Copied from sdks/plan-lifecycle.mdx by scripts/sync_doc_examples.py: do not edit by hand.

# --- sdks/plan-lifecycle.mdx:12
from kardinal import Kardinal
from kardinal.routing import examples

k = Kardinal()
plan = k.routing.plans.submit(examples.small_delivery_plan())
print(plan.id, plan.version)
for warning in plan.warnings:
    print(warning.code, warning.properties)


# --- sdks/plan-lifecycle.mdx:44
solution = k.routing.solutions.wait(plan.id)            # no time limit
solution = k.routing.solutions.wait(plan.id, timeout=600)  # at most 10 minutes
print(solution.final_state)


# --- sdks/plan-lifecycle.mdx:71
from kardinal.routing import models

state = k.routing.plans.get_status(plan.id)  # waiting, processing, optimizing, optimized, ...
if state == models.PlanState.optimized:
    solution = k.routing.solutions.get(plan.id)
objectives = k.routing.solutions.get_objectives(plan.id)  # objective values only


# --- sdks/plan-lifecycle.mdx:119
from kardinal.routing import models
from kardinal.routing.plans import Order

plan = k.routing.plans.get(plan.id)
plan.orders.append(
    Order(
        id="order-10",
        stops=[models.SingleStop(type="single", id="stop-10", position=models.Position(lat=48.86, lon=2.35))],
    )
)
plan = k.routing.plans.update(plan)  # same id, new version
solution = k.routing.solutions.wait(plan.id)


# --- sdks/plan-lifecycle.mdx:155
k.routing.plans.stop(plan.id)   # stop the optimization in progress
k.routing.plans.start(plan.id)  # restart it, on the same version


# --- sdks/plan-lifecycle.mdx:173
page = k.routing.plans.list(page=1, items_per_page=20)
print(page.total, page.total_pages, page.next_page)

for light_plan in k.routing.plans.iter_all():  # every page, one plan at a time
    print(light_plan.id, light_plan.state)


# --- sdks/plan-lifecycle.mdx:199
k.routing.plans.delete(plan.id)
