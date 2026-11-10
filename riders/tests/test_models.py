from __future__ import annotations

from datetime import datetime, timedelta, timezone as dt_timezone

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from riders.models import DevelopmentSquad, Rider, RiderAttributeSnapshot
from schedule.models import Season, Week


def _snapshot_kwargs(rider):
    return dict(rider=rider, climb=9, sprint=3, flat=4, resistance=8, positioning=5)


def test_rider_has_speciality_and_hidden_traits(rider):
    assert rider.speciality == Rider.Speciality.ROULEUR
    assert rider.nationality == Rider.Nationality.SPAIN
    assert rider.height_cm == 178
    assert rider.weight_kg == 70
    assert rider.age == 25
    assert rider.potential == 70
    assert rider.peak_age == 27
    assert rider.decline_rate == 50
    assert rider.injury_proneness == 50
    assert rider.training_affinity == {}


def test_growth_debt_defaults_to_an_empty_dict(rider):
    assert rider.growth_debt == {}


def test_rider_speciality_rejects_value_outside_choices(rider):
    rider.speciality = "time-trialist"
    with pytest.raises(ValidationError):
        rider.full_clean()


def test_weekly_salary_defaults_to_the_flat_wage(rider):
    assert rider.weekly_salary == 1200


def test_weekly_salary_rejects_zero(rider):
    rider.weekly_salary = 0
    with pytest.raises(ValidationError):
        rider.full_clean()


def test_a_rider_can_have_a_snapshot_for_two_different_weeks(rider):
    monday = datetime(2027, 3, 1, 0, 0, tzinfo=dt_timezone.utc)
    season = Season.objects.create(number=1, starts_at=monday)
    week_one = Week.objects.create(
        season=season, number=1, starts_at=monday, ends_at=monday + timedelta(weeks=1),
    )
    week_two = Week.objects.create(
        season=season, number=2,
        starts_at=monday + timedelta(weeks=1), ends_at=monday + timedelta(weeks=2),
    )

    RiderAttributeSnapshot.objects.create(week=week_one, **_snapshot_kwargs(rider))
    RiderAttributeSnapshot.objects.create(week=week_two, **_snapshot_kwargs(rider))

    assert rider.attribute_snapshots.count() == 2


def test_a_rider_cannot_have_two_snapshots_for_the_same_week(rider):
    monday = datetime(2027, 3, 1, 0, 0, tzinfo=dt_timezone.utc)
    season = Season.objects.create(number=1, starts_at=monday)
    week = Week.objects.create(
        season=season, number=1, starts_at=monday, ends_at=monday + timedelta(weeks=1),
    )
    RiderAttributeSnapshot.objects.create(week=week, **_snapshot_kwargs(rider))

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            RiderAttributeSnapshot.objects.create(week=week, **_snapshot_kwargs(rider))


def test_a_rider_can_have_two_baseline_snapshots(rider):
    """The unique constraint is on (rider, week); Postgres treats NULL week
    values as distinct, so it does not restrict baseline (week=None) rows.
    Only one code path ever creates a baseline, so this is a property of the
    constraint, not a behaviour the feature relies on."""
    RiderAttributeSnapshot.objects.create(week=None, **_snapshot_kwargs(rider))
    RiderAttributeSnapshot.objects.create(week=None, **_snapshot_kwargs(rider))

    assert rider.attribute_snapshots.count() == 2


def test_active_excludes_retired_riders(rider):
    retired_at = datetime(2027, 3, 1, tzinfo=dt_timezone.utc)
    retired = Rider.objects.create(
        name="Retired Rider",
        climb=50,
        sprint=50,
        flat=50,
        resistance=50,
        positioning=50,
        retired_at=retired_at,
    )

    assert list(Rider.objects.active()) == [rider]
    assert retired.retired_at == retired_at


def test_retired_rider_cannot_have_a_team(rider):
    rider.retired_at = datetime(2027, 3, 1, tzinfo=dt_timezone.utc)

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            rider.save()


def test_rider_cannot_be_on_roster_and_in_squad(rider, team):
    squad = DevelopmentSquad.objects.create(
        team=team, level=DevelopmentSquad.Level.REGIONAL,
        opened_at=datetime(2027, 3, 1, tzinfo=dt_timezone.utc),
    )
    rider.development_squad = squad

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            rider.save()


def test_retired_rider_cannot_be_in_squad(rider, team):
    squad = DevelopmentSquad.objects.create(
        team=team, level=DevelopmentSquad.Level.REGIONAL,
        opened_at=datetime(2027, 3, 1, tzinfo=dt_timezone.utc),
    )
    rider.team = None
    rider.development_squad = squad
    rider.retired_at = datetime(2027, 3, 1, tzinfo=dt_timezone.utc)

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            rider.save()


def test_graduated_requires_intake(rider):
    """A graduate is a rider who came through intake and served a squad
    spell, so graduated_at without intake_at is a state no code path can
    produce — the constraint says so rather than trusting it."""
    rider.graduated_at = datetime(2027, 3, 1, tzinfo=dt_timezone.utc)

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            rider.save()


def test_a_squad_rider_can_have_both_intake_at_and_graduated_at(rider, team):
    squad = DevelopmentSquad.objects.create(
        team=team, level=DevelopmentSquad.Level.REGIONAL,
        opened_at=datetime(2027, 3, 1, tzinfo=dt_timezone.utc),
    )
    rider.team = None
    rider.development_squad = squad
    rider.intake_at = datetime(2027, 2, 1, tzinfo=dt_timezone.utc)
    rider.graduated_at = datetime(2027, 3, 1, tzinfo=dt_timezone.utc)
    rider.save()

    assert rider.graduated_at is not None


def test_age_17_is_valid(rider):
    rider.age = 17
    # training_affinity isn't set by the `rider` fixture (blank=False, but
    # unrelated to this test's concern), so exclude it here the same way a
    # partial full_clean() is used elsewhere for a single field's validity.
    rider.full_clean(exclude=["training_affinity"])


def test_squad_delete_nulls_rider_link(rider, team):
    squad = DevelopmentSquad.objects.create(
        team=team, level=DevelopmentSquad.Level.REGIONAL,
        opened_at=datetime(2027, 3, 1, tzinfo=dt_timezone.utc),
    )
    rider.team = None
    rider.development_squad = squad
    rider.save()

    squad.delete()
    rider.refresh_from_db()

    assert rider.development_squad_id is None
