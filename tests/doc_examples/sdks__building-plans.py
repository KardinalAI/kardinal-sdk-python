# Copied from sdks/building-plans.mdx by scripts/sync_doc_examples.py: do not edit by hand.

# --- sdks/building-plans.mdx:36
from kardinal.routing import examples, models
from kardinal.routing.plans import Order

plan = examples.small_delivery_plan()
plan.orders.append(
    Order(
        id="order-9",
        stops=[
            models.SingleStop(
                type="single",
                id="stop-9",
                position=models.Position(lat=48.8584, lon=2.2945),
                operationDuration="PT5M",
            )
        ],
    )
)


# --- sdks/building-plans.mdx:87
from pathlib import Path

from kardinal import Kardinal
from kardinal.routing.plans import PlanCreate

plan = PlanCreate.model_validate_json(Path("plan.json").read_text())
created = Kardinal().routing.plans.submit(plan)


# --- sdks/building-plans.mdx:119
from kardinal.routing import unknown_fields

for field in unknown_fields(plan):
    print(field)  # plan.resources[0].maxWorkingDurationn  (did you mean maxWorkingDuration?)
