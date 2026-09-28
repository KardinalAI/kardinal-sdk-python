"""Root CLI: `version`, `auth check`, `init`, and the `routing` subcommands."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version as _package_version
from pathlib import Path

import typer

from ._core.cli import emit, fail
from ._core.errors import KardinalError
from .routing.cli import routing

app = typer.Typer(help="Kardinal CLI.", no_args_is_help=True)
app.add_typer(routing, name="routing")


@app.command("version")
def version() -> None:
    """Package version and the API version it targets."""
    try:
        package_version = _package_version("kardinal-ai")
    except PackageNotFoundError:
        package_version = "unknown (not installed as a package)"
    typer.echo(f"kardinal {package_version} (API v2)")


auth_app = typer.Typer(help="Diagnose the configured API key.")
app.add_typer(auth_app, name="auth")


@auth_app.command("check")
def auth_check(json_out: bool = typer.Option(False, "--json")) -> None:
    """The first thing to run when nothing else works: confirms the API key
    works, and reports the host it was checked against and the agency
    (sandbox or production) it resolves to.
    """
    from kardinal import Kardinal

    try:
        with Kardinal() as client:
            response = client._transport.request(
                "GET", "/plans", params={"page": 1, "itemsPerPage": 1, "archived": "excluded"}
            )
            base_url = client._transport.base_url
    except KardinalError as exc:
        fail(exc)
    emit(
        {
            "valid": True,
            "baseUrl": base_url,
            "agencyId": response.get("agencyId"),
        },
        force_json=json_out,
    )


@app.command("init")
def init() -> None:
    """Drop a short pointer file into the current project, so an AI coding
    assistant working in this repo knows this SDK is available.
    """
    target = Path(".kardinal/SKILL.md")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        "# Kardinal SDK\n\n"
        "This project uses the `kardinal` Python SDK for route optimization.\n\n"
        "```python\n"
        "from kardinal import Kardinal\n"
        "from kardinal.routing import examples\n\n"
        "k = Kardinal()  # reads KARDINAL_API_KEY\n"
        "plan = k.routing.plans.submit(examples.small_delivery_plan())\n"
        "solution = k.routing.solutions.wait(plan.id)\n"
        "```\n\n"
        "Documentation: https://pypi.org/project/kardinal-ai/ "
        "(or run `kardinal --help`).\n"
    )
    typer.echo(f"Wrote {target}")
