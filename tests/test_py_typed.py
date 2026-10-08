"""PEP 561: without this marker in the installed package, a user's mypy or
pyright skips `kardinal` entirely — every annotation in it is invisible to
them, and `plan.resourcess` or a wrong argument type is reported nowhere.
It is one empty file, and nothing else in the test suite would notice it
going missing from the wheel.
"""

import subprocess
import sys
import zipfile
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent


def test_the_marker_is_in_the_package() -> None:
    assert (_ROOT / "kardinal" / "py.typed").is_file()


def test_the_marker_is_in_the_built_wheel(tmp_path) -> None:
    # Present in the tree but left out of the distribution is the failure
    # that matters: the repo type-checks, the user still sees nothing.
    build = subprocess.run(
        [sys.executable, "-m", "build", "--wheel", "-o", str(tmp_path)],
        cwd=_ROOT,
        capture_output=True,
        text=True,
    )
    if build.returncode != 0:
        import pytest

        pytest.skip(f"wheel build unavailable: {build.stderr[-200:]}")
    wheel = next(tmp_path.glob("*.whl"))
    assert "kardinal/py.typed" in zipfile.ZipFile(wheel).namelist()
