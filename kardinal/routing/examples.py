"""Ready-to-submit example plans. Written by hand as code (not loaded from
a JSON fixture) so that reading the example is the first lesson in
modelling this API — a function, not a module constant, so every call
returns a fresh object the caller can modify freely.

Also the source for `kardinal routing demo` and the CI test that the README
quickstart runs end to end.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from . import models
from .plans import Order, PlanCreate

# Fixed +01:00, not zoneinfo.ZoneInfo("Europe/Paris"): the exact DST offset
# doesn't matter for a demo working window with hours of margin either way,
# and a fixed offset needs no system IANA tzdata (not guaranteed present,
# e.g. on a minimal container image) — pip install kardinal-ai stays at two
# dependencies either way.
_DEMO_UTC_OFFSET = timezone(timedelta(hours=1))

# Depot and eight delivery addresses around central Paris.
_DEPOT = models.Position(lat=48.8566, lon=2.3522)
_ADDRESSES = [
    models.Position(lat=48.8738, lon=2.2950),  # Arc de Triomphe
    models.Position(lat=48.8606, lon=2.3376),  # Louvre
    models.Position(lat=48.8462, lon=2.3372),  # Montparnasse
    models.Position(lat=48.8867, lon=2.3431),  # Montmartre
    models.Position(lat=48.8534, lon=2.3488),  # Notre-Dame
    models.Position(lat=48.8656, lon=2.3212),  # Champs-Élysées
    models.Position(lat=48.8417, lon=2.3324),  # Denfert-Rochereau
    models.Position(lat=48.8799, lon=2.3550),  # Gare du Nord
]


def _tomorrows_working_window() -> models.TimeWindow:
    # Computed fresh on every call, not a fixed calendar date: this example
    # is meant to stay submittable indefinitely (kardinal routing demo, the
    # CI quickstart test), and a resource whose workingTimeWindow is already
    # in the past is not a meaningful plan to optimize.
    tomorrow = (datetime.now(_DEMO_UTC_OFFSET) + timedelta(days=1)).replace(
        hour=8, minute=0, second=0, microsecond=0
    )
    return models.TimeWindow(
        begin=tomorrow.isoformat(), end=tomorrow.replace(hour=18).isoformat()
    )


def small_delivery_plan() -> PlanCreate:
    """Two resources, eight stops, a ten-second optimization budget — enough
    to pose a real routing decision, small enough to return quickly and cost
    only a few credits. Copy and adapt this rather than building a plan from
    scratch.
    """
    working_time_window = _tomorrows_working_window()
    resources = [
        models.Resource(
            id=f"truck-{i}",
            vehicleProfile=models.VehicleProfileCar(type="car"),
            departure=_DEPOT,
            workingTimeWindow=working_time_window,
            capacities=models.Capacities({"packages": 20}),
        )
        for i in range(1, 3)
    ]

    orders = [
        Order(
            id=f"order-{i}",
            stops=[
                models.SingleStop(
                    type="single",
                    id=f"stop-{i}",
                    position=position,
                    operationDuration="PT5M",
                    capacities=models.Capacities({"packages": 1}),
                )
            ],
        )
        for i, position in enumerate(_ADDRESSES, start=1)
    ]

    return PlanCreate(
        tz="Europe/Paris",
        maxOptimizationDuration="PT10S",
        resources=resources,
        orders=orders,
    )
