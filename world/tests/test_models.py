from __future__ import annotations

from django.utils import timezone

from world.models import GameClock, TickRun


def test_load_creates_single_clock(db):
    first = GameClock.load()
    second = GameClock.load()

    assert first.pk == 1
    assert second.pk == 1
    assert GameClock.objects.count() == 1


def test_tick_run_orders_newest_first(db):
    now = timezone.now()
    older = TickRun.objects.create(
        from_game_time=now, to_game_time=now,
    )
    newer = TickRun.objects.create(
        from_game_time=now, to_game_time=now,
    )

    assert list(TickRun.objects.all()) == [newer, older]
