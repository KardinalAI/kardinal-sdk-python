"""The PyPI distribution is `kardinal-ai` (PyPI refuses `kardinal`), while
the import name and the CLI command stay `kardinal`.
"""

import re
from importlib.metadata import distribution
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent


def test_distribution_is_named_kardinal_ai() -> None:
    dist = distribution("kardinal-ai")
    scripts = {ep.name: ep.value for ep in dist.entry_points if ep.group == "console_scripts"}
    assert dist.metadata["Name"] == "kardinal-ai"
    assert scripts == {"kardinal": "kardinal.cli:app"}


def test_no_install_instruction_uses_the_refused_name() -> None:
    files = [_ROOT / "README.md", *(_ROOT / "kardinal").rglob("*.py")]
    offenders = [
        f"{path.relative_to(_ROOT)}: {line.strip()}"
        for path in files
        for line in path.read_text().splitlines()
        if re.search(r"pip install \"?kardinal(?!-ai)\b", line)
    ]
    assert offenders == []
