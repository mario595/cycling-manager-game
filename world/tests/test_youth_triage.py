"""The squad's own clock: development, graduation, and the window in which a
graduate is still the squad's to decide about (#34).

Every test here drives the real `tick()` across real week boundaries, because
the whole feature is a statement about *time* — a spell is 14 weeks, a window
is 2, and a boundary is when each fires. A test that called
`_graduate_squad_riders` directly would prove the query works and say nothing
about whether it fires on the week the player expects.

`_weeks_ago_cutoff` counts a season's weeks, so most of these declare two
seasons: SPELL_WEEKS is 14 and a season is 12, so no single season is long
enough for anyone to graduate.
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from riders.development_squad import LEVELS
from riders.display import to_display_scale
from riders.models import ENGINE_ATTRIBUTES, DevelopmentSquad, Rider
from schedule.models import Season, Week
from teams.models import Team
from transfers.models import Auction
from transfers.services import list_for_auction
from world.clocks import MockClock
from world.services import get_clock, now, tick

from .test_tick import make_season_with_weeks


@pytest.fixture
def team(db) -> Team:
    return Team.objects.create(name="Team Alpha", code="ALP")


@pytest.fixture
def buyer(db) -> Team:
    """Managed, so the AI market has nothing to do with it: an unmanaged team
    bids on any listing it wants, which would sell the graduate this test is
    trying to keep listed."""
    return Team.objects.create(
        name="Team Bravo", code="BRA", managed_since=now(),
    )


def open_squad(team, level: int = 1) -> DevelopmentSquad:
    return DevelopmentSquad.objects.create(team=team, level=level, opened_at=now())


def two_seasons(starts_at) -> Season:
    """Season 1 and season 2 back to back — 24 weeks, long enough for a full
    14-week spell plus the 2-week window after it."""
    first = make_season_with_weeks(1, starts_at)
    make_season_with_weeks(2, starts_at + timedelta(weeks=12))
    return first


def week(number: int) -> Week:
    """The `number`th week boundary of the game, counting across seasons —
    `Week.number` restarts at 1 each season, but a 14-week spell spans them,
    so "week 18" has to mean the 18th boundary overall."""
    return Week.objects.order_by("starts_at")[number - 1]


def tick_into(number: int):
    """Set the clock just inside week `number` and tick everything up to and
    including it."""
    target = week(number)
    get_clock().set(target.starts_at + timedelta(hours=1))
    return tick()


def arrivals(team) -> list[Rider]:
    """The squad's first batch, which arrives at week 4's boundary — two
    riders, both starting their 14-week spell there."""
    return list(
        Rider.objects.filter(development_squad__team=team, graduated_at=None),
    )


def _prospect(squad, *, intake_at, name="Prospect", potential=70, value=50) -> Rider:
    return Rider.objects.create(
        name=name, development_squad=squad, intake_at=intake_at,
        potential=potential,
        climb=value, sprint=value, flat=value, resistance=value, positioning=value,
    )


def test_a_week_four_arrival_graduates_after_fourteen_weeks(db, team):
    """The load-bearing timing test: arriving at week 4's boundary, the squad's
    first batch is still prospects at week 17 and graduated at week 18."""
    two_seasons(now())
    open_squad(team)
    tick_into(4)
    batch = arrivals(team)
    assert len(batch) == 2

    tick_into(17)
    for rider in batch:
        rider.refresh_from_db()
        assert rider.graduated_at is None
        assert rider.development_squad_id is not None

    graduating = week(18)
    run = tick_into(18)
    for rider in batch:
        rider.refresh_from_db()
        # They keep their squad link: graduated, not released. That is what
        # makes them the squad's to promote, list or discard.
        assert rider.graduated_at == graduating.starts_at
        assert rider.development_squad_id is not None
        assert rider.team_id is None
    assert run.youth_graduated == 2


def test_nobody_graduates_before_fourteen_weeks_have_opened(db, team):
    """A first season is 12 weeks: too short for anyone to graduate, and a
    squad must not hand out degrees early because the game started mid-season."""
    make_season_with_weeks(1, now())
    open_squad(team)

    run = tick_into(12)

    assert run.youth_graduated == 0
    assert Rider.objects.filter(
        development_squad__team=team, graduated_at__isnull=False,
    ).count() == 0


def test_graduation_frees_the_place_for_a_batch_arriving_the_same_week(db, team):
    """Graduation runs before intake, and that order is load-bearing (#34):
    without it a rider leaving and a batch arriving at the same boundary
    collide on the last place and the batch is turned away.

    Six prospects fill the squad at level 1. Only the veteran is due to
    graduate at week 20 — the rest arrived at week 8 and still have six weeks
    to run — so exactly one place opens, and week 20's intake of two finds
    one place and one space at the door.
    """
    two_seasons(now())
    squad = open_squad(team)
    capacity = LEVELS[squad.level].places
    for index in range(capacity - 1):
        _prospect(squad, intake_at=week(8).starts_at, name=f"Holding {index}")
    veteran = _prospect(squad, intake_at=week(6).starts_at, name="Veteran")

    # Into week 19 first, so the tick under test covers week 20 alone: one
    # tick catching up nineteen weeks would also report the batches turned
    # away at weeks 4, 8 and 12.
    tick_into(19)
    run = tick_into(20)
    veteran.refresh_from_db()

    assert run.youth_graduated == 1
    assert veteran.graduated_at == week(20).starts_at
    assert run.youth_intake_riders == 1  # the place they freed was used
    assert run.youth_intake_turned_away == 1  # and the rest were not
    assert Rider.objects.filter(
        development_squad=squad, graduated_at__isnull=True,
    ).count() == capacity


def test_a_graduates_window_closes_two_weeks_after_graduating(db, team):
    """Graduate, then decide: for two weeks they are still the squad's, and at
    the boundary after that they go to the free-agent pool stamped."""
    two_seasons(now())
    open_squad(team)
    tick_into(4)
    batch = arrivals(team)
    tick_into(18)  # graduates

    one_week_later = tick_into(19)
    for rider in batch:
        rider.refresh_from_db()
    assert one_week_later.youth_graduates_released == 0  # a week of window left
    assert all(r.development_squad_id is not None for r in batch)

    closing = week(20)
    run = tick_into(20)
    for rider in batch:
        rider.refresh_from_db()
        assert rider.development_squad_id is None
        assert rider.team_id is None
        assert rider.unattached_since == closing.starts_at
    assert run.youth_graduates_released == 2


def test_a_listed_graduate_is_not_pulled_out_from_under_their_auction(db, team, buyer):
    """The window skips a graduate with an OPEN auction (#34): the auction's
    outcome decides, and releasing them at the boundary would put them in the
    free-agent pool mid-auction and cancel a sale the seller was owed.

    Listed at week 19, inside the window: the auction's three-day deadline
    has not passed when week 20's boundary closes the window, so this is
    exactly the collision the decision exists to avoid. Note what the tick
    then does — the window skips them, and the auction resolves unsold at
    the end of the same tick, which releases them. Both riders land in the
    pool stamped with the *tick's* timestamp rather than the boundary's,
    which is how this test tells those two steps apart.
    """
    two_seasons(now())
    open_squad(team)
    tick_into(4)
    batch = arrivals(team)
    tick_into(18)  # graduates; window closes at week 20

    tick_into(19)
    auctions = [list_for_auction(team, r.pk, at=week(19).starts_at) for r in batch]

    run = tick_into(20)
    resolved_at = week(20).starts_at + timedelta(hours=1)

    # The window's own report: nobody was released by it.
    assert run.youth_graduates_released == 0
    # The unsold resolution, not the boundary, is what let them go.
    assert all(
        Auction.objects.get(pk=a.pk).status == Auction.Status.UNSOLD for a in auctions
    )
    for rider in batch:
        rider.refresh_from_db()
        assert rider.development_squad_id is None
        assert rider.team_id is None
        assert rider.unattached_since == resolved_at


def test_a_squad_rider_develops_faster_than_an_identical_rider_with_no_squad(db, team):
    """The spell has to be worth paying for: two riders with identical
    attributes and potential, one in the squad and one on a roster, and over a
    season the squad rider's are clearly ahead.

    Compared as a summed display total, and over a whole spell rather than a
    week: squad growth is spread across the five attributes and floored on the
    0-10 display scale, so a single week is too small to show — the same
    lesson as `test_every_youth_gains_over_a_spell`.
    """
    two_seasons(now())
    squad = open_squad(team)
    tick_into(1)
    started = week(1).starts_at
    # A high potential against low attributes leaves plenty of headroom, so
    # the difference is several display points rather than one.
    prospect = _prospect(
        squad, intake_at=started, name="Prospect", potential=90, value=40,
    )
    plain = Rider.objects.create(
        name="Plain", team=team, potential=90,
        climb=40, sprint=40, flat=40, resistance=40, positioning=40,
    )
    before = (_display_total(prospect), _display_total(plain))

    tick_into(18)
    prospect.refresh_from_db()
    plain.refresh_from_db()

    prospect_gain = _display_total(prospect) - before[0]
    plain_gain = _display_total(plain) - before[1]

    assert prospect.graduated_at == week(15).starts_at  # a full spell
    assert prospect_gain > plain_gain
    # Not merely "not worse": squad development is a large share of a spell.
    assert prospect_gain >= plain_gain + 2


def _display_total(rider: Rider) -> int:
    """Sum of the rider's five floored display attributes — the value the
    player actually reads."""
    return sum(to_display_scale(getattr(rider, name)) for name in ENGINE_ATTRIBUTES)


def test_the_tick_counters_match(db, team):
    """Every new TickRun field is checked against what the week actually did,
    because these are what the dashboard reports."""
    two_seasons(now())
    open_squad(team)

    intake = tick_into(4)
    assert intake.youth_intake_riders == 2
    assert intake.youth_intake_turned_away == 0
    assert intake.youth_graduated == 0
    assert intake.youth_graduates_released == 0

    graduating = tick_into(18)
    assert graduating.youth_graduated == 2  # the whole week-4 batch
    assert graduating.youth_graduates_released == 0

    # Week 20 is an intake week and the week-8 batch is not due until week 22.
    releasing = tick_into(20)
    assert releasing.youth_graduated == 0
    assert releasing.youth_graduates_released == 2  # the week-18 batch's window
    assert releasing.youth_intake_riders == 2  # two places freed at week 18


def test_a_full_squad_reports_the_riders_it_turned_away(db, team):
    """The counter the squad screen warns with before the week arrives."""
    season = make_season_with_weeks(1, now())
    squad = open_squad(team)
    for index in range(LEVELS[squad.level].places):
        _prospect(squad, intake_at=season.weeks.get(number=1).starts_at)

    run = tick_into(4)

    assert run.youth_intake_riders == 0
    assert run.youth_intake_turned_away == 2