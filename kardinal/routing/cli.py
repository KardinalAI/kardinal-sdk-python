"""`kardinal routing ...` subcommands: a word-for-word projection of the SDK
surface (`k.routing.plans.submit` -> `kardinal routing plans submit`), plus
`validate` and `demo`, which aren't.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal, Optional

import typer
from pydantic import ValidationError

from .._core.cli import Exit, cli_client, emit, fail
from .._core.errors import KardinalError

routing = typer.Typer(help="Route optimization.")
plans = typer.Typer(help="Submit, retrieve, and update plans.")
solutions = typer.Typer(help="Retrieve a solution and its objectives.")
routing.add_typer(plans, name="plans")
routing.add_typer(solutions, name="solutions")


def _client():
    # cli_client() imports the client lazily, so `--help` answers without
    # loading the models or opening a connection. Used as a context manager
    # at every call site below so the CLI process doesn't leak the
    # underlying httpx connection pool past the command's lifetime.
    return cli_client()


@plans.command("submit")
def plans_submit(
    file: Path = typer.Argument(..., exists=True, help="JSON file with the plan."),
    json_out: bool = typer.Option(False, "--json", help="Force JSON output."),
) -> None:
    """Submit a new plan and start optimization. Billed in full."""
    from .plans import PlanCreate

    try:
        plan = PlanCreate.model_validate_json(file.read_text())
        with _client() as client:
            created = client.routing.plans.submit(plan)
    except ValidationError as exc:
        emit(
            [
                {"field": ".".join(map(str, e["loc"])), "error": e["msg"]}
                for e in exc.errors()
            ],
            force_json=True,
        )
        raise typer.Exit(Exit.BUSINESS_ERROR)
    except KardinalError as exc:
        fail(exc)
    emit(created, force_json=json_out)


@plans.command("get")
def plans_get(plan_id: str, json_out: bool = typer.Option(False, "--json")) -> None:
    """Retrieve a plan by id."""
    try:
        with _client() as client:
            plan = client.routing.plans.get(plan_id)
    except KardinalError as exc:
        fail(exc)
    emit(plan, force_json=json_out)


@plans.command("update")
def plans_update(
    file: Path = typer.Argument(
        ..., exists=True, help="JSON file with the full plan, including its id."
    ),
    force: bool = typer.Option(False, "--force", help="Unarchive the plan first, if archived."),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Update a plan. Re-optimizes if needed; only new unique stops are billed."""
    from .plans import Plan

    try:
        plan = Plan.model_validate_json(file.read_text())
        with _client() as client:
            updated = client.routing.plans.update(plan, force=force)
    except ValidationError as exc:
        emit(
            [
                {"field": ".".join(map(str, e["loc"])), "error": e["msg"]}
                for e in exc.errors()
            ],
            force_json=True,
        )
        raise typer.Exit(Exit.BUSINESS_ERROR)
    except KardinalError as exc:
        fail(exc)
    emit(updated, force_json=json_out)


@plans.command("delete")
def plans_delete(plan_id: str) -> None:
    """Delete a plan."""
    try:
        with _client() as client:
            client.routing.plans.delete(plan_id)
    except KardinalError as exc:
        fail(exc)
    typer.echo("OK")


@plans.command("list")
def plans_list(
    page: int = 1,
    items_per_page: int = 20,
    archived: Literal["excluded", "included", "only"] = "excluded",
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """List plans, one page at a time."""
    try:
        with _client() as client:
            result = client.routing.plans.list(
                page=page, items_per_page=items_per_page, archived=archived
            )
    except KardinalError as exc:
        fail(exc)
    emit(
        [item.model_dump(mode="json", exclude_none=True) for item in result.items],
        force_json=json_out,
    )


@plans.command("start")
def plans_start(
    plan_id: str,
    force: bool = typer.Option(False, "--force", help="Unarchive the plan first, if archived."),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Restart optimization on a stopped plan."""
    try:
        with _client() as client:
            reference = client.routing.plans.start(plan_id, force=force)
    except KardinalError as exc:
        fail(exc)
    emit(reference, force_json=json_out)


@plans.command("stop")
def plans_stop(
    plan_id: str,
    force: bool = typer.Option(False, "--force", help="Unarchive the plan first, if archived."),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Stop optimization on a plan without changing its data."""
    try:
        with _client() as client:
            reference = client.routing.plans.stop(plan_id, force=force)
    except KardinalError as exc:
        fail(exc)
    emit(reference, force_json=json_out)


@plans.command("status")
def plans_status(plan_id: str, json_out: bool = typer.Option(False, "--json")) -> None:
    """Show the plan's current optimization state."""
    try:
        with _client() as client:
            state = client.routing.plans.get_status(plan_id)
    except KardinalError as exc:
        fail(exc)
    # A state this SDK version doesn't know comes back as a plain string.
    emit({"state": getattr(state, "value", state)}, force_json=json_out)


@plans.command("validate")
def plans_validate(file: Path = typer.Argument(..., exists=True)) -> None:
    """Validate a plan locally. No API call, no credits consumed."""
    from .plans import PlanCreate

    try:
        PlanCreate.model_validate_json(file.read_text())
    except ValidationError as exc:
        emit(
            [
                {"field": ".".join(map(str, e["loc"])), "error": e["msg"]}
                for e in exc.errors()
            ],
            force_json=True,
        )
        raise typer.Exit(Exit.BUSINESS_ERROR)
    typer.echo("OK")


@solutions.command("get")
def solutions_get(plan_id: str, json_out: bool = typer.Option(False, "--json")) -> None:
    """Retrieve a plan's solution."""
    try:
        with _client() as client:
            solution = client.routing.solutions.get(plan_id)
    except KardinalError as exc:
        fail(exc)
    emit(solution, force_json=json_out)


@solutions.command("objectives")
def solutions_objectives(
    plan_id: str, json_out: bool = typer.Option(False, "--json")
) -> None:
    """Objective values only, without the full solution."""
    try:
        with _client() as client:
            objectives = client.routing.solutions.get_objectives(plan_id)
    except KardinalError as exc:
        fail(exc)
    emit(
        [o.model_dump(mode="json", exclude_none=True) for o in objectives],
        force_json=json_out,
    )


@solutions.command("wait")
def solutions_wait(
    plan_id: str,
    timeout: Optional[float] = typer.Option(None, help="Hard timeout, in seconds."),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Block until the plan finishes optimizing, then print its solution."""
    try:
        with _client() as client:
            solution = client.routing.solutions.wait(plan_id, timeout=timeout)
    except KardinalError as exc:
        fail(exc)
    emit(solution, force_json=json_out)


@routing.command("demo")
def routing_demo(json_out: bool = typer.Option(False, "--json")) -> None:
    """Submit the example plan and wait for its solution."""
    from . import examples

    try:
        with _client() as client:
            plan = client.routing.plans.submit(examples.small_delivery_plan())
            # Printed before wait(), not after, and to stderr so --json output
            # stays clean: submit() already billed this plan, so its id must
            # reach the user even if wait() itself times out or the
            # connection drops — every other command takes a plan id as
            # input, this is the only one that creates one and could
            # otherwise lose track of it.
            typer.echo(f"Submitted plan {plan.id}", err=True)
            solution = client.routing.solutions.wait(plan.id)
    except KardinalError as exc:
        fail(exc)
    emit(solution, force_json=json_out)
