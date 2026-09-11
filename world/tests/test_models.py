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
