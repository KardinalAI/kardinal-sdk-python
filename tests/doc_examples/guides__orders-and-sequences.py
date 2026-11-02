# Copied from guides/orders-and-sequences.mdx by scripts/sync_doc_examples.py: do not edit by hand.

# --- guides/orders-and-sequences.mdx:342
from kardinal.routing import models
from kardinal.routing.plans import Order, PlanCreate

depot = models.Position(lon=2.35, lat=48.85)


def stop(stop_id, kind, lon):
    return models.SingleStop(
        type="single",
        id=stop_id,
        kind=kind,
        position=models.Position(lon=lon, lat=48.85),
        operationDuration="PT5M",
    )


van = models.Resource(
    id="van-1",
    vehicleProfile=models.VehicleProfileCar(type="car"),
    workingTimeWindow=models.TimeWindow(begin="2026-11-03 08:00", end="2026-11-03 18:00"),
    departure=depot,
    arrival=depot,
)

drop_site = models.AlternativesStop(
    type="alternatives",
    id="drop-site",
    alternatives=[stop("drop-far", "delivery", 2.145), stop("drop-near", "delivery", 2.282)],
)

plan = PlanCreate(
    tz="Europe/Paris",
    maxOptimizationDuration="PT5S",
    resources=[van],
    orders=[
        Order(
            id="order-1",
            successiveStops=True,
            stops=[stop("pickup-1", "pickup", 2.364), stop("delivery-1", "delivery", 2.487)],
        ),
        Order(
            id="order-2",
            successiveStops=True,
            stops=[stop("pickup-2", "pickup", 2.378), stop("delivery-2", "delivery", 2.501)],
        ),
        Order(id="order-3", stops=[stop("collect-3", "pickup", 2.309), drop_site]),
    ],
)


# --- guides/orders-and-sequences.mdx:490
def check_orders(plan, solution):
    """Return one message for each order that the engine did not fully serve."""
    served = {
        waypoint.stopId
        for tour in solution.tours
        for waypoint in tour.wayPoints
        if waypoint.type == "stop"
    }
    left_out = set(solution.unaffectedStopIds or [])

    # Map each candidate id to the id of its group.
    group_of = {
        candidate.id: stop.id
        for order in plan.orders
        for stop in order.stops
        if stop.type == "alternatives"
        for candidate in stop.alternatives
    }
    served_groups = {group_of[stop_id] for stop_id in served if stop_id in group_of}

    problems = []
    for order in plan.orders:
        for stop in order.stops:
            if stop.type == "single" and stop.id in left_out:
                problems.append(f"{order.id}: {stop.id} is left out")
            if stop.type == "alternatives" and stop.id not in served_groups:
                problems.append(f"{order.id}: no candidate of {stop.id} is in a tour")
    return problems
