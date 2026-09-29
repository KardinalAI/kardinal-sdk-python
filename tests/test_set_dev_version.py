"""scripts/set_dev_version.py gives each TestPyPI dry run a unique version:
TestPyPI, like PyPI, never accepts the same version twice.
"""

import subprocess
import sys
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "set_dev_version.py"
_PYPROJECT = '[project]\nname = "kardinal-ai"\nversion = "1.0.0"\nrequires-python = ">=3.10"\n'


def _run(tmp_path, *args) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(_SCRIPT), *args], cwd=tmp_path, capture_output=True, text=True
    )


def test_appends_dev_n_to_the_version(tmp_path) -> None:
    (tmp_path / "pyproject.toml").write_text(_PYPROJECT)
    result = _run(tmp_path, "7")
    assert result.returncode == 0, result.stderr
    assert (tmp_path / "pyproject.toml").read_text() == _PYPROJECT.replace('"1.0.0"', '"1.0.0.dev7"')
    assert "1.0.0.dev7" in result.stdout


def test_fails_when_no_version_line_is_found(tmp_path) -> None:
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "kardinal-ai"\n')
    assert _run(tmp_path, "7").returncode == 1


def test_rejects_a_non_numeric_run_number(tmp_path) -> None:
    (tmp_path / "pyproject.toml").write_text(_PYPROJECT)
    assert _run(tmp_path, "abc").returncode == 1
    assert (tmp_path / "pyproject.toml").read_text() == _PYPROJECT
