import logging
import os
import subprocess
import sys
import textwrap

import httpx
import pytest
import respx

from kardinal._core.transport import DEFAULT_BASE_URL, Transport
from kardinal.routing.plans import PlanCreate, PlansAPI

_PLAN_ID = "4cbd0ab8-282c-4b30-b981-29e1ed8a2016"
_CROW = "The crowfly mode is forced for agency A_sandbox"


def _warning(path=None, details=None, message="The field value is not valid."):
    properties = {}
    if path is not None:
        properties["path"] = path
    if details is not None:
        properties["details"] = details
    warning = {"code": "INVALID_VALUE", "message": message}
    if properties:
        warning["properties"] = properties
    return warning


def _crow(n):
    return [_warning(f"resources.{i}.vehicleProfile", _CROW) for i in range(n)]


_CLAMP = _warning("maxOptimizationDuration", "The value is clamped to 5 seconds")


def _plans() -> PlansAPI:
    return PlansAPI(Transport(api_key="test-key"))


def _mock(method, url, warnings, status=200):
    respx.route(method=method, url=url).mock(
        return_value=httpx.Response(
            status, json={"item": {"id": _PLAN_ID, "resources": []}, "warnings": warnings}
        )
    )


def _records(caplog):
    return [r for r in caplog.records if r.name == "kardinal"]


@respx.mock
def test_submit_logs_one_line_per_kind_of_warning(caplog) -> None:
    warnings = _crow(3) + [_CLAMP]
    _mock("POST", f"{DEFAULT_BASE_URL}/plans", warnings, 201)
    with caplog.at_level(logging.WARNING, logger="kardinal"):
        plan = _plans().submit(PlanCreate(resources=[]))
    records = _records(caplog)
    assert [r.levelno for r in records] == [logging.WARNING, logging.WARNING]
    assert records[0].getMessage() == (
        f"Kardinal API warning INVALID_VALUE: {_CROW} "
        "(resources.0.vehicleProfile, resources.1.vehicleProfile, resources.2.vehicleProfile)"
    )
    assert records[1].getMessage() == (
        "Kardinal API warning INVALID_VALUE: The value is clamped to 5 seconds "
        "(maxOptimizationDuration)"
    )
    assert len(plan.warnings) == 4


@respx.mock
def test_more_than_three_paths_are_summed_up(caplog) -> None:
    _mock("POST", f"{DEFAULT_BASE_URL}/plans", _crow(5), 201)
    with caplog.at_level(logging.WARNING, logger="kardinal"):
        _plans().submit(PlanCreate(resources=[]))
    assert _records(caplog)[0].getMessage().endswith(
        "(resources.0.vehicleProfile, resources.1.vehicleProfile, "
        "resources.2.vehicleProfile, and 2 more)"
    )


@respx.mock
def test_a_warning_without_details_uses_its_message_and_without_path_lists_none(caplog) -> None:
    _mock("POST", f"{DEFAULT_BASE_URL}/plans", [_warning(message="Something was amended")], 201)
    with caplog.at_level(logging.WARNING, logger="kardinal"):
        _plans().submit(PlanCreate(resources=[]))
    assert [r.getMessage() for r in _records(caplog)] == [
        "Kardinal API warning INVALID_VALUE: Something was amended"
    ]


@respx.mock
@pytest.mark.parametrize("call", ["update", "replace"])
def test_update_and_replace_log_the_same_way(caplog, call) -> None:
    _mock("PUT", f"{DEFAULT_BASE_URL}/plans/{_PLAN_ID}", _crow(2))
    plans = _plans()
    with caplog.at_level(logging.WARNING, logger="kardinal"):
        if call == "update":
            plans.update(_fetched(plans))
        else:
            plans.replace(_PLAN_ID, PlanCreate(resources=[]))
    assert len(_records(caplog)) == 1


class _RaisingHandler(logging.Handler):
    def emit(self, record):
        raise RuntimeError("handler broke")


class _RaisingFilter(logging.Filter):
    def filter(self, record):
        raise RuntimeError("filter broke")


@respx.mock
@pytest.mark.parametrize("broken", [_RaisingHandler(), _RaisingFilter()], ids=["handler", "filter"])
def test_a_failing_log_handler_or_filter_does_not_make_submit_fail(broken, capsys) -> None:
    _mock("POST", f"{DEFAULT_BASE_URL}/plans", _crow(1), 201)
    logger = logging.getLogger("kardinal")
    logger.addHandler(broken) if isinstance(broken, logging.Handler) else logger.addFilter(broken)
    try:
        plan = _plans().submit(PlanCreate(resources=[]))
    finally:
        logger.removeHandler(broken) if isinstance(broken, logging.Handler) else logger.removeFilter(broken)
    assert plan.id == _PLAN_ID
    assert "logging the API warning failed" in capsys.readouterr().err


@respx.mock
def test_an_empty_path_is_not_listed(caplog) -> None:
    _mock("POST", f"{DEFAULT_BASE_URL}/plans", [_warning(path="", details="Amended")], 201)
    with caplog.at_level(logging.WARNING, logger="kardinal"):
        _plans().submit(PlanCreate(resources=[]))
    assert [r.getMessage() for r in _records(caplog)] == ["Kardinal API warning INVALID_VALUE: Amended"]


def _fetched(plans):
    respx.get(f"{DEFAULT_BASE_URL}/plans/{_PLAN_ID}").mock(
        return_value=httpx.Response(200, json={"item": {"id": _PLAN_ID, "resources": []}})
    )
    return plans.get(_PLAN_ID)


@respx.mock
def test_get_and_a_response_without_warnings_log_nothing(caplog) -> None:
    _mock("GET", f"{DEFAULT_BASE_URL}/plans/{_PLAN_ID}", _crow(2))
    _mock("POST", f"{DEFAULT_BASE_URL}/plans", [], 201)
    plans = _plans()
    with caplog.at_level(logging.WARNING, logger="kardinal"):
        plans.get(_PLAN_ID)
        plans.submit(PlanCreate(resources=[]))
    assert _records(caplog) == []


_SCRIPT = textwrap.dedent(
    """
    import logging.config
    import httpx, respx
    import kardinal
    import kardinal.routing.plans
    {configure}
    from kardinal import Kardinal
    from kardinal.routing.plans import PlanCreate

    with respx.mock:
        respx.post("https://app.kardinal.ai/api/v2/plans").mock(
            return_value=httpx.Response(201, json={
                "item": {"id": "p1", "resources": []},
                "warnings": [{"code": "INVALID_VALUE", "message": "m",
                              "properties": {"path": "a.b", "details": "Crow-fly forced"}}],
            })
        )
        Kardinal(api_key="test-key").routing.plans.submit(PlanCreate(resources=[]))
    """
)


def _run(configure: str) -> str:
    # The child must import this worktree's code, not an installed copy.
    env = dict(os.environ, PYTHONPATH=os.pathsep.join(sys.path))
    result = subprocess.run(
        [sys.executable, "-c", _SCRIPT.replace("{configure}", configure)],
        env=env, capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, result.stderr
    return result.stderr


def test_the_line_reaches_stderr_when_the_application_configures_no_logging() -> None:
    assert "Kardinal API warning INVALID_VALUE: Crow-fly forced (a.b)" in _run("")


def test_the_line_survives_a_dictconfig_called_after_the_import() -> None:
    err = _run('logging.config.dictConfig({"version": 1})')
    assert "Kardinal API warning INVALID_VALUE: Crow-fly forced (a.b)" in err
