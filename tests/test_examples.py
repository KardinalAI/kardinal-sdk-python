import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

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


class _PinnedNow(datetime):
    # 23:30 UTC on 2026-08-01 is 00:30 on 2026-08-02 at +01:00, so tomorrow is 2026-08-03.
    @classmethod
    def now(cls, tz=None):
        return datetime(2026, 8, 1, 23, 30, tzinfo=timezone.utc).astimezone(tz)


def test_cold_chain_plan_equals_the_published_payload(monkeypatch) -> None:
    monkeypatch.setattr(examples, "datetime", _PinnedNow)
    published = json.loads(
        (Path(__file__).parent / "case_studies" / "cold-chain-last-mile.json").read_text()
    )
    plan = examples.cold_chain_plan()
    assert plan.model_dump(mode="json", exclude_unset=True) == published
    # The docstring states the stop count: keep it in step with the payload.
    assert sum(len(order.stops) for order in plan.orders or []) == 15


def test_cold_chain_plan_passes_local_validation() -> None:
    plan = examples.cold_chain_plan()
    assert PlanCreate.model_validate(plan.model_dump(exclude_none=True)) is not None


def test_cold_chain_plan_is_fresh_and_follows_tomorrow() -> None:
    a = examples.cold_chain_plan()
    assert a is not examples.cold_chain_plan()
    tomorrow = (datetime.now(timezone(timedelta(hours=1))) + timedelta(days=1)).date()
    assert a.resources[0].workingTimeWindow.begin == f"{tomorrow} 05:00"


def test_parcel_express_plan_equals_the_published_payload(monkeypatch) -> None:
    monkeypatch.setattr(examples, "datetime", _PinnedNow)
    published = json.loads(
        (Path(__file__).parent / "case_studies" / "parcel-express.json").read_text()
    )
    plan = examples.parcel_express_plan()
    assert plan.model_dump(mode="json", exclude_unset=True) == published
    # The docstring states the stop count: keep it in step with the payload.
    assert sum(len(order.stops) for order in plan.orders or []) == 10


def test_parcel_express_plan_passes_local_validation() -> None:
    plan = examples.parcel_express_plan()
    assert PlanCreate.model_validate(plan.model_dump(exclude_none=True)) is not None


def test_parcel_express_plan_is_fresh_and_follows_tomorrow() -> None:
    a = examples.parcel_express_plan()
    assert a is not examples.parcel_express_plan()
    tomorrow = (datetime.now(timezone(timedelta(hours=1))) + timedelta(days=1)).date()
    assert a.resources[0].workingTimeWindow.begin == f"{tomorrow} 07:00"
