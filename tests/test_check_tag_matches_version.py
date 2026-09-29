"""scripts/check_tag_matches_version.py guards the publish workflow: a tag
that doesn't match the package version must stop the release.
"""

import subprocess
import sys
from importlib.metadata import version
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "check_tag_matches_version.py"


def _run(tag: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(_SCRIPT), tag], capture_output=True, text=True)


def test_a_tag_matching_the_package_version_passes() -> None:
    result = _run(f"v{version('kardinal-ai')}")
    assert result.returncode == 0, result.stdout + result.stderr


def test_a_tag_not_matching_the_package_version_fails() -> None:
    result = _run("v0.0.0")
    assert result.returncode == 1
    assert version("kardinal-ai") in result.stderr


def test_a_tag_without_the_v_prefix_fails() -> None:
    assert _run(version("kardinal-ai")).returncode == 1
