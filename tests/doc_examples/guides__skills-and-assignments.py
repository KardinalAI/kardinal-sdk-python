# Copied from guides/skills-and-assignments.mdx by scripts/sync_doc_examples.py: do not edit by hand.

# --- guides/skills-and-assignments.mdx:175
from kardinal.routing import models
from kardinal.routing.plans import Order, PlanCreate


def technician(id: str, lon: float, skills: list[str]) -> models.Resource:
    home = models.Position(lon=lon, lat=48.85)
    return models.Resource(
        id=id,
        vehicleProfile=models.VehicleProfileCar(type="car"),
        workingTimeWindow=models.TimeWindow(begin="2026-11-02 08:00", end="2026-11-02 18:00"),
        departure=home,
        arrival=home,
        skills=skills,
    )


def job(id: str, lon: float, lat: float, required_skills: list[str]) -> Order:
    stop = models.SingleStop(
        type="single",
        id=f"stop-{id}",
        kind="delivery",
        position=models.Position(lon=lon, lat=lat),
        operationDuration="PT30M",
    )
    return Order(id=f"order-{id}", stops=[stop], requiredSkills=required_skills)


plan = PlanCreate(
    tz="Europe/Paris",
    maxOptimizationDuration="PT5S",
    resources=[technician("tech-certified", 2.40, ["gas-certified"]), technician("tech-plain", 2.30, [])],
    orders=[
        job("boiler", 2.303, 48.85, ["gas-certified"]),
        job("meter", 2.403, 48.85, []),
        job("panel", 2.353, 48.86, ["electrical-certified"]),
    ],
)


# --- guides/skills-and-assignments.mdx:293
for stop_id in solution.unaffectedStopIds or []:
    print(stop_id, "was not planned")

for tour in solution.tours:
    resource_id = tour.resourceId
    print(resource_id, "valid" if tour.isValid else "NOT VALID")
    for violation in tour.violations or []:
        if violation.type == "skills":
            print(" ", resource_id, "lacks", violation.lackingSkills)
        elif violation.type == "forbiddenAssignment":
            print(" ", resource_id, "is barred by a forbiddenAssignment")
