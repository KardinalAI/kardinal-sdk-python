# Copied from guides/breaks.mdx by scripts/sync_doc_examples.py: do not edit by hand.

# --- guides/breaks.mdx:192
from kardinal.routing import models
from kardinal.routing.plans import Order, PlanCreate

depot = models.Position(lon=2.35, lat=48.85)

van = models.Resource(
    id="van-1",
    vehicleProfile=models.VehicleProfileCar(type="car"),
    workingTimeWindow=models.TimeWindow(begin="2026-10-29 08:00", end="2026-10-29 20:00"),
    departure=depot,
    arrival=depot,
    breaks=[
        models.TimeWindowBreak(
            type="timeWindowBreak",
            duration="PT45M",
            timeWindow=models.TimeWindow(begin="2026-10-29 12:00", end="2026-10-29 14:00"),
        )
    ],
)

morning = models.SingleStop(
    type="single",
    id="stop-morning",
    kind="delivery",
    position=models.Position(lon=2.36, lat=48.855),
    operationDuration="PT10M",
)

afternoon = models.SingleStop(
    type="single",
    id="stop-afternoon",
    kind="delivery",
    position=models.Position(lon=2.34, lat=48.845),
    operationDuration="PT10M",
    authorizedTimeWindows=[models.TaggedTimeWindow(begin="2026-10-29 15:00", end="2026-10-29 16:00")],
)

plan = PlanCreate(
    tz="Europe/Paris",
    maxOptimizationDuration="PT5S",
    resources=[van],
    orders=[Order(id="order-morning", stops=[morning]), Order(id="order-afternoon", stops=[afternoon])],
)
