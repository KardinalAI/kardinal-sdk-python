"""Append `.devN` to the version in pyproject.toml, for a TestPyPI dry run.

TestPyPI, like PyPI, never accepts the same version twice: each dry run of
.github/workflows/publish.yml therefore publishes X.Y.Z.devN, N being the
workflow run number. Only the CI checkout is modified; nothing is committed.
Never used for a real release (a vX.Y.Z tag publishes the version as is).

Usage: python scripts/set_dev_version.py <run number>
"""

import re
import sys
from pathlib import Path

_VERSION_LINE = re.compile(r'^version = "([^"]+)"$', re.MULTILINE)


def main(run_number: str) -> int:
    if not run_number.isdigit():
        print(f"Run number must be an integer, got {run_number!r}.", file=sys.stderr)
        return 1
    pyproject = Path("pyproject.toml")
    text = pyproject.read_text()
    match = _VERSION_LINE.search(text)
    if match is None:
        print("No `version = \"...\"` line found in pyproject.toml.", file=sys.stderr)
        return 1
    dev_version = f"{match.group(1)}.dev{run_number}"
    pyproject.write_text(_VERSION_LINE.sub(f'version = "{dev_version}"', text, count=1))
    print(f"Version set to {dev_version} for this dry run.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
