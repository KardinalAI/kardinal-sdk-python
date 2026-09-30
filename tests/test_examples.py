from datetime import datetime, timezone

from kardinal.routing import examples
from kardinal.routing.plans import PlanCreate


def test_the_example_plan_passes_local_validation() -> None:
    plan = PlanCreate.model_validate(examples.small_delivery_plan().model_dump(exclude_none=True))
    assert len(plan.resources) == 2
    assert len(plan.orders) == 8


def test_the_working_window_is_always_in_the_future_not_a_fixed_stale_date() -> None:
    begin = examples.small_delivery_plan().resources[0].workingTimeWindow.begin
    assert datetime.fromisoformat(str(begin)) > datetime.now(timezone.utc)


def test_every_call_returns_a_fresh_object() -> None:
    a = examples.small_delivery_plan()
    b = examples.small_delivery_plan()
    assert a is not b
    assert a.resources is not b.resources


def test_tomorrow_is_computed_at_plus_one_hour_not_in_utc(monkeypatch) -> None:
    # 23:30 UTC is already 00:30 the next day at +01:00.
    class _FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 10, 1, 23, 30, tzinfo=timezone.utc).astimezone(tz)

    monkeypatch.setattr(examples, "datetime", _FixedDatetime)
    begin = examples.small_delivery_plan().resources[0].workingTimeWindow.begin
    assert str(begin) == "2026-10-03T08:00:00+01:00"
