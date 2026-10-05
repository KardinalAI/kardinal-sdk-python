"""The patches in `_annotations.py` used to be applied by importing
plans.py or solutions.py. A caller who imported the models on their own —
to build a payload before touching the client — got the unpatched ones, so
the same code worked or failed depending on what the program had imported
first, and submit()'s spelling check silently did nothing.

Each case runs in a subprocess: once the models are in this process's
sys.modules, the import order under test can no longer be reproduced.
"""

import subprocess
import sys

import pytest

_ENTRY_POINTS = [
    "import kardinal",
    "from kardinal import Kardinal",
    "import kardinal.routing",
    "import kardinal.routing.models",
    "from kardinal.routing import models",
    "import kardinal.routing.plans",
    "import kardinal.routing.solutions",
    "import kardinal.cli",
]


def _run(code: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)


@pytest.mark.parametrize("entry", _ENTRY_POINTS)
def test_the_patches_are_applied_whatever_was_imported_first(entry: str) -> None:
    result = _run(
        f"{entry}\n"
        "import typing\n"
        "from kardinal.routing import models\n"
        "assert models.Solution.model_fields['planId'].annotation == typing.Optional[str], 'PlanId'\n"
        "assert models.Resource.model_config['extra'] == 'allow', 'unknown fields'\n"
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_a_typo_is_reported_even_when_the_models_were_imported_first() -> None:
    # The case that used to send the plan with the field silently gone.
    result = _run(
        "from kardinal.routing import models\n"
        "tw = {'begin': '2026-10-06T08:00:00Z', 'end': '2026-10-06T18:00:00Z'}\n"
        "r = models.Resource(id='v', vehicleProfile={'type': 'car'},"
        " workingTimeWindow=tw, maxWorkingDurationn='PT8H')\n"
        "from kardinal.routing.plans import PlanCreate, PlansAPI\n"
        "from kardinal import UnknownFieldError\n"
        "class T:\n"
        "    def request(self, *a, **k):\n"
        "        raise AssertionError('the plan was sent')\n"
        "try:\n"
        "    PlansAPI(T()).submit(PlanCreate(resources=[r]))\n"
        "    raise AssertionError('no error raised')\n"
        "except UnknownFieldError as exc:\n"
        "    assert exc.paths == ['plan.resources[0].maxWorkingDurationn'], exc.paths\n"
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_help_still_does_not_load_the_models() -> None:
    # The patches must not be bought at the cost of `--help` loading them.
    result = _run("import sys, kardinal.cli; assert 'kardinal.routing.models' not in sys.modules")
    assert result.returncode == 0, result.stdout + result.stderr
