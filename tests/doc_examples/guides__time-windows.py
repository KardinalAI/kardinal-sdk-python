# Copied from guides/time-windows.mdx by scripts/sync_doc_examples.py: do not edit by hand.

# --- guides/time-windows.mdx:136
from kardinal.routing import models
from kardinal.routing.plans import Order, PlanCreate

depot = models.Position(lon=2.35, lat=48.85)

van = models.Resource(
    id="van-1",
    vehicleProfile=models.VehicleProfileCar(type="car"),
    workingTimeWindow=models.TimeWindow(begin="2026-10-29 08:00", end="2026-10-29 20:00"),
    departure=depot,
    arrival=depot,
)

clinic = models.SingleStop(
    type="single",
    id="stop-clinic",
    kind="delivery",
    position=models.Position(lon=2.36, lat=48.855),
    operationDuration="PT10M",
    authorizedTimeWindows=[
        models.TaggedTimeWindow(begin="2026-10-29 08:00", end="2026-10-29 09:00", resourceTags=["certified"]),
        models.TaggedTimeWindow(begin="2026-10-29 10:00", end="2026-10-29 12:00"),
    ],
)

shop = models.SingleStop(
    type="single",
    id="stop-shop",
    kind="delivery",
    position=models.Position(lon=2.34, lat=48.845),
    operationDuration="PT10M",
    preferredTimeWindows=[models.TaggedTimeWindow(begin="2026-10-29 06:00", end="2026-10-29 06:30")],
)

plan = PlanCreate(
    tz="Europe/Paris",
    maxOptimizationDuration="PT5S",
    resources=[van],
    orders=[Order(id="order-clinic", stops=[clinic]), Order(id="order-shop", stops=[shop])],
)


# --- guides/time-windows.mdx:274
from datetime import datetime
from zoneinfo import ZoneInfo

zone = ZoneInfo(plan.tz)


def instant(text: str) -> datetime:
    """Read "2026-10-29 10:00" in the plan's tz, or "2026-10-29T10:00:00+01:00" as is."""
    value = datetime.fromisoformat(text)
    return value if value.tzinfo else value.replace(tzinfo=zone)


stops = {s.id: s for order in plan.orders for s in order.stops}
tags = {r.id: set(r.tags or []) for r in plan.resources}

for stop_id in solution.unaffectedStopIds or []:
    print(stop_id, "was not planned")

for tour in solution.tours:
    for wp in tour.wayPoints:
        if wp.type != "stop":
            continue
        stop = stops[wp.stopId]
        begin = instant(wp.beginTime)
        applying = [
            w
            for w in stop.authorizedTimeWindows or []
            if not w.resourceTags or tags[tour.resourceId] & set(w.resourceTags)
        ]
        inside = not stop.authorizedTimeWindows or any(
            instant(w.begin) <= begin <= instant(w.end) for w in applying
        )
        print(stop.id, "authorized: ok" if inside else "authorized: OUTSIDE", "delay:", wp.delay)
