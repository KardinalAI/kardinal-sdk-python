import json
import subprocess
import sys
from importlib.metadata import PackageNotFoundError, version

import httpx
import respx
from typer.testing import CliRunner

from kardinal._core.transport import DEFAULT_BASE_URL
from kardinal.cli import app
from kardinal.routing.examples import small_delivery_plan
from kardinal.routing.plans import Plan

runner = CliRunner()
_PLAN_ID = "4cbd0ab8-282c-4b30-b981-29e1ed8a2016"


def test_help_does_not_load_models_or_open_a_connection() -> None:
    """Imports live inside command functions so `--help` answers without
    loading the models or opening a connection. Run in a subprocess since
    the models module may already be cached in this process's sys.modules
    from an earlier test.
    """
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys, kardinal.cli; "
            "assert 'kardinal.routing.models' not in sys.modules",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_version() -> None:
    """The version is read from the installed distribution, `kardinal-ai`
    (PyPI refuses `kardinal`) — not from the `kardinal` import name.
    """
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert result.stdout == f"kardinal {version('kardinal-ai')} (API v2)\n"


def test_validate_rejects_malformed_plan(tmp_path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text('{"resources": [{"id": "r1"}]}')
    result = runner.invoke(app, ["routing", "plans", "validate", str(bad)])
    assert result.exit_code == 1
    assert "vehicleProfile" in result.stdout


def test_validate_accepts_example_plan(tmp_path) -> None:
    good = tmp_path / "good.json"
    good.write_text(small_delivery_plan().model_dump_json(exclude_none=True))
    result = runner.invoke(app, ["routing", "plans", "validate", str(good)])
    assert result.exit_code == 0
    assert "OK" in result.stdout


@respx.mock
def test_submit_json_output(tmp_path) -> None:
    respx.post(f"{DEFAULT_BASE_URL}/plans").mock(
        return_value=httpx.Response(201, json={"item": {"id": _PLAN_ID, "resources": []}})
    )
    plan_file = tmp_path / "plan.json"
    plan_file.write_text(small_delivery_plan().model_dump_json(exclude_none=True))

    result = runner.invoke(
        app,
        ["routing", "plans", "submit", str(plan_file), "--json"],
        env={"KARDINAL_API_KEY": "test-key"},
    )
    assert result.exit_code == 0
    assert _PLAN_ID in result.stdout


def test_version_falls_back_when_package_is_not_installed(monkeypatch) -> None:
    def _raise(_name: str) -> None:
        raise PackageNotFoundError

    monkeypatch.setattr("kardinal._core.transport._package_version", _raise)
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert "unknown (not installed as a package)" in result.stdout


def test_auth_check_without_api_key_fails_with_clean_json_not_a_traceback(monkeypatch) -> None:
    monkeypatch.delenv("KARDINAL_API_KEY", raising=False)
    result = runner.invoke(app, ["auth", "check"])
    assert result.exit_code == 1
    assert result.exception is None or isinstance(result.exception, SystemExit)
    payload = json.loads(result.stdout)
    assert payload["code"] == "MISSING_API_KEY"


@respx.mock
def test_auth_check_reports_base_url_and_agency(monkeypatch) -> None:
    monkeypatch.setenv("KARDINAL_API_KEY", "test-key")
    respx.get(f"{DEFAULT_BASE_URL}/plans").mock(
        return_value=httpx.Response(200, json={"agencyId": "BLD1234567_production", "items": []})
    )
    result = runner.invoke(app, ["auth", "check", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["valid"] is True
    assert payload["baseUrl"] == DEFAULT_BASE_URL
    assert payload["agencyId"] == "BLD1234567_production"


def test_init_writes_a_skill_pointer_file(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["init"])
    assert result.exit_code == 0
    written = tmp_path / ".kardinal" / "SKILL.md"
    assert written.exists()
    assert "kardinal" in written.read_text()


def test_submit_rejects_malformed_json_with_clean_error_not_a_traceback(tmp_path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text('{"resources": [{"id": "r1"}]}')
    result = runner.invoke(
        app,
        ["routing", "plans", "submit", str(bad)],
        env={"KARDINAL_API_KEY": "test-key"},
    )
    assert result.exit_code == 1
    assert "vehicleProfile" in result.stdout


@respx.mock
def test_update_rejects_malformed_json_with_clean_error_not_a_traceback(tmp_path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text('{"resources": [{"id": "r1"}]}')
    result = runner.invoke(
        app,
        ["routing", "plans", "update", str(bad)],
        env={"KARDINAL_API_KEY": "test-key"},
    )
    assert result.exit_code == 1
    assert "vehicleProfile" in result.stdout


@respx.mock
def test_submit_api_error_fails_with_clean_json_not_a_traceback(tmp_path) -> None:
    respx.post(f"{DEFAULT_BASE_URL}/plans").mock(
        return_value=httpx.Response(400, json={"errors": [{"code": "INVALID_INPUT", "message": "no"}]})
    )
    plan_file = tmp_path / "plan.json"
    plan_file.write_text(small_delivery_plan().model_dump_json(exclude_none=True))

    result = runner.invoke(
        app,
        ["routing", "plans", "submit", str(plan_file)],
        env={"KARDINAL_API_KEY": "test-key"},
    )
    assert result.exit_code == 1


@respx.mock
def test_update_api_error_fails_with_clean_json_not_a_traceback(tmp_path) -> None:
    respx.put(f"{DEFAULT_BASE_URL}/plans/{_PLAN_ID}").mock(
        return_value=httpx.Response(404, json={"errors": [{"code": "NOT_FOUND", "message": "no"}]})
    )
    plan_file = tmp_path / "plan.json"
    plan_file.write_text(Plan(id=_PLAN_ID, resources=[]).model_dump_json(exclude_none=True))

    result = runner.invoke(
        app,
        ["routing", "plans", "update", str(plan_file)],
        env={"KARDINAL_API_KEY": "test-key"},
    )
    assert result.exit_code == 1


@respx.mock
def test_plans_get_404_fails_with_clean_json_not_a_traceback() -> None:
    respx.get(f"{DEFAULT_BASE_URL}/plans/{_PLAN_ID}").mock(
        return_value=httpx.Response(404, json={"errors": [{"code": "NOT_FOUND", "message": "no"}]})
    )
    result = runner.invoke(
        app, ["routing", "plans", "get", _PLAN_ID, "--json"], env={"KARDINAL_API_KEY": "test-key"}
    )
    assert result.exit_code == 1
    assert json.loads(result.stdout)["code"] == "NOT_FOUND"


@respx.mock
def test_plans_delete_404_fails_with_clean_json_not_a_traceback() -> None:
    respx.delete(f"{DEFAULT_BASE_URL}/plans/{_PLAN_ID}").mock(
        return_value=httpx.Response(404, json={"errors": [{"code": "NOT_FOUND", "message": "no"}]})
    )
    result = runner.invoke(
        app, ["routing", "plans", "delete", _PLAN_ID], env={"KARDINAL_API_KEY": "test-key"}
    )
    assert result.exit_code == 1


@respx.mock
def test_plans_list_404_fails_with_clean_json_not_a_traceback() -> None:
    respx.get(f"{DEFAULT_BASE_URL}/plans").mock(return_value=httpx.Response(500))
    result = runner.invoke(
        app, ["routing", "plans", "list", "--json"], env={"KARDINAL_API_KEY": "test-key"}
    )
    assert result.exit_code == 1


@respx.mock
def test_plans_start_404_fails_with_clean_json_not_a_traceback() -> None:
    respx.put(f"{DEFAULT_BASE_URL}/plans/{_PLAN_ID}/running").mock(
        return_value=httpx.Response(404, json={"errors": [{"code": "NOT_FOUND", "message": "no"}]})
    )
    result = runner.invoke(
        app, ["routing", "plans", "start", _PLAN_ID], env={"KARDINAL_API_KEY": "test-key"}
    )
    assert result.exit_code == 1


@respx.mock
def test_plans_stop_404_fails_with_clean_json_not_a_traceback() -> None:
    respx.put(f"{DEFAULT_BASE_URL}/plans/{_PLAN_ID}/running").mock(
        return_value=httpx.Response(404, json={"errors": [{"code": "NOT_FOUND", "message": "no"}]})
    )
    result = runner.invoke(
        app, ["routing", "plans", "stop", _PLAN_ID], env={"KARDINAL_API_KEY": "test-key"}
    )
    assert result.exit_code == 1


@respx.mock
def test_plans_status_404_fails_with_clean_json_not_a_traceback() -> None:
    respx.get(f"{DEFAULT_BASE_URL}/plans/{_PLAN_ID}/state").mock(
        return_value=httpx.Response(404, json={"errors": [{"code": "NOT_FOUND", "message": "no"}]})
    )
    result = runner.invoke(
        app, ["routing", "plans", "status", _PLAN_ID], env={"KARDINAL_API_KEY": "test-key"}
    )
    assert result.exit_code == 1


@respx.mock
def test_solutions_get_and_objectives_404_fail_with_clean_json_not_a_traceback() -> None:
    respx.get(f"{DEFAULT_BASE_URL}/plans/{_PLAN_ID}/solution").mock(
        return_value=httpx.Response(404, json={"errors": [{"code": "NOT_FOUND", "message": "no"}]})
    )
    result = runner.invoke(
        app, ["routing", "solutions", "get", _PLAN_ID], env={"KARDINAL_API_KEY": "test-key"}
    )
    assert result.exit_code == 1

    respx.get(f"{DEFAULT_BASE_URL}/plans/{_PLAN_ID}/solution/objectives").mock(
        return_value=httpx.Response(404, json={"errors": [{"code": "NOT_FOUND", "message": "no"}]})
    )
    result = runner.invoke(
        app, ["routing", "solutions", "objectives", _PLAN_ID], env={"KARDINAL_API_KEY": "test-key"}
    )
    assert result.exit_code == 1


@respx.mock
def test_solutions_wait_404_fails_with_clean_json_not_a_traceback() -> None:
    respx.get(f"{DEFAULT_BASE_URL}/plans/{_PLAN_ID}").mock(
        return_value=httpx.Response(404, json={"errors": [{"code": "NOT_FOUND", "message": "no"}]})
    )
    result = runner.invoke(
        app, ["routing", "solutions", "wait", _PLAN_ID], env={"KARDINAL_API_KEY": "test-key"}
    )
    assert result.exit_code == 1


@respx.mock
def test_routing_demo_submit_failure_fails_with_clean_json_not_a_traceback() -> None:
    respx.post(f"{DEFAULT_BASE_URL}/plans").mock(
        return_value=httpx.Response(400, json={"errors": [{"code": "INVALID_INPUT", "message": "no"}]})
    )
    result = runner.invoke(app, ["routing", "demo"], env={"KARDINAL_API_KEY": "test-key"})
    assert result.exit_code == 1


@respx.mock
def test_plans_get() -> None:
    respx.get(f"{DEFAULT_BASE_URL}/plans/{_PLAN_ID}").mock(
        return_value=httpx.Response(200, json={"item": {"id": _PLAN_ID, "resources": []}})
    )
    result = runner.invoke(
        app, ["routing", "plans", "get", _PLAN_ID, "--json"], env={"KARDINAL_API_KEY": "test-key"}
    )
    assert result.exit_code == 0
    assert _PLAN_ID in result.stdout


@respx.mock
def test_plans_update(tmp_path) -> None:
    respx.put(f"{DEFAULT_BASE_URL}/plans/{_PLAN_ID}").mock(
        return_value=httpx.Response(200, json={"item": {"id": _PLAN_ID, "resources": []}})
    )
    plan_file = tmp_path / "plan.json"
    plan_file.write_text(Plan(id=_PLAN_ID, resources=[]).model_dump_json(exclude_none=True))

    result = runner.invoke(
        app,
        ["routing", "plans", "update", str(plan_file), "--json"],
        env={"KARDINAL_API_KEY": "test-key"},
    )
    assert result.exit_code == 0
    assert _PLAN_ID in result.stdout


@respx.mock
def test_plans_delete() -> None:
    respx.delete(f"{DEFAULT_BASE_URL}/plans/{_PLAN_ID}").mock(return_value=httpx.Response(204))
    result = runner.invoke(
        app, ["routing", "plans", "delete", _PLAN_ID], env={"KARDINAL_API_KEY": "test-key"}
    )
    assert result.exit_code == 0
    assert "OK" in result.stdout


@respx.mock
def test_plans_list() -> None:
    respx.get(f"{DEFAULT_BASE_URL}/plans").mock(
        return_value=httpx.Response(
            200, json={"items": [{"id": _PLAN_ID}], "paging": {"total": 1, "totalPages": 1, "page": 1}}
        )
    )
    result = runner.invoke(
        app, ["routing", "plans", "list", "--json"], env={"KARDINAL_API_KEY": "test-key"}
    )
    assert result.exit_code == 0
    assert _PLAN_ID in result.stdout


@respx.mock
def test_plans_start_and_stop_with_force() -> None:
    respx.put(f"{DEFAULT_BASE_URL}/plans/{_PLAN_ID}/running").mock(
        return_value=httpx.Response(200, json={"planId": _PLAN_ID, "planVersion": 1})
    )
    result = runner.invoke(
        app,
        ["routing", "plans", "start", _PLAN_ID, "--force", "--json"],
        env={"KARDINAL_API_KEY": "test-key"},
    )
    assert result.exit_code == 0
    result = runner.invoke(
        app,
        ["routing", "plans", "stop", _PLAN_ID, "--json"],
        env={"KARDINAL_API_KEY": "test-key"},
    )
    assert result.exit_code == 0


@respx.mock
def test_plans_status() -> None:
    respx.get(f"{DEFAULT_BASE_URL}/plans/{_PLAN_ID}/state").mock(
        return_value=httpx.Response(200, json={"item": {"state": "optimized"}})
    )
    result = runner.invoke(
        app, ["routing", "plans", "status", _PLAN_ID, "--json"], env={"KARDINAL_API_KEY": "test-key"}
    )
    assert result.exit_code == 0
    assert "optimized" in result.stdout


@respx.mock
def test_solutions_get_objectives_and_wait() -> None:
    respx.get(f"{DEFAULT_BASE_URL}/plans/{_PLAN_ID}/solution").mock(
        return_value=httpx.Response(200, json={"item": {}})
    )
    result = runner.invoke(
        app, ["routing", "solutions", "get", _PLAN_ID, "--json"], env={"KARDINAL_API_KEY": "test-key"}
    )
    assert result.exit_code == 0

    respx.get(f"{DEFAULT_BASE_URL}/plans/{_PLAN_ID}/solution/objectives").mock(
        return_value=httpx.Response(200, json={"items": []})
    )
    result = runner.invoke(
        app,
        ["routing", "solutions", "objectives", _PLAN_ID, "--json"],
        env={"KARDINAL_API_KEY": "test-key"},
    )
    assert result.exit_code == 0


@respx.mock
def test_solutions_wait(monkeypatch) -> None:
    monkeypatch.setattr("time.sleep", lambda _seconds: None)
    respx.get(f"{DEFAULT_BASE_URL}/plans/{_PLAN_ID}").mock(
        return_value=httpx.Response(200, json={"item": {"id": _PLAN_ID, "resources": []}})
    )
    respx.get(f"{DEFAULT_BASE_URL}/plans/{_PLAN_ID}/state").mock(
        return_value=httpx.Response(200, json={"item": {"state": "optimized"}})
    )
    respx.get(f"{DEFAULT_BASE_URL}/plans/{_PLAN_ID}/solution").mock(
        return_value=httpx.Response(200, json={"item": {}})
    )
    result = runner.invoke(
        app,
        ["routing", "solutions", "wait", _PLAN_ID, "--json"],
        env={"KARDINAL_API_KEY": "test-key"},
    )
    assert result.exit_code == 0


@respx.mock
def test_routing_demo(monkeypatch) -> None:
    monkeypatch.setattr("time.sleep", lambda _seconds: None)
    respx.post(f"{DEFAULT_BASE_URL}/plans").mock(
        return_value=httpx.Response(201, json={"item": {"id": _PLAN_ID, "resources": []}})
    )
    respx.get(f"{DEFAULT_BASE_URL}/plans/{_PLAN_ID}").mock(
        return_value=httpx.Response(200, json={"item": {"id": _PLAN_ID, "resources": []}})
    )
    respx.get(f"{DEFAULT_BASE_URL}/plans/{_PLAN_ID}/state").mock(
        return_value=httpx.Response(200, json={"item": {"state": "optimized"}})
    )
    respx.get(f"{DEFAULT_BASE_URL}/plans/{_PLAN_ID}/solution").mock(
        return_value=httpx.Response(200, json={"item": {}})
    )
    result = runner.invoke(app, ["routing", "demo", "--json"], env={"KARDINAL_API_KEY": "test-key"})
    assert result.exit_code == 0
    assert f"Submitted plan {_PLAN_ID}" in result.stderr


@respx.mock
def test_cli_requests_are_marked_cli_in_user_agent() -> None:
    route = respx.get(f"{DEFAULT_BASE_URL}/plans/{_PLAN_ID}").mock(
        return_value=httpx.Response(200, json={"item": {"id": _PLAN_ID, "resources": []}})
    )
    result = runner.invoke(
        app, ["routing", "plans", "get", _PLAN_ID, "--json"], env={"KARDINAL_API_KEY": "test-key"}
    )
    assert result.exit_code == 0
    headers = route.calls.last.request.headers
    assert headers["User-Agent"].startswith(f"kardinal-sdk-python/{version('kardinal-ai')} (cli; Python/")
    assert headers["X-Kardinal-Client"] == f"kardinal-sdk-python/{version('kardinal-ai')}"


@respx.mock
def test_auth_check_requests_are_marked_cli_in_user_agent() -> None:
    route = respx.get(f"{DEFAULT_BASE_URL}/plans").mock(
        return_value=httpx.Response(200, json={"items": [], "paging": {"page": 1}, "agencyId": "a"})
    )
    result = runner.invoke(app, ["auth", "check", "--json"], env={"KARDINAL_API_KEY": "test-key"})
    assert result.exit_code == 0
    assert "(cli; " in route.calls.last.request.headers["User-Agent"]
