from __future__ import annotations

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from racing.models import Race, RaceResult, RaceSquad
from racing.services import set_squad
from riders.models import Rider, RiderAttributeSnapshot
from teams.models import Team


@pytest.fixture
def second_team(db) -> Team:
    return Team.objects.create(name="Team Beta", code="BET", primary_colour="#0000FF")


@pytest.fixture
def four_riders(db, team) -> list[Rider]:
    return [
        Rider.objects.create(
            name=f"Rider {i}",
            team=team,
            climb=60, sprint=60, flat=60, resistance=60, positioning=60,
        )
        for i in range(4)
    ]


@pytest.fixture
def race(db) -> Race:
    return Race.objects.create(
        name="Old Race",
        course=[{"length": 500.0, "gradient": 0.0}],
        status=Race.Status.SCHEDULED,
    )


def test_refuses_without_yes(db, rider):
    with pytest.raises(CommandError):
        call_command("reset_riders")

    assert Rider.objects.count() == 1


def test_replaces_population(db, team, second_team, four_riders, race, capsys):
    set_squad(race, team, [r.pk for r in four_riders], four_riders[0].pk)
    RaceResult.objects.create(race=race, rider=four_riders[0], position=1, finish_time=100.0)

    old_ids = set(Rider.objects.values_list("pk", flat=True))

    call_command("reset_riders", "--yes", "--per-team=12")

    new_riders = Rider.objects.all()
    assert new_riders.count() == 24  # 12 per team, 2 teams
    assert not set(new_riders.values_list("pk", flat=True)) & old_ids
    assert new_riders.filter(team=team).count() == 12
    assert new_riders.filter(team=second_team).count() == 12
    assert RaceResult.objects.count() == 0
    assert RaceSquad.objects.count() == 0


def test_replaces_population_gives_every_new_rider_a_baseline_snapshot_and_no_orphans(
    db, team, second_team, rider,
):
    old_snapshot = RiderAttributeSnapshot.objects.create(
        rider=rider, week=None, climb=5, sprint=5, flat=5, resistance=5, positioning=5,
    )

    call_command("reset_riders", "--yes", "--per-team=12")

    new_riders = Rider.objects.all()
    assert new_riders.count() == 24
    for r in new_riders:
        assert r.attribute_snapshots.filter(week=None).count() == 1
    assert RiderAttributeSnapshot.objects.count() == 24
    assert not RiderAttributeSnapshot.objects.filter(pk=old_snapshot.pk).exists()
