"""The ```python blocks of the doc pages, copied into tests/doc_examples/ by
scripts/sync_doc_examples.py, run page by page (in order, in one namespace per
page, as a reader chaining the examples would) against the mocked API of
tests/fake_api.py.

Running is not enough: `if state == "optimized":` runs fine and is simply
never true. So each page also has a few expected values below, checked after
its blocks ran. A page with blocks but no entry in EXPECTED fails the test.
"""

import re
from pathlib import Path

import pytest
import respx
from fake_api import PLAN_ID, FakeApi, mock_routes

from kardinal import Kardinal
from kardinal.routing import examples, models

_COPY = Path(__file__).resolve().parent / "doc_examples"
_MARKER = re.compile(r"^# --- (?P<where>\S+)$", re.MULTILINE)


def _blocks(path: Path):
    """(page:line, code) for each block of a copied page."""
    text = path.read_text()
    marks = list(_MARKER.finditer(text))
    for mark, following in zip(marks, marks[1:] + [None]):
        yield mark["where"], text[mark.end() : following.start() if following else None]


def _solution(tours=(), unaffected=()):
    return models.Solution.model_validate(
        {"planId": PLAN_ID, "planVersion": 1, "tours": list(tours), "unaffectedStopIds": list(unaffected)}
    )


def _stop_waypoint(stop_id, begin="2026-10-29T10:00:00+01:00"):
    return {"type": "stop", "stopId": stop_id, "beginTime": begin, "delay": "PT0S",
            "position": {"lon": 2.35, "lat": 48.85}}


# Names a page's blocks use without defining them: the page text says "the
# solution you got above", and the test supplies it.
_PRELUDES = {
    "sdks__errors-and-warnings": lambda: {"k": Kardinal(), "plan_input": examples.small_delivery_plan()},
    "guides__skills-and-assignments": lambda: {
        "solution": _solution(
            tours=[{"resourceId": "tech-plain", "isValid": False, "wayPoints": [],
                    "violations": [{"type": "skills", "lackingSkills": ["gas-certified"]}]}],
            unaffected=["stop-panel"],
        )
    },
    "guides__time-windows": lambda: {
        "solution": _solution(tours=[{"resourceId": "van-1", "wayPoints": [_stop_waypoint("stop-clinic")]}])
    },
    # The guide reads the solution as the JSON dict the API returns.
    "guides__capacities": lambda: {"solution": {"unaffectedStopIds": ["pickup-1"]}},
}


def _lifecycle(ns, out):
    assert ns["state"] == "optimized"
    assert ns["state"] == models.PlanState.optimized
    assert "solution" in ns, "the state check never became true: `solution` was not fetched"
    assert ns["solution"].final_state == "optimized"
    assert ns["plan"].version == 2
    assert ns["page"].total == 1
    assert PLAN_ID in out


def _orders(ns, out):
    assert len(ns["plan"].orders) == 3
    served = _solution(tours=[{"resourceId": "van-1", "wayPoints": [_stop_waypoint("drop-near")]}],
                       unaffected=["pickup-1"])
    assert ns["check_orders"](ns["plan"], served) == ["order-1: pickup-1 is left out"]


def _capacities(ns, out):
    assert len(ns["plan"].orders) == 4
    tour = {"maxFilledCapacities": {"frozenVolume": 4, "chilledVolume": 5}, "wayPoints": []}
    assert ns["check_tour"](tour, ns["setups"]) == ([], {"frozenVolume": 5, "chilledVolume": 5})
    assert "Left out: ['pickup-1']" in out


def _resource_limits(ns, out):
    assert len(ns["plan"].orders) == 4
    assert ns["seconds"]("PT1H39M40S") == 5980
    tour = {"workingDuration": "PT3H30M", "distanceInKm": 5}
    assert ns["check_limits"](tour, {"maxWorkingDuration": "PT3H"}) == [
        "workingDuration PT3H30M is over PT3H"
    ]


def _quickstart(ns, out):
    assert ns["solution"].final_state == "optimized"


def _configuration(ns, out):
    assert ns["plans"].total == 1


def _building_plans(ns, out):
    assert ns["created"].id == PLAN_ID, "plan.json was not submitted"
    assert out == "", f"unknown_fields reported {out!r} on a valid plan"


def _errors_and_warnings(ns, out):
    assert ns["plan"].warnings[0].code == "INVALID_VALUE"
    assert "INVALID_VALUE" in out


def _breaks(ns, out):
    assert len(ns["plan"].orders) == 2


def _time_windows(ns, out):
    assert len(ns["plan"].orders) == 2
    assert "stop-clinic authorized: ok" in out, out


def _skills(ns, out):
    assert len(ns["plan"].orders) == 3
    assert "stop-panel was not planned" in out, out
    assert "tech-plain lacks ['gas-certified']" in out, out


# Page (path without .mdx, "/" as "__") -> checks run on its namespace and
# on what its blocks printed.
EXPECTED = {
    "sdks__plan-lifecycle": _lifecycle,
    "sdks__quickstart": _quickstart,
    "sdks__configuration": _configuration,
    "sdks__building-plans": _building_plans,
    "sdks__errors-and-warnings": _errors_and_warnings,
    "guides__breaks": _breaks,
    "guides__time-windows": _time_windows,
    "guides__skills-and-assignments": _skills,
    "guides__orders-and-sequences": _orders,
    "guides__capacities": _capacities,
    "guides__resource-limits": _resource_limits,
}


def _state_check_fetched_the_solution(before, ns):
    # `state` being "optimized" is not enough: the `if` must have been true.
    assert ns["solution"] is not before["solution"], "`if state == ...` was never true: no solution fetched"


# Page -> (text that identifies a block, check run right after it, on the
# namespace before and after the block).
AFTER_BLOCK = {"sdks__plan-lifecycle": [("get_status", _state_check_fetched_the_solution)]}


def _pages():
    return sorted(_COPY.glob("*.py")) if _COPY.is_dir() else []


def test_every_page_with_examples_has_expected_values() -> None:
    pages = {p.stem for p in _pages()}
    assert pages, "tests/doc_examples/ is empty: run scripts/sync_doc_examples.py"
    assert pages == set(EXPECTED), f"pages and EXPECTED differ: {sorted(pages ^ set(EXPECTED))}"


@respx.mock
@pytest.mark.parametrize("page", _pages(), ids=lambda p: p.stem)
def test_page_examples_run_and_give_the_documented_values(page, monkeypatch, tmp_path, capsys) -> None:
    monkeypatch.setattr("time.sleep", lambda _seconds: None)
    monkeypatch.chdir(tmp_path)
    api = FakeApi()
    mock_routes(api)
    # building-plans reads a plan.json from the current folder.
    (tmp_path / "plan.json").write_text(examples.small_delivery_plan().model_dump_json(exclude_none=True))

    namespace: dict = _PRELUDES.get(page.stem, dict)()
    blocks = list(_blocks(page))
    assert blocks, f"no block in {page.name}"
    for where, code in blocks:
        before = dict(namespace)
        exec(compile(code, where, "exec"), namespace)
        for marker, check in AFTER_BLOCK.get(page.stem, ()):
            if marker in code:
                check(before, namespace)
    EXPECTED[page.stem](namespace, capsys.readouterr().out)
