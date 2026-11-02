# Copied from guides/resource-limits.mdx by scripts/sync_doc_examples.py: do not edit by hand.

# --- guides/resource-limits.mdx:233
from kardinal.routing import models
from kardinal.routing.plans import Order, PlanCreate

depot = models.Position(lon=2.35, lat=48.85)

def delivery(number, stop_id, lon):
    stop = models.SingleStop(
        type="single",
        id=stop_id,
        kind="delivery",
        position=models.Position(lon=lon, lat=48.85),
        operationDuration="PT30M",
    )
    return Order(id=f"order-{number}", stops=[stop])

van = models.Resource(
    id="van-1",
    vehicleProfile=models.VehicleProfileCar(type="car"),
    workingTimeWindow=models.TimeWindow(begin="2026-11-04 08:00", end="2026-11-04 17:00"),
    departure=depot,
    arrival=depot,
    maxWorkingDuration="PT3H",
)

plan = PlanCreate(
    tz="Europe/Paris",
    maxOptimizationDuration="PT5S",
    resources=[van],
    orders=[
        delivery(1, "stop-1", 2.377),
        delivery(2, "stop-2", 2.391),
        delivery(3, "stop-3", 2.405),
        delivery(4, "stop-far", 2.9),
    ],
)


# --- guides/resource-limits.mdx:355
import re

DURATION = re.compile(r"^P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+(?:\.\d+)?)S)?)?$")

def seconds(duration):
    """Turn an ISO 8601 duration such as PT1H39M40S into seconds."""
    days, hours, minutes, secs = (float(part or 0) for part in DURATION.match(duration).groups())
    return ((days * 24 + hours) * 60 + minutes) * 60 + secs

def check_limits(tour, resource):
    """Return the limits that the tour is over."""
    problems = []
    cap = resource.get("maxWorkingDuration")
    if cap and seconds(tour["workingDuration"]) > seconds(cap):
        problems.append(f"workingDuration {tour['workingDuration']} is over {cap}")
    limit = resource.get("maxDistanceInKm")
    if limit and tour["distanceInKm"] > limit:
        problems.append(f"distanceInKm {tour['distanceInKm']} is over {limit}")
    return problems
