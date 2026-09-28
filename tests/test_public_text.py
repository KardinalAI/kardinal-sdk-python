"""The README becomes the pypi.org page and docstrings show up in `help()`:
neither may carry internal details or claims we haven't verified (P6).
"""

import re
import subprocess
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_GENERATED = _ROOT / "kardinal" / "routing" / "models"

# Internal environments and hosts, the GitLab path, a fake key format (API
# keys are JWTs), the webhook endpoints (x-excluded from the public spec),
# a performance claim nobody verified, and CONTRIBUTING.md (maintainer
# notes, not shipped in the package: a dead reference on pypi.org).
_FORBIDDEN = [
    r"contributing\.md",
    r"sk-",
    r"console",
    r"per-deployment",
    r"plt\.",
    r"gitlab",
    r"webhook",
    r"cheap.to.poll",
    r"signature mismatch",
]


def _public_files():
    yield _ROOT / "README.md"
    for path in (_ROOT / "kardinal").rglob("*.py"):
        if _GENERATED not in path.parents:
            yield path


def test_no_internal_detail_in_public_text() -> None:
    offenders = [
        f"{path.relative_to(_ROOT)}:{number}: {line.strip()}"
        for path in _public_files()
        for number, line in enumerate(path.read_text().splitlines(), start=1)
        for pattern in _FORBIDDEN
        if re.search(pattern, line, re.IGNORECASE)
    ]
    assert offenders == []


# Beyond the README and the package, every tracked file ends up in the public
# repository: no internal host, repository path or internal document there
# either. The spec and the models generated from it are excluded (they're
# the public API reference), as is this file, which lists the patterns.
_FORBIDDEN_ANYWHERE = [
    r"plt\.",
    r"gitlab\.kardinal",
    r"public-docs",
    r"guidelines",
    r"aropy",
    r"sk-[a-z0-9]",
]
_EXCLUDED = {"spec/openapi.yaml", "kardinal/routing/models/__init__.py", "tests/test_public_text.py"}


def test_no_internal_detail_in_any_tracked_file() -> None:
    tracked = subprocess.run(
        ["git", "ls-files"], cwd=_ROOT, capture_output=True, text=True, check=True
    ).stdout.split()
    offenders = [
        f"{name}:{number}: {line.strip()}"
        for name in tracked
        if name not in _EXCLUDED and (_ROOT / name).is_file()
        for number, line in enumerate((_ROOT / name).read_text(errors="replace").splitlines(), start=1)
        for pattern in _FORBIDDEN_ANYWHERE
        if re.search(pattern, line, re.IGNORECASE)
    ]
    assert offenders == []
