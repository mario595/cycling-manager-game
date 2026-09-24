from __future__ import annotations

from datetime import timedelta

import pytest

from accounts.models import User
from schedule.models import SEASON_WEEKS, Season, Week
from schedule.services import weeks_opened_between
from teams.models import ManagerialSpell, Team
from world.clocks import MockClock
from world.services import INACTIVITY_WEEKS, get_clock, now, tick


def make_season_with_weeks(number: int, starts_at) -> Season:
    season = Season.objects.create(number=number, starts_at=starts_at)
    for week_number in range(1, SEASON_WEEKS + 1):
        week_start = season.starts_at + timedelta(weeks=week_number - 1)
        Week.objects.create(
            season=season,
            number=week_number,
            starts_at=week_start,
            ends_at=week_start + timedelta(weeks=1),
        )
    return season


@pytest.fixture
def manager(db) -> User:
    return User.objects.create_user(email="manager@example.com", password="s0meth1ng-good")


@pytest.fixture
def team(db, manager) -> Team:
    return Team.objects.create(name="Team Alpha", code="ALP", manager=manager)


# -- schedule.services.weeks_opened_between --------


def test_counts_weeks_that_opened_in_the_interval(db):
    season = make_season_with_weeks(1, now())

    last_seen = season.weeks.get(number=1).starts_at
    boundary = season.weeks.get(number=6).starts_at

    assert weeks_opened_between(last_seen, boundary) == 5


def test_off_season_gap_contributes_no_weeks(db):
    # Two seasons with a real gap between them. A span crossing the gap
    # must count only the in-season weeks on either side of it, never the
    # calendar time the gap itself spans.
    season_one = make_season_with_weeks(1, now())
    gap_start = season_one.ends_at
    season_two_start = gap_start + timedelta(weeks=4)
    season_two = make_season_with_weeks(2, season_two_start)

    last_seen = season_one.weeks.get(number=11).starts_at  # two weeks before season one ends
    boundary = season_two.weeks.get(number=2).starts_at    # one week into season two

    # season one's weeks 11-12 (2) + season two's week 1 (1) = 3, not the
    # 6 weeks that separate the two timestamps by the calendar.
    assert weeks_opened_between(last_seen, boundary) == 3


def test_week_opening_exactly_at_last_seen_is_not_counted(db):
    season = make_season_with_weeks(1, now())
    week_one = season.weeks.get(number=1)

    assert weeks_opened_between(week_one.starts_at, week_one.starts_at) == 0


# -- _release_inactive / tick() -----------------------------------------


def test_releases_a_manager_inactive_ten_weeks(db, manager, team):
    clock: MockClock = get_clock()
    season = make_season_with_weeks(1, now())
    manager.last_seen_at = season.weeks.get(number=1).starts_at
    manager.save(update_fields=["last_seen_at"])
    clock.set(season.weeks.get(number=11).starts_at + timedelta(hours=1))

    run = tick()

    team.refresh_from_db()
    assert team.manager_id is None
    assert run.teams_released == 1


def test_leaves_a_manager_inactive_nine_weeks(db, manager, team):
    clock: MockClock = get_clock()
    season = make_season_with_weeks(1, now())
    manager.last_seen_at = season.weeks.get(number=1).starts_at
    manager.save(update_fields=["last_seen_at"])
    clock.set(season.weeks.get(number=10).starts_at + timedelta(hours=1))

    run = tick()

    team.refresh_from_db()
    assert team.manager_id == manager.pk
    assert run.teams_released == 0


def test_never_logged_in_manager_is_exempt(db, manager, team):
    clock: MockClock = get_clock()
    season = make_season_with_weeks(1, now())
    assert manager.last_seen_at is None
    clock.set(season.weeks.get(number=12).starts_at + timedelta(hours=1))

    run = tick()

    team.refresh_from_db()
    assert team.manager_id == manager.pk
    assert run.teams_released == 0


def test_unmanaged_teams_are_untouched(db):
    clock: MockClock = get_clock()
    season = make_season_with_weeks(1, now())
    Team.objects.create(name="Pool Team", code="POL")
    clock.set(season.weeks.get(number=12).starts_at + timedelta(hours=1))

    run = tick()

    assert run.teams_released == 0


def test_release_records_inactivity_reason(db, manager, team):
    clock: MockClock = get_clock()
    season = make_season_with_weeks(1, now())
    manager.last_seen_at = season.weeks.get(number=1).starts_at
    manager.save(update_fields=["last_seen_at"])
    clock.set(season.weeks.get(number=11).starts_at + timedelta(hours=1))

    tick()

    spell = ManagerialSpell.objects.get(manager=manager)
    assert spell.reason == ManagerialSpell.Reason.INACTIVITY
    assert spell.team_id == team.pk


def test_a_late_tick_evaluates_each_boundary_separately(db, manager, team):
    # A catch-up tick that jumps straight from before week 1 to week 12 in
    # one go must date the release to the boundary that actually crossed
    # the threshold (week 11's starts_at, ten weeks after week 1's), not to
    # `at` — the tick's own read time, days after week 12 opened. Using
    # `at` for every week's boundary would still release the team (both
    # readings exceed ten weeks by week 11), but would record the wrong
    # ended_at: this asserts the spell is dated to week 11, catching a
    # boundary collapsed to the tick's `at` rather than each week's own
    # starts_at.
    clock: MockClock = get_clock()
    season = make_season_with_weeks(1, now())
    manager.last_seen_at = season.weeks.get(number=1).starts_at
    manager.save(update_fields=["last_seen_at"])
    clock.set(season.weeks.get(number=12).starts_at + timedelta(days=3))

    tick()

    spell = ManagerialSpell.objects.get(manager=manager)
    assert spell.ended_at == season.weeks.get(number=11).starts_at


def test_a_failed_release_does_not_stop_the_week_loop(db, manager, team, monkeypatch):
    from riders.models import Rider

    Rider.objects.create(
        name="Rider", team=team,
        climb=60, sprint=60, flat=60, resistance=60, positioning=60,
        weekly_salary=1000,
    )
    clock: MockClock = get_clock()
    season = make_season_with_weeks(1, now())
    manager.last_seen_at = season.weeks.get(number=1).starts_at
    manager.save(update_fields=["last_seen_at"])
    clock.set(season.weeks.get(number=11).starts_at + timedelta(hours=1))

    monkeypatch.setattr(
        "world.services.release_team",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")),
    )

    run = tick()

    from economy.models import LedgerEntry
    assert LedgerEntry.objects.filter(team=team, kind=LedgerEntry.Kind.WAGES).exists()
    assert run.teams_released == 0
    assert "boom" in run.error
