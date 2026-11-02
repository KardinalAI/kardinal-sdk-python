# Copied from guides/capacities.mdx by scripts/sync_doc_examples.py: do not edit by hand.

# --- guides/capacities.mdx:331
from kardinal.routing import models
from kardinal.routing.plans import Order, PlanCreate

depot = models.Position(lon=2.35, lat=48.85)
window = [models.TaggedTimeWindow(begin="2026-11-03 09:00", end="2026-11-03 12:00")]


def delivery(number, lon):
    stop = models.SingleStop(
        type="single",
        id=f"delivery-{number}",
        kind="delivery",
        position=models.Position(lon=lon, lat=48.85),
        operationDuration="PT10M",
        capacities={"weight": 200, "nbDeliveries": 1},
        authorizedTimeWindows=window,
    )
    return Order(id=f"order-{number}", stops=[stop])


pickup = models.SingleStop(
    type="single",
    id="pickup-1",
    kind="pickup",
    position=models.Position(lon=2.364, lat=48.85),
    operationDuration="PT10M",
    capacities={"weight": 60, "nbPickups": 1},
    authorizedTimeWindows=[models.TaggedTimeWindow(begin="2026-11-03 08:00", end="2026-11-03 12:00")],
)

truck = models.Resource(
    id="truck-1",
    vehicleProfile=models.VehicleProfileCar(type="car"),
    workingTimeWindow=models.TimeWindow(begin="2026-11-03 08:00", end="2026-11-03 17:00"),
    departure=depot,
    arrival=depot,
    capacities={"weight": 1200, "nbDeliveries": 30, "nbPickups": 10},
)

rule = models.AdditionalConstraintAtLeastOneValidCapacity(
    type="atLeastOneValidCapacity",
    name="pickups-late",
    capacities={"nbDeliveries": 0, "nbPickups": 0, "weight": 300},
)

plan = PlanCreate(
    tz="Europe/Paris",
    maxOptimizationDuration="PT5S",
    resources=[truck],
    orders=[delivery(1, 2.377), delivery(2, 2.391), delivery(3, 2.405), Order(id="order-4", stops=[pickup])],
    additionalConstraints=[rule],
)


# --- guides/capacities.mdx:515
def check_tour(tour, setups=()):
    """Return the problems found in one tour, and the compartment setup that fits."""
    problems = []
    ceilings = tour.get("resourceCapacities") or {}

    for key, ceiling in ceilings.items():
        peak = tour["maxFilledCapacities"].get(key, 0)
        if peak > ceiling:
            problems.append(f"{key}: peak {peak} is over the ceiling {ceiling}")

    for waypoint in tour["wayPoints"]:
        if waypoint["type"] != "stop":
            continue
        for key, load in waypoint["filledCapacitiesAfterStop"].items():
            if key in ceilings and load > ceilings[key]:
                problems.append(f"{waypoint['stopId']}: {key} {load} is over the ceiling {ceilings[key]}")

    # The solution doesn't name the compartment setup. Take the first one that fits the peaks.
    peaks = tour["maxFilledCapacities"]
    fitting = next((s for s in setups if all(peaks.get(k, 0) <= v for k, v in s.items())), None)
    return problems, fitting


setups = [{"frozenVolume": 0, "chilledVolume": 10}, {"frozenVolume": 5, "chilledVolume": 5}]
# A tour with a peak of 4 frozen and 5 chilled returns the second setup.


# --- guides/capacities.mdx:545
if solution["unaffectedStopIds"]:
    print("Left out:", solution["unaffectedStopIds"])
