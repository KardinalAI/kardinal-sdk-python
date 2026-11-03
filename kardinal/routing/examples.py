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
            capacities={"packages": 20},
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
                    capacities={"packages": 1},
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


def _tomorrow_at(hhmm: str, days: int = 0) -> str:
    # The payloads write local wall-clock times, "YYYY-MM-DD HH:MM", read in
    # the plan's `tz`; `days` moves past tomorrow, for a later day.
    day = datetime.now(_DEMO_UTC_OFFSET) + timedelta(days=1 + days)
    return f"{day:%Y-%m-%d} {hhmm}"


def cold_chain_plan() -> PlanCreate:
    """The plan of the cold-chain last-mile case study, built field by field:
    https://developers.kardinal.ai/case-studies/cold-chain-last-mile

    One bi-temperature truck driver plus two extra drivers deliver ambient,
    chilled and frozen goods in Paris, from one depot. Dates move to tomorrow.

    Submitting it as is:

    - with a production key costs one credit per stop, so 15 credits here;
    - leaves `maxOptimizationDuration` unset, so production optimizes for up
      to 15 minutes and stops earlier once the result stops improving;
    - in the sandbox is free, and the answer carries warnings that traffic
      is ignored and that routes are computed as the crow flies.
    """
    depot = models.Position(lon=2.295, lat=48.872)
    # Driver tags: `driver` counts toward the one-driver-per-key-set limit,
    # `bi-temperature` selects the ambient/frozen compartment constraint.
    driver_tags = ["driver", "bi-temperature"]

    resources = [
        # Truck with a worked-hours cost, a break rule and a preferred sector.
        models.Resource(
            id="truck-1",
            vehicleProfile=models.VehicleProfileTruck(type="truck", withTraffic=True),
            workingTimeWindow=models.TimeWindow(
                begin=_tomorrow_at("05:00"), end=_tomorrow_at("20:00")
            ),
            departure=depot,
            arrival=depot,
            capacities={"weight": 1200, "pallets": 12, "ambiant": 400, "frozen": 250},
            preferredStopTags=["zone:usual-sector-7"],
            tags=driver_tags,
            breaks=[
                models.WorkingDurationSlidingBreak(
                    type="workingDurationSlidingBreak",
                    minBreakDuration="PT30M",
                    maxInterBreakDuration="PT6H",
                )
            ],
            maxWorkingDuration="PT9H",
            cost=models.Cost(
                workedHours=models.CostFloorsAndCoeffs(
                    costFloor=8, costCoeff=1, overcostFloor=10, overcostCoeff=1.25
                )
            ),
        ),
        # Two drivers with the two compartments only, on a shorter day.
        *[
            models.Resource(
                id=f"driver-{i}",
                vehicleProfile=models.VehicleProfileTruck(type="truck"),
                workingTimeWindow=models.TimeWindow(
                    begin=_tomorrow_at("07:00"), end=_tomorrow_at("17:00")
                ),
                departure=depot,
                arrival=depot,
                capacities={"ambiant": 400, "frozen": 250},
                tags=driver_tags,
            )
            for i in (1, 2)
        ],
    ]

    def pickup(id: str, capacities: dict[str, float]) -> models.SingleStop:
        # Every temperature-controlled or pallet delivery starts at the depot.
        return models.SingleStop(
            type="single",
            id=id,
            position=depot,
            kind=models.StopKind.pickup,
            operationDuration="PT5M",
            capacities=capacities,
        )

    # Compartments: each temperature class loads its own capacity, in the
    # pickup and the delivery alike.
    orders = [
        Order(
            id=f"order-{name}",
            stops=[
                pickup(f"stop-pickup-{name}", {capacity: quantity}),
                models.SingleStop(
                    type="single",
                    id=f"stop-{name}",
                    position=models.Position(lon=lon, lat=lat),
                    kind=models.StopKind.delivery,
                    operationDuration="PT6M",
                    capacities={capacity: quantity},
                ),
            ],
        )
        for name, capacity, quantity, lon, lat in [
            ("ambient", "ambiant", 40, 2.31, 48.882),
            ("chilled", "frozen", 30, 2.275, 48.88),
            ("frozen", "frozen", 20, 2.305, 48.854),
        ]
    ]

    # Afternoon pallets: the first one has a window and a preferred slot, in
    # the truck's preferred sector; the third is outside it, in an overflow zone.
    for i, (lon, lat, zone) in enumerate(
        [
            (2.32, 48.867, "zone:usual-sector-7"),
            (2.265, 48.887, "zone:usual-sector-7"),
            (2.3, 48.894, "zone:overflow"),
        ]
    ):
        stop = models.SingleStop(
            type="single",
            id=f"stop-afternoon-{i}",
            position=models.Position(lon=lon, lat=lat),
            kind=models.StopKind.delivery,
            operationDuration="PT8M",
            capacities={"pallets": 1},
            tags=[zone],
        )
        if i == 0:
            stop.authorizedTimeWindows = [
                models.TaggedTimeWindow(begin=_tomorrow_at("08:00"), end=_tomorrow_at("18:00"))
            ]
            stop.preferredTimeWindows = [
                models.TaggedTimeWindow(begin=_tomorrow_at("14:00"), end=_tomorrow_at("16:00"))
            ]
        orders.append(
            Order(
                id=f"order-afternoon-{i}",
                stops=[pickup(f"stop-pickup-afternoon-{i}", {"pallets": 1}), stop],
            )
        )

    # Keychain: three early deliveries share one set of keys, which only one
    # driver may hold (see the global constraint below).
    for i, (lon, lat) in enumerate([(2.31, 48.882), (2.275, 48.88), (2.305, 48.854)]):
        orders.append(
            Order(
                id=f"order-keychain-{i}",
                stops=[
                    models.SingleStop(
                        type="single",
                        id=f"stop-keychain-{i}",
                        position=models.Position(lon=lon, lat=lat),
                        kind=models.StopKind.delivery,
                        operationDuration="PT5M",
                        tags=["keychain:trusted-set-1"],
                        authorizedTimeWindows=[
                            models.TaggedTimeWindow(
                                begin=_tomorrow_at("06:30"), end=_tomorrow_at("08:00")
                            )
                        ],
                    )
                ],
            )
        )

    return PlanCreate(
        tz="Europe/Paris",
        resources=resources,
        orders=orders,
        objectives=[
            models.ObjectivesEnum.maximizeMandatoryStops,
            models.ObjectivesEnum.minimizeResources,
            models.ObjectivesEnum.minimizeLargestTourDuration,
            models.ObjectivesEnum.minimizeCosts,
            models.ObjectivesEnum.maximizePreferredStops,
            models.ObjectivesEnum.minimizeDelay,
            models.ObjectivesEnum.minimizeWorkingDuration,
            models.ObjectivesEnum.minimizeDistance,
        ],
        additionalConstraints=[
            # A bi-temperature vehicle carries ambient or frozen goods at a
            # time, never both: one of the two loads must be 0.
            models.AdditionalConstraintAtLeastOneValidCapacity(
                type="atLeastOneValidCapacity",
                capacities={"frozen": 0, "ambiant": 0},
                name="bi-temperature-single-mode-at-a-time",
                resourceTags=["bi-temperature"],
            )
        ],
        globalConstraints=[
            # One driver per key set: each driver is charged for the keychain
            # stops it serves, and the cap keeps that to one driver.
            models.GlobalConstraintMaxCumulatedCost(
                type=models.Type2.maxCumulatedCost,
                maximum=1,
                costsByResourceTag={
                    "driver": models.Cost(
                        costsByStopTag={
                            "keychain:trusted-set-1": models.CostFloorsAndCoeffs(
                                costFloor=0, costCoeff=1, overcostFloor=1, overcostCoeff=0
                            )
                        }
                    )
                },
                name="one-driver-per-key-set",
            )
        ],
    )
