# Copied from guides/multi-day.mdx by scripts/sync_doc_examples.py: do not edit by hand.

# --- guides/multi-day.mdx:140
from kardinal.routing import models
from kardinal.routing.plans import Order, PlanCreate

paris = models.Position(lon=2.36, lat=48.75)

def night(begin, end):
    return models.TimeWindowBreak(
        type="timeWindowBreak",
        duration="PT11H",
        timeWindow=models.TimeWindow(begin=begin, end=end),
    )

def delivery(name, lon, lat, begin, end):
    stop = models.SingleStop(
        type="single",
        id=f"stop-{name}",
        kind="delivery",
        position=models.Position(lon=lon, lat=lat),
        operationDuration="PT30M",
        authorizedTimeWindows=[models.TaggedTimeWindow(begin=begin, end=end)],
    )
    return Order(id=f"order-{name}", stops=[stop])

truck = models.Resource(
    id="truck-1",
    vehicleProfile=models.VehicleProfileTruck(type="truck"),
    workingTimeWindow=models.TimeWindow(begin="2026-11-09 06:00", end="2026-11-11 20:00"),
    departure=paris,
    arrival=paris,
    breaks=[
        night("2026-11-09 19:00", "2026-11-10 07:00"),
        night("2026-11-10 19:00", "2026-11-11 07:00"),
    ],
)

plan = PlanCreate(
    tz="Europe/Paris",
    maxOptimizationDuration="PT5S",
    resources=[truck],
    orders=[
        delivery("lyon", 4.85, 45.75, "2026-11-09 14:00", "2026-11-09 18:00"),
        delivery("marseille", 5.37, 43.30, "2026-11-10 10:00", "2026-11-10 14:00"),
        delivery("montpellier", 3.88, 43.61, "2026-11-10 15:00", "2026-11-10 19:00"),
        delivery("clermont", 3.09, 45.78, "2026-11-11 10:00", "2026-11-11 14:00"),
    ],
)


# --- guides/multi-day.mdx:276
from datetime import datetime
from zoneinfo import ZoneInfo

def local_day(text, tz):
    """Return the calendar day of an ISO 8601 time, in the zone of the plan."""
    return datetime.fromisoformat(text).astimezone(ZoneInfo(tz)).date()

def check_nights(tour, tz):
    """Return the nights where the vehicle doesn't rest."""
    problems = []
    previous, rested = None, False
    for point in tour["wayPoints"]:
        if point["type"] == "break":
            if point["fromPrevious"]["travelDuration"] != "PT0S":
                problems.append(f"the break at {point['arrivalTime']} comes after a drive")
            if local_day(point["departureTime"], tz) > local_day(point["arrivalTime"], tz):
                rested = True
            continue
        day = local_day(point.get("arrivalTime") or point["departureTime"], tz)
        if previous and day > previous and not rested:
            problems.append(f"no rest between the stop reached on {previous} and the one reached on {day}")
        previous, rested = day, False
    return problems
