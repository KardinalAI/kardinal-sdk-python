# kardinal

Python SDK for the Kardinal route-optimization API: submit a plan, follow
its optimization, retrieve the solution, update it to re-optimize.

```bash
pip install kardinal-ai          # library only
pip install "kardinal-ai[cli]"   # + the `kardinal` command
```

The package is published as `kardinal-ai`, but you import it as `kardinal`
(`from kardinal import Kardinal`) and the command is `kardinal`. Python 3.10
or later.

API documentation: https://developers.kardinal.ai

## Quickstart

```python
from kardinal import Kardinal
from kardinal.routing import examples

k = Kardinal()                                             # KARDINAL_API_KEY
plan = k.routing.plans.submit(examples.small_delivery_plan())
solution = k.routing.solutions.wait(plan.id)                # returns in ~20s
```

`wait`, not `get`, on purpose: the API is asynchronous. Right after `submit`,
`get` raises `KardinalNotFoundError` (404) while the plan is still waiting
or being processed, then returns whatever the engine has found so far,
which can be empty or incomplete until the optimization is over. `wait`
returns once it is.

## API reference

All methods hang off the client: `k = Kardinal()`.

| Method | HTTP call | What it does |
|---|---|---|
| `k.routing.plans.submit(plan)` | `POST /plans` | Creates a plan from a `PlanCreate` (no `id`: the server assigns it) and starts its optimization. Consumes credits. Returns the `Plan`, with `.warnings`. |
| `k.routing.plans.get(plan_id)` | `GET /plans/{id}` | Returns the plan as currently stored. |
| `k.routing.plans.update(plan, force=False)` | `PUT /plans/{id}` | Replaces the whole plan (anything left out is removed). The version increments, and the plan is re-optimized, only if the plan actually changed; an identical update is a free no-op. `force=True` unarchives an archived plan first. |
| `k.routing.plans.delete(plan_id)` | `DELETE /plans/{id}` | Permanently deletes the plan and its solution; any optimization in progress is stopped. |
| `k.routing.plans.list(page=1, items_per_page=20, archived="excluded")` | `GET /plans` | Returns one `Page` of plans, in their light form (`PlanLight`). |
| `k.routing.plans.iter_all(archived="excluded")` | `GET /plans`, every page | Iterates over every plan. |
| `k.routing.plans.start(plan_id, force=False)` | `PUT /plans/{id}/running` | Restarts the optimization of the current version, without changing its data or version. |
| `k.routing.plans.stop(plan_id, force=False)` | `PUT /plans/{id}/running` | Stops the optimization, without changing the plan's data or version. |
| `k.routing.plans.get_status(plan_id)` | `GET /plans/{id}/state` | Returns the plan's current `PlanState`: `waiting`, `processing`, `optimizing`, `optimized`, `stopped`, `interrupted`, ... |
| `k.routing.solutions.wait(plan_id, timeout=None)` | `GET /plans/{id}/state`, then `/solution` | Blocks until the current version stops optimizing, then returns its solution (see below). |
| `k.routing.solutions.get(plan_id)` | `GET /plans/{id}/solution` | Returns the current best solution right away, without waiting. |
| `k.routing.solutions.get_objectives(plan_id)` | `GET /plans/{id}/solution/objectives` | Returns only the value of each objective, without the tours. |

A `Page` has `items`, `page`, `total_pages`, `total`, `next_page` (`None`
on the last page), `previous_page` (`None` on the first page) and
`items_per_page`. Asking for a page past the last one returns the last page:
`.page` gives the page actually returned.

### How `wait()` works

- It polls `get_status()` every 10 seconds at first, stretching to every 60
  seconds on long optimizations, and fetches the solution only once the plan
  is done. It never sleeps through the whole `maxOptimizationDuration`: the
  engine stops on its own once it stops finding improvements.
- The returned solution's `final_state` tells how the optimization ended:
  `optimized`, or `interrupted` / `stopped` when it was cut short (stopped,
  replaced by a newer version, or given up by the engine). Check it before
  treating the result as final.
- It raises `KardinalOptimizationError` when it has no solution to return:
  `NO_SOLUTION` (the plan ended without one for this version),
  `PLAN_SUPERSEDED` (a newer version was pushed meanwhile), or
  `OPTIMIZATION_STALLED` (still optimizing 5 minutes past its
  `maxOptimizationDuration`: the engine most likely crashed). A plan deleted
  while waiting raises `KardinalNotFoundError`.
- `timeout` (seconds) is a hard limit that raises `KardinalTimeoutError`,
  after checking the state one last time.
- It's meant for scripts and notebooks. A server tracking many plans should
  schedule its own `get_status()` calls instead of blocking, and like any
  manual tracking, **poll no more than once every 10 seconds per plan**.

## Configuration

`Kardinal(api_key=None, *, base_url=None, timeout=30, max_retries=3)`

| | argument | env var | default |
|---|---|---|---|
| `api_key` | `Kardinal(api_key="<your API key>")` | `KARDINAL_API_KEY` | *(required: raises `MissingApiKeyError` if none is found)* |
| `base_url` | `Kardinal(base_url="https://...")` | `KARDINAL_BASE_URL` | `https://app.kardinal.ai/api/v2` |

The argument wins over the environment variable, which wins over the
default. `api_key=""` raises `EmptyApiKeyError` rather than silently falling
back to the environment variable.

Sandbox and production share the same host: the API key you use determines
which of your agencies a call applies to.

`timeout` (seconds) is passed to `httpx` as each request's timeout.
`max_retries` is how many times a read, `update()`, `delete()`, `start()` or
`stop()` is retried after a network error, a `429` or a `5xx`; `submit()` is
never retried (see "Good to know" below).

The client can be used as a context manager (`with Kardinal() as k:`), or
closed with `k.close()`.

## Full walkthrough

```python
from datetime import datetime, timedelta, timezone

from kardinal import Kardinal
from kardinal.routing.plans import PlanCreate, Order
from kardinal.routing import models
from kardinal import KardinalValidationError, KardinalNotFoundError

k = Kardinal(timeout=30, max_retries=3)

# A resource's workingTimeWindow in the past isn't a meaningful plan to
# optimize — computing "tomorrow" here keeps this example runnable as-is,
# rather than pinning a calendar date that goes stale.
tomorrow = (datetime.now(timezone.utc) + timedelta(days=1)).replace(
    hour=8, minute=0, second=0, microsecond=0
)

plan_input = PlanCreate(
    tz="Europe/Paris",
    maxOptimizationDuration="PT5M",
    resources=[
        models.Resource(
            id="truck-1",
            vehicleProfile=models.VehicleProfileCar(type="car"),
            workingTimeWindow=models.TimeWindow(
                begin=tomorrow.isoformat(), end=tomorrow.replace(hour=18).isoformat()
            ),
        )
    ],
    orders=[
        Order(
            id="order-1",
            stops=[
                models.SingleStop(
                    type="single",
                    id="stop-1",
                    position=models.Position(lat=48.8566, lon=2.3522),
                )
            ],
        )
    ],
)

try:
    plan = k.routing.plans.submit(plan_input)      # the server assigns `id`
except KardinalValidationError as e:
    print(e.code)                                  # INVALID_VALUE, ID_NOT_UNIQUE, ...
    print(e.errors)                                # every error, not just the first
    raise

solution = k.routing.solutions.wait(plan.id)       # blocks until it's done
print(solution.final_state)        # optimized, or interrupted/stopped if cut short
for tour in solution.tours or []:   # tours is None when no stop could be planned
    print(tour.resourceId, len(tour.wayPoints))

# manual tracking instead of a blocking wait, what a server tracking many
# plans should do (no more than one call every 10 seconds per plan)
objectives = k.routing.solutions.get_objectives(plan.id)   # objective values only
status = k.routing.plans.get_status(plan.id)

# re-optimize: same id; the version increments only if the plan changed
# (an identical update is a free no-op)
plan.orders.append(
    Order(id="order-2", stops=[models.SingleStop(type="single", id="stop-2",
        position=models.Position(lat=48.86, lon=2.35))])
)
plan = k.routing.plans.update(plan)
```

A plan has no top-level list of stops: stops live inside `Order.stops[]`,
and `Plan.orders[]` is the list of orders. An `Order` groups one or more
stops that must be planned onto the same resource (for example a pickup and
its delivery).

## Errors

```
KardinalError
├── KardinalAuthError           NOT_AUTHENTICATED (401): missing, invalid or expired key
├── KardinalLimitError          any 403 (NOT_ALLOWED): plan-size limit, optimization quota,
│                               or insufficient credits
├── KardinalValidationError     the 7 codes under 400, with the full error list
├── KardinalNotFoundError       NOT_FOUND: raised on every 404, including reads
├── KardinalRateLimitError      429: temporary overload, retry after a pause
├── KardinalServerError         INTERNAL_SERVER_ERROR, or any other 5xx
├── KardinalTimeoutError        solutions.wait()'s hard `timeout` elapsed
├── KardinalOptimizationError   solutions.wait() has no solution to return: NO_SOLUTION,
│                               PLAN_SUPERSEDED, OPTIMIZATION_STALLED (engine crashed)
└── KardinalConnectionError     DNS/connection/read failure, no HTTP response at all
```

All of them are importable from `kardinal` itself
(`from kardinal import KardinalNotFoundError`), as are `MissingApiKeyError`
and `EmptyApiKeyError` (both `KardinalError`s, raised by `Kardinal()`
without a usable key) and `Page`, the type `plans.list()` returns.

Every exception carries `.code`, `.status`, `.request_id`, `.retryable`,
`.warnings`, `.errors` and `.details`. `.errors` is every error object of
the response; `.details` is the `properties.details` of the error `.code`
came from, the only way to tell apart errors that share a code.

`KardinalLimitError` is what every 403 becomes: for a builder account, a
403 always means a limit was hit, never a permission refusal. `.details`
says which one. For a plan-size limit (too many resources, orders or
stops, or more than 4 stops in an order without `successiveStops`),
`.errors` also holds one `INVALID_VALUE` entry per exceeded limit, whose
`properties.path` and `properties.details` name the field and the allowed
value: shrink the plan. For the daily/monthly quota, wait or ask for a
higher one; for credits, top them up.

```python
from kardinal import KardinalLimitError

try:
    plan = k.routing.plans.submit(plan_input)
except KardinalLimitError as e:
    print(e.details)   # which limit was hit
    print(e.errors)    # for a plan-size limit, the field and the allowed value
```

`KardinalRateLimitError` (429) signals a temporary overload, not a quota: it
comes with an empty body and no `Retry-After` header. Reads, `update()`,
`delete()`, `start()`, `stop()` and `wait()` retry it automatically;
`submit()` doesn't, so retry it yourself after a pause.

`.retryable` is computed by the SDK and means "retrying is safe and may
succeed": true for a `429`, and for a `5xx` or a connection error, except
when a `submit()` may have reached the server (the plan may then already
exist: check with `list()` before submitting again). An unrecognized `code`
falls back to the family matching the HTTP status rather than disappearing,
since the API may add new codes in a non-breaking release. `.warnings` is
usually empty: it's populated when a rejected payload had already been
amended (a value clamped, crow-fly distances forced, ...) before the error
that rejected it was found.

## Warnings

When the API accepts a plan but amends part of it, `submit()` and
`update()` return the amendments in `.warnings`:

```python
plan = k.routing.plans.submit(plan_input)
for warning in plan.warnings:
    print(warning.code, warning.properties)   # e.g. maxOptimizationDuration clamped
```

Read them from that return value: warnings aren't stored with the plan, so
a later `get()` never returns them, only the amended value.

## The CLI

```
kardinal auth check                    confirms the API key works, and shows its host and agency
kardinal version

kardinal routing plans submit <file> | get <id> | update <file> | delete <id>
kardinal routing plans list | start <id> | stop <id> | status <id>
kardinal routing plans validate <file> local only, no API call, no credits
kardinal routing solutions get <id> | objectives <id> | wait <id>

kardinal routing demo                  submits the example plan, waits for it
kardinal init                          writes .kardinal/SKILL.md, a pointer to this SDK for AI coding assistants
```

JSON output when stdout isn't a terminal, or with `--json`; a readable table
otherwise. Error output is always JSON, regardless of `--json` or the
terminal, since it's the one output shape a caller is most likely to parse
programmatically. Exit codes: `0` success, `1` business error, `2` usage
error. The CLI reads the same `KARDINAL_API_KEY` / `KARDINAL_BASE_URL` as
`Kardinal()` (see Configuration above), with no `--api-key` flag, so a key
never lands in shell history or the process list.

## Good to know

- **`submit()` is never retried automatically**, not even after a network
  error or a `5xx`: the API has no idempotency key, so a retry could create
  the plan twice. Reads, `update()`, `delete()`, `start()` and `stop()` are
  retried. Replaying the same `update()` is harmless: an identical update
  keeps the same version and isn't billed.
- **`maxOptimizationDuration` is capped by your agency.** A value above the
  cap is clamped to it, and `submit()`/`update()` report it in `.warnings`.
  By default: 5 seconds in the sandbox (also the default when omitted); in
  production, 15 minutes when omitted and 6 hours at most. The engine stops
  earlier on its own once it stops finding improvements.
- **In the sandbox, distances are crow-fly**: road routing is replaced, and
  each resource's `vehicleProfile` gets a warning saying so.
- **The SDK identifies itself** in two headers on every request:
  `User-Agent` (SDK version, Python version, OS and architecture, and the
  `httpx` version, plus `cli` for calls made by the `kardinal` command) and
  `X-Kardinal-Client` (SDK version). Nothing personal: no hostname, user or
  key.
- **`.request_id` is usually `None`**: it's only set when the server happens
  to send an `X-Request-Id` response header.
- **`get_status()` returns a `PlanState`** (a single value), not the
  detailed `PlanStatus` object embedded in `Plan.status`.
- **`get_objectives()` returns a plain `list`** of `SolutionObjective`,
  with a `.warnings` attribute attached.
- **`start()` / `stop()` return an `EnvelopedPlanReference`** (`agencyId`,
  `planId`, `planVersion`, `warnings`): the plan's current version, which
  starting or stopping doesn't change.

## License

MIT.
