"""Departures (#158, #162): who left a team without the manager acting, and
why. Written where the rider leaves; see riders/README.md, *Departures*."""

from __future__ import annotations

from datetime import datetime, timezone as dt_timezone

import pytest

from riders.development_squad import close_squad
from riders.models import Departure, DevelopmentSquad, Rider
from riders.services import retire_due_riders
from riders.youth_triage import release_graduates
from teams.models import Team

AT = datetime(2027, 3, 1, tzinfo=dt_timezone.utc)
LATER = datetime(2027, 4, 5, tzinfo=dt_timezone.utc)

ATTRS = dict(climb=40, sprint=40, flat=40, resistance=40, positioning=40)


def _veteran(**overrides) -> Rider:
    fields = dict(
        name="Veteran", age=40, peak_age=32, decline_rate=1,
        speciality=Rider.Speciality.CLIMBER, **ATTRS,
    )
    fields.update(overrides)
    return Rider.objects.create(**fields)


@pytest.fixture
def squad(team) -> DevelopmentSquad:
    return DevelopmentSquad.objects.create(
        team=team, level=DevelopmentSquad.Level.REGIONAL, opened_at=AT,
    )


def _graduate(squad, *, name="Graduate") -> Rider:
    return Rider.objects.create(
        name=name, age=19, speciality=Rider.Speciality.SPRINTER,
        development_squad=squad, intake_at=AT, graduated_at=LATER, **ATTRS,
    )


# --- Retirement -----------------------------------------------------------


def test_a_rostered_retirement_records_the_team_it_left(team):
    rider = _veteran(team=team)

    retire_due_riders(at=LATER)

    departure = Departure.objects.get()
    assert departure.team == team
    assert departure.rider == rider
    assert departure.kind == Departure.Kind.RETIRED
    assert departure.at == LATER
    assert (departure.rider_name, departure.speciality, departure.age) == (
        "Veteran", Rider.Speciality.CLIMBER, 40,
    )


def test_a_free_agent_retiring_records_nothing(db):
    _veteran(team=None)

    retire_due_riders(at=LATER)

    assert not Departure.objects.exists()


def test_a_rider_below_their_age_records_nothing(team):
    _veteran(team=team, age=24)

    retire_due_riders(at=LATER)

    assert not Departure.objects.exists()


def test_each_team_gets_its_own_retirements(team):
    other = Team.objects.create(name="Team Beta", code="BET", primary_colour="#0000FF")
    _veteran(team=team, name="Mine")
    _veteran(team=other, name="Theirs")

    retire_due_riders(at=LATER)

    assert set(Departure.objects.values_list("team__code", "rider_name")) == {
        ("ALP", "Mine"), ("BET", "Theirs"),
    }


# --- Graduate release -----------------------------------------------------


def test_a_recorded_release_is_against_the_squads_team(team, squad):
    rider = _graduate(squad)

    release_graduates([rider.pk], at=LATER, record=True)

    departure = Departure.objects.get()
    assert departure.team == team
    assert departure.rider == rider
    assert departure.kind == Departure.Kind.RELEASED
    assert departure.speciality == Rider.Speciality.SPRINTER


def test_an_unrecorded_release_writes_nothing(squad):
    rider = _graduate(squad)

    release_graduates([rider.pk], at=LATER, record=False)

    assert not Departure.objects.exists()


def test_a_rider_who_was_not_released_is_not_recorded(squad):
    prospect = Rider.objects.create(
        name="Prospect", age=18, development_squad=squad, intake_at=AT, **ATTRS,
    )

    release_graduates([prospect.pk], at=LATER, record=True)

    assert not Departure.objects.exists()


def test_closing_the_squad_records_nothing(team, squad):
    """The manager closed it: they were there."""
    _graduate(squad)

    close_squad(team, at=LATER)

    assert not Departure.objects.exists()


def test_a_deleted_rider_keeps_their_departure_by_name(team, squad):
    """Free-agent expiry deletes riders who never raced, a released graduate
    among them; the manager should still see who it was."""
    rider = _graduate(squad, name="Gone For Good")
    release_graduates([rider.pk], at=LATER, record=True)

    rider.delete()

    departure = Departure.objects.get()
    assert departure.rider is None
    assert departure.rider_name == "Gone For Good"
