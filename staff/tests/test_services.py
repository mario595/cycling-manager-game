from __future__ import annotations

from datetime import datetime, timedelta, timezone as dt_timezone

import pytest

from schedule.models import Season, Week
from staff.generation import TRAINERS_PER_SEASON_BOUNDARY
from staff.models import DEFAULT_FOCUS, Trainer, TrainingFocus, TrainingWeekReport
from staff.services import (
    InsufficientFunds,
    NoTrainerHired,
    SlotOccupied,
    TrainerNotAvailable,
    available_trainers,
    fire_trainer,
    focus_for,
    hire_trainer,
    latest_report,
    set_focus,
    top_up_pool,
)


def test_hire_fills_the_slot(trainer, team):
    hire_trainer(team, trainer.pk)

    trainer.refresh_from_db()
    assert trainer.team_id == team.pk
    assert trainer not in available_trainers()


def test_hire_a_trainer_already_hired_is_refused(trainer, team, other_team):
    hire_trainer(team, trainer.pk)

    with pytest.raises(TrainerNotAvailable):
        hire_trainer(other_team, trainer.pk)

    trainer.refresh_from_db()
    assert trainer.team_id == team.pk


def test_hire_when_slot_occupied_is_refused(trainer, team):
    hire_trainer(team, trainer.pk)
    second = Trainer.objects.create(
        name="Coach Two",
        climb=30,
        sprint=90,
        flat=45,
        resistance=50,
        positioning=35,
    )

    with pytest.raises(SlotOccupied):
        hire_trainer(team, second.pk)


def test_hire_unknown_id_is_refused(team):
    with pytest.raises(TrainerNotAvailable):
        hire_trainer(team, 999999)


def test_hire_invokes_charge(trainer, team):
    called = []

    def charge(t):
        called.append(t)

    hire_trainer(team, trainer.pk, charge=charge)

    assert called == [trainer]
    trainer.refresh_from_db()
    assert trainer.team_id == team.pk


def test_charge_raising_rolls_back_the_hire(trainer, team):
    def charge(t):
        raise InsufficientFunds("Not enough credits.")

    with pytest.raises(InsufficientFunds):
        hire_trainer(team, trainer.pk, charge=charge)

    trainer.refresh_from_db()
    assert trainer.team is None
    assert trainer in available_trainers()


def test_hire_without_charge_still_works(trainer, team):
    # The seed path: an unemployed trainer exists to be claimed, fee-free.
    hire_trainer(team, trainer.pk)

    trainer.refresh_from_db()
    assert trainer.team_id == team.pk


def test_charge_not_called_when_trainer_already_taken(trainer, team, other_team):
    hire_trainer(team, trainer.pk)
    called = []

    def charge(t):
        called.append(t)

    with pytest.raises(TrainerNotAvailable):
        hire_trainer(other_team, trainer.pk, charge=charge)

    assert called == []


def test_fire_returns_the_trainer_to_the_pool(trainer, team):
    hire_trainer(team, trainer.pk)

    fire_trainer(team)

    trainer.refresh_from_db()
    assert trainer.team is None
    assert trainer in available_trainers()


def test_fire_with_no_trainer_is_refused(team):
    with pytest.raises(NoTrainerHired):
        fire_trainer(team)


def test_fired_trainer_can_be_rehired_by_the_same_team(trainer, team):
    hire_trainer(team, trainer.pk)
    fire_trainer(team)

    hire_trainer(team, trainer.pk)

    trainer.refresh_from_db()
    assert trainer.team_id == team.pk


def test_top_up_only_adds(trainer, team):
    hire_trainer(team, trainer.pk)
    before_count = Trainer.objects.count()

    top_up_pool()

    assert Trainer.objects.count() == before_count + TRAINERS_PER_SEASON_BOUNDARY
    trainer.refresh_from_db()
    assert trainer.team_id == team.pk


def test_set_focus_requires_a_trainer(team):
    with pytest.raises(NoTrainerHired):
        set_focus(team, "climb")


def test_focus_defaults_without_writing_a_row(trainer, team):
    hire_trainer(team, trainer.pk)

    assert focus_for(team) == DEFAULT_FOCUS
    assert not TrainingFocus.objects.filter(team=team).exists()


def test_set_focus_creates_the_row(trainer, team):
    hire_trainer(team, trainer.pk)

    focus = set_focus(team, "sprint")

    assert focus.attribute == "sprint"
    assert focus_for(team) == "sprint"
    assert TrainingFocus.objects.filter(team=team).count() == 1


def test_set_focus_updates_an_existing_row(trainer, team):
    hire_trainer(team, trainer.pk)
    first = set_focus(team, "sprint")

    second = set_focus(team, "flat")

    assert second.pk == first.pk
    assert focus_for(team) == "flat"


def test_set_focus_rejects_an_unknown_attribute(trainer, team):
    hire_trainer(team, trainer.pk)

    with pytest.raises(ValueError):
        set_focus(team, "luck")


def _make_week(season, number, monday):
    return Week.objects.create(
        season=season, number=number, starts_at=monday, ends_at=monday + timedelta(weeks=1),
    )


def test_latest_report_returns_the_most_recent_week(db, trainer, team):
    hire_trainer(team, trainer.pk)
    monday = datetime(2027, 3, 1, 0, 0, tzinfo=dt_timezone.utc)
    season = Season.objects.create(number=1, starts_at=monday)
    week_one = _make_week(season, 1, monday)
    week_two = _make_week(season, 2, monday + timedelta(weeks=1))
    old = TrainingWeekReport.objects.create(team=team, week=week_one, attribute="flat")
    recent = TrainingWeekReport.objects.create(team=team, week=week_two, attribute="climb")

    assert latest_report(team).pk == recent.pk
    assert latest_report(team).pk != old.pk


def test_latest_report_is_none_without_one(db, team):
    assert latest_report(team) is None
