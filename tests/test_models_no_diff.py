import os
import subprocess
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent


def test_models_regeneration_produces_no_diff() -> None:
    # scripts/generate_models.sh shells out to `datamodel-codegen`, a console
    # script installed next to whichever Python is running this test. If the
    # caller invoked pytest without `source .venv/bin/activate` (e.g. via the
    # venv's absolute path), that script's directory isn't on PATH and the
    # subprocess below would resolve a different (or no) `datamodel-codegen`,
    # failing with a misleading "command not found" that looks like a real
    # models/spec drift rather than an environment issue. Prepending it here
    # makes the check depend only on which interpreter is running pytest,
    # not on how the caller's shell was set up.
    env = dict(os.environ, PATH=os.pathsep.join([os.path.dirname(sys.executable), os.environ.get("PATH", "")]))
    result = subprocess.run(
        ["bash", "scripts/check_models_no_diff.sh"],
        cwd=_ROOT,
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.returncode == 0, result.stdout + result.stderr
