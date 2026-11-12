"""seed_world, add_season and the world wipe (#139, specs/archive/beta-world.md)."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone as dt_timezone

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import override_settings

from accounts.models import User
from economy.models import SponsorOffer
from racing.models import Race
from schedule.models import Season
from staff.models import Trainer
from teams.models import Team
from world.services import now
from world.world_setup import WORLD_CALENDAR, next_monday

START = "2030-01-07"  # a Monday


@pytest.fixture
def calendar(tmp_path):
    """A one-race calendar: seed_world's behaviour does not depend on what
    the calendar holds, and the real one is checked on its own below."""
    path = tmp_path / "calendar.json"
    path.write_text(json.dumps({
        "number": 1,
        "starts_at": "2027-03-01T00:00:00Z",
        "races": [{
            "week": 1, "day": "sunday", "time": "14:00", "name": "Test Classic",
            "course": [{"length": 50000, "gradient": 0.0}],
        }],
    }))
    return str(path)


def seed(calendar, *args):
    call_command(
        "seed_world", "--calendar", calendar, "--starts-at", START,
        "--teams", "4", "--trainers", "3", *args,
    )


def test_builds_teams_trainers_and_chained_seasons(db, calendar):
    seed(calendar)

    assert Team.objects.count() == 4
    assert not Team.objects.filter(manager__isnull=False).exists()
    assert Trainer.objects.count() == 3
    seasons = list(Season.objects.order_by("number"))
    assert [s.number for s in seasons] == [1, 2, 3, 4]
    assert seasons[0].starts_at.isoformat() == "2030-01-07T00:00:00+00:00"
    for earlier, later in zip(seasons, seasons[1:]):
        assert later.starts_at == earlier.ends_at
    assert Race.objects.count() == 4


def test_never_creates_a_user(db, calendar):
    seed(calendar)

    assert not User.objects.exists()


def test_defaults_to_the_next_monday(db, calendar):
    call_command("seed_world", "--calendar", calendar, "--teams", "2", "--trainers", "1",
                 "--seasons", "1")

    assert Season.objects.get().starts_at == next_monday(now())


def test_refuses_to_build_over_an_existing_world(db, calendar):
    seed(calendar)

    with pytest.raises(CommandError, match="already exists"):
        seed(calendar)


def test_refuses_a_start_that_is_not_a_monday_and_creates_nothing(db, calendar):
    with pytest.raises(CommandError, match="Monday"):
        call_command("seed_world", "--calendar", calendar, "--starts-at", "2030-01-08")

    assert not Team.objects.exists()


def test_set_clock_opens_season_one_with_sponsor_offers(db, calendar):
    seed(calendar, "--set-clock", "--seasons", "1")

    assert now() == datetime(2030, 1, 7, tzinfo=dt_timezone.utc)
    season = Season.objects.get()
    assert season.transitions.filter(kind="opened").exists()
    for team in Team.objects.all():
        assert SponsorOffer.objects.filter(team=team, season=season).exists()


def test_set_clock_is_refused_on_the_real_clock(db, calendar):
    import world.services as world_services

    world_services._clock = None
    with override_settings(GAME_CLOCK_CLASS="world.clocks.RealClock"):
        with pytest.raises(CommandError, match="MockClock"):
            seed(calendar, "--set-clock")
    world_services._clock = None
    assert not Team.objects.exists()


def test_reset_wipes_the_world_but_keeps_accounts(db, calendar):
    seed(calendar)
    user = User.objects.create_user(email="agent@example.com", password="x")
    team = Team.objects.first()
    team.manager = user
    team.save(update_fields=["manager"])

    seed(calendar, "--reset", "--seasons", "1")

    assert User.objects.filter(pk=user.pk).exists()
    assert Team.objects.count() == 4
    assert not Team.objects.filter(manager=user).exists()
    assert Season.objects.count() == 1
    assert Trainer.objects.count() == 3


@override_settings(ALLOW_WORLD_RESET=False)
def test_reset_is_refused_where_not_allowed(db, calendar):
    seed(calendar)

    with pytest.raises(CommandError, match="ALLOW_WORLD_RESET"):
        seed(calendar, "--reset")

    assert Season.objects.count() == 4


def test_add_season_appends_where_the_last_one_ends(db, calendar):
    seed(calendar, "--seasons", "2")
    last = Season.objects.get(number=2)

    call_command("add_season", "--calendar", calendar)

    added = Season.objects.get(number=3)
    assert added.starts_at == last.ends_at
    assert added.ends_at - added.starts_at == timedelta(weeks=12)


def test_add_season_needs_a_world(db, calendar):
    with pytest.raises(CommandError, match="seed_world"):
        call_command("add_season", "--calendar", calendar)


def test_the_world_calendar_loads(db):
    """The real calendar is a valid season file — the cheap half of its
    check. Whether it is *balanced* is `check_calendar`'s job, which is too
    slow for the suite (see world/README.md, *The world calendar*)."""
    call_command("load_season", str(WORLD_CALENDAR), "--starts-at", START)

    season = Season.objects.get()
    assert Race.objects.filter(week__season=season).count() >= 20


def test_reset_keeps_reports_detached_from_the_wiped_teams(db, calendar):
    """A report outlives the world it was filed in (#131): the wipe's
    TRUNCATE … CASCADE must not reach feedback_report, and the report must
    not point at whichever new team reuses its old team's id."""
    from feedback.models import Report

    seed(calendar)
    user = User.objects.create_user(email="agent@example.com", password="x")
    team = Team.objects.first()
    report = Report.objects.create(
        author=user, category=Report.Category.BUG, text="Wages doubled.",
        team=team, team_name=team.name, game_time=now(),
        status=Report.Status.TRIAGED, triage_note="Seen it.",
    )

    seed(calendar, "--reset", "--seasons", "1")

    report.refresh_from_db()
    assert report.team is None
    assert report.team_name == team.name
    assert report.status == Report.Status.TRIAGED
    assert report.triage_note == "Seen it."
