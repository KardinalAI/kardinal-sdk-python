import pytest
import typer

from kardinal._core.cli import Exit, emit, fail
from kardinal._core.errors import KardinalLimitError, KardinalValidationError


def test_emit_prints_a_readable_table_when_not_json_and_stdout_is_a_tty(monkeypatch, capsys) -> None:
    # emit() defaults to JSON when stdout isn't a tty — simulate a real
    # terminal to exercise the table-printing branch instead.
    monkeypatch.setattr("sys.stdout.isatty", lambda: True)
    emit({"id": "p1", "state": "optimized"}, force_json=False)
    out = capsys.readouterr().out
    assert "id" in out
    assert "p1" in out
    assert "{" not in out


def test_emit_prints_a_table_row_per_list_item_when_a_tty(monkeypatch, capsys) -> None:
    monkeypatch.setattr("sys.stdout.isatty", lambda: True)
    emit([{"id": "p1"}, {"id": "p2"}], force_json=False)
    out = capsys.readouterr().out
    assert "p1" in out
    assert "p2" in out


def test_emit_prints_plain_values_for_a_non_dict_row(monkeypatch, capsys) -> None:
    monkeypatch.setattr("sys.stdout.isatty", lambda: True)
    emit(["a", "b"], force_json=False)
    out = capsys.readouterr().out
    assert "a" in out
    assert "b" in out


def test_fail_emits_json_and_exits_with_business_error_code(capsys) -> None:
    exc = KardinalValidationError(
        "bad input",
        code="INVALID_VALUE",
        status=400,
        request_id=None,
        retryable=False,
        errors=[{"code": "INVALID_VALUE", "message": "bad"}],
    )
    with pytest.raises(typer.Exit) as exc_info:
        fail(exc)
    assert exc_info.value.exit_code == Exit.BUSINESS_ERROR
    out = capsys.readouterr().out
    assert '"code": "INVALID_VALUE"' in out
    assert '"retryable": false' in out


def test_fail_shows_details_so_each_kind_of_limit_can_be_told_apart(capsys) -> None:
    exc = KardinalLimitError(
        "The requested action is not allowed.",
        code="NOT_ALLOWED",
        status=403,
        request_id=None,
        retryable=False,
        errors=[{"code": "NOT_ALLOWED", "message": "no", "properties": {"details": "Monthly credit quota exhausted"}}],
    )
    with pytest.raises(typer.Exit):
        fail(exc)
    assert '"details": "Monthly credit quota exhausted"' in capsys.readouterr().out


def test_emit_prints_non_string_table_values_as_json(monkeypatch, capsys) -> None:
    monkeypatch.setattr("sys.stdout.isatty", lambda: True)
    emit({"id": "p1", "running": True, "tags": ["a"]}, force_json=False)
    out = capsys.readouterr().out
    assert "true" in out
    assert '["a"]' in out
    assert "'" not in out
