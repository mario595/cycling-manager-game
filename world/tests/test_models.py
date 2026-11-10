from __future__ import annotations

from world.models import GameClock, TickRun


def test_load_creates_single_clock(db):
    first = GameClock.load()
    second = GameClock.load()

    assert first.pk == 1
    assert second.pk == 1
    assert GameClock.objects.count() == 1


def test_tick_run_orders_newest_first(db):
    older = TickRun.objects.create()
    newer = TickRun.objects.create()

    assert list(TickRun.objects.all()) == [newer, older]


def test_tick_run_ai_management_counters_default_to_zero(db):
    run = TickRun.objects.create()

    assert run.ai_trainers_hired == 0
    assert run.ai_sponsors_signed == 0
