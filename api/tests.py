from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone as dt_timezone
from pathlib import Path

import brotli
import pytest
from django.core.files.base import ContentFile
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient

import world.services as world_services
from competitions.models import RacePoints
from competitions.scoring import gc_points_for, gc_prize_for, points_for, prize_for, stage_points_for
from competitions.services import score_general_classification, score_mountains, score_race, score_sprints
from economy.models import STARTING_BALANCE, LedgerEntry, SalaryReviewReport
from racing.models import (
    MarkerCrossing,
    Race,
    RaceLog,
    RaceMarker,
    RaceResult,
    RaceSquad,
    RaceSquadRider,
    StageRace,
)
from racing.services import SquadError, set_squad
from riders.development_squad import LEVELS, close_squad, open_squad
from riders.display import to_display_scale
from riders.models import DISPLAY_MAX, DevelopmentSquad, Rider, RiderAttributeSnapshot
from riders.youth_intake import run_intake
from schedule.models import SEASON_WEEKS, Season, Week
from staff.models import Trainer, TrainingWeekReport
from staff.pricing import hire_fee, weekly_salary
from riders.pricing import weekly_salary_for
from transfers.models import Auction, Bid
from transfers.pricing import market_value_for, severance_fee_for, signing_fee_for
from transfers.services import ROSTER_CAP, list_for_auction
from teams.models import ManagerialSpell, Team
from world.services import now

from accounts.models import User


@override_settings(GAME_CLOCK_CLASS="world.clocks.MockClock")
def test_clock_endpoint_returns_current_game_time(db):
    # MockClock, not whatever GAME_CLOCK_CLASS a developer's environment
    # happens to be running: against RealClock, two separate now() reads
    # (the view's and this assertion's) would almost never match exactly.
    world_services._clock = None
    try:
        client = APIClient()
        user = User.objects.create_user(email="clock@example.com", password="s0meth1ng-good")
        client.force_authenticate(user=user)
        response = client.get("/api/world/clock/")

        assert response.status_code == 200
        assert response.data["current"] == now().isoformat().replace("+00:00", "Z")
    finally:
        world_services._clock = None


@override_settings(GAME_CLOCK_CLASS="world.clocks.MockClock")
def test_position_endpoint_reports_the_current_week(db):
    world_services._clock = None
    try:
        season = Season.objects.create(number=1, starts_at=now())
        Week.objects.create(
            season=season, number=1,
            starts_at=season.starts_at, ends_at=season.starts_at + timedelta(weeks=1),
        )

        client = APIClient()
        user = User.objects.create_user(email="position@example.com", password="s0meth1ng-good")
        client.force_authenticate(user=user)
        response = client.get("/api/schedule/position/")

        assert response.status_code == 200
        assert response.data["state"] == "in_season"
        assert response.data["season"] == 1
        assert response.data["week"] == 1
    finally:
        world_services._clock = None


@override_settings(GAME_CLOCK_CLASS="world.clocks.MockClock")
def test_position_endpoint_reports_no_season_when_none_declared(db):
    world_services._clock = None
    try:
        client = APIClient()
        user = User.objects.create_user(email="position@example.com", password="s0meth1ng-good")
        client.force_authenticate(user=user)
        response = client.get("/api/schedule/position/")

        assert response.status_code == 200
        assert response.data["state"] == "no_season"
        assert response.data["season"] is None
        assert response.data["week"] is None
    finally:
        world_services._clock = None


def _create_season_with_weeks(starts_at) -> Season:
    season = Season.objects.create(number=1, starts_at=starts_at)
    for week_number in range(1, 13):
        week_start = starts_at + timedelta(weeks=week_number - 1)
        Week.objects.create(
            season=season, number=week_number,
            starts_at=week_start, ends_at=week_start + timedelta(weeks=1),
        )
    return season


@override_settings(GAME_CLOCK_CLASS="world.clocks.MockClock")
def test_calendar_returns_twelve_weeks(db):
    world_services._clock = None
    try:
        season = _create_season_with_weeks(now())
        week_one = Week.objects.get(season=season, number=1)
        Race.objects.create(
            name="Opening Classic",
            course=[{"length": 40000.0, "gradient": 0.0}],
            starts_at=week_one.starts_at + timedelta(hours=14),
            week=week_one,
        )

        client = APIClient()
        user = User.objects.create_user(email="calendar@example.com", password="s0meth1ng-good")
        client.force_authenticate(user=user)
        response = client.get("/api/schedule/calendar/")

        assert response.status_code == 200
        assert len(response.data["weeks"]) == 12
        non_empty = [w for w in response.data["weeks"] if w["races"]]
        assert len(non_empty) == 1
        assert non_empty[0]["races"][0]["name"] == "Opening Classic"
    finally:
        world_services._clock = None


@override_settings(GAME_CLOCK_CLASS="world.clocks.MockClock")
def test_calendar_reports_off_season_with_no_weeks(db):
    world_services._clock = None
    try:
        _create_season_with_weeks(now() - timedelta(weeks=13))

        client = APIClient()
        user = User.objects.create_user(email="calendar@example.com", password="s0meth1ng-good")
        client.force_authenticate(user=user)
        response = client.get("/api/schedule/calendar/")

        assert response.status_code == 200
        assert response.data["state"] == "off_season"
        assert response.data["weeks"] == []
    finally:
        world_services._clock = None


@override_settings(GAME_CLOCK_CLASS="world.clocks.MockClock")
def test_calendar_reports_no_season_before_any_is_declared(db):
    world_services._clock = None
    try:
        client = APIClient()
        user = User.objects.create_user(email="calendar@example.com", password="s0meth1ng-good")
        client.force_authenticate(user=user)
        response = client.get("/api/schedule/calendar/")

        assert response.status_code == 200
        assert response.data["state"] == "no_season"
        assert response.data["weeks"] == []
    finally:
        world_services._clock = None


@override_settings(GAME_CLOCK_CLASS="world.clocks.MockClock")
def test_calendar_race_carries_status_and_distance(db):
    world_services._clock = None
    try:
        season = _create_season_with_weeks(now())
        week_one = Week.objects.get(season=season, number=1)
        Race.objects.create(
            name="Opening Classic",
            course=[{"length": 40000.0, "gradient": 0.0}, {"length": 10000.0, "gradient": 0.0}],
            starts_at=week_one.starts_at + timedelta(hours=14),
            week=week_one,
        )

        client = APIClient()
        user = User.objects.create_user(email="calendar@example.com", password="s0meth1ng-good")
        client.force_authenticate(user=user)
        response = client.get("/api/schedule/calendar/")

        race_data = next(w for w in response.data["weeks"] if w["races"])["races"][0]
        assert race_data["status"] == "scheduled"
        assert race_data["distance_km"] == 50.0
    finally:
        world_services._clock = None


@override_settings(GAME_CLOCK_CLASS="world.clocks.MockClock")
def test_calendar_race_carries_stage_race(db):
    world_services._clock = None
    try:
        season = _create_season_with_weeks(now())
        week_one = Week.objects.get(season=season, number=1)
        stage_race = StageRace.objects.create(name="Alpine Tour", week=week_one)
        for n in range(1, 4):
            Race.objects.create(
                name=f"Alpine Tour — Stage {n}",
                course=[{"length": 40000.0, "gradient": 0.0}],
                starts_at=week_one.starts_at + timedelta(days=n - 1, hours=14),
                week=week_one, stage_race=stage_race, stage_number=n,
            )

        client = APIClient()
        user = User.objects.create_user(email="calendar-stage@example.com", password="s0meth1ng-good")
        client.force_authenticate(user=user)
        response = client.get("/api/schedule/calendar/")

        week_data = next(w for w in response.data["weeks"] if w["races"])
        assert len(week_data["races"]) == 3
        for race_data in week_data["races"]:
            assert race_data["stage_race"]["name"] == "Alpine Tour"
            assert race_data["stage_race"]["stage_count"] == 3
        assert [r["stage_race"]["stage_number"] for r in week_data["races"]] == [1, 2, 3]
    finally:
        world_services._clock = None


@override_settings(GAME_CLOCK_CLASS="world.clocks.MockClock")
def test_calendar_query_count_does_not_grow_with_stages(db, django_assert_max_num_queries):
    world_services._clock = None
    try:
        season = _create_season_with_weeks(now())
        week_one = Week.objects.get(season=season, number=1)
        stage_race = StageRace.objects.create(name="Long Tour", week=week_one)
        for n in range(1, 6):
            Race.objects.create(
                name=f"Long Tour — Stage {n}",
                course=[{"length": 40000.0, "gradient": 0.0}],
                starts_at=week_one.starts_at + timedelta(days=n - 1, hours=14),
                week=week_one, stage_race=stage_race, stage_number=n,
            )

        client = APIClient()
        user = User.objects.create_user(email="calendar-queries@example.com", password="s0meth1ng-good")
        client.force_authenticate(user=user)

        with django_assert_max_num_queries(15):
            response = client.get("/api/schedule/calendar/")
        assert response.status_code == 200
    finally:
        world_services._clock = None


def test_clock_requires_login(db):
    client = APIClient()

    assert client.get("/api/world/clock/").status_code == 403

    user = User.objects.create_user(email="clocker@example.com", password="s0meth1ng-good")
    client.force_authenticate(user=user)

    assert client.get("/api/world/clock/").status_code == 200


def test_position_requires_login(db):
    client = APIClient()

    assert client.get("/api/schedule/position/").status_code == 403

    user = User.objects.create_user(email="positioner@example.com", password="s0meth1ng-good")
    client.force_authenticate(user=user)

    assert client.get("/api/schedule/position/").status_code == 200


def test_calendar_requires_login(db):
    client = APIClient()

    assert client.get("/api/schedule/calendar/").status_code == 403

    user = User.objects.create_user(email="calendars@example.com", password="s0meth1ng-good")
    client.force_authenticate(user=user)

    assert client.get("/api/schedule/calendar/").status_code == 200


def test_me_reports_anonymous_for_a_visitor(db):
    response = APIClient().get("/api/accounts/me/")

    assert response.status_code == 200
    assert response.data["authenticated"] is False
    assert response.data["display_name"] is None
    assert response.data["team"] is None


def test_me_reports_the_logged_in_player_and_their_team(db):
    user = User.objects.create_user(email="mario@example.com", password="s0meth1ng-good", display_name="Mario")
    Team.objects.create(name="Squad Team", code="SQD", manager=user)
    client = APIClient()
    client.force_authenticate(user=user)

    response = client.get("/api/accounts/me/")

    assert response.status_code == 200
    assert response.data["authenticated"] is True
    assert response.data["display_name"] == "Mario"
    assert response.data["team"]["name"] == "Squad Team"


def test_me_reports_null_team_for_a_player_without_one(db):
    user = User.objects.create_user(email="mario@example.com", password="s0meth1ng-good")
    client = APIClient()
    client.force_authenticate(user=user)

    response = client.get("/api/accounts/me/")

    assert response.status_code == 200
    assert response.data["authenticated"] is True
    assert response.data["team"] is None


def test_me_sets_the_csrf_cookie(db):
    response = APIClient(enforce_csrf_checks=True).get("/api/accounts/me/")

    assert response.status_code == 200
    assert "csrftoken" in response.cookies


def test_me_reports_lost_team_for_teamless_ex_manager(db):
    user = User.objects.create_user(email="ex-manager@example.com", password="s0meth1ng-good")
    ManagerialSpell.objects.create(
        manager=user,
        team_name="Lost Team",
        team_code="LST",
        ended_at=timezone.now(),
        reason=ManagerialSpell.Reason.ADMIN,
    )
    client = APIClient()
    client.force_authenticate(user=user)

    response = client.get("/api/accounts/me/")

    assert response.status_code == 200
    assert response.data["team"] is None
    assert response.data["lost_team"]["name"] == "Lost Team"
    assert response.data["lost_team"]["code"] == "LST"
    assert response.data["lost_team"]["reason"] == "Released by an operator"


def test_me_omits_lost_team_once_acknowledged(db):
    user = User.objects.create_user(email="ex-manager2@example.com", password="s0meth1ng-good")
    ManagerialSpell.objects.create(
        manager=user,
        team_name="Lost Team",
        team_code="LST",
        ended_at=timezone.now(),
        acknowledged_at=timezone.now(),
        reason=ManagerialSpell.Reason.ADMIN,
    )
    client = APIClient()
    client.force_authenticate(user=user)

    response = client.get("/api/accounts/me/")

    assert response.data["lost_team"] is None


def test_me_omits_lost_team_when_user_has_claimed_again(db):
    user = User.objects.create_user(email="ex-manager3@example.com", password="s0meth1ng-good")
    ManagerialSpell.objects.create(
        manager=user,
        team_name="Lost Team",
        team_code="LST",
        ended_at=timezone.now(),
        reason=ManagerialSpell.Reason.ADMIN,
    )
    Team.objects.create(name="New Team", code="NEW", manager=user)
    client = APIClient()
    client.force_authenticate(user=user)

    response = client.get("/api/accounts/me/")

    assert response.data["team"]["name"] == "New Team"
    assert response.data["lost_team"] is None


def test_acknowledge_spell_is_idempotent(db):
    user = User.objects.create_user(email="ex-manager4@example.com", password="s0meth1ng-good")
    spell = ManagerialSpell.objects.create(
        manager=user,
        team_name="Lost Team",
        team_code="LST",
        ended_at=timezone.now(),
        reason=ManagerialSpell.Reason.ADMIN,
    )
    client = APIClient()
    client.force_authenticate(user=user)

    first = client.post(f"/api/teams/spells/{spell.pk}/acknowledge/")
    second = client.post(f"/api/teams/spells/{spell.pk}/acknowledge/")

    assert first.status_code == 204
    assert second.status_code == 404
    spell.refresh_from_db()
    assert spell.acknowledged_at is not None


def test_acknowledge_another_users_spell_404s(db):
    owner = User.objects.create_user(email="owner@example.com", password="s0meth1ng-good")
    other = User.objects.create_user(email="other@example.com", password="s0meth1ng-good")
    spell = ManagerialSpell.objects.create(
        manager=owner,
        team_name="Lost Team",
        team_code="LST",
        ended_at=timezone.now(),
        reason=ManagerialSpell.Reason.ADMIN,
    )
    client = APIClient()
    client.force_authenticate(user=other)

    response = client.post(f"/api/teams/spells/{spell.pk}/acknowledge/")

    assert response.status_code == 404
    spell.refresh_from_db()
    assert spell.acknowledged_at is None


@pytest.fixture
def squad_manager(db) -> User:
    return User.objects.create_user(email="squad-manager@example.com", password="s0meth1ng-good")


@pytest.fixture
def squad_team(db, squad_manager) -> Team:
    return Team.objects.create(name="Squad Team", code="SQD", manager=squad_manager)


@pytest.fixture
def squad_riders(db, squad_team) -> list[Rider]:
    return [
        Rider.objects.create(
            name=f"Squad Rider {i}", team=squad_team,
            climb=50, sprint=50, flat=50, resistance=50, positioning=50,
        )
        for i in range(4)
    ]


@pytest.fixture
def squad_race(db) -> Race:
    return Race.objects.create(
        name="Squad Check Race",
        course=[{"length": 40000.0, "gradient": 0.0}],
    )


@pytest.fixture
def squad_client(squad_manager) -> APIClient:
    client = APIClient()
    client.force_authenticate(user=squad_manager)
    return client


def test_squad_requires_authentication(squad_race, squad_riders):
    client = APIClient()

    response = client.get(f"/api/racing/races/{squad_race.pk}/squad/")

    assert response.status_code == 403


def test_squad_forbids_a_player_with_no_team(squad_race, squad_riders):
    manager_without_a_team = User.objects.create_user(
        email="no-team@example.com", password="s0meth1ng-good",
    )
    client = APIClient()
    client.force_authenticate(user=manager_without_a_team)

    response = client.get(f"/api/racing/races/{squad_race.pk}/squad/")

    assert response.status_code == 403


def test_squad_returns_the_callers_own_team(squad_race, squad_riders, squad_client):
    response = squad_client.get(f"/api/racing/races/{squad_race.pk}/squad/")

    assert response.status_code == 200
    assert response.data["saved"] is False
    selected = [c for c in response.data["candidates"] if c["selected"]]
    assert len(selected) == 4


def test_squad_put_saves_for_the_callers_own_team(squad_race, squad_riders, squad_team, squad_client):
    body = {
        "rider_ids": [r.pk for r in squad_riders],
        "leader_id": squad_riders[1].pk,
    }

    response = squad_client.put(f"/api/racing/races/{squad_race.pk}/squad/", body, format="json")

    assert response.status_code == 200
    assert response.data["saved"] is True
    squad = RaceSquad.objects.get(race=squad_race, team=squad_team)
    assert squad.members.count() == 4
    assert squad.members.get(is_leader=True).rider_id == squad_riders[1].pk


def test_putting_five_riders_is_a_400(squad_race, squad_riders, squad_team, squad_client):
    extra = Rider.objects.create(
        name="Extra Rider", team=squad_team,
        climb=50, sprint=50, flat=50, resistance=50, positioning=50,
    )
    body = {
        "rider_ids": [r.pk for r in squad_riders] + [extra.pk],
        "leader_id": squad_riders[0].pk,
    }

    response = squad_client.put(f"/api/racing/races/{squad_race.pk}/squad/", body, format="json")

    assert response.status_code == 400


@pytest.fixture
def squad_stage_race(db, squad_team, squad_riders) -> tuple[Race, Race]:
    """A two-stage tour whose team has already chosen its stage-1 squad."""
    from racing.services import set_squad

    season = Season.objects.create(number=1, starts_at=datetime(2027, 3, 1, tzinfo=dt_timezone.utc))
    week = Week.objects.create(
        season=season, number=1, starts_at=season.starts_at, ends_at=season.starts_at + timedelta(weeks=1),
    )
    stage_race = StageRace.objects.create(name="Alpine Tour", week=week)
    stage1 = Race.objects.create(
        name="Alpine Tour — Stage 1", course=[{"length": 40000.0, "gradient": 0.0}],
        starts_at=week.starts_at, week=week, stage_race=stage_race, stage_number=1,
    )
    stage2 = Race.objects.create(
        name="Alpine Tour — Stage 2", course=[{"length": 40000.0, "gradient": 0.0}],
        starts_at=week.starts_at + timedelta(days=1), week=week, stage_race=stage_race, stage_number=2,
    )
    set_squad(stage1, squad_team, [r.pk for r in squad_riders], squad_riders[0].pk)
    return stage1, stage2


def test_squad_later_stage_is_read_only_carried(squad_stage_race, squad_riders, squad_client):
    _, stage2 = squad_stage_race

    response = squad_client.get(f"/api/racing/races/{stage2.pk}/squad/")

    assert response.status_code == 200
    assert response.data["editable"] is False
    assert response.data["saved"] is True
    assert response.data["stage_race"] == {"name": "Alpine Tour", "stage_number": 2}
    selected = {c["id"] for c in response.data["candidates"] if c["selected"]}
    assert selected == {r.pk for r in squad_riders}
    leader = next(c for c in response.data["candidates"] if c["is_leader"])
    assert leader["id"] == squad_riders[0].pk


def test_squad_put_later_stage_400(squad_stage_race, squad_riders, squad_client):
    _, stage2 = squad_stage_race
    body = {"rider_ids": [r.pk for r in squad_riders], "leader_id": squad_riders[0].pk}

    response = squad_client.put(f"/api/racing/races/{stage2.pk}/squad/", body, format="json")

    assert response.status_code == 400


def test_putting_a_squad_for_a_finished_race_is_a_400(squad_race, squad_riders, squad_client):
    squad_race.status = Race.Status.FINISHED
    squad_race.save(update_fields=["status"])
    body = {
        "rider_ids": [r.pk for r in squad_riders],
        "leader_id": squad_riders[0].pk,
    }

    response = squad_client.put(f"/api/racing/races/{squad_race.pk}/squad/", body, format="json")

    assert response.status_code == 400


def test_unknown_race_is_a_404(squad_client):
    assert squad_client.get("/api/racing/races/999999/squad/").status_code == 404


def test_squad_candidates_use_display_scale(squad_race, squad_riders, squad_client):
    """Load-bearing: the squad screen shows 0-10, not the stored 1-100 —
    see specs/rider-attributes.md, *Display scale*."""
    rider = squad_riders[0]
    rider.climb = 94
    rider.save(update_fields=["climb"])

    response = squad_client.get(f"/api/racing/races/{squad_race.pk}/squad/")

    candidate = next(c for c in response.data["candidates"] if c["id"] == rider.pk)
    assert candidate["climb"] == 9


def test_squad_riders_include_freshness_on_display_scale(squad_race, squad_riders, squad_client):
    rider = squad_riders[0]
    rider.freshness = 30
    rider.save(update_fields=["freshness"])

    response = squad_client.get(f"/api/racing/races/{squad_race.pk}/squad/")

    candidate = next(c for c in response.data["candidates"] if c["id"] == rider.pk)
    assert candidate["freshness"] == to_display_scale(30)
    assert not isinstance(candidate["freshness"], str)


def test_squad_riders_never_expose_recovery_rate(squad_race, squad_riders, squad_client):
    response = squad_client.get(f"/api/racing/races/{squad_race.pk}/squad/")

    assert "recovery_rate" not in response.data["candidates"][0]


@pytest.fixture
def roster_manager(db) -> User:
    return User.objects.create_user(email="roster-manager@example.com", password="s0meth1ng-good")


@pytest.fixture
def roster_team(db, roster_manager) -> Team:
    return Team.objects.create(name="Roster Team", code="ROS", manager=roster_manager)


@pytest.fixture
def roster_rider(db, roster_team) -> Rider:
    return Rider.objects.create(
        name="Roster Rider", team=roster_team,
        speciality=Rider.Speciality.CLIMBER, age=24,
        height_cm=170, weight_kg=60,
        climb=94, sprint=30, flat=40, resistance=80, positioning=52,
    )


@pytest.fixture
def roster_client(roster_manager) -> APIClient:
    client = APIClient()
    client.force_authenticate(user=roster_manager)
    return client


def test_rider_list_requires_authentication(roster_rider):
    client = APIClient()

    assert client.get("/api/riders/").status_code == 403


def test_rider_list_forbids_a_player_with_no_team(db):
    manager_without_a_team = User.objects.create_user(
        email="no-team-roster@example.com", password="s0meth1ng-good",
    )
    client = APIClient()
    client.force_authenticate(user=manager_without_a_team)

    assert client.get("/api/riders/").status_code == 403


def test_rider_list_returns_the_callers_own_team(roster_rider, roster_client):
    response = roster_client.get("/api/riders/")

    assert response.status_code == 200
    assert len(response.data["riders"]) == 1
    rider_data = response.data["riders"][0]
    assert rider_data["id"] == roster_rider.pk
    assert rider_data["name"] == "Roster Rider"
    assert rider_data["speciality"] == "Climber"
    assert rider_data["age"] == 24
    assert rider_data["height_cm"] == 170
    assert rider_data["weight_kg"] == 60
    assert rider_data["climb"] == 9  # display scale, not the stored 94
    assert rider_data["weekly_salary"] == roster_rider.weekly_salary


def test_rider_serializer_hides_traits(roster_rider, roster_client):
    """Load-bearing: the hidden traits must never reach the player. A test
    asserting only the visible fields would pass even if this leaked —
    assert on absence."""
    response = roster_client.get("/api/riders/")

    rider_data = response.data["riders"][0]
    for hidden_field in (
        "potential", "peak_age", "decline_rate",
        "injury_proneness", "training_affinity", "recovery_rate",
    ):
        assert hidden_field not in rider_data


def test_rider_list_includes_freshness_on_display_scale(roster_rider, roster_client):
    roster_rider.freshness = 30
    roster_rider.save(update_fields=["freshness"])

    response = roster_client.get("/api/riders/")

    assert response.data["riders"][0]["freshness"] == to_display_scale(30)


def test_rider_list_never_exposes_recovery_rate(roster_rider, roster_client):
    response = roster_client.get("/api/riders/")

    assert "recovery_rate" not in response.data["riders"][0]


def test_rider_list_weekly_salary_is_exact_not_display_scale(roster_rider, roster_client):
    roster_rider.weekly_salary = 3450
    roster_rider.save(update_fields=["weekly_salary"])

    response = roster_client.get("/api/riders/")

    assert response.data["riders"][0]["weekly_salary"] == 3450


def test_roster_includes_market_value_per_rider(roster_rider, roster_client):
    response = roster_client.get("/api/riders/")

    rider_data = response.data["riders"][0]
    assert rider_data["market_value"] == market_value_for(roster_rider)


def test_roster_includes_squad_value_total(roster_team, roster_rider, roster_client):
    second_rider = Rider.objects.create(
        name="Second Rider", team=roster_team,
        speciality=Rider.Speciality.SPRINTER, age=29,
        height_cm=180, weight_kg=72,
        climb=40, sprint=88, flat=70, resistance=55, positioning=48,
    )

    response = roster_client.get("/api/riders/")

    values = [rider["market_value"] for rider in response.data["riders"]]
    assert len(values) == 2
    assert response.data["squad_value"] == sum(values)


def test_rider_list_response_has_no_hidden_traits(roster_rider, roster_client):
    response = roster_client.get("/api/riders/")

    rider_data = response.data["riders"][0]
    for hidden_field in (
        "potential", "peak_age", "decline_rate",
        "injury_proneness", "training_affinity", "recovery_rate", "growth_debt",
        "retirement_age",
    ):
        assert hidden_field not in rider_data


def test_roster_includes_salary_review_when_one_exists(roster_team, roster_client):
    season = Season.objects.create(number=4, starts_at=now() - timedelta(weeks=12))
    SalaryReviewReport.objects.create(
        team=roster_team, season=season,
        changes=[{"rider_id": 7, "rider_name": "Star", "from": 1900, "to": 2400}],
        payroll_before=1900, payroll_after=2400,
    )

    response = roster_client.get("/api/riders/")

    review = response.data["salary_review"]
    assert review["season_number"] == 4
    assert review["payroll_before"] == 1900
    assert review["payroll_after"] == 2400
    assert review["changes"] == [{
        "rider_id": 7, "rider_name": "Star", "from_value": 1900, "to_value": 2400,
    }]


def test_roster_salary_review_is_null_without_one(roster_team, roster_client):
    response = roster_client.get("/api/riders/")

    assert "salary_review" in response.data
    assert response.data["salary_review"] is None


def test_roster_salary_review_serializes_from_and_to(roster_team, roster_client):
    # Load-bearing: stored changes carry the Python-keyword key "from". The
    # serializer must map it to from_value via source=, never leak a "from"
    # key that would be a syntax error to read in the SPA.
    season = Season.objects.create(number=5, starts_at=now() - timedelta(weeks=12))
    SalaryReviewReport.objects.create(
        team=roster_team, season=season,
        changes=[{"rider_id": 7, "rider_name": "Star", "from": 1900, "to": 2400}],
        payroll_before=1900, payroll_after=2400,
    )

    response = roster_client.get("/api/riders/")

    change = response.data["salary_review"]["changes"][0]
    assert change["from_value"] == 1900
    assert change["to_value"] == 2400
    assert "from" not in change


@pytest.fixture
def claimant(db) -> User:
    return User.objects.create_user(email="claimant@example.com", password="s0meth1ng-good")


@pytest.fixture
def claim_client(claimant) -> APIClient:
    client = APIClient()
    client.force_authenticate(user=claimant)
    return client


def test_claim_requires_authentication(db):
    Team.objects.create(name="Unclaimed Team", code="UNC")
    client = APIClient()

    response = client.post("/api/teams/claim/", {"name": "New Name", "code": "NEW"}, format="json")

    assert response.status_code == 403


@pytest.fixture
def finished_race_with_points(db) -> Race:
    team = Team.objects.create(name="Results Team", code="RES")
    rider = Rider.objects.create(
        name="Winner", team=team,
        climb=50, sprint=50, flat=50, resistance=50, positioning=50,
    )
    race = Race.objects.create(
        name="Results Check Race",
        course=[{"length": 40000.0, "gradient": 0.0}],
        status=Race.Status.FINISHED,
    )
    RaceResult.objects.create(race=race, rider=rider, position=1, finish_time=1000.0)
    score_race(race)
    return race


def test_race_results_returns_order_and_points(finished_race_with_points):
    client = APIClient()
    user = User.objects.create_user(email="viewer@example.com", password="s0meth1ng-good")
    client.force_authenticate(user=user)

    response = client.get(f"/api/racing/races/{finished_race_with_points.pk}/results/")

    assert response.status_code == 200
    assert response.data["race"]["status"] == "finished"
    assert response.data["results"][0]["position"] == 1
    assert response.data["results"][0]["finished"] is True
    assert response.data["points"][0]["points"] == 20


def test_points_include_teams_that_scored_nothing(finished_race_with_points):
    """Load-bearing: starters come from RaceSquad, not from the distinct
    teams in results — a team entered in the race but with no result row
    still gets a zero row. See specs/race-detail-view-plan.md, D3."""
    non_scoring = Team.objects.create(name="Zero Team", code="ZRO")
    RaceSquad.objects.create(race=finished_race_with_points, team=non_scoring)

    client = APIClient()
    user = User.objects.create_user(email="viewer5@example.com", password="s0meth1ng-good")
    client.force_authenticate(user=user)

    response = client.get(f"/api/racing/races/{finished_race_with_points.pk}/results/")

    assert response.status_code == 200
    zero_row = next(p for p in response.data["points"] if p["team"]["id"] == non_scoring.pk)
    assert zero_row["points"] == 0
    assert zero_row["position"] is None
    assert response.data["points"][0]["team"]["id"] != non_scoring.pk


def test_unfinished_race_results_404(db):
    race = Race.objects.create(
        name="Not Yet Run", course=[{"length": 40000.0, "gradient": 0.0}],
        status=Race.Status.SCHEDULED,
    )
    client = APIClient()
    user = User.objects.create_user(email="viewer2@example.com", password="s0meth1ng-good")
    client.force_authenticate(user=user)

    response = client.get(f"/api/racing/races/{race.pk}/results/")

    assert response.status_code == 404


def test_race_results_includes_prize_per_team(finished_race_with_points):
    at = datetime(2027, 3, 2, 0, 0, tzinfo=dt_timezone.utc)
    team = finished_race_with_points.points.get().team
    for position, amount in [(1, 20_000), (5, 8_000)]:
        LedgerEntry.objects.create(
            team=team, kind=LedgerEntry.Kind.PRIZE_MONEY, amount=amount,
            occurred_at=at, race=finished_race_with_points, position=position,
            description=f"Prize money — {finished_race_with_points.name}",
        )

    client = APIClient()
    user = User.objects.create_user(email="viewer3@example.com", password="s0meth1ng-good")
    client.force_authenticate(user=user)

    response = client.get(f"/api/racing/races/{finished_race_with_points.pk}/results/")

    assert response.status_code == 200
    scored_row = next(
        p for p in response.data["points"]
        if p["team"]["id"] == team.pk and p["position"] is not None
    )
    assert scored_row["prize"] == 28_000


def test_race_results_prize_is_zero_for_unplaced_starters(finished_race_with_points):
    non_scoring = Team.objects.create(name="Zero Team", code="ZRO")
    RaceSquad.objects.create(race=finished_race_with_points, team=non_scoring)

    client = APIClient()
    user = User.objects.create_user(email="viewer4@example.com", password="s0meth1ng-good")
    client.force_authenticate(user=user)

    response = client.get(f"/api/racing/races/{finished_race_with_points.pk}/results/")

    assert response.status_code == 200
    zero_row = next(p for p in response.data["points"] if p["team"]["id"] == non_scoring.pk)
    assert zero_row["points"] == 0
    assert zero_row["prize"] == 0


def test_race_results_requires_login(finished_race_with_points):
    client = APIClient()

    response = client.get(f"/api/racing/races/{finished_race_with_points.pk}/results/")

    assert response.status_code == 403


@pytest.fixture
def finished_stage_race(db) -> tuple[Race, Race]:
    """A two-stage tour, both stages finished, squad set and results
    recorded, ready for score_race/score_general_classification."""
    from racing.services import set_squad

    team = Team.objects.create(name="Tour Team", code="TUR")
    riders = [
        Rider.objects.create(
            name=f"Tour Rider {i}", team=team,
            climb=50, sprint=50, flat=50, resistance=50, positioning=50,
        )
        for i in range(4)
    ]
    season = Season.objects.create(number=1, starts_at=datetime(2027, 3, 1, tzinfo=dt_timezone.utc))
    week = Week.objects.create(
        season=season, number=1, starts_at=season.starts_at, ends_at=season.starts_at + timedelta(weeks=1),
    )
    stage_race = StageRace.objects.create(name="Alpine Tour", week=week)
    stage1 = Race.objects.create(
        name="Alpine Tour — Stage 1", course=[{"length": 40000.0, "gradient": 0.0}],
        starts_at=week.starts_at, week=week, stage_race=stage_race, stage_number=1,
        status=Race.Status.FINISHED,
    )
    stage2 = Race.objects.create(
        name="Alpine Tour — Stage 2", course=[{"length": 40000.0, "gradient": 0.0}],
        starts_at=week.starts_at + timedelta(days=1), week=week, stage_race=stage_race, stage_number=2,
        status=Race.Status.FINISHED,
    )
    stage1.status = Race.Status.SCHEDULED
    stage1.save(update_fields=["status"])
    set_squad(stage1, team, [r.pk for r in riders], riders[0].pk)
    stage1.status = Race.Status.FINISHED
    stage1.save(update_fields=["status"])

    for i, r in enumerate(riders, start=1):
        RaceResult.objects.create(
            race=stage1, rider=r, position=i, finish_time=1000.0 + i, group_time=1000.0 + i,
        )
        RaceResult.objects.create(
            race=stage2, rider=r, position=i, finish_time=2000.0 + i, group_time=2000.0 + i,
        )
    score_race(stage1)
    score_race(stage2)
    return stage1, stage2


def test_results_stage_points_exclude_gc_rows(finished_stage_race):
    stage1, stage2 = finished_stage_race
    score_general_classification(stage1.stage_race)

    client = APIClient()
    user = User.objects.create_user(email="stage-results@example.com", password="s0meth1ng-good")
    client.force_authenticate(user=user)

    response = client.get(f"/api/racing/races/{stage2.pk}/results/")

    assert response.status_code == 200
    # The GC award lives on stage2 too (the final stage), but the team
    # points table must show only stage2's own stage points — one row.
    assert len(response.data["points"]) == 1
    assert response.data["points"][0]["points"] == stage_points_for(1)


def test_results_gc_after_stage(finished_stage_race):
    stage1, stage2 = finished_stage_race
    team = stage1.results.first().rider.team

    client = APIClient()
    user = User.objects.create_user(email="gc-after-stage1@example.com", password="s0meth1ng-good")
    client.force_authenticate(user=user)

    response = client.get(f"/api/racing/races/{stage1.pk}/results/")

    assert response.status_code == 200
    gc = response.data["gc"]
    assert gc is not None
    assert gc["after_stage"] == 1
    assert gc["final"] is False
    assert gc["points"] == []
    assert gc["standings"][0]["team"]["id"] == team.pk
    assert gc["standings"][0]["gap"] == 0.0


def test_results_final_gc_has_points_and_prizes(finished_stage_race):
    stage1, stage2 = finished_stage_race
    stage_race = stage1.stage_race
    score_general_classification(stage_race)
    team = stage1.results.first().rider.team
    LedgerEntry.objects.create(
        team=team, kind=LedgerEntry.Kind.GC_PRIZE_MONEY, amount=40_000,
        occurred_at=timezone.now(), race=stage2, position=1,
        description="General classification — Alpine Tour",
    )

    client = APIClient()
    user = User.objects.create_user(email="gc-final@example.com", password="s0meth1ng-good")
    client.force_authenticate(user=user)

    response = client.get(f"/api/racing/races/{stage2.pk}/results/")

    assert response.status_code == 200
    gc = response.data["gc"]
    assert gc["after_stage"] == 2
    assert gc["final"] is True
    assert len(gc["points"]) == 1
    assert gc["points"][0]["team"]["id"] == team.pk
    assert gc["points"][0]["points"] == gc_points_for(1)
    assert gc["points"][0]["prize"] == 40_000


def test_results_one_day_race_gc_is_null(finished_race_with_points):
    client = APIClient()
    user = User.objects.create_user(email="one-day-gc@example.com", password="s0meth1ng-good")
    client.force_authenticate(user=user)

    response = client.get(f"/api/racing/races/{finished_race_with_points.pk}/results/")

    assert response.status_code == 200
    assert response.data["gc"] is None
    assert response.data["race"]["stage_race"] is None


def test_race_results_team_is_team_raced_for_after_release(db):
    """Load-bearing: the team on a result row is the one the rider raced
    for, from RaceSquadRider — never rider.team. After the race, releasing
    the rider must not blank the row's team (see specs/rider-detail-view-plan.md, D4)."""
    team = Team.objects.create(name="Release Team", code="REL")
    rider = Rider.objects.create(
        name="Released Rider", team=team,
        climb=50, sprint=50, flat=50, resistance=50, positioning=50,
    )
    race = Race.objects.create(
        name="Team Raced For Race",
        course=[{"length": 40000.0, "gradient": 0.0}],
        status=Race.Status.FINISHED,
    )
    squad = RaceSquad.objects.create(race=race, team=team)
    RaceSquadRider.objects.create(squad=squad, rider=rider, is_leader=True)
    RaceResult.objects.create(race=race, rider=rider, position=1, finish_time=3600.0)

    rider.team = None
    rider.save()

    client = APIClient()
    user = User.objects.create_user(email="release-viewer@example.com", password="s0meth1ng-good")
    client.force_authenticate(user=user)

    response = client.get(f"/api/racing/races/{race.pk}/results/")

    assert response.status_code == 200
    row = response.data["results"][0]
    assert row["team"]["id"] == team.pk


def test_race_detail_returns_course_and_distance(db):
    race = Race.objects.create(
        name="Route Detail Race",
        course=[{"length": 40000.0, "gradient": 0.0}, {"length": 10000.0, "gradient": 0.03}],
        status=Race.Status.SCHEDULED,
    )
    client = APIClient()
    user = User.objects.create_user(email="race-detail@example.com", password="s0meth1ng-good")
    client.force_authenticate(user=user)

    response = client.get(f"/api/racing/races/{race.pk}/")

    assert response.status_code == 200
    assert response.data["id"] == race.pk
    assert response.data["name"] == "Route Detail Race"
    assert response.data["status"] == "scheduled"
    assert response.data["distance_km"] == 50.0
    assert response.data["course"] == [
        {"length": 40000.0, "gradient": 0.0},
        {"length": 10000.0, "gradient": 0.03},
    ]


def test_race_detail_includes_payout_table(db):
    race = Race.objects.create(
        name="Payout Detail Race",
        course=[{"length": 40000.0, "gradient": 0.0}],
        status=Race.Status.SCHEDULED,
    )
    client = APIClient()
    user = User.objects.create_user(email="race-payout@example.com", password="s0meth1ng-good")
    client.force_authenticate(user=user)

    response = client.get(f"/api/racing/races/{race.pk}/")

    assert response.status_code == 200
    assert response.data["payout"] == [
        {"position": position, "points": points_for(position), "prize": prize_for(position)}
        for position in range(1, 11)
    ]
    assert response.data["gc_payout"] == []
    assert response.data["stage_race"] is None


def test_race_detail_stage_payout_and_gc_payout(db):
    season = Season.objects.create(number=1, starts_at=datetime(2027, 3, 1, tzinfo=dt_timezone.utc))
    week_one = Week.objects.create(
        season=season, number=1,
        starts_at=season.starts_at, ends_at=season.starts_at + timedelta(weeks=1),
    )
    stage_race = StageRace.objects.create(name="Alpine Tour", week=week_one)
    stage1 = Race.objects.create(
        name="Alpine Tour — Stage 1", course=[{"length": 40000.0, "gradient": 0.0}],
        starts_at=week_one.starts_at, week=week_one, stage_race=stage_race, stage_number=1,
    )
    stage2 = Race.objects.create(
        name="Alpine Tour — Stage 2", course=[{"length": 40000.0, "gradient": 0.0}],
        starts_at=week_one.starts_at + timedelta(days=1), week=week_one,
        stage_race=stage_race, stage_number=2,
    )
    client = APIClient()
    user = User.objects.create_user(email="stage-payout@example.com", password="s0meth1ng-good")
    client.force_authenticate(user=user)

    response = client.get(f"/api/racing/races/{stage1.pk}/")

    assert response.status_code == 200
    assert response.data["payout"][0]["points"] == stage_points_for(1)
    assert response.data["payout"][0]["points"] != points_for(1)  # the stage table, not the one-day table
    assert response.data["gc_payout"] == [
        {"position": p, "points": gc_points_for(p), "prize": gc_prize_for(p)}
        for p in range(1, 11)
    ]
    assert response.data["stage_race"]["name"] == "Alpine Tour"
    assert response.data["stage_race"]["stage_number"] == 1
    assert response.data["stage_race"]["stage_count"] == 2
    assert [s["id"] for s in response.data["stage_race"]["stages"]] == [stage1.pk, stage2.pk]


def test_race_detail_available_without_a_team(db):
    race = Race.objects.create(
        name="Team-less Race", course=[{"length": 40000.0, "gradient": 0.0}],
    )
    manager_without_a_team = User.objects.create_user(
        email="no-team-detail@example.com", password="s0meth1ng-good",
    )
    client = APIClient()
    client.force_authenticate(user=manager_without_a_team)

    response = client.get(f"/api/racing/races/{race.pk}/")

    assert response.status_code == 200


def test_race_detail_requires_login(db):
    race = Race.objects.create(
        name="Private Race", course=[{"length": 40000.0, "gradient": 0.0}],
    )
    client = APIClient()

    response = client.get(f"/api/racing/races/{race.pk}/")

    assert response.status_code == 403


def test_race_detail_includes_markers(db):
    race = Race.objects.create(
        name="Marked Detail Race",
        course=[{"length": 40000.0, "gradient": 0.0}],
        status=Race.Status.SCHEDULED,
    )
    first = RaceMarker.objects.create(
        race=race, kind=RaceMarker.Kind.SPRINT, name="Line One", distance=10000.0
    )
    second = RaceMarker.objects.create(
        race=race, kind=RaceMarker.Kind.MOUNTAIN, name="Summit", distance=30000.0
    )
    client = APIClient()
    user = User.objects.create_user(email="marker-detail@example.com", password="s0meth1ng-good")
    client.force_authenticate(user=user)

    response = client.get(f"/api/racing/races/{race.pk}/")

    assert response.status_code == 200
    assert response.data["markers"] == [
        {
            "id": first.pk, "kind": "sprint", "name": "Line One", "distance": 10000.0,
            "weight": "standard", "category": None, "points": [6, 4, 3, 2, 1],
        },
        {
            "id": second.pk, "kind": "mountain", "name": "Summit", "distance": 30000.0,
            "weight": None, "category": "cat2", "points": [6, 4, 3, 2, 1],
        },
    ]


def test_race_detail_sprint_marker_has_weight_and_points(db):
    race = Race.objects.create(
        name="Major Sprint Race",
        course=[{"length": 40000.0, "gradient": 0.0}],
        status=Race.Status.SCHEDULED,
    )
    marker = RaceMarker.objects.create(
        race=race, kind=RaceMarker.Kind.SPRINT, name="Big One", distance=10000.0,
        weight=RaceMarker.Weight.MAJOR,
    )
    client = APIClient()
    user = User.objects.create_user(email="major-sprint@example.com", password="s0meth1ng-good")
    client.force_authenticate(user=user)

    response = client.get(f"/api/racing/races/{race.pk}/")

    payload = next(m for m in response.data["markers"] if m["id"] == marker.pk)
    assert payload["weight"] == "major"
    assert payload["points"] == [10, 7, 5, 3, 2]


def test_race_detail_mountain_marker_has_null_weight(db):
    race = Race.objects.create(
        name="Mountain Only Race",
        course=[{"length": 40000.0, "gradient": 0.0}],
        status=Race.Status.SCHEDULED,
    )
    marker = RaceMarker.objects.create(
        race=race, kind=RaceMarker.Kind.MOUNTAIN, name="Summit", distance=30000.0,
    )
    client = APIClient()
    user = User.objects.create_user(email="mountain-only@example.com", password="s0meth1ng-good")
    client.force_authenticate(user=user)

    response = client.get(f"/api/racing/races/{race.pk}/")

    payload = next(m for m in response.data["markers"] if m["id"] == marker.pk)
    assert payload["weight"] is None


def test_race_detail_sprint_marker_has_null_category(db):
    race = Race.objects.create(
        name="Sprint Only Race",
        course=[{"length": 40000.0, "gradient": 0.0}],
        status=Race.Status.SCHEDULED,
    )
    marker = RaceMarker.objects.create(
        race=race, kind=RaceMarker.Kind.SPRINT, name="Line", distance=10000.0,
    )
    client = APIClient()
    user = User.objects.create_user(email="sprint-only-detail@example.com", password="s0meth1ng-good")
    client.force_authenticate(user=user)

    response = client.get(f"/api/racing/races/{race.pk}/")

    payload = next(m for m in response.data["markers"] if m["id"] == marker.pk)
    assert payload["category"] is None
    assert payload["points"] == [6, 4, 3, 2, 1]


def test_race_detail_mountain_marker_has_category_and_points(db):
    race = Race.objects.create(
        name="Categorised Race",
        course=[{"length": 40000.0, "gradient": 0.0}],
        status=Race.Status.SCHEDULED,
    )
    marker = RaceMarker.objects.create(
        race=race, kind=RaceMarker.Kind.MOUNTAIN, name="Final Top", distance=40000.0,
        category=RaceMarker.Category.HC,
    )
    client = APIClient()
    user = User.objects.create_user(email="categorised@example.com", password="s0meth1ng-good")
    client.force_authenticate(user=user)

    response = client.get(f"/api/racing/races/{race.pk}/")

    payload = next(m for m in response.data["markers"] if m["id"] == marker.pk)
    assert payload["category"] == "hc"
    assert payload["points"] == [10, 7, 5, 3, 2]


def test_race_detail_markers_empty_for_plain_course(db):
    race = Race.objects.create(
        name="Plain Detail Race",
        course=[{"length": 40000.0, "gradient": 0.0}],
        status=Race.Status.SCHEDULED,
    )
    client = APIClient()
    user = User.objects.create_user(email="plain-detail@example.com", password="s0meth1ng-good")
    client.force_authenticate(user=user)

    response = client.get(f"/api/racing/races/{race.pk}/")

    assert response.status_code == 200
    assert response.data["markers"] == []


#: One header line of a real log, brotli-compressed the way
#: `racing.services.run_race` stores it — see racing/README.md, *Race logs*.
LOG_BODY = b'{"v":1}\n'
LOG_BYTES = brotli.compress(LOG_BODY)


@pytest.fixture
def logged_race(db, settings, tmp_path) -> Race:
    """A finished race with a stored log. The media root is the test's own
    temporary directory, so nothing is written into the repository."""
    settings.MEDIA_ROOT = tmp_path
    race = Race.objects.create(
        name="Logged Race",
        course=[{"length": 40000.0, "gradient": 0.0}],
        status=Race.Status.FINISHED,
    )
    RaceLog.objects.create(race=race, file=ContentFile(LOG_BYTES, name="r.jsonl.br"))
    return race


@pytest.fixture
def log_client(db) -> APIClient:
    client = APIClient()
    user = User.objects.create_user(email="log-viewer@example.com", password="s0meth1ng-good")
    client.force_authenticate(user=user)
    return client


def test_race_log_served_brotli_when_accepted(logged_race, log_client):
    response = log_client.get(
        f"/api/racing/races/{logged_race.pk}/log/",
        HTTP_ACCEPT_ENCODING="gzip, br",
    )

    assert response.status_code == 200
    # Load-bearing: without an explicit content_type Django guesses from the
    # .br name and labels the body application/x-brotli, which the browser
    # hands straight to JSON.parse (D4).
    assert response["Content-Type"].startswith("application/x-ndjson")
    assert response["Content-Encoding"] == "br"
    assert "Accept-Encoding" in response["Vary"]
    assert b"".join(response.streaming_content) == LOG_BYTES


def test_race_log_decompressed_when_br_not_accepted(logged_race, log_client):
    response = log_client.get(
        f"/api/racing/races/{logged_race.pk}/log/",
        HTTP_ACCEPT_ENCODING="gzip",
    )

    assert response.status_code == 200
    assert response["Content-Type"].startswith("application/x-ndjson")
    assert not response.has_header("Content-Encoding")
    assert response.content == LOG_BODY


def test_race_log_br_with_q_zero_is_not_accepted(logged_race, log_client):
    response = log_client.get(
        f"/api/racing/races/{logged_race.pk}/log/",
        HTTP_ACCEPT_ENCODING="br;q=0, gzip",
    )

    assert response.status_code == 200
    assert not response.has_header("Content-Encoding")
    assert response.content == LOG_BODY


def test_race_log_br_with_q_zero_padded_zeroes_is_not_accepted(logged_race, log_client):
    response = log_client.get(
        f"/api/racing/races/{logged_race.pk}/log/",
        HTTP_ACCEPT_ENCODING="br;q=0.00, gzip",
    )

    assert response.status_code == 200
    assert not response.has_header("Content-Encoding")
    assert response.content == LOG_BODY


def test_race_log_br_with_low_but_positive_q_is_accepted(logged_race, log_client):
    response = log_client.get(
        f"/api/racing/races/{logged_race.pk}/log/",
        HTTP_ACCEPT_ENCODING="br;q=0.5, gzip",
    )

    assert response.status_code == 200
    assert response["Content-Encoding"] == "br"
    assert b"".join(response.streaming_content) == LOG_BYTES


def test_race_log_404_for_unfinished_race(db, settings, tmp_path, log_client):
    settings.MEDIA_ROOT = tmp_path
    race = Race.objects.create(
        name="Unfinished Logged Race",
        course=[{"length": 40000.0, "gradient": 0.0}],
        status=Race.Status.SCHEDULED,
    )
    RaceLog.objects.create(race=race, file=ContentFile(LOG_BYTES, name="r.jsonl.br"))

    response = log_client.get(f"/api/racing/races/{race.pk}/log/")

    assert response.status_code == 404


def test_race_log_404_without_log(db, log_client):
    race = Race.objects.create(
        name="Unlogged Race",
        course=[{"length": 40000.0, "gradient": 0.0}],
        status=Race.Status.FINISHED,
    )

    response = log_client.get(f"/api/racing/races/{race.pk}/log/")

    assert response.status_code == 404


def test_race_log_404_when_file_missing(logged_race, log_client):
    log = RaceLog.objects.get(race=logged_race)
    Path(log.file.path).unlink()

    response = log_client.get(f"/api/racing/races/{logged_race.pk}/log/")

    assert response.status_code == 404


def test_race_log_requires_login(logged_race):
    client = APIClient()

    response = client.get(f"/api/racing/races/{logged_race.pk}/log/")

    assert response.status_code == 403


def test_race_detail_has_replay_false_without_log(db):
    race = Race.objects.create(
        name="No Replay Race",
        course=[{"length": 40000.0, "gradient": 0.0}],
        status=Race.Status.FINISHED,
    )
    client = APIClient()
    user = User.objects.create_user(email="no-replay@example.com", password="s0meth1ng-good")
    client.force_authenticate(user=user)

    response = client.get(f"/api/racing/races/{race.pk}/")

    assert response.status_code == 200
    assert response.data["has_replay"] is False


def test_race_detail_has_replay_true_with_log(logged_race, log_client):
    response = log_client.get(f"/api/racing/races/{logged_race.pk}/")

    assert response.status_code == 200
    assert response.data["has_replay"] is True


def test_race_results_include_first_five_per_marker(db):
    team = Team.objects.create(name="Marker Team", code="MKT")
    race = Race.objects.create(
        name="Marked Results Race",
        course=[{"length": 40000.0, "gradient": 0.0}],
        status=Race.Status.FINISHED,
    )
    markers = [
        RaceMarker.objects.create(
            race=race, kind=RaceMarker.Kind.SPRINT, name=f"Line {i}", distance=5000.0 * i
        )
        for i in range(1, 4)
    ]
    squad = RaceSquad.objects.create(race=race, team=team)
    riders = []
    for i in range(6):
        rider = Rider.objects.create(
            name=f"Marker Rider {i}", team=team,
            climb=50, sprint=50, flat=50, resistance=50, positioning=50,
        )
        riders.append(rider)
        RaceSquadRider.objects.create(squad=squad, rider=rider, is_leader=i == 0)
        RaceResult.objects.create(
            race=race, rider=rider, position=i + 1, finish_time=100.0 + i,
        )
    for marker in markers:
        for position, rider in enumerate(riders, start=1):
            MarkerCrossing.objects.create(
                marker=marker, rider=rider, position=position, crossed_at=100.0 + position,
            )

    client = APIClient()
    user = User.objects.create_user(email="marker-results@example.com", password="s0meth1ng-good")
    client.force_authenticate(user=user)

    response = client.get(f"/api/racing/races/{race.pk}/results/")

    assert response.status_code == 200
    for marker in markers:
        entry = next(m for m in response.data["markers"] if m["id"] == marker.pk)
        assert [c["position"] for c in entry["crossings"]] == [1, 2, 3, 4, 5]
        assert [c["rider"]["name"] for c in entry["crossings"]] == [
            r.name for r in riders[:5]
        ]


def test_race_results_marker_team_is_team_raced_for(db):
    """Same load-bearing rule as the results rows: a marker crossing's team
    is the one the rider raced for, from RaceSquadRider — so releasing the
    rider afterwards must not blank it."""
    team = Team.objects.create(name="Marker Release Team", code="MRT")
    rider = Rider.objects.create(
        name="Released Marker Rider", team=team,
        climb=50, sprint=50, flat=50, resistance=50, positioning=50,
    )
    race = Race.objects.create(
        name="Marker Team Race",
        course=[{"length": 40000.0, "gradient": 0.0}],
        status=Race.Status.FINISHED,
    )
    squad = RaceSquad.objects.create(race=race, team=team)
    RaceSquadRider.objects.create(squad=squad, rider=rider, is_leader=True)
    RaceResult.objects.create(race=race, rider=rider, position=1, finish_time=3600.0)
    marker = RaceMarker.objects.create(
        race=race, kind=RaceMarker.Kind.SPRINT, name="Line", distance=10000.0
    )
    MarkerCrossing.objects.create(marker=marker, rider=rider, position=1, crossed_at=1000.0)

    rider.team = None
    rider.save()

    client = APIClient()
    user = User.objects.create_user(email="marker-release@example.com", password="s0meth1ng-good")
    client.force_authenticate(user=user)

    response = client.get(f"/api/racing/races/{race.pk}/results/")

    assert response.status_code == 200
    assert response.data["markers"][0]["crossings"][0]["team"]["id"] == team.pk


def test_race_results_crossing_shows_points_for_scoring_rider_only(db):
    team = Team.objects.create(name="Double Team", code="DBL")
    race = Race.objects.create(
        name="Double Sprint Race",
        course=[{"length": 40000.0, "gradient": 0.0}],
        status=Race.Status.FINISHED,
    )
    marker = RaceMarker.objects.create(
        race=race, kind=RaceMarker.Kind.SPRINT, name="Line", distance=10000.0,
        weight=RaceMarker.Weight.STANDARD,
    )
    squad = RaceSquad.objects.create(race=race, team=team)
    first = Rider.objects.create(
        name="First Across", team=team,
        climb=50, sprint=50, flat=50, resistance=50, positioning=50,
    )
    second = Rider.objects.create(
        name="Second Across", team=team,
        climb=50, sprint=50, flat=50, resistance=50, positioning=50,
    )
    for i, rider in enumerate([first, second]):
        RaceSquadRider.objects.create(squad=squad, rider=rider, is_leader=i == 0)
        RaceResult.objects.create(race=race, rider=rider, position=i + 1, finish_time=100.0 + i)
    MarkerCrossing.objects.create(marker=marker, rider=first, position=1, crossed_at=100.0)
    MarkerCrossing.objects.create(marker=marker, rider=second, position=2, crossed_at=101.0)
    score_sprints(race)

    client = APIClient()
    user = User.objects.create_user(email="double-sprint@example.com", password="s0meth1ng-good")
    client.force_authenticate(user=user)

    response = client.get(f"/api/racing/races/{race.pk}/results/")

    crossings = {c["rider"]["id"]: c["points"] for c in response.data["markers"][0]["crossings"]}
    assert crossings[first.pk] == 6
    assert crossings[second.pk] is None


def test_race_results_team_points_split_finish_and_sprint(db):
    team = Team.objects.create(name="Split Team", code="SPL")
    race = Race.objects.create(
        name="Split Points Race",
        course=[{"length": 40000.0, "gradient": 0.0}],
        status=Race.Status.FINISHED,
    )
    finisher = Rider.objects.create(
        name="Finisher", team=team,
        climb=50, sprint=50, flat=50, resistance=50, positioning=50,
    )
    RaceResult.objects.create(race=race, rider=finisher, position=1, finish_time=1000.0)
    score_race(race)
    marker = RaceMarker.objects.create(
        race=race, kind=RaceMarker.Kind.SPRINT, name="Line", distance=10000.0,
        weight=RaceMarker.Weight.STANDARD,
    )
    MarkerCrossing.objects.create(marker=marker, rider=finisher, position=1, crossed_at=100.0)
    score_sprints(race)

    client = APIClient()
    user = User.objects.create_user(email="split-points@example.com", password="s0meth1ng-good")
    client.force_authenticate(user=user)

    response = client.get(f"/api/racing/races/{race.pk}/results/")

    row = next(p for p in response.data["points"] if p["team"]["id"] == team.pk)
    assert row["finish_points"] == 20
    assert row["sprint_points"] == 6
    assert row["points"] == 26


def test_race_results_team_with_only_sprint_points_listed_with_them(db):
    scoring_team = Team.objects.create(name="Scorer", code="SCR")
    sprint_only_team = Team.objects.create(name="Sprinter", code="SPT")
    race = Race.objects.create(
        name="Sprint Only Race",
        course=[{"length": 40000.0, "gradient": 0.0}],
        status=Race.Status.FINISHED,
    )
    winner = Rider.objects.create(
        name="Winner", team=scoring_team,
        climb=50, sprint=50, flat=50, resistance=50, positioning=50,
    )
    RaceResult.objects.create(race=race, rider=winner, position=1, finish_time=1000.0)
    score_race(race)
    RaceSquad.objects.create(race=race, team=sprint_only_team)
    marker = RaceMarker.objects.create(
        race=race, kind=RaceMarker.Kind.SPRINT, name="Line", distance=10000.0,
    )
    sprinter = Rider.objects.create(
        name="Sprinter", team=sprint_only_team,
        climb=50, sprint=50, flat=50, resistance=50, positioning=50,
    )
    MarkerCrossing.objects.create(marker=marker, rider=sprinter, position=1, crossed_at=100.0)
    score_sprints(race)

    client = APIClient()
    user = User.objects.create_user(email="sprint-only@example.com", password="s0meth1ng-good")
    client.force_authenticate(user=user)

    response = client.get(f"/api/racing/races/{race.pk}/results/")

    row = next(p for p in response.data["points"] if p["team"]["id"] == sprint_only_team.pk)
    assert row["position"] is None
    assert row["finish_points"] == 0
    assert row["sprint_points"] == 6
    assert row["mountain_points"] == 0
    assert row["points"] == 6


def test_race_results_mountain_crossing_shows_points_for_scoring_rider_only(db):
    team = Team.objects.create(name="Climb Team", code="CLB")
    other = Team.objects.create(name="Other Team", code="OTH")
    race = Race.objects.create(
        name="Crossing Race",
        course=[{"length": 40000.0, "gradient": 0.0}],
        status=Race.Status.FINISHED,
    )
    marker = RaceMarker.objects.create(
        race=race, kind=RaceMarker.Kind.MOUNTAIN, name="Hilltop", distance=30000.0,
        category=RaceMarker.Category.CAT1,
    )
    winner = Rider.objects.create(
        name="Climber", team=team,
        climb=50, sprint=50, flat=50, resistance=50, positioning=50,
    )
    teammate = Rider.objects.create(
        name="Teammate", team=team,
        climb=50, sprint=50, flat=50, resistance=50, positioning=50,
    )
    other_rider = Rider.objects.create(
        name="Rival", team=other,
        climb=50, sprint=50, flat=50, resistance=50, positioning=50,
    )
    for rider, position in [(winner, 1), (teammate, 2), (other_rider, 3)]:
        MarkerCrossing.objects.create(
            marker=marker, rider=rider, position=position, crossed_at=100.0,
        )
    score_mountains(race)

    client = APIClient()
    user = User.objects.create_user(email="crossings@example.com", password="s0meth1ng-good")
    client.force_authenticate(user=user)

    response = client.get(f"/api/racing/races/{race.pk}/results/")

    crossings = {
        c["rider"]["id"]: c["points"]
        for m in response.data["markers"] if m["id"] == marker.pk
        for c in m["crossings"]
    }
    assert crossings[winner.pk] == 8
    assert crossings[teammate.pk] is None
    assert crossings[other_rider.pk] == 4


def test_race_results_team_points_split_finish_sprint_and_mountain(db):
    """D8: a mountain total must never be folded into sprint_points, and
    points is always the sum of the three."""
    team = Team.objects.create(name="Split Team", code="SPL")
    race = Race.objects.create(
        name="Three Way Race",
        course=[{"length": 40000.0, "gradient": 0.0}],
        status=Race.Status.FINISHED,
    )
    finisher = Rider.objects.create(
        name="Finisher", team=team,
        climb=50, sprint=50, flat=50, resistance=50, positioning=50,
    )
    RaceResult.objects.create(race=race, rider=finisher, position=1, finish_time=1000.0)
    score_race(race)
    sprint = RaceMarker.objects.create(
        race=race, kind=RaceMarker.Kind.SPRINT, name="Line", distance=10000.0,
        weight=RaceMarker.Weight.STANDARD,
    )
    mountain = RaceMarker.objects.create(
        race=race, kind=RaceMarker.Kind.MOUNTAIN, name="Hilltop", distance=30000.0,
        category=RaceMarker.Category.HC,
    )
    MarkerCrossing.objects.create(marker=sprint, rider=finisher, position=1, crossed_at=100.0)
    MarkerCrossing.objects.create(marker=mountain, rider=finisher, position=1, crossed_at=200.0)
    score_sprints(race)
    score_mountains(race)

    client = APIClient()
    user = User.objects.create_user(email="three-way@example.com", password="s0meth1ng-good")
    client.force_authenticate(user=user)

    response = client.get(f"/api/racing/races/{race.pk}/results/")

    row = next(p for p in response.data["points"] if p["team"]["id"] == team.pk)
    assert row["finish_points"] == 20
    assert row["sprint_points"] == 6
    assert row["mountain_points"] == 10
    assert row["points"] == 20 + 6 + 10


def test_race_results_team_with_only_mountain_points_listed_with_them(db):
    scoring_team = Team.objects.create(name="Scorer", code="SCR")
    climbing_team = Team.objects.create(name="Climbers", code="CLM")
    race = Race.objects.create(
        name="Mountain Only Race",
        course=[{"length": 40000.0, "gradient": 0.0}],
        status=Race.Status.FINISHED,
    )
    winner = Rider.objects.create(
        name="Winner", team=scoring_team,
        climb=50, sprint=50, flat=50, resistance=50, positioning=50,
    )
    RaceResult.objects.create(race=race, rider=winner, position=1, finish_time=1000.0)
    score_race(race)
    RaceSquad.objects.create(race=race, team=climbing_team)
    marker = RaceMarker.objects.create(
        race=race, kind=RaceMarker.Kind.MOUNTAIN, name="Hilltop", distance=30000.0,
    )
    climber = Rider.objects.create(
        name="Climber", team=climbing_team,
        climb=50, sprint=50, flat=50, resistance=50, positioning=50,
    )
    MarkerCrossing.objects.create(marker=marker, rider=climber, position=1, crossed_at=100.0)
    score_mountains(race)

    client = APIClient()
    user = User.objects.create_user(email="mountain-only@example.com", password="s0meth1ng-good")
    client.force_authenticate(user=user)

    response = client.get(f"/api/racing/races/{race.pk}/results/")

    row = next(p for p in response.data["points"] if p["team"]["id"] == climbing_team.pk)
    assert row["position"] is None
    assert row["finish_points"] == 0
    assert row["sprint_points"] == 0
    assert row["mountain_points"] == 6
    assert row["points"] == 6


def test_standings_total_includes_sprint_points(db):
    world_services._clock = None
    try:
        season = make_season_with_weeks(1, now().replace(hour=0, minute=0, second=0, microsecond=0))
        week = season.weeks.get(number=1)
        team = Team.objects.create(name="Standings Team", code="STA")
        rider = Rider.objects.create(
            name="Standings Rider", team=team,
            climb=50, sprint=50, flat=50, resistance=50, positioning=50,
        )
        race = Race.objects.create(
            name="Standings Sprint Race",
            course=[{"length": 40000.0, "gradient": 0.0}],
            status=Race.Status.FINISHED, week=week, starts_at=week.starts_at,
        )
        RaceResult.objects.create(race=race, rider=rider, position=3, finish_time=1000.0)
        score_race(race)
        marker = RaceMarker.objects.create(
            race=race, kind=RaceMarker.Kind.SPRINT, name="Line", distance=10000.0,
        )
        MarkerCrossing.objects.create(marker=marker, rider=rider, position=1, crossed_at=100.0)
        score_sprints(race)

        client = APIClient()
        user = User.objects.create_user(email="standings-sprint@example.com", password="s0meth1ng-good")
        client.force_authenticate(user=user)

        response = client.get("/api/competitions/standings/")

        row = next(e for e in response.data["standings"] if e["team"]["id"] == team.pk)
        assert row["points"] == 12 + 6
    finally:
        world_services._clock = None


def test_standings_total_includes_mountain_points(db):
    world_services._clock = None
    try:
        season = make_season_with_weeks(1, now().replace(hour=0, minute=0, second=0, microsecond=0))
        week = season.weeks.get(number=1)
        team = Team.objects.create(name="Standings Team", code="STA")
        rider = Rider.objects.create(
            name="Standings Rider", team=team,
            climb=50, sprint=50, flat=50, resistance=50, positioning=50,
        )
        race = Race.objects.create(
            name="Standings Mountain Race",
            course=[{"length": 40000.0, "gradient": 0.0}],
            status=Race.Status.FINISHED, week=week, starts_at=week.starts_at,
        )
        RaceResult.objects.create(race=race, rider=rider, position=3, finish_time=1000.0)
        score_race(race)
        marker = RaceMarker.objects.create(
            race=race, kind=RaceMarker.Kind.MOUNTAIN, name="Hilltop", distance=30000.0,
            category=RaceMarker.Category.CAT1,
        )
        MarkerCrossing.objects.create(marker=marker, rider=rider, position=1, crossed_at=100.0)
        score_mountains(race)

        client = APIClient()
        user = User.objects.create_user(email="standings-mountain@example.com", password="s0meth1ng-good")
        client.force_authenticate(user=user)

        response = client.get("/api/competitions/standings/")

        row = next(e for e in response.data["standings"] if e["team"]["id"] == team.pk)
        assert row["points"] == 12 + 8
    finally:
        world_services._clock = None


def test_claim_returns_the_new_team(db, claim_client):
    Team.objects.create(name="Unclaimed Team", code="UNC")

    response = claim_client.post(
        "/api/teams/claim/", {"name": "Mountain Goats", "code": "MGO"}, format="json",
    )

    assert response.status_code == 201
    assert response.data["name"] == "Mountain Goats"
    assert response.data["code"] == "MGO"


def test_claim_twice_is_409(db, claim_client):
    Team.objects.create(name="Unclaimed Team", code="UNC")
    Team.objects.create(name="Another Team", code="ANO")

    first = claim_client.post(
        "/api/teams/claim/", {"name": "Mountain Goats", "code": "MGO"}, format="json",
    )
    second = claim_client.post(
        "/api/teams/claim/", {"name": "Second Try", "code": "SEC"}, format="json",
    )

    assert first.status_code == 201
    assert second.status_code == 409


def test_claim_with_no_teams_available_is_409(db, claim_client):
    response = claim_client.post(
        "/api/teams/claim/", {"name": "Mountain Goats", "code": "MGO"}, format="json",
    )

    assert response.status_code == 409


def test_claim_withdraws_the_claimed_teams_standing_bids(
    db, claim_client, market_team,
):
    from transfers.services import list_for_auction, place_bid

    bidder_team = Team.objects.create(name="AI Team", code="AIT")
    rider = _market_rider(name="For Sale", team=market_team)
    auction = list_for_auction(market_team, rider.pk, at=now())
    place_bid(auction.pk, bidder_team, auction.reserve_price, at=now())

    response = claim_client.post(
        "/api/teams/claim/", {"name": "Claimed Team", "code": "CLM"}, format="json",
    )

    bid = Bid.objects.get(auction=auction, bidder_team=bidder_team)
    auction.refresh_from_db()
    assert response.status_code == 201
    assert bid.withdrawn_at is not None
    assert auction.current_price == auction.reserve_price


def test_claim_rolls_back_the_withdrawal_when_it_fails(
    db, claim_client, market_team, monkeypatch,
):
    # The point is atomicity: claim_team commits on its own, so if the
    # withdrawal that follows it raised outside the view's transaction, the
    # manager would be left holding a renamed, re-rostered team with the bid
    # still standing. Forcing the withdrawal to blow up is the only way to see
    # which of the two happened.
    from transfers.services import list_for_auction, place_bid

    bidder = Team.objects.create(name="AI Team", code="AIT")
    for i in range(3):
        _market_rider(name=f"AI Rider {i}", team=bidder)
    rider = _market_rider(name="For Sale", team=market_team)
    auction = list_for_auction(market_team, rider.pk, at=now())
    place_bid(auction.pk, bidder, auction.reserve_price, at=now())
    roster_before = list(bidder.riders.values_list("pk", flat=True))

    def _explode(*args, **kwargs):
        raise RuntimeError("the ledger is on fire")

    monkeypatch.setattr("api.views.withdraw_bids", _explode)

    with pytest.raises(RuntimeError):
        claim_client.post(
            "/api/teams/claim/", {"name": "Mountain Goats", "code": "MGO"}, format="json",
        )

    bidder.refresh_from_db()
    assert bidder.manager is None
    assert (bidder.name, bidder.code) == ("AI Team", "AIT")
    assert list(bidder.riders.values_list("pk", flat=True)) == roster_before
    assert Bid.objects.get(auction=auction, bidder_team=bidder).withdrawn_at is None
    assert Auction.objects.get(pk=auction.pk).current_price == auction.reserve_price


def test_claim_cancels_the_claimed_teams_open_listings(
    db, claim_client, market_client, market_team,
):
    from transfers.services import list_for_auction, place_bid

    # The only unmanaged team, so the claim takes the seller.
    seller = Team.objects.create(name="Claimable Seller", code="CSL")
    rider = _market_rider(name="For Sale", team=seller)
    auction = list_for_auction(seller, rider.pk, at=now())
    place_bid(auction.pk, market_team, auction.reserve_price, at=now())

    response = claim_client.post(
        "/api/teams/claim/", {"name": "Claimed Team", "code": "CLM"}, format="json",
    )

    auction.refresh_from_db()
    rider.refresh_from_db()
    assert response.status_code == 201
    assert auction.status == Auction.Status.CANCELLED
    assert auction.resolved_at is not None
    # The listing is cancelled and the rider stays: a claimed team keeps its
    # riders (#156).
    assert rider.team_id == seller.pk

    market = market_client.get("/api/transfers/auctions/")
    mine = market_client.get("/api/transfers/auctions/mine/")
    listed_ids = {row["id"] for row in market.data["auctions"]}
    mine_ids = {row["id"] for row in mine.data}
    assert auction.pk not in listed_ids
    assert auction.pk not in mine_ids


def test_claim_rolls_back_listing_cancellation_when_it_fails(
    db, claim_client, market_team, monkeypatch,
):
    # The same atomicity the bid withdrawal relies on: a cancellation that
    # raised outside the view's transaction would leave the manager holding a
    # re-rostered team whose old listings were cancelled anyway.
    from transfers.services import list_for_auction, place_bid

    seller = Team.objects.create(name="Claimable Seller", code="CSL")
    rider = _market_rider(name="For Sale", team=seller)
    auction = list_for_auction(seller, rider.pk, at=now())
    place_bid(auction.pk, market_team, auction.reserve_price, at=now())
    name_before, code_before = seller.name, seller.code

    def _explode(*args, **kwargs):
        raise RuntimeError("the ledger is on fire")

    monkeypatch.setattr("api.views.cancel_listings", _explode)

    with pytest.raises(RuntimeError):
        claim_client.post(
            "/api/teams/claim/", {"name": "Mountain Goats", "code": "MGO"}, format="json",
        )

    seller.refresh_from_db()
    rider.refresh_from_db()
    auction.refresh_from_db()
    assert seller.manager is None
    assert (seller.name, seller.code) == (name_before, code_before)
    assert rider.team_id == seller.pk
    assert auction.status == Auction.Status.OPEN
    assert auction.resolved_at is None


def test_claim_lowercase_code_is_accepted_and_uppercased(db, claim_client):
    Team.objects.create(name="Unclaimed Team", code="UNC")

    response = claim_client.post(
        "/api/teams/claim/", {"name": "Mountain Goats", "code": "mgo"}, format="json",
    )

    assert response.status_code == 201
    assert response.data["code"] == "MGO"


def test_claim_duplicate_name_is_400(db, claim_client):
    other_manager = User.objects.create_user(
        email="other-manager@example.com", password="s0meth1ng-good",
    )
    Team.objects.create(name="Taken Name", code="TKN", manager=other_manager)
    Team.objects.create(name="Unclaimed Team", code="UNC")

    response = claim_client.post(
        "/api/teams/claim/", {"name": "Taken Name", "code": "MGO"}, format="json",
    )

    assert response.status_code == 400


def make_season_with_weeks(number: int, starts_at) -> Season:
    season = Season.objects.create(number=number, starts_at=starts_at)
    for week_number in range(1, SEASON_WEEKS + 1):
        week_start = season.starts_at + timedelta(weeks=week_number - 1)
        Week.objects.create(
            season=season, number=week_number,
            starts_at=week_start, ends_at=week_start + timedelta(weeks=1),
        )
    return season


@override_settings(GAME_CLOCK_CLASS="world.clocks.MockClock")
def test_standings_returns_ranked_table(db):
    world_services._clock = None
    try:
        season = make_season_with_weeks(1, now().replace(hour=0, minute=0, second=0, microsecond=0))
        week = season.weeks.get(number=1)
        team = Team.objects.create(name="Standings Team", code="STA")
        rider = Rider.objects.create(
            name="Winner", team=team,
            climb=50, sprint=50, flat=50, resistance=50, positioning=50,
        )
        race = Race.objects.create(
            name="Standings Check Race",
            course=[{"length": 40000.0, "gradient": 0.0}],
            status=Race.Status.FINISHED, week=week, starts_at=week.starts_at,
        )
        RaceResult.objects.create(race=race, rider=rider, position=1, finish_time=1000.0)
        score_race(race)

        client = APIClient()
        user = User.objects.create_user(email="viewer3@example.com", password="s0meth1ng-good")
        client.force_authenticate(user=user)

        response = client.get("/api/competitions/standings/")

        assert response.status_code == 200
        assert response.data["state"] == "in_season"
        assert response.data["standings"][0]["rank"] == 1
        assert response.data["standings"][0]["team"]["code"] == "STA"
        assert response.data["standings"][0]["points"] == 20
    finally:
        world_services._clock = None


def test_standings_no_season_returns_empty(db):
    client = APIClient()
    user = User.objects.create_user(email="viewer4@example.com", password="s0meth1ng-good")
    client.force_authenticate(user=user)

    response = client.get("/api/competitions/standings/")

    assert response.status_code == 200
    assert response.data["state"] == "no_season"
    assert response.data["standings"] == []


def test_standings_requires_login(db):
    client = APIClient()

    response = client.get("/api/competitions/standings/")

    assert response.status_code == 403


def test_rider_serializer_has_no_role(roster_rider, roster_client):
    """Leadership is a per-race property, not a fact about a rider — see
    specs/leadership-is-per-race.md."""
    response = roster_client.get("/api/riders/")

    assert "role" not in response.data["riders"][0]


def test_squad_candidates_have_no_role(squad_race, squad_riders, squad_client):
    """Leadership is a per-race property, held by is_leader — see
    specs/leadership-is-per-race.md."""
    response = squad_client.get(f"/api/racing/races/{squad_race.pk}/squad/")

    assert "role" not in response.data["candidates"][0]


@pytest.fixture
def staff_manager(db) -> User:
    return User.objects.create_user(email="staff-manager@example.com", password="s0meth1ng-good")


@pytest.fixture
def staff_team(db, staff_manager) -> Team:
    return Team.objects.create(name="Staff Team", code="STF", manager=staff_manager)


@pytest.fixture
def staff_client(staff_manager) -> APIClient:
    client = APIClient()
    client.force_authenticate(user=staff_manager)
    return client


@pytest.fixture
def pool_trainer(db) -> Trainer:
    return Trainer.objects.create(
        name="Coach One", climb=90, sprint=40, flat=45, resistance=50, positioning=35,
    )


def test_staff_requires_authentication(db):
    client = APIClient()

    assert client.get("/api/staff/").status_code == 403


def test_staff_without_a_team_is_403(db):
    manager_without_a_team = User.objects.create_user(
        email="no-team-staff@example.com", password="s0meth1ng-good",
    )
    client = APIClient()
    client.force_authenticate(user=manager_without_a_team)

    assert client.get("/api/staff/").status_code == 403


def test_staff_shows_the_pool_when_the_slot_is_empty(staff_client, staff_team, pool_trainer):
    response = staff_client.get("/api/staff/")

    assert response.status_code == 200
    assert response.data["trainer"] is None
    assert len(response.data["pool"]) == 1
    assert response.data["pool"][0]["id"] == pool_trainer.pk


def test_staff_shows_the_trainer_when_hired(staff_client, staff_team, pool_trainer):
    pool_trainer.team = staff_team
    pool_trainer.save()

    response = staff_client.get("/api/staff/")

    assert response.data["trainer"]["id"] == pool_trainer.pk
    assert response.data["pool"] == []


def test_staff_payload_carries_prices_and_balance(staff_client, staff_team, pool_trainer):
    make_ledger_entry(
        staff_team, "starting_balance", STARTING_BALANCE, now(), "Starting balance",
    )

    response = staff_client.get("/api/staff/")

    assert response.data["balance"] == STARTING_BALANCE
    trainer = response.data["pool"][0]
    assert trainer["hire_fee"] == hire_fee(pool_trainer)
    assert trainer["weekly_salary"] == weekly_salary(pool_trainer)


def test_staff_skills_are_on_the_display_scale(staff_client, staff_team, pool_trainer):
    response = staff_client.get("/api/staff/")

    skills = response.data["pool"][0]["skills"]
    for value in skills.values():
        assert 0 <= value <= DISPLAY_MAX
    assert skills["climb"] == 9  # display scale, not the stored 90


def test_hire_fills_the_slot(staff_client, staff_team, pool_trainer):
    # A hire now costs a fee, so the team needs a balance for it to go
    # through — the plain unaffordable case is its own test below.
    make_ledger_entry(
        staff_team, "starting_balance", STARTING_BALANCE, now(), "Starting balance",
    )

    response = staff_client.post("/api/staff/trainer/hire/", {"trainer_id": pool_trainer.pk})

    assert response.status_code == 204
    follow_up = staff_client.get("/api/staff/")
    assert follow_up.data["trainer"]["id"] == pool_trainer.pk


def test_hire_debits_the_fee(staff_client, staff_team, pool_trainer):
    make_ledger_entry(
        staff_team, "starting_balance", STARTING_BALANCE, now(), "Starting balance",
    )

    response = staff_client.post("/api/staff/trainer/hire/", {"trainer_id": pool_trainer.pk})

    assert response.status_code == 204
    follow_up = staff_client.get("/api/staff/")
    assert follow_up.data["balance"] == STARTING_BALANCE - hire_fee(pool_trainer)
    fee_entry = LedgerEntry.objects.get(team=staff_team, kind="trainer_fee")
    assert fee_entry.amount == -hire_fee(pool_trainer)
    assert pool_trainer.name in fee_entry.description


def test_hire_refused_when_balance_too_low(staff_client, staff_team, pool_trainer):
    make_ledger_entry(staff_team, "starting_balance", 100, now(), "Starting balance")

    response = staff_client.post("/api/staff/trainer/hire/", {"trainer_id": pool_trainer.pk})

    assert response.status_code == 409
    pool_trainer.refresh_from_db()
    assert pool_trainer.team_id is None
    assert not LedgerEntry.objects.filter(team=staff_team, kind="trainer_fee").exists()


def test_fire_refunds_nothing(staff_client, staff_team, pool_trainer):
    make_ledger_entry(
        staff_team, "starting_balance", STARTING_BALANCE, now(), "Starting balance",
    )
    staff_client.post("/api/staff/trainer/hire/", {"trainer_id": pool_trainer.pk})

    response = staff_client.post("/api/staff/trainer/fire/")

    assert response.status_code == 204
    follow_up = staff_client.get("/api/staff/")
    assert follow_up.data["balance"] == STARTING_BALANCE - hire_fee(pool_trainer)


def test_hire_an_already_hired_trainer_returns_409(staff_client, staff_team, pool_trainer):
    other_manager = User.objects.create_user(email="other-staff@example.com", password="s0meth1ng-good")
    other_team = Team.objects.create(name="Other Staff Team", code="OST", manager=other_manager)
    pool_trainer.team = other_team
    pool_trainer.save()

    response = staff_client.post("/api/staff/trainer/hire/", {"trainer_id": pool_trainer.pk})

    assert response.status_code == 409


def test_hire_when_slot_occupied_returns_409(staff_client, staff_team, pool_trainer):
    hired = Trainer.objects.create(
        name="Coach Two", team=staff_team,
        climb=30, sprint=90, flat=45, resistance=50, positioning=35,
    )

    response = staff_client.post("/api/staff/trainer/hire/", {"trainer_id": pool_trainer.pk})

    assert response.status_code == 409
    hired.refresh_from_db()
    assert hired.team_id == staff_team.pk


def test_fire_empties_the_slot(staff_client, staff_team, pool_trainer):
    pool_trainer.team = staff_team
    pool_trainer.save()

    response = staff_client.post("/api/staff/trainer/fire/")

    assert response.status_code == 204
    follow_up = staff_client.get("/api/staff/")
    assert follow_up.data["trainer"] is None
    assert any(t["id"] == pool_trainer.pk for t in follow_up.data["pool"])


def test_fire_with_no_trainer_returns_409(staff_client, staff_team):
    response = staff_client.post("/api/staff/trainer/fire/")

    assert response.status_code == 409


def test_hire_cannot_target_another_teams_trainer(staff_client, staff_team):
    other_manager = User.objects.create_user(email="employed-staff@example.com", password="s0meth1ng-good")
    other_team = Team.objects.create(name="Employed Team", code="EMP", manager=other_manager)
    employed = Trainer.objects.create(
        name="Coach Three", team=other_team,
        climb=90, sprint=40, flat=45, resistance=50, positioning=35,
    )

    response = staff_client.post("/api/staff/trainer/hire/", {"trainer_id": employed.pk})

    assert response.status_code == 409
    employed.refresh_from_db()
    assert employed.team_id == other_team.pk


def test_training_get_without_trainer_has_no_focus(staff_client, staff_team):
    response = staff_client.get("/api/staff/training/")

    assert response.status_code == 200
    assert response.data["has_trainer"] is False
    assert response.data["focus"] is None
    assert response.data["last_week"] is None
    assert set(response.data["options"]) == set(["climb", "sprint", "flat", "resistance", "positioning"])


def test_training_put_sets_focus(staff_client, staff_team):
    # Hire a trainer first so the team has a focus decision to make.
    trainer = Trainer.objects.create(
        name="Coach", team=staff_team,
        climb=90, sprint=40, flat=45, resistance=50, positioning=35,
    )

    response = staff_client.put("/api/staff/training/", {"attribute": "sprint"}, format="json")
    follow_up = staff_client.get("/api/staff/training/")

    assert response.status_code == 204
    assert follow_up.data["has_trainer"] is True
    assert follow_up.data["focus"] == "sprint"


def test_training_put_without_trainer_is_409(staff_client, staff_team):
    response = staff_client.put("/api/staff/training/", {"attribute": "climb"}, format="json")

    assert response.status_code == 409


def test_training_never_exposes_training_affinity(staff_client, staff_team):
    monday = datetime(2027, 3, 1, 0, 0, tzinfo=dt_timezone.utc)
    season = Season.objects.create(number=1, starts_at=monday)
    week = Week.objects.create(
        season=season, number=1, starts_at=monday, ends_at=monday + timedelta(weeks=1),
    )
    rider = Rider.objects.create(
        name="Trainee", team=staff_team,
        climb=89, sprint=40, flat=40, resistance=40, positioning=40,
        training_affinity={"climb": 1.5, "sprint": 0.5, "flat": 1.0, "resistance": 1.0, "positioning": 1.0},
    )
    TrainingWeekReport.objects.create(
        team=staff_team, week=week, attribute="climb",
        changes=[{
            "rider_id": rider.pk, "rider_name": rider.name, "team_id": staff_team.pk,
            "attribute": "climb", "from": 8, "to": 9,
        }],
    )

    response = staff_client.get("/api/staff/training/")

    assert response.status_code == 200
    body = json.dumps(response.data)
    assert "training_affinity" not in body
    change = response.data["last_week"]["changes"][0]
    assert change["from_value"] == 8
    assert change["to_value"] == 9


@pytest.fixture
def finances_manager(db) -> User:
    return User.objects.create_user(email="finances-manager@example.com", password="s0meth1ng-good")


@pytest.fixture
def finances_team(db, finances_manager) -> Team:
    return Team.objects.create(name="Finances Team", code="FIN", manager=finances_manager)


@pytest.fixture
def finances_client(finances_manager) -> APIClient:
    client = APIClient()
    client.force_authenticate(user=finances_manager)
    return client


def make_ledger_entry(team, kind, amount, occurred_at, description):
    from economy.models import LedgerEntry
    return LedgerEntry.objects.create(
        team=team, kind=kind, amount=amount,
        occurred_at=occurred_at, description=description,
    )


def make_fanbase_entry(team, kind, delta, occurred_at, *, week=None, points=0):
    from economy.models import FanbaseEntry
    return FanbaseEntry.objects.create(
        team=team, kind=kind, delta=delta, occurred_at=occurred_at,
        week=week, points=points,
    )


def test_finances_requires_a_session(finances_team):
    client = APIClient()

    response = client.get("/api/economy/finances/")

    assert response.status_code == 403


def test_finances_returns_balance_and_entries(finances_client, finances_team):
    at = datetime(2027, 3, 1, 0, 0, tzinfo=dt_timezone.utc)
    make_ledger_entry(
        finances_team, "starting_balance", 500_000, at, "Starting balance",
    )
    make_ledger_entry(
        finances_team, "wages", -14_400, at + timedelta(weeks=1), "Weekly wages",
    )

    response = finances_client.get("/api/economy/finances/")

    assert response.status_code == 200
    assert response.data["balance"] == 485_600
    assert len(response.data["entries"]) == 2


def test_entries_are_newest_first_with_running_balance(finances_client, finances_team):
    """Load-bearing: D7's off-by-one lives here. The oldest entry's
    `balance_after` must equal the starting balance, and the newest must
    equal the current `balance`."""
    at = datetime(2027, 3, 1, 0, 0, tzinfo=dt_timezone.utc)
    make_ledger_entry(
        finances_team, "starting_balance", 500_000, at, "Starting balance",
    )
    make_ledger_entry(
        finances_team, "wages", -14_400, at + timedelta(weeks=1), "Weekly wages",
    )
    make_ledger_entry(
        finances_team, "wages", -14_400, at + timedelta(weeks=2), "Weekly wages",
    )

    response = finances_client.get("/api/economy/finances/")

    entries = response.data["entries"]
    assert [e["kind"] for e in entries] == ["wages", "wages", "starting_balance"]
    assert entries[-1]["balance_after"] == 500_000
    assert entries[0]["balance_after"] == 471_200
    assert entries[0]["balance_after"] == response.data["balance"]


def test_finances_for_a_user_with_no_team(db):
    manager_without_a_team = User.objects.create_user(
        email="no-team-finances@example.com", password="s0meth1ng-good",
    )
    client = APIClient()
    client.force_authenticate(user=manager_without_a_team)

    response = client.get("/api/economy/finances/")

    assert response.status_code == 200
    assert response.data["balance"] == 0
    assert response.data["weekly_wage_bill"] == 0
    assert response.data["entries"] == []


def test_finances_weekly_wage_bill_is_current_roster_payroll(finances_client, finances_team):
    # Deliberately not the ledger's last wages entry — the bill reflects
    # the roster as it stands now, per FinancesSerializer's docstring.
    attrs = dict(climb=50, sprint=50, flat=50, resistance=50, positioning=50)
    Rider.objects.create(team=finances_team, name="A", weekly_salary=1500, **attrs)
    Rider.objects.create(team=finances_team, name="B", weekly_salary=2200, **attrs)

    response = finances_client.get("/api/economy/finances/")

    assert response.status_code == 200
    assert response.data["weekly_wage_bill"] == 3700


def test_finances_includes_fanbase_and_weekly_change(finances_client, finances_team):
    at = datetime(2027, 3, 1, 0, 0, tzinfo=dt_timezone.utc)
    make_fanbase_entry(finances_team, "starting", 10_000, at)
    make_fanbase_entry(
        finances_team, "weekly", 650, at + timedelta(weeks=1), points=20,
    )
    make_fanbase_entry(
        finances_team, "weekly", -200, at + timedelta(weeks=2),
    )

    response = finances_client.get("/api/economy/finances/")

    assert response.status_code == 200
    assert response.data["fanbase"] == 10_450
    assert response.data["fanbase_change"] == -200


def test_finances_fanbase_change_is_zero_before_any_weekly_entry(finances_client, finances_team):
    at = datetime(2027, 3, 1, 0, 0, tzinfo=dt_timezone.utc)
    make_fanbase_entry(finances_team, "starting", 10_000, at)

    response = finances_client.get("/api/economy/finances/")

    assert response.status_code == 200
    assert response.data["fanbase"] == 10_000
    assert response.data["fanbase_change"] == 0


def test_finances_without_a_team_returns_zero_fanbase(db):
    manager_without_a_team = User.objects.create_user(
        email="no-team-finances-fanbase@example.com", password="s0meth1ng-good",
    )
    client = APIClient()
    client.force_authenticate(user=manager_without_a_team)

    response = client.get("/api/economy/finances/")

    assert response.status_code == 200
    assert response.data["fanbase"] == 0
    assert response.data["fanbase_change"] == 0


def test_merchandise_entry_serializes_with_its_kind(finances_client, finances_team):
    at = datetime(2027, 3, 1, 0, 0, tzinfo=dt_timezone.utc)
    make_ledger_entry(
        finances_team, "starting_balance", 500_000, at, "Starting balance",
    )
    make_ledger_entry(
        finances_team, "merchandise", 400, at + timedelta(weeks=1),
        "Merchandise revenue",
    )

    response = finances_client.get("/api/economy/finances/")

    assert response.status_code == 200
    entry = response.data["entries"][0]
    assert entry["kind"] == "merchandise"
    assert entry["amount"] == 400


@override_settings(GAME_CLOCK_CLASS="world.clocks.MockClock")
def test_finances_history_built_through_services_orders_by_game_time(db):
    """The regression test for review finding 1: every ledger entry must be
    stamped with *game* time, never the wall clock. A season dated 2027
    against a wall clock that reads one year earlier is exactly the trap —
    had opening balance / takeover used timezone.now(), they'd sort as the
    oldest rows and the newest-first order and running balance would invert.
    Serve the history from games, not read it off the page: opening balance,
    a week of wages, then a claim, each through the real services callers
    use, passing world.services.now() as `at`.
    """
    world_services._clock = None
    try:
        from economy.services import charge_weekly_wages, ensure_opening_balance
        from teams.services import claim_team
        from world.services import get_clock, now

        clock: MockClock = get_clock()
        season_start = datetime(2027, 3, 1, 0, 0, tzinfo=dt_timezone.utc)
        # The world's clock lives a year in the future of the wall clock this
        # test runs under. That divergence is the bug's fuel. load() first:
        # MockClock.set() reads the GameClock row, which load() creates.
        import world.models as world_models
        world_models.GameClock.load()
        clock.set(season_start - timedelta(days=1))

        unmanaged = Team.objects.create(name="Pool Team", code="POL")
        Rider.objects.create(
            name="Pool Rider", team=unmanaged,
            climb=60, sprint=60, flat=60, resistance=60, positioning=60,
        )
        user = User.objects.create_user(
            email="claim-finances@example.com", password="s0meth1ng-good",
        )

        ensure_opening_balance(unmanaged, at=now())   # stamped 2027-02-28

        season = Season.objects.create(number=1, starts_at=season_start)
        week = Week.objects.create(
            season=season, number=1,
            starts_at=season_start, ends_at=season_start + timedelta(weeks=1),
        )
        charge_weekly_wages(week)                      # stamped week.starts_at (2027-03-01)

        clock.set(season_start + timedelta(days=7))
        claim_team(user, name="Claimed Team", code="CLM", roster_size=0, at=now())

        client = APIClient()
        client.force_authenticate(user=user)
        response = client.get("/api/economy/finances/")
        assert response.status_code == 200

        entries = response.data["entries"]
        assert [e["kind"] for e in entries] == ["takeover", "wages", "starting_balance"]
        # Newest first, each balance_after chaining onto the previous one.
        assert entries[0]["occurred_at"] == "2027-03-08T00:00:00Z"
        assert entries[1]["occurred_at"] == "2027-03-01T00:00:00Z"
        assert entries[2]["occurred_at"] == "2027-02-28T00:00:00Z"
        assert entries[2]["balance_after"] == 500_000
        assert entries[1]["balance_after"] == 500_000 - 1_200
        assert entries[0]["balance_after"] == 500_000
        assert entries[0]["balance_after"] == response.data["balance"]
    finally:
        world_services._clock = None


@override_settings(GAME_CLOCK_CLASS="world.clocks.MockClock")
def test_touch_last_seen_writes_game_time(db):
    """The same trap as test_finances_history_built_through_services_orders_by_game_time:
    the world's clock lives a year away from the wall clock, so a
    touch_last_seen that reads timezone.now() instead of the passed-in `at`
    would still write *a* datetime, and only this divergence exposes it."""
    from api.services import touch_last_seen
    from world.services import get_clock

    world_services._clock = None
    try:
        clock: MockClock = get_clock()
        clock.now()  # GameClock.load() — creates the row set() requires
        game_time = datetime(2027, 3, 1, 0, 0, tzinfo=dt_timezone.utc)
        clock.set(game_time)

        user = User.objects.create_user(email="last-seen@example.com", password="s0meth1ng-good")
        touch_last_seen(user, now())
        user.refresh_from_db()

        assert user.last_seen_at == game_time
        assert user.last_seen_at != timezone.now()
    finally:
        world_services._clock = None


@override_settings(GAME_CLOCK_CLASS="world.clocks.MockClock")
def test_login_stamps_last_seen_at(db):
    """Posting through the real URL, not calling the view directly — this
    is what actually proves api.urls routes accounts/login/ to api's
    LoginView ahead of the plain one accounts.urls also registers."""
    from world.services import get_clock

    world_services._clock = None
    try:
        clock: MockClock = get_clock()
        clock.now()  # GameClock.load() — creates the row set() requires
        game_time = datetime(2027, 3, 1, 0, 0, tzinfo=dt_timezone.utc)
        clock.set(game_time)

        User.objects.create_user(email="login-stamp@example.com", password="s0meth1ng-good")
        client = APIClient()

        response = client.post("/api/accounts/login/", {
            "email": "login-stamp@example.com",
            "password": "s0meth1ng-good",
        }, format="json")

        assert response.status_code == 200
        user = User.objects.get(email="login-stamp@example.com")
        assert user.last_seen_at == game_time
    finally:
        world_services._clock = None


def test_failed_login_does_not_stamp_last_seen_at(db):
    User.objects.create_user(email="login-fail@example.com", password="s0meth1ng-good")
    client = APIClient()

    response = client.post("/api/accounts/login/", {
        "email": "login-fail@example.com",
        "password": "wrong-password-1",
    }, format="json")

    assert response.status_code == 400
    user = User.objects.get(email="login-fail@example.com")
    assert user.last_seen_at is None


@pytest.fixture
def sponsors_manager(db) -> User:
    return User.objects.create_user(email="sponsors-manager@example.com", password="s0meth1ng-good")


@pytest.fixture
def sponsors_team(db, sponsors_manager) -> Team:
    return Team.objects.create(name="Sponsors Team", code="SPN", manager=sponsors_manager)


@pytest.fixture
def sponsors_client(sponsors_manager) -> APIClient:
    client = APIClient()
    client.force_authenticate(user=sponsors_manager)
    return client


@pytest.fixture
def sponsors_season(db):
    """An in-season MockClock position, so current_position(now()) resolves
    to a real Season for SponsorsView — the same shape sponsors_team needs
    to generate offers against. Resets the clock after the test, matching
    the clock/finances tests above."""
    world_services._clock = None
    season_start = datetime(2027, 3, 1, 0, 0, tzinfo=dt_timezone.utc)
    season = Season.objects.create(number=1, starts_at=season_start)
    Week.objects.create(
        season=season, number=1,
        starts_at=season_start, ends_at=season_start + timedelta(weeks=1),
    )
    with override_settings(GAME_CLOCK_CLASS="world.clocks.MockClock"):
        clock = world_services.get_clock()
        clock.now()  # GameClock.load() — creates the row set() requires
        clock.set(season_start + timedelta(hours=1))
        yield season
    world_services._clock = None


def test_sponsors_requires_authentication(db):
    client = APIClient()

    assert client.get("/api/economy/sponsors/").status_code == 403


def test_sponsors_without_a_team_is_empty_not_403(db):
    manager_without_a_team = User.objects.create_user(
        email="no-team-sponsors@example.com", password="s0meth1ng-good",
    )
    client = APIClient()
    client.force_authenticate(user=manager_without_a_team)

    response = client.get("/api/economy/sponsors/")

    assert response.status_code == 200
    assert response.data == {"contract": None, "offers": []}


def test_sponsors_returns_a_round_for_a_new_team(sponsors_client, sponsors_team, sponsors_season):
    response = sponsors_client.get("/api/economy/sponsors/")

    assert response.status_code == 200
    assert response.data["contract"] is None
    assert len(response.data["offers"]) == 3
    assert {o["profile"] for o in response.data["offers"]} == {"steady", "balanced", "demanding"}


def test_sponsors_returns_the_contract_once_signed(sponsors_client, sponsors_team, sponsors_season):
    first = sponsors_client.get("/api/economy/sponsors/")
    offer_id = first.data["offers"][0]["id"]
    sponsors_client.post("/api/economy/sponsors/sign/", {"offer_id": offer_id})

    response = sponsors_client.get("/api/economy/sponsors/")

    assert response.data["offers"] == []
    assert response.data["contract"]["sponsor_name"] == first.data["offers"][0]["sponsor_name"]


def test_sign_creates_the_contract(sponsors_client, sponsors_team, sponsors_season):
    round_response = sponsors_client.get("/api/economy/sponsors/")
    offer_id = round_response.data["offers"][0]["id"]

    response = sponsors_client.post("/api/economy/sponsors/sign/", {"offer_id": offer_id})

    assert response.status_code == 204
    from economy.models import SponsorContract
    assert SponsorContract.objects.filter(team=sponsors_team).count() == 1


def test_sign_twice_is_409(sponsors_client, sponsors_team, sponsors_season):
    round_response = sponsors_client.get("/api/economy/sponsors/")
    offers = round_response.data["offers"]
    sponsors_client.post("/api/economy/sponsors/sign/", {"offer_id": offers[0]["id"]})

    response = sponsors_client.post("/api/economy/sponsors/sign/", {"offer_id": offers[1]["id"]})

    assert response.status_code == 409


def test_sign_someone_elses_offer_is_409(sponsors_client, sponsors_team, sponsors_season):
    other_manager = User.objects.create_user(email="other-sponsors@example.com", password="s0meth1ng-good")
    other_team = Team.objects.create(name="Other Sponsors Team", code="OSP", manager=other_manager)
    from economy.services import ensure_offer_round
    other_offers = ensure_offer_round(other_team, sponsors_season, at=now())

    response = sponsors_client.post("/api/economy/sponsors/sign/", {"offer_id": other_offers[0].pk})

    assert response.status_code == 409


@pytest.fixture
def market_manager(db) -> User:
    return User.objects.create_user(email="market-manager@example.com", password="s0meth1ng-good")


@pytest.fixture
def market_team(db, market_manager) -> Team:
    # managed_since in the past, so a Week can open after the claim and the
    # cooldown can genuinely expire; the free-release test leaves it alone.
    return Team.objects.create(
        name="Market Team", code="MKT", manager=market_manager,
        managed_since=datetime(2026, 3, 1, 0, 0, tzinfo=dt_timezone.utc),
    )


@pytest.fixture
def market_client(market_manager) -> APIClient:
    client = APIClient()
    client.force_authenticate(user=market_manager)
    return client


def _market_rider(name, **overrides) -> Rider:
    """A persisted rider owned by the transfer-market suite; mirrors
    transfers/tests/test_services.py's _rider."""
    defaults = dict(
        name=name,
        speciality=Rider.Speciality.ROULEUR,
        age=27,
        climb=50, sprint=50, flat=50, resistance=50, positioning=50,
    )
    defaults.update(overrides)
    return Rider.objects.create(**defaults)


def test_free_agents_requires_a_team(db):
    manager = User.objects.create_user(email="no-team-mkt@example.com", password="s0meth1ng-good")
    client = APIClient()
    client.force_authenticate(user=manager)

    response = client.get("/api/transfers/free-agents/")

    assert response.status_code == 403


def test_free_agents_view_lists_teamless_riders(market_client, market_team):
    _market_rider(name="Rostered", team=market_team)
    alice = _market_rider(name="Alice Free")
    bob = _market_rider(name="Bob Free")

    response = market_client.get("/api/transfers/free-agents/")

    assert response.status_code == 200
    assert [r["name"] for r in response.data["riders"]] == ["Alice Free", "Bob Free"]
    assert response.data["balance"] == 0
    alice_payload = response.data["riders"][0]
    assert alice_payload["signing_fee"] == signing_fee_for(alice)
    assert alice_payload["market_value"] == market_value_for(alice)
    # A free agent is on nobody's roster, so there is nothing to release —
    # the context-less degrade path, not a number.
    assert alice_payload["release_cost"] is None


def test_free_agents_endpoint_omits_retired_riders(market_client, market_team):
    _market_rider(name="Active Free")
    retired = _market_rider(name="Retired Free", retired_at=datetime(2027, 3, 1, tzinfo=dt_timezone.utc))

    response = market_client.get("/api/transfers/free-agents/")

    assert response.status_code == 200
    assert [rider["name"] for rider in response.data["riders"]] == ["Active Free"]
    assert retired.pk not in {rider["id"] for rider in response.data["riders"]}


def test_sign_free_agent_debits_the_fee_and_assigns_the_rider(market_client, market_team):
    make_ledger_entry(
        market_team, "starting_balance", STARTING_BALANCE, now(), "Starting balance",
    )
    free = _market_rider(name="Free Rider")

    response = market_client.post("/api/transfers/free-agents/sign/", {"rider_id": free.pk})

    assert response.status_code == 204
    free.refresh_from_db()
    assert free.team_id == market_team.pk
    assert free.joined_team_at is not None
    assert free.unattached_since is None
    fee_entry = LedgerEntry.objects.get(team=market_team, kind="transfer_fee")
    assert fee_entry.amount == -signing_fee_for(free)
    assert "Free Rider" in fee_entry.description


def test_signing_a_retired_rider_returns_409(market_client, market_team):
    retired = _market_rider(
        name="Retired Sign Target",
        retired_at=datetime(2027, 3, 1, tzinfo=dt_timezone.utc),
    )

    response = market_client.post(
        "/api/transfers/free-agents/sign/", {"rider_id": retired.pk}, format="json",
    )

    assert response.status_code == 409
    retired.refresh_from_db()
    assert retired.team_id is None
    assert retired.retired_at is not None


def test_sign_free_agent_409s_when_unaffordable(market_client, market_team):
    make_ledger_entry(market_team, "starting_balance", 100, now(), "Starting balance")
    strong = _market_rider(
        name="Pricy Rider",
        climb=99, sprint=99, flat=99, resistance=99, positioning=99,
    )

    response = market_client.post("/api/transfers/free-agents/sign/", {"rider_id": strong.pk})

    assert response.status_code == 409
    strong.refresh_from_db()
    assert strong.team_id is None
    assert not LedgerEntry.objects.filter(team=market_team, kind="transfer_fee").exists()


def test_release_rider_is_free_within_claim_cooldown(market_client, market_team):
    # No Week has opened since the claim, so the cooldown holds and the
    # inherited roster releases for free (Design decision 2).
    inherited = _market_rider(
        name="Inherited",
        team=market_team, joined_team_at=market_team.managed_since,
    )

    response = market_client.post(
        "/api/transfers/riders/release/", {"rider_id": inherited.pk},
    )

    assert response.status_code == 204
    inherited.refresh_from_db()
    assert inherited.team_id is None
    assert inherited.unattached_since is not None
    assert not LedgerEntry.objects.filter(team=market_team, kind="transfer_fee").exists()


def test_release_rider_charges_severance_after_cooldown(market_client, market_team):
    # One in-season Week opened since the claim, so the cooldown has run
    # out and the release costs severance (Design decision 2).
    season = Season.objects.create(number=1, starts_at=now())
    Week.objects.create(
        season=season, number=1,
        starts_at=now() - timedelta(days=1),
        ends_at=now(),
    )
    make_ledger_entry(
        market_team, "starting_balance", 500_000, now(), "Starting balance",
    )
    inherited = _market_rider(
        name="Inherited",
        team=market_team, joined_team_at=market_team.managed_since,
    )

    response = market_client.post(
        "/api/transfers/riders/release/", {"rider_id": inherited.pk},
    )

    assert response.status_code == 204
    inherited.refresh_from_db()
    assert inherited.team_id is None
    fee_entry = LedgerEntry.objects.get(team=market_team, kind="transfer_fee")
    assert fee_entry.amount == -severance_fee_for(inherited)
    assert "Inherited" in fee_entry.description


def test_roster_view_reports_release_cost_per_rider(market_client, market_team):
    inherited = _market_rider(
        name="Inherited",
        team=market_team, joined_team_at=market_team.managed_since,
    )
    signed = _market_rider(
        name="Signed Later",
        team=market_team,
        joined_team_at=market_team.managed_since + timedelta(days=2),
    )

    response = market_client.get("/api/riders/")

    by_name = {r["name"]: r for r in response.data["riders"]}
    assert by_name["Inherited"]["release_cost"] == 0
    assert by_name["Signed Later"]["release_cost"] == severance_fee_for(signed)


@pytest.fixture
def bidder_manager(db) -> User:
    return User.objects.create_user(email="bidder-manager@example.com", password="s0meth1ng-good")


@pytest.fixture
def bidder_team(db, bidder_manager) -> Team:
    return Team.objects.create(name="Bidder Team", code="BID", manager=bidder_manager)


@pytest.fixture
def bidder_client(bidder_manager) -> APIClient:
    client = APIClient()
    client.force_authenticate(user=bidder_manager)
    return client


def test_list_for_auction_requires_team(db):
    manager = User.objects.create_user(email="no-team-auction@example.com", password="s0meth1ng-good")
    client = APIClient()
    client.force_authenticate(user=manager)

    response = client.post("/api/transfers/auctions/list/", {"rider_id": 1})

    assert response.status_code == 403
    assert Auction.objects.count() == 0


def test_place_bid_rejects_amount_above_balance_with_409(
    market_client, market_team, bidder_client, bidder_team,
):
    make_ledger_entry(bidder_team, "starting_balance", 1_000, now(), "Starting balance")
    rider = _market_rider(name="For Sale", team=market_team)
    list_response = market_client.post(
        "/api/transfers/auctions/list/", {"rider_id": rider.pk},
    )
    assert list_response.status_code == 204
    auction = Auction.objects.get(rider=rider)

    response = bidder_client.post(
        f"/api/transfers/auctions/{auction.pk}/bid/", {"amount": auction.reserve_price},
    )

    assert response.status_code == 409
    assert not auction.bids.exists()


def test_auction_market_min_next_bid_is_the_reserve_itself_before_any_bid(
    market_client, market_team,
):
    # place_bid accepts the reserve itself as the opening bid (spec items
    # 3-4); min_next_bid must match that exactly, not the reserve plus an
    # increment nobody has to clear yet.
    rider = _market_rider(name="For Sale", team=market_team)
    market_client.post("/api/transfers/auctions/list/", {"rider_id": rider.pk})
    auction = Auction.objects.get(rider=rider)

    response = market_client.get("/api/transfers/auctions/")

    entry = response.data["auctions"][0]
    assert entry["bids"] == []
    assert entry["current_price"] == auction.reserve_price
    assert entry["min_next_bid"] == auction.reserve_price


def test_auction_market_shows_full_bid_history_with_team_identity(
    market_client, market_team, bidder_client, bidder_team,
):
    make_ledger_entry(bidder_team, "starting_balance", STARTING_BALANCE, now(), "Starting balance")
    rider = _market_rider(name="For Sale", team=market_team)
    market_client.post("/api/transfers/auctions/list/", {"rider_id": rider.pk})
    auction = Auction.objects.get(rider=rider)
    bidder_client.post(
        f"/api/transfers/auctions/{auction.pk}/bid/", {"amount": auction.reserve_price},
    )

    response = market_client.get("/api/transfers/auctions/")

    assert response.status_code == 200
    entry = response.data["auctions"][0]
    assert set(entry) == {
        "id", "rider", "current_price", "min_next_bid", "deadline", "is_own_listing", "forced", "bids",
    }
    assert entry["bids"] == [
        {"team_name": bidder_team.name, "amount": auction.reserve_price, "placed_at": entry["bids"][0]["placed_at"]},
    ]
    assert entry["current_price"] == auction.reserve_price
    assert entry["min_next_bid"] == auction.reserve_price + auction.min_increment


def test_auction_market_orders_bid_history_newest_first(
    market_client, market_team, bidder_client, bidder_team,
):
    make_ledger_entry(bidder_team, "starting_balance", STARTING_BALANCE, now(), "Starting balance")
    rider = _market_rider(name="For Sale", team=market_team)
    market_client.post("/api/transfers/auctions/list/", {"rider_id": rider.pk})
    auction = Auction.objects.get(rider=rider)
    bidder_client.post(
        f"/api/transfers/auctions/{auction.pk}/bid/", {"amount": auction.reserve_price},
    )
    second_amount = auction.reserve_price + auction.min_increment
    bidder_client.post(
        f"/api/transfers/auctions/{auction.pk}/bid/", {"amount": second_amount},
    )

    response = market_client.get("/api/transfers/auctions/")

    bids = response.data["auctions"][0]["bids"]
    assert [b["amount"] for b in bids] == [second_amount, auction.reserve_price]


def test_auction_market_hides_withdrawn_bids(market_client, market_team):
    rider = _market_rider(name="For Sale", team=market_team)
    market_client.post("/api/transfers/auctions/list/", {"rider_id": rider.pk})
    auction = Auction.objects.get(rider=rider)
    bidder_team = Team.objects.create(name="Bidder Team", code="BID")
    Bid.objects.create(
        auction=auction,
        bidder_team=bidder_team,
        amount=auction.reserve_price,
        placed_at=now(),
        withdrawn_at=now(),
    )

    response = market_client.get("/api/transfers/auctions/")

    entry = response.data["auctions"][0]
    assert entry["bids"] == []
    assert entry["min_next_bid"] == auction.reserve_price


def test_my_bids_shows_winning_status_when_high_bidder(
    market_client, market_team, bidder_client, bidder_team,
):
    make_ledger_entry(bidder_team, "starting_balance", STARTING_BALANCE, now(), "Starting balance")
    rider = _market_rider(name="For Sale", team=market_team)
    market_client.post("/api/transfers/auctions/list/", {"rider_id": rider.pk})
    auction = Auction.objects.get(rider=rider)
    bidder_client.post(
        f"/api/transfers/auctions/{auction.pk}/bid/", {"amount": auction.reserve_price},
    )

    response = bidder_client.get("/api/transfers/auctions/mine/")

    assert response.status_code == 200
    assert len(response.data) == 1
    row = response.data[0]
    assert row["auction_id"] == auction.pk
    assert row["rider_name"] == "For Sale"
    assert row["my_last_bid"] == auction.reserve_price
    assert row["current_price"] == auction.reserve_price
    assert row["is_high_bidder"] is True

    # The seller never placed a bid — not their auction to track.
    assert market_client.get("/api/transfers/auctions/mine/").data == []


def test_my_bids_shows_outbid_status_when_someone_else_leads(
    market_client, market_team, bidder_client, bidder_team,
):
    third_manager = User.objects.create_user(email="third-bidder@example.com", password="s0meth1ng-good")
    third_team = Team.objects.create(name="Third Team", code="THR", manager=third_manager)
    third_client = APIClient()
    third_client.force_authenticate(user=third_manager)
    make_ledger_entry(bidder_team, "starting_balance", STARTING_BALANCE, now(), "Starting balance")
    make_ledger_entry(third_team, "starting_balance", STARTING_BALANCE, now(), "Starting balance")
    rider = _market_rider(name="For Sale", team=market_team)
    market_client.post("/api/transfers/auctions/list/", {"rider_id": rider.pk})
    auction = Auction.objects.get(rider=rider)
    bidder_client.post(
        f"/api/transfers/auctions/{auction.pk}/bid/", {"amount": auction.reserve_price},
    )
    higher = auction.reserve_price + auction.min_increment
    third_client.post(
        f"/api/transfers/auctions/{auction.pk}/bid/", {"amount": higher},
    )

    response = bidder_client.get("/api/transfers/auctions/mine/")

    assert len(response.data) == 1
    row = response.data[0]
    assert row["my_last_bid"] == auction.reserve_price
    assert row["current_price"] == higher
    assert row["is_high_bidder"] is False

    # The new high bidder sees themself winning.
    winner_row = third_client.get("/api/transfers/auctions/mine/").data[0]
    assert winner_row["is_high_bidder"] is True


def test_my_bids_excludes_a_resolved_auction(
    market_client, market_team, bidder_client, bidder_team,
):
    from transfers.services import resolve_auction

    make_ledger_entry(bidder_team, "starting_balance", STARTING_BALANCE, now(), "Starting balance")
    rider = _market_rider(name="For Sale", team=market_team)
    market_client.post("/api/transfers/auctions/list/", {"rider_id": rider.pk})
    auction = Auction.objects.get(rider=rider)
    bidder_client.post(
        f"/api/transfers/auctions/{auction.pk}/bid/", {"amount": auction.reserve_price},
    )

    resolve_auction(
        auction, at=auction.deadline,
        charge_buyer=lambda *a, **kw: None, pay_seller=lambda *a, **kw: None,
    )

    response = bidder_client.get("/api/transfers/auctions/mine/")

    assert response.data == []


def test_my_bids_excludes_withdrawn_bids(
    market_team, bidder_client, bidder_team,
):
    rider = _market_rider(name="For Sale", team=market_team)
    auction = Auction.objects.create(
        rider=rider,
        seller_team=market_team,
        reserve_price=50_000,
        current_price=50_000,
        min_increment=2_500,
        deadline=now() + timedelta(days=3),
        listed_at=now(),
    )
    Bid.objects.create(
        auction=auction,
        bidder_team=bidder_team,
        amount=auction.reserve_price,
        placed_at=now(),
        withdrawn_at=now(),
    )

    response = bidder_client.get("/api/transfers/auctions/mine/")

    assert response.data == []


def test_my_bids_query_count_is_constant(
    market_team, bidder_client, bidder_team, django_assert_max_num_queries,
):
    make_ledger_entry(bidder_team, "starting_balance", STARTING_BALANCE, now(), "Starting balance")

    from transfers.services import list_for_auction

    def _list_and_bid(rider_name: str) -> None:
        rider = _market_rider(name=rider_name, team=market_team)
        auction = list_for_auction(market_team, rider.pk, at=now())
        bidder_client.post(
            f"/api/transfers/auctions/{auction.pk}/bid/", {"amount": auction.reserve_price},
        )

    _list_and_bid("Rider One")

    with django_assert_max_num_queries(10):
        response = bidder_client.get("/api/transfers/auctions/mine/")
    assert response.status_code == 200
    assert len(response.data) == 1

    for i in range(2, 6):
        _list_and_bid(f"Rider {i}")

    with django_assert_max_num_queries(10):
        response = bidder_client.get("/api/transfers/auctions/mine/")
    assert response.status_code == 200
    assert len(response.data) == 5


# --- rider profile ---


@pytest.fixture
def profile_teams(db) -> tuple[Team, Team]:
    return (
        Team.objects.create(name="Profile Team A", code="PFA"),
        Team.objects.create(name="Profile Team B", code="PFB"),
    )


@pytest.fixture
def profile_rider(db, profile_teams) -> Rider:
    team_a, _ = profile_teams
    return Rider.objects.create(
        name="Profile Rider", team=team_a,
        speciality=Rider.Speciality.CLIMBER, age=24,
        height_cm=170, weight_kg=60,
        climb=84, sprint=30, flat=40, resistance=60, positioning=52,
    )


@pytest.fixture
def profile_owner(db, profile_teams) -> User:
    team_a, _ = profile_teams
    manager = User.objects.create_user(email="profile-owner@example.com", password="s0meth1ng-good")
    team_a.manager = manager
    team_a.save()
    return manager


@pytest.fixture
def profile_owner_client(profile_owner) -> APIClient:
    client = APIClient()
    client.force_authenticate(user=profile_owner)
    return client


@pytest.fixture
def profile_client(db) -> APIClient:
    viewer = User.objects.create_user(email="profile-viewer@example.com", password="s0meth1ng-good")
    client = APIClient()
    client.force_authenticate(user=viewer)
    return client


def _finished_race(name: str, *, starts_at=None) -> Race:
    return Race.objects.create(
        name=name, course=[{"length": 40000.0, "gradient": 0.0}],
        status=Race.Status.FINISHED, starts_at=starts_at,
    )


def _enter_squad(race: Race, team: Team, rider: Rider) -> RaceSquad:
    squad = RaceSquad.objects.create(race=race, team=team)
    RaceSquadRider.objects.create(squad=squad, rider=rider, is_leader=True)
    return squad


def test_rider_profile_requires_authentication(profile_rider):
    client = APIClient()

    response = client.get(f"/api/riders/{profile_rider.pk}/")

    assert response.status_code == 403


def test_rider_profile_readable_by_any_manager_and_by_teamless_user(profile_rider, profile_teams):
    _, team_b = profile_teams
    rival_manager = User.objects.create_user(email="rival@example.com", password="s0meth1ng-good")
    team_b.manager = rival_manager
    team_b.save()
    rival_client = APIClient()
    rival_client.force_authenticate(user=rival_manager)

    response = rival_client.get(f"/api/riders/{profile_rider.pk}/")
    assert response.status_code == 200

    teamless = User.objects.create_user(email="teamless@example.com", password="s0meth1ng-good")
    teamless_client = APIClient()
    teamless_client.force_authenticate(user=teamless)

    response = teamless_client.get(f"/api/riders/{profile_rider.pk}/")
    assert response.status_code == 200


def test_rider_profile_of_a_retired_rider_returns_200_with_retired_week(
    profile_client, profile_rider, profile_teams,
):
    monday = datetime(2027, 3, 1, 0, 0, tzinfo=dt_timezone.utc)
    season = _create_season_with_weeks(monday)
    week_11 = season.weeks.get(number=11)
    team_a, _ = profile_teams
    race = _finished_race("Retired Rider Race", starts_at=week_11.starts_at)
    _enter_squad(race, team_a, profile_rider)
    RaceResult.objects.create(
        race=race, rider=profile_rider, position=1, finish_time=3600.0,
    )
    profile_rider.team = None
    profile_rider.retired_at = week_11.starts_at
    profile_rider.save()

    response = profile_client.get(f"/api/riders/{profile_rider.pk}/")

    assert response.status_code == 200
    assert response.data["retired"] == {"season": 1, "week": 11}
    assert response.data["team"] is None
    assert response.data["races"]


def test_rider_profile_of_an_active_rider_has_null_retired(profile_client, profile_rider):
    response = profile_client.get(f"/api/riders/{profile_rider.pk}/")

    assert response.status_code == 200
    assert response.data["retired"] is None


def test_retired_payload_outside_a_season_does_not_error(profile_client, profile_rider):
    monday = datetime(2027, 3, 1, 0, 0, tzinfo=dt_timezone.utc)
    season = _create_season_with_weeks(monday)
    profile_rider.team = None
    profile_rider.retired_at = season.ends_at + timedelta(days=1)
    profile_rider.save()

    response = profile_client.get(f"/api/riders/{profile_rider.pk}/")

    assert response.status_code == 200
    assert response.data["retired"] == {"season": 1, "week": None}


def test_rider_profile_unknown_rider_is_404(profile_client):
    response = profile_client.get("/api/riders/999999/")

    assert response.status_code == 404


def test_rider_profile_has_no_hidden_traits(profile_client, profile_rider):
    # Load-bearing: the exact key set, not just the absence of known hidden
    # names — a new hidden trait added later must fail this test.
    response = profile_client.get(f"/api/riders/{profile_rider.pk}/")

    assert response.status_code == 200
    assert set(response.data.keys()) == {
        "id", "name", "speciality", "nationality", "age", "height_cm", "weight_kg",
        "climb", "sprint", "flat", "resistance", "positioning",
        "freshness", "weekly_salary", "market_value", "release_cost", "final_season",
        "team", "current_week", "retired", "attribute_history", "races", "career",
        "development_squad",
    }
    # The retirement age itself stays hidden; only the boolean consequence ships.
    assert "retirement_age" not in response.data


def test_rider_profile_identity_matches_roster_payload(profile_rider, profile_owner_client):
    roster = profile_owner_client.get("/api/riders/").data["riders"]
    roster_rider = next(r for r in roster if r["id"] == profile_rider.pk)

    response = profile_owner_client.get(f"/api/riders/{profile_rider.pk}/")

    for key, value in roster_rider.items():
        if key == "release_cost":
            continue
        assert response.data[key] == value, key


def test_rider_profile_attribute_history_orders_baseline_first_then_by_week(profile_client, profile_rider):
    monday = datetime(2027, 3, 1, 0, 0, tzinfo=dt_timezone.utc)
    season = Season.objects.create(number=1, starts_at=monday)
    week1 = Week.objects.create(
        season=season, number=1, starts_at=monday, ends_at=monday + timedelta(weeks=1),
    )
    week2 = Week.objects.create(
        season=season, number=2,
        starts_at=monday + timedelta(weeks=1), ends_at=monday + timedelta(weeks=2),
    )

    # Written out of created_at order, to prove ordering does not follow it.
    RiderAttributeSnapshot.objects.create(
        rider=profile_rider, week=week2, climb=9, sprint=3, flat=4, resistance=6, positioning=5,
    )
    RiderAttributeSnapshot.objects.create(
        rider=profile_rider, week=week1, climb=8, sprint=3, flat=4, resistance=6, positioning=5,
    )
    RiderAttributeSnapshot.objects.create(
        rider=profile_rider, week=None, climb=7, sprint=3, flat=4, resistance=6, positioning=5,
    )

    response = profile_client.get(f"/api/riders/{profile_rider.pk}/")

    history = response.data["attribute_history"]
    assert [(h["season"], h["week"]) for h in history] == [(None, None), (1, 1), (1, 2)]
    assert [h["climb"] for h in history] == [7, 8, 9]


def test_rider_profile_attribute_history_values_are_not_rescaled(profile_client, profile_rider):
    RiderAttributeSnapshot.objects.create(
        rider=profile_rider, week=None, climb=8, sprint=3, flat=4, resistance=6, positioning=5,
    )

    response = profile_client.get(f"/api/riders/{profile_rider.pk}/")

    assert response.data["attribute_history"][0]["climb"] == 8


def test_rider_profile_race_team_is_team_raced_for_not_current_team(profile_client, profile_rider, profile_teams):
    team_a, team_b = profile_teams
    race = _finished_race("History Race")
    _enter_squad(race, team_a, profile_rider)
    RaceResult.objects.create(race=race, rider=profile_rider, position=2, finish_time=3600.0)

    profile_rider.team = team_b
    profile_rider.save()

    response = profile_client.get(f"/api/riders/{profile_rider.pk}/")

    assert response.data["races"][0]["team"]["id"] == team_a.pk
    assert response.data["team"]["id"] == team_b.pk


def test_rider_profile_dnf_row_and_career_counts(profile_client, profile_rider, profile_teams):
    team_a, _ = profile_teams
    race = _finished_race("DNF Race")
    _enter_squad(race, team_a, profile_rider)
    RaceResult.objects.create(race=race, rider=profile_rider, position=3, finish_time=None)

    response = profile_client.get(f"/api/riders/{profile_rider.pk}/")

    row = response.data["races"][0]
    assert row["finished"] is False
    assert row["finish_time"] is None
    assert row["position"] == 3
    assert response.data["career"] == {"starts": 1, "wins": 0, "podiums": 0, "top_tens": 0, "dnfs": 1}


def test_rider_profile_has_no_points_field(profile_client, profile_rider, profile_teams):
    team_a, _ = profile_teams
    race = _finished_race("Points Race")
    _enter_squad(race, team_a, profile_rider)
    RaceResult.objects.create(race=race, rider=profile_rider, position=1, finish_time=3600.0)

    response = profile_client.get(f"/api/riders/{profile_rider.pk}/")

    assert "points" not in response.data["races"][0]
    assert "points" not in response.data["career"]


def test_rider_profile_winner_time_and_order_newest_first(profile_client, profile_rider, profile_teams):
    team_a, _ = profile_teams
    early = _finished_race("Earlier Race", starts_at=datetime(2027, 3, 1, 12, 0, tzinfo=dt_timezone.utc))
    late = _finished_race("Later Race", starts_at=datetime(2027, 3, 8, 12, 0, tzinfo=dt_timezone.utc))
    early_squad = _enter_squad(early, team_a, profile_rider)
    _enter_squad(late, team_a, profile_rider)

    mate = Rider.objects.create(
        name="Teammate", team=team_a,
        climb=50, sprint=50, flat=50, resistance=50, positioning=50,
    )
    RaceSquadRider.objects.create(squad=early_squad, rider=mate)
    RaceResult.objects.create(race=early, rider=mate, position=1, finish_time=3600.0)
    RaceResult.objects.create(race=early, rider=profile_rider, position=2, finish_time=3700.0)
    RaceResult.objects.create(race=late, rider=profile_rider, position=1, finish_time=3500.0)

    response = profile_client.get(f"/api/riders/{profile_rider.pk}/")

    races = response.data["races"]
    assert [r["race"]["id"] for r in races] == [late.pk, early.pk]
    early_row = next(r for r in races if r["race"]["id"] == early.pk)
    assert early_row["finish_time"] == 3700.0
    assert early_row["winner_time"] == 3600.0


def test_rider_profile_current_week_in_off_and_no_season(profile_client, profile_rider):
    response = profile_client.get(f"/api/riders/{profile_rider.pk}/")
    assert response.data["current_week"] is None  # no_season

    monday = datetime(2020, 1, 6, 0, 0, tzinfo=dt_timezone.utc)
    Season.objects.create(number=1, starts_at=monday)

    response = profile_client.get(f"/api/riders/{profile_rider.pk}/")
    assert response.data["current_week"] == {"season": 1, "week": SEASON_WEEKS}


def test_roster_in_season_is_computed_once(
    roster_team, roster_client, django_assert_max_num_queries,
):
    """The in-season check is cached on the shared serializer context, so a
    roster costs the same number of queries whatever its size (#42)."""
    for index in range(9):
        Rider.objects.create(
            name=f"Extra {index}", team=roster_team, speciality=Rider.Speciality.CLIMBER,
            age=24, climb=40, sprint=40, flat=40, resistance=40, positioning=40,
        )
    _create_season_with_weeks(now() - timedelta(weeks=1))

    with django_assert_max_num_queries(10):
        response = roster_client.get("/api/riders/")
    assert response.status_code == 200
    assert len(response.data["riders"]) == 9

    for index in range(9, 19):
        Rider.objects.create(
            name=f"Extra {index}", team=roster_team, speciality=Rider.Speciality.CLIMBER,
            age=24, climb=40, sprint=40, flat=40, resistance=40, positioning=40,
        )

    with django_assert_max_num_queries(10):
        response = roster_client.get("/api/riders/")
    assert response.status_code == 200
    assert len(response.data["riders"]) == 19


def test_roster_marks_final_season_rider_in_season(roster_rider, roster_client):
    _create_season_with_weeks(now() - timedelta(weeks=1))
    roster_rider.age = 38
    roster_rider.peak_age = 32
    roster_rider.decline_rate = 1
    roster_rider.save()

    response = roster_client.get("/api/riders/")

    assert response.data["riders"][0]["final_season"] is True


def test_roster_does_not_mark_final_season_off_season(roster_rider, roster_client):
    _create_season_with_weeks(now() - timedelta(weeks=13))
    roster_rider.age = 38
    roster_rider.peak_age = 32
    roster_rider.decline_rate = 1
    roster_rider.save()

    response = roster_client.get("/api/riders/")

    assert response.data["riders"][0]["final_season"] is False


def test_rider_profile_carries_final_season(profile_client, profile_rider):
    _create_season_with_weeks(now() - timedelta(weeks=1))
    profile_rider.age = 38
    profile_rider.peak_age = 32
    profile_rider.decline_rate = 1
    profile_rider.save()

    response = profile_client.get(f"/api/riders/{profile_rider.pk}/")

    assert response.data["final_season"] is True


def test_retired_rider_profile_final_season_false(profile_client, profile_rider):
    """A rider who has already retired is never tagged, whatever their age —
    the marker means "still to happen"."""
    _create_season_with_weeks(now() - timedelta(weeks=1))
    profile_rider.age = 38
    profile_rider.peak_age = 32
    profile_rider.decline_rate = 1
    profile_rider.team = None
    profile_rider.retired_at = datetime(2027, 3, 1, tzinfo=dt_timezone.utc)
    profile_rider.save()

    response = profile_client.get(f"/api/riders/{profile_rider.pk}/")

    assert response.data["final_season"] is False


def test_free_agents_carry_final_season(market_client, market_team):
    _create_season_with_weeks(now() - timedelta(weeks=1))
    marked = _market_rider(
        name="Marked Free", age=38, peak_age=32, decline_rate=1,
    )
    _market_rider(name="Young Free", age=24, peak_age=32, decline_rate=1)

    response = market_client.get("/api/transfers/free-agents/")

    by_name = {r["name"]: r for r in response.data["riders"]}
    assert by_name["Marked Free"]["final_season"] is True
    assert by_name["Young Free"]["final_season"] is False
    assert by_name["Marked Free"]["id"] == marked.pk


def test_rider_profile_query_count_is_constant(
    profile_client, profile_rider, profile_teams, django_assert_max_num_queries,
):
    team_a, _ = profile_teams

    def add_race(position: int) -> None:
        race = _finished_race(f"Race {position}")
        _enter_squad(race, team_a, profile_rider)
        RaceResult.objects.create(race=race, rider=profile_rider, position=position, finish_time=3600.0 + position)

    add_race(1)

    with django_assert_max_num_queries(10):
        response = profile_client.get(f"/api/riders/{profile_rider.pk}/")
    assert response.status_code == 200

    for position in range(2, 6):
        add_race(position)

    with django_assert_max_num_queries(10):
        response = profile_client.get(f"/api/riders/{profile_rider.pk}/")
    assert response.status_code == 200


# --- Development squad (#32) -------------------------------------------------


@pytest.fixture
def dev_squad_manager(db) -> User:
    """Named apart from the race-squad-selection `squad_*` fixtures above:
    this is a development squad, a different feature with a different
    vocabulary, and reusing those names would shadow them."""
    return User.objects.create_user(
        email="dev-squad-manager@example.com", password="s0meth1ng-good",
    )


@pytest.fixture
def dev_squad_team(db, dev_squad_manager) -> Team:
    team = Team.objects.create(name="Youth Team", code="YTH", manager=dev_squad_manager)
    # Funded, since almost every squad move costs something. The too-poor case
    # that must be refused is its own test, which lowers this balance.
    make_ledger_entry(team, "starting_balance", STARTING_BALANCE, now(), "Starting balance")
    return team


@pytest.fixture
def dev_squad_client(dev_squad_team) -> APIClient:
    """Depends on the team fixture, not just the user: a manager with no team
    is 403 on every one of these endpoints, which would make the client
    useless in a test that does not also ask for the team."""
    client = APIClient()
    client.force_authenticate(user=dev_squad_team.manager)
    return client


def _open_squad(team, level) -> None:
    """Put a squad row at `level` directly, for the tests that need a squad
    somewhere up the ladder.

    Not `open_squad`, which only opens at the entry level and charges a fee for
    it: these tests are about the *API* over a state that already exists, and
    they have their own tests for the fee an opening actually debits. The row
    is what a squad is, and the ladder is a rule about reaching one.
    """
    DevelopmentSquad.objects.create(team=team, level=level, opened_at=now())


def test_development_squad_requires_authentication(db):
    client = APIClient()

    assert client.get("/api/development-squad/").status_code == 403
    assert client.post("/api/development-squad/open/", {"level": 1}).status_code == 403
    assert client.post("/api/development-squad/level/", {"level": 1}).status_code == 403
    assert client.post("/api/development-squad/close/").status_code == 403


def test_development_squad_without_team_is_403(db):
    manager_without_a_team = User.objects.create_user(
        email="no-team-squad@example.com", password="s0meth1ng-good",
    )
    client = APIClient()
    client.force_authenticate(user=manager_without_a_team)

    assert client.get("/api/development-squad/").status_code == 403
    assert client.post("/api/development-squad/open/", {"level": 1}).status_code == 403
    assert client.post("/api/development-squad/level/", {"level": 1}).status_code == 403
    assert client.post("/api/development-squad/close/").status_code == 403


def test_development_squad_closed_payload(dev_squad_client, dev_squad_team):
    response = dev_squad_client.get("/api/development-squad/")

    assert response.status_code == 200
    assert response.data["level"] is None
    assert response.data["balance"] == STARTING_BALANCE
    assert [level["level"] for level in response.data["levels"]] == [1, 2, 3]
    assert [level["name"] for level in response.data["levels"]] == [
        "Regional", "National", "Elite",
    ]
    # Closed: only the entry level can be opened, and the rest are locked with
    # the level they are waiting for. The fee is each level's own, in every
    # state — the card shows what moving onto it would cost.
    assert [level["action"] for level in response.data["levels"]] == [
        "open", "locked", "locked",
    ]
    assert [level["requires"] for level in response.data["levels"]] == [
        None, "Open Regional first.", "Open Regional first.",
    ]
    assert [level["fee"] for level in response.data["levels"]] == [
        LEVELS[1].opening_fee, LEVELS[2].opening_fee, LEVELS[3].opening_fee,
    ]
    for level in response.data["levels"]:
        terms = LEVELS[level["level"]]
        assert level["weekly_cost"] == terms.weekly_cost
        assert level["season_cost"] == terms.weekly_cost * SEASON_WEEKS
    assert not DevelopmentSquad.objects.filter(team=dev_squad_team).exists()


def test_development_squad_payload_lists_riders_without_salary_or_value(dev_squad_client, dev_squad_team):
    _open_squad(dev_squad_team, 1)
    run_intake(at=now())

    response = dev_squad_client.get("/api/development-squad/")

    assert response.status_code == 200
    assert len(response.data["riders"]) == 2
    rider_payload = response.data["riders"][0]
    for absent_key in ("weekly_salary", "market_value", "release_cost", "final_season"):
        assert absent_key not in rider_payload
    for present_key in ("id", "name", "speciality", "nationality", "age", "arrived", "is_new"):
        assert present_key in rider_payload
    for attribute in ("climb", "sprint", "flat", "resistance", "positioning"):
        assert attribute in rider_payload
    assert response.data["intake"]["every_weeks"] == 4
    assert response.data["intake"]["batch_size"] == 2


@override_settings(GAME_CLOCK_CLASS="world.clocks.MockClock")
def test_development_squad_marks_only_latest_batch_new(dev_squad_client, dev_squad_team):
    world_services._clock = None
    try:
        import world.models as world_models
        from world.clocks import MockClock
        from world.services import get_clock

        world_models.GameClock.load()
        clock: MockClock = get_clock()
        season_start = datetime(2027, 3, 1, 0, 0, tzinfo=dt_timezone.utc)
        clock.set(season_start)
        season = Season.objects.create(number=1, starts_at=season_start)
        for n in range(1, 9):
            week_start = season_start + timedelta(weeks=n - 1)
            Week.objects.create(
                season=season, number=n, starts_at=week_start,
                ends_at=week_start + timedelta(weeks=1),
            )
        _open_squad(dev_squad_team, 1)
        week_four_start = season.weeks.get(number=4).starts_at
        week_eight_start = season.weeks.get(number=8).starts_at
        run_intake(at=week_four_start)
        run_intake(at=week_eight_start)
        clock.set(week_eight_start + timedelta(hours=1))

        response = dev_squad_client.get("/api/development-squad/")

        assert len(response.data["riders"]) == 4
        is_new_by_arrival = {}
        for rider in response.data["riders"]:
            is_new_by_arrival.setdefault(tuple(rider["arrived"].values()), []).append(rider["is_new"])
        assert all(is_new_by_arrival[(1, 8)])
        assert not any(is_new_by_arrival[(1, 4)])
    finally:
        world_services._clock = None


@override_settings(GAME_CLOCK_CLASS="world.clocks.MockClock")
def test_development_squad_intake_next_week(dev_squad_client, dev_squad_team):
    world_services._clock = None
    try:
        import world.models as world_models
        from world.clocks import MockClock
        from world.services import get_clock

        world_models.GameClock.load()
        clock: MockClock = get_clock()
        season_start = datetime(2027, 3, 1, 0, 0, tzinfo=dt_timezone.utc)
        clock.set(season_start)
        season = Season.objects.create(number=1, starts_at=season_start)
        for n in range(1, SEASON_WEEKS + 1):
            week_start = season_start + timedelta(weeks=n - 1)
            Week.objects.create(
                season=season, number=n, starts_at=week_start,
                ends_at=week_start + timedelta(weeks=1),
            )
        _open_squad(dev_squad_team, 1)

        response = dev_squad_client.get("/api/development-squad/")
        # arrivals_at_risk is 0 for an empty squad: every one of the batch's
        # two riders has a place to land in (#34).
        assert response.data["intake"]["next"] == {
            "season": 1, "week": 4, "arrivals_at_risk": 0,
        }

        # After the season's last intake week (12), nothing further is declared.
        clock.set(season.weeks.get(number=12).starts_at + timedelta(hours=1))
        response = dev_squad_client.get("/api/development-squad/")
        assert response.data["intake"]["next"] is None
    finally:
        world_services._clock = None


def test_development_squad_closed_has_no_riders(dev_squad_client, dev_squad_team):
    response = dev_squad_client.get("/api/development-squad/")

    assert response.data["riders"] == []
    assert response.data["intake"] is None


def test_close_endpoint_releases_graduates_to_free_agent_list(dev_squad_client, dev_squad_team):
    """Closing the squad discards the prospects still in development and
    lists the graduates; only the latter reach the market (#34)."""
    _open_squad(dev_squad_team, 1)
    run_intake(at=now())
    graduated, still_here = list(
        Rider.objects.filter(development_squad__team=dev_squad_team).order_by("pk"),
    )
    graduated.graduated_at = now()
    graduated.save(update_fields=["graduated_at"])
    market_client = APIClient()
    market_manager = User.objects.create_user(
        email="squad-close-buyer@example.com", password="s0meth1ng-good",
    )
    market_team = Team.objects.create(name="Buyer Team", code="BUY", manager=market_manager)
    market_client.force_authenticate(user=market_manager)

    response = dev_squad_client.post("/api/development-squad/close/")

    assert response.status_code == 204
    pool = market_client.get("/api/transfers/free-agents/")
    assert [r["id"] for r in pool.data["riders"]] == [graduated.pk]
    assert not Rider.objects.filter(pk=still_here.pk).exists()


def test_rider_profile_shows_development_squad_team(dev_squad_client, dev_squad_team):
    _open_squad(dev_squad_team, 1)
    run_intake(at=now())
    rider = Rider.objects.filter(development_squad__team=dev_squad_team).first()

    response = dev_squad_client.get(f"/api/riders/{rider.pk}/")

    assert response.status_code == 200
    assert response.data["development_squad"] == {
        "id": dev_squad_team.pk, "name": dev_squad_team.name, "code": dev_squad_team.code,
    }


def test_squad_rider_cannot_be_listed_released_or_raced(dev_squad_client, dev_squad_team):
    _open_squad(dev_squad_team, 1)
    run_intake(at=now())
    rider = Rider.objects.filter(development_squad__team=dev_squad_team).first()

    list_response = dev_squad_client.post(
        "/api/transfers/auctions/list/", {"rider_id": rider.pk},
    )
    assert list_response.status_code == 409

    release_response = dev_squad_client.post(
        "/api/transfers/riders/release/", {"rider_id": rider.pk},
    )
    assert release_response.status_code == 409

    race = Race.objects.create(
        name="Squad Test Race",
        course=[{"length": 40000.0, "gradient": 0.0}],
    )
    with pytest.raises(SquadError):
        set_squad(race, dev_squad_team, [rider.pk], rider.pk)


def test_every_level_is_priced_from_the_table(dev_squad_client):
    """The extra behind test_development_squad_closed_payload: whatever the
    state, no level's figures are ever anything but the table's."""
    response = dev_squad_client.get("/api/development-squad/")

    for level in response.data["levels"]:
        terms = LEVELS[level["level"]]
        assert level["fee"] == terms.opening_fee
        assert level["weekly_cost"] == terms.weekly_cost
        assert level["season_cost"] == terms.weekly_cost * SEASON_WEEKS


@pytest.mark.parametrize("current", [1, 2, 3])
def test_open_payload_unlocks_only_the_next_level_up(dev_squad_client, dev_squad_team, current):
    _open_squad(dev_squad_team, current)

    response = dev_squad_client.get("/api/development-squad/")

    assert response.data["level"] == current
    by_level = {level["level"]: level for level in response.data["levels"]}
    assert by_level[current]["action"] == "current"
    assert by_level[current]["requires"] is None
    above = by_level.get(current + 1)
    if above is None:
        assert {level["action"] for level in by_level.values()} == {"current", "locked"}
    else:
        assert above["action"] == "upgrade"
        assert above["requires"] is None
    # Everything else is locked and says what it is waiting for, and no level
    # anywhere is a downgrade — there is no such move to offer.
    for level_number, level in by_level.items():
        if level_number in (current, current + 1):
            continue
        assert level["action"] == "locked"
        assert level["requires"]
    assert all(level["action"] != "downgrade" for level in by_level.values())


@pytest.mark.parametrize(
    "current,locked,note",
    [
        (2, 1, "Climbed past. Close the squad to start over."),
        (3, 1, "Climbed past. Close the squad to start over."),
        (1, 3, "Upgrade to National first."),
    ],
)
def test_open_payload_distinguishes_climbed_past_from_not_yet_reached(
    dev_squad_client, dev_squad_team, current, locked, note,
):
    """The two kinds of lock are different advice — one is a step forward, the
    other means the only way back is to close — and the screen can only tell
    them apart if the server says which."""
    _open_squad(dev_squad_team, current)

    by_level = {
        level["level"]: level
        for level in dev_squad_client.get("/api/development-squad/").data["levels"]
    }

    assert by_level[locked]["action"] == "locked"
    assert by_level[locked]["requires"] == note


def test_open_debits_fee(dev_squad_client, dev_squad_team):
    response = dev_squad_client.post("/api/development-squad/open/", {"level": 1})

    assert response.status_code == 204
    assert DevelopmentSquad.objects.filter(team=dev_squad_team, level=1).exists()
    follow_up = dev_squad_client.get("/api/development-squad/")
    assert follow_up.data["balance"] == STARTING_BALANCE - LEVELS[1].opening_fee
    entry = LedgerEntry.objects.get(team=dev_squad_team, kind="development_squad_fee")
    assert entry.amount == -LEVELS[1].opening_fee
    assert entry.description == "Opened development squad — Regional"


@pytest.mark.parametrize("level", [2, 3])
def test_open_above_the_entry_level_is_409(dev_squad_client, dev_squad_team, level):
    """The ladder is climbed, not entered at any height — however rich the
    team is, there is no door straight into the upper floors."""
    response = dev_squad_client.post("/api/development-squad/open/", {"level": level})

    assert response.status_code == 409
    assert not DevelopmentSquad.objects.filter(team=dev_squad_team).exists()
    assert not LedgerEntry.objects.filter(
        team=dev_squad_team, kind="development_squad_fee",
    ).exists()


def test_open_squad_refused_when_balance_too_low(dev_squad_client, dev_squad_team):
    LedgerEntry.objects.filter(team=dev_squad_team).update(amount=100)

    response = dev_squad_client.post("/api/development-squad/open/", {"level": 1})

    assert response.status_code == 409
    assert not DevelopmentSquad.objects.filter(team=dev_squad_team).exists()
    # The refusal must leave no fee behind, or a player too poor to open a
    # squad is charged for having tried.
    assert not LedgerEntry.objects.filter(
        team=dev_squad_team, kind="development_squad_fee",
    ).exists()


def test_open_squad_when_already_open_returns_409(dev_squad_client, dev_squad_team):
    _open_squad(dev_squad_team, 1)
    fees_before = LedgerEntry.objects.filter(
        team=dev_squad_team, kind="development_squad_fee",
    ).count()

    response = dev_squad_client.post("/api/development-squad/open/", {"level": 1})

    assert response.status_code == 409
    assert DevelopmentSquad.objects.get(team=dev_squad_team).level == 1
    assert LedgerEntry.objects.filter(
        team=dev_squad_team, kind="development_squad_fee",
    ).count() == fees_before


def test_open_invalid_level_is_400(dev_squad_client):
    response = dev_squad_client.post("/api/development-squad/open/", {"level": 4})

    assert response.status_code == 400
    assert "level" in response.data


def test_upgrade_debits_the_target_levels_own_fee(dev_squad_client, dev_squad_team):
    _open_squad(dev_squad_team, 1)
    balance_before = dev_squad_client.get("/api/development-squad/").data["balance"]

    response = dev_squad_client.post("/api/development-squad/level/", {"level": 2})

    assert response.status_code == 204
    assert DevelopmentSquad.objects.get(team=dev_squad_team).level == 2
    # The target level's full fee, not a difference against Regional, so the
    # quoted figure and the debited one are the same number.
    expected = LEVELS[2].opening_fee
    assert dev_squad_client.get("/api/development-squad/").data["balance"] == (
        balance_before - expected
    )
    entry = LedgerEntry.objects.get(team=dev_squad_team, kind="development_squad_fee")
    assert entry.amount == -expected
    assert entry.description == "Upgraded development squad to National"


def test_upgrade_skipping_a_level_is_409(dev_squad_client, dev_squad_team):
    _open_squad(dev_squad_team, 1)

    response = dev_squad_client.post("/api/development-squad/level/", {"level": 3})

    assert response.status_code == 409
    assert DevelopmentSquad.objects.get(team=dev_squad_team).level == 1
    assert not LedgerEntry.objects.filter(
        team=dev_squad_team, kind="development_squad_fee",
    ).exists()


@pytest.mark.parametrize("target", [1, 2])
def test_downgrade_is_409(dev_squad_client, dev_squad_team, target):
    _open_squad(dev_squad_team, 3)
    balance_before = dev_squad_client.get("/api/development-squad/").data["balance"]

    response = dev_squad_client.post("/api/development-squad/level/", {"level": target})

    assert response.status_code == 409
    assert DevelopmentSquad.objects.get(team=dev_squad_team).level == 3
    assert dev_squad_client.get("/api/development-squad/").data["balance"] == balance_before


def test_change_level_refused_when_balance_too_low(dev_squad_client, dev_squad_team):
    _open_squad(dev_squad_team, 1)
    # Enough to be open, nowhere near enough to upgrade.
    LedgerEntry.objects.filter(team=dev_squad_team).update(amount=LEVELS[1].opening_fee + 1_000)

    response = dev_squad_client.post("/api/development-squad/level/", {"level": 2})

    assert response.status_code == 409
    assert DevelopmentSquad.objects.get(team=dev_squad_team).level == 1
    assert not LedgerEntry.objects.filter(
        team=dev_squad_team, kind="development_squad_fee",
    ).exists()


def test_change_level_when_closed_returns_409(dev_squad_client):
    response = dev_squad_client.post("/api/development-squad/level/", {"level": 2})

    assert response.status_code == 409


def test_change_level_to_the_same_level_returns_409(dev_squad_client, dev_squad_team):
    _open_squad(dev_squad_team, 2)

    response = dev_squad_client.post("/api/development-squad/level/", {"level": 2})

    assert response.status_code == 409
    assert DevelopmentSquad.objects.get(team=dev_squad_team).level == 2


def test_close_squad_succeeds_and_refunds_nothing(dev_squad_client, dev_squad_team):
    _open_squad(dev_squad_team, 2)
    balance_before = dev_squad_client.get("/api/development-squad/").data["balance"]
    fees_before = LedgerEntry.objects.filter(
        team=dev_squad_team, kind="development_squad_fee",
    ).count()

    response = dev_squad_client.post("/api/development-squad/close/")

    assert response.status_code == 204
    assert not DevelopmentSquad.objects.filter(team=dev_squad_team).exists()
    follow_up = dev_squad_client.get("/api/development-squad/")
    assert follow_up.data["level"] is None
    assert follow_up.data["balance"] == balance_before
    assert LedgerEntry.objects.filter(
        team=dev_squad_team, kind="development_squad_fee",
    ).count() == fees_before


def test_close_then_close_again_is_409(dev_squad_client):
    response = dev_squad_client.post("/api/development-squad/close/")

    assert response.status_code == 409
    assert "detail" in response.data


def test_reopening_after_close_starts_from_the_bottom(dev_squad_client, dev_squad_team):
    """A team that shut down an Elite squad to stop the weekly cost and later
    recovers opens at Regional again, for the full fee — the same position and
    the same price as a team that never had one."""
    _open_squad(dev_squad_team, 3)
    dev_squad_client.post("/api/development-squad/close/")

    response = dev_squad_client.post("/api/development-squad/open/", {"level": 1})

    assert response.status_code == 204
    entry = LedgerEntry.objects.get(team=dev_squad_team, kind="development_squad_fee")
    assert entry.amount == -LEVELS[1].opening_fee


def test_reopening_above_the_entry_level_is_409(dev_squad_client, dev_squad_team):
    """Closing forgets the level rather than resuming it, so there is no way
    back to the top except paying every fee on the ladder again."""
    _open_squad(dev_squad_team, 3)
    dev_squad_client.post("/api/development-squad/close/")

    response = dev_squad_client.post("/api/development-squad/open/", {"level": 3})

    assert response.status_code == 409
    assert not DevelopmentSquad.objects.filter(team=dev_squad_team).exists()


# --- Youth triage over the API (#34) ------------------------------------------------


def _graduate(rider):
    """Mark a squad rider as having finished their spell, in place."""
    rider.graduated_at = now()
    rider.save(update_fields=["graduated_at"])
    return rider


def _first_prospect(team):
    return Rider.objects.filter(
        development_squad__team=team, graduated_at__isnull=True,
    ).first()


@pytest.fixture
def squad_season(settings):
    """A declared season plus a MockClock, handed over as `(clock, start)`.

    `weeks_left` counts *declared* weeks, so it only means anything once a
    season exists — with no `Week` rows at all it degenerates to the full
    length, and a test asserting it would be asserting the absence of a
    season rather than the arithmetic. Tests move the clock to a week
    boundary, do their thing, then step a day in before asking, because
    `weeks_opened_between` counts a week as seen only once it has opened.

    `settings` rather than `@override_settings` because pytest resolves
    fixtures before it invokes the (decorated) test, so a decorator is not
    yet in force while this runs.
    """
    settings.GAME_CLOCK_CLASS = "world.clocks.MockClock"
    world_services._clock = None
    try:
        import world.models as world_models
        from world.clocks import MockClock
        from world.services import get_clock

        world_models.GameClock.load()
        clock: MockClock = get_clock()
        season_start = datetime(2027, 3, 1, 0, 0, tzinfo=dt_timezone.utc)
        clock.set(season_start)
        _create_season_with_weeks(season_start)
        yield clock, season_start
    finally:
        world_services._clock = None


def _a_day_into_week_one(clock, season_start) -> None:
    clock.set(season_start + timedelta(days=1))


def test_squad_payload_carries_places_and_roster_room(dev_squad_client, dev_squad_team):
    """The screen needs three separate things and gets all three: how many
    places the level has, how many are used, and whether the roster has room
    to promote into — the last so Promote can be disabled instead of
    provoking a 409."""
    _open_squad(dev_squad_team, 1)
    run_intake(at=now())

    response = dev_squad_client.get("/api/development-squad/")
    data = response.data

    assert response.status_code == 200
    assert [level["places"] for level in data["levels"]] == [6, 8, 10]
    assert data["places"] == 6
    assert data["in_squad"] == 2
    assert data["roster_count"] == 0
    assert data["roster_cap"] == 30
    # Graduates are listed apart, and are not counted as occupying a place.
    assert data["graduates"] == []


def test_a_closed_squad_reports_no_places_and_no_riders(dev_squad_client):
    """The both-keys-always-present shape: a closed squad is a state this
    screen shows, not a 404, so `places` is null rather than absent."""
    data = dev_squad_client.get("/api/development-squad/").data

    assert data["places"] is None
    assert data["in_squad"] == 0
    assert data["riders"] == []
    assert data["graduates"] == []
    assert data["intake"] is None


def test_prospect_payload_carries_weeks_left_change_and_promotion_salary(
    dev_squad_client, dev_squad_team, squad_season,
):
    """A prospect's row has to say how long their spell has left, what they
    have gained since they arrived, and what promoting them would cost in
    wages — a rider in a squad draws none of that today."""
    clock, season_start = squad_season
    _open_squad(dev_squad_team, 1)
    run_intake(at=now())
    _a_day_into_week_one(clock, season_start)

    data = dev_squad_client.get("/api/development-squad/").data

    assert len(data["riders"]) == 2
    rider = data["riders"][0]
    assert rider["weeks_left"] == 14  # arrived at this boundary: all 14 ahead
    assert rider["promotion_salary"] > 0
    # Change is measured against the baseline snapshot the intake wrote, so it
    # is zero on arrival rather than null (no snapshot to compare against).
    assert set(rider["change"]) == {
        "climb", "sprint", "flat", "resistance", "positioning",
    }
    assert all(value == 0 for value in rider["change"].values())


@override_settings(GAME_CLOCK_CLASS="world.clocks.MockClock")
def test_change_is_null_for_a_rider_with_no_baseline(dev_squad_client, dev_squad_team):
    """Defensive, per the plan: a rider with no arrival snapshot gets null
    changes rather than a fabricated zero, so the screen shows nothing
    rather than a claim it cannot back."""
    squad_row = DevelopmentSquad.objects.create(
        team=dev_squad_team, level=1, opened_at=now(),
    )
    Rider.objects.create(
        name="No Baseline", development_squad=squad_row, intake_at=now(),
        climb=40, sprint=40, flat=40, resistance=40, positioning=40,
    )

    data = dev_squad_client.get("/api/development-squad/").data

    assert data["riders"][0]["change"] is None


def test_graduate_payload_carries_window_value_and_listed_state(
    dev_squad_client, dev_squad_team, squad_season,
):
    """A graduate is a different decision from a prospect, so their row adds
    what it takes to make it: what the window leaves, what the market would
    pay, and whether they are already listed."""
    clock, season_start = squad_season
    _open_squad(dev_squad_team, 1)
    run_intake(at=now())
    graduate = _graduate(_first_prospect(dev_squad_team))
    _a_day_into_week_one(clock, season_start)

    data = dev_squad_client.get("/api/development-squad/").data

    # The graduate has left the squad's places; the other arrival still holds
    # one.
    assert len(data["riders"]) == 1
    assert data["in_squad"] == 1
    assert len(data["graduates"]) == 1
    row = data["graduates"][0]
    assert row["id"] == graduate.pk
    assert row["weeks_left"] == 2  # stamped at this boundary: both weeks ahead
    assert row["market_value"] > 0
    assert row["promotion_salary"] > 0
    assert row["listed"] is False


def test_a_listed_graduate_is_reported_as_listed(dev_squad_client, dev_squad_team):
    _open_squad(dev_squad_team, 1)
    run_intake(at=now())
    graduate = _graduate(_first_prospect(dev_squad_team))
    list_for_auction(dev_squad_team, graduate.pk, at=now())

    data = dev_squad_client.get("/api/development-squad/").data

    assert data["graduates"][0]["listed"] is True


def test_weeks_left_reads_the_full_wait_at_the_boundary_it_starts(
    dev_squad_client, dev_squad_team, squad_season,
):
    """The count has to be read *at* the boundary, not a day into the week
    after it — which is when a player actually sees it, since intake and
    graduation both happen inside a tick.

    An arriving prospect has the whole spell ahead of them and a rider who has
    just graduated has the whole window: the week they arrived in is the week
    whose opening already counted, and #33 has them grow nothing until the next
    boundary. Counting that week twice would read "Decide within 3 weeks" for a
    two-week window, and a deadline that over-states itself is worse than no
    deadline at all.
    """
    clock, season_start = squad_season
    _open_squad(dev_squad_team, 1)
    run_intake(at=season_start)
    _graduate(_first_prospect(dev_squad_team))
    clock.set(season_start)

    data = dev_squad_client.get("/api/development-squad/").data

    assert data["graduates"][0]["weeks_left"] == 2
    assert data["riders"][0]["weeks_left"] == 14


def test_weeks_left_counts_down_one_per_boundary_mid_week(
    dev_squad_client, dev_squad_team, squad_season,
):
    """Read between ticks, as a player always does: a day into the start's own
    week the whole wait is still ahead, and a day into the next week one
    boundary has gone. The tick releases a week-1 graduate at week 3 and
    graduates a week-1 arrival at week 15, so these are the boundaries left."""
    clock, season_start = squad_season
    _open_squad(dev_squad_team, 1)
    run_intake(at=season_start)
    _graduate(_first_prospect(dev_squad_team))

    clock.set(season_start + timedelta(days=1))
    week_one = dev_squad_client.get("/api/development-squad/").data
    clock.set(season_start + timedelta(weeks=1, days=1))
    week_two = dev_squad_client.get("/api/development-squad/").data

    assert week_one["graduates"][0]["weeks_left"] == 2
    assert week_one["riders"][0]["weeks_left"] == 14
    assert week_two["graduates"][0]["weeks_left"] == 1
    assert week_two["riders"][0]["weeks_left"] == 13


def test_arrivals_at_risk_counts_the_batch_a_full_squad_cannot_take(
    dev_squad_client, dev_squad_team, squad_season,
):
    """The warning the squad screen gives *before* the week arrives: at 6 of 6
    places, both arrivals would be turned away."""
    clock, season_start = squad_season
    squad_row = DevelopmentSquad.objects.create(
        team=dev_squad_team, level=1, opened_at=now(),
    )
    for index in range(LEVELS[1].places):
        Rider.objects.create(
            name=f"Prospect {index}", development_squad=squad_row,
            intake_at=now(), climb=40, sprint=40, flat=40,
            resistance=40, positioning=40,
        )
    _a_day_into_week_one(clock, season_start)

    data = dev_squad_client.get("/api/development-squad/").data

    assert data["in_squad"] == LEVELS[1].places
    assert data["intake"]["next"]["week"] == 4
    assert data["intake"]["next"]["arrivals_at_risk"] == 2


def test_arrivals_at_risk_counts_riders_graduating_before_the_intake_as_gone(
    dev_squad_client, dev_squad_team, squad_season,
):
    """A full squad whose oldest rider graduates before the next intake has a
    place for that batch: the tick graduates before it runs intake.

    One rider arrived at season 1, week 4; five arrived at season 2, week 4.
    At season 2, week 4 the squad is 6/6. The veteran graduates at season 2,
    week 6 — two weeks before the week-8 intake — so one of that batch has a
    place and only one is at risk, not both."""
    clock, season_start = squad_season
    season_2_start = season_start + timedelta(weeks=SEASON_WEEKS)
    season_2 = Season.objects.create(number=2, starts_at=season_2_start)
    for week_number in range(1, SEASON_WEEKS + 1):
        week_start = season_2_start + timedelta(weeks=week_number - 1)
        Week.objects.create(
            season=season_2, number=week_number,
            starts_at=week_start, ends_at=week_start + timedelta(weeks=1),
        )
    squad_row = DevelopmentSquad.objects.create(
        team=dev_squad_team, level=1, opened_at=season_start,
    )
    veteran_arrival = season_start + timedelta(weeks=3)
    recent_arrival = season_2_start + timedelta(weeks=3)
    arrivals = [veteran_arrival] + [recent_arrival] * (LEVELS[1].places - 1)
    for index, intake_at in enumerate(arrivals):
        Rider.objects.create(
            name=f"Prospect {index}", development_squad=squad_row,
            intake_at=intake_at, climb=40, sprint=40, flat=40,
            resistance=40, positioning=40,
        )
    clock.set(recent_arrival + timedelta(days=1))

    data = dev_squad_client.get("/api/development-squad/").data

    assert data["in_squad"] == LEVELS[1].places
    assert data["graduates"] == []
    assert (data["intake"]["next"]["season"], data["intake"]["next"]["week"]) == (2, 8)
    assert data["intake"]["next"]["arrivals_at_risk"] == 1


def test_promote_endpoint_moves_a_prospect_to_the_roster(dev_squad_client, dev_squad_team):
    _open_squad(dev_squad_team, 1)
    run_intake(at=now())
    prospect = Rider.objects.filter(graduated_at__isnull=True).first()
    salary = weekly_salary_for(prospect)

    response = dev_squad_client.post(
        f"/api/development-squad/riders/{prospect.pk}/promote/",
    )

    assert response.status_code == 204
    prospect.refresh_from_db()
    assert prospect.team_id == dev_squad_team.pk
    assert prospect.development_squad_id is None
    assert prospect.weekly_salary == salary


def test_promote_endpoint_promotes_a_graduate_too(dev_squad_client, dev_squad_team):
    """Deciding early is a choice a manager is entitled to make."""
    _open_squad(dev_squad_team, 1)
    run_intake(at=now())
    graduate = _graduate(Rider.objects.filter(graduated_at__isnull=True).first())

    response = dev_squad_client.post(
        f"/api/development-squad/riders/{graduate.pk}/promote/",
    )

    assert response.status_code == 204
    graduate.refresh_from_db()
    assert graduate.team_id == dev_squad_team.pk
    assert graduate.development_squad_id is None


def test_promote_is_409_when_the_roster_is_full(dev_squad_client, dev_squad_team):
    _open_squad(dev_squad_team, 1)
    run_intake(at=now())
    prospect = Rider.objects.filter(graduated_at__isnull=True).first()
    for index in range(ROSTER_CAP):
        Rider.objects.create(
            name=f"Roster {index}", team=dev_squad_team,
            climb=50, sprint=50, flat=50, resistance=50, positioning=50,
        )

    response = dev_squad_client.post(
        f"/api/development-squad/riders/{prospect.pk}/promote/",
    )

    assert response.status_code == 409
    prospect.refresh_from_db()
    assert prospect.team_id is None


def test_promote_is_409_for_another_teams_prospect(dev_squad_client, dev_squad_team):
    rival_manager = User.objects.create_user(
        email="rival-squad@example.com", password="rival-pass-good",
    )
    rival_team = Team.objects.create(
        name="Rival Squad", code="RVS", manager=rival_manager,
    )
    squad_row = DevelopmentSquad.objects.create(team=rival_team, level=1, opened_at=now())
    theirs = Rider.objects.create(
        name="Theirs", development_squad=squad_row, intake_at=now(),
        climb=40, sprint=40, flat=40, resistance=40, positioning=40,
    )

    response = dev_squad_client.post(
        f"/api/development-squad/riders/{theirs.pk}/promote/",
    )

    assert response.status_code == 409


def test_discard_endpoint_deletes_a_prospect(dev_squad_client, dev_squad_team):
    _open_squad(dev_squad_team, 1)
    run_intake(at=now())
    prospect = Rider.objects.filter(graduated_at__isnull=True).first()

    response = dev_squad_client.post(
        f"/api/development-squad/riders/{prospect.pk}/discard/",
    )

    assert response.status_code == 204
    assert not Rider.objects.filter(pk=prospect.pk).exists()


def test_discard_is_409_while_a_listing_is_open(dev_squad_client, dev_squad_team):
    """A buyer has money on the table; the auction resolves on its own terms
    instead."""
    _open_squad(dev_squad_team, 1)
    run_intake(at=now())
    graduate = _graduate(Rider.objects.filter(graduated_at__isnull=True).first())
    list_for_auction(dev_squad_team, graduate.pk, at=now())

    response = dev_squad_client.post(
        f"/api/development-squad/riders/{graduate.pk}/discard/",
    )

    assert response.status_code == 409
    assert Rider.objects.filter(pk=graduate.pk).exists()


def test_close_cancels_a_listed_graduate_auction(dev_squad_client, dev_squad_team):
    """A released graduate's auction must not stay biddable until its
    deadline, when the winner would be refused by the ownership check."""
    _open_squad(dev_squad_team, 1)
    run_intake(at=now())
    graduate = _graduate(Rider.objects.filter(graduated_at__isnull=True).first())
    auction = list_for_auction(dev_squad_team, graduate.pk, at=now())

    response = dev_squad_client.post("/api/development-squad/close/")

    assert response.status_code == 204
    assert Auction.objects.get(pk=auction.pk).status == Auction.Status.CANCELLED


def test_claim_cancels_the_old_rosters_open_listings(db, dev_squad_manager):
    """Closes #114: a claim releases the claimed team's whole roster to the
    pool, so an OPEN auction for one of those riders must not survive with
    `seller_team` pointing at the now-managed team — the new manager would
    see it as their own listing for a rider they no longer have, and the AI
    would bid on it. An unmanaged team with a listing is exactly the shape the
    AI market leaves behind."""
    claimed = Team.objects.create(name="Unmanaged Team", code="UNM")
    rider = Rider.objects.create(
        name="Listed Then Claimed", team=claimed,
        climb=50, sprint=50, flat=50, resistance=50, positioning=50,
    )
    auction = list_for_auction(claimed, rider.pk, at=now())
    dev_squad_client = APIClient()
    dev_squad_client.force_authenticate(user=dev_squad_manager)

    response = dev_squad_client.post("/api/teams/claim/", {"name": "New Team", "code": "NEW"})

    assert response.status_code == 201
    assert Auction.objects.get(pk=auction.pk).status == Auction.Status.CANCELLED


def test_promote_cancels_a_listed_graduate_auction(dev_squad_client, dev_squad_team):
    """Promote stays available on a listed graduate — the sale is what a
    listing takes away, not the option of keeping them — so choosing to keep
    the rider has to end the sale. Otherwise the auction sits open over a
    player the team is now paying and fielding, and the winner at its
    deadline takes them off the roster."""
    _open_squad(dev_squad_team, 1)
    run_intake(at=now())
    graduate = _graduate(_first_prospect(dev_squad_team))
    auction = list_for_auction(dev_squad_team, graduate.pk, at=now())

    response = dev_squad_client.post(
        f"/api/development-squad/riders/{graduate.pk}/promote/",
    )

    assert response.status_code == 204
    assert Auction.objects.get(pk=auction.pk).status == Auction.Status.CANCELLED
    graduate.refresh_from_db()
    assert graduate.team_id == dev_squad_team.pk


# --- Insolvency (#27) ---------------------------------------------------------


@pytest.fixture
def insolvent_week(db) -> Week:
    season = Season.objects.create(number=1, starts_at=datetime(2027, 3, 1, 0, 0, tzinfo=dt_timezone.utc))
    return Week.objects.create(
        season=season, number=1, starts_at=season.starts_at,
        ends_at=season.starts_at + timedelta(weeks=1),
    )


@pytest.fixture
def broke_manager(db) -> User:
    return User.objects.create_user(email="broke@example.com", password="s0meth1ng-good")


@pytest.fixture
def broke_team(db, broke_manager) -> Team:
    """A managed team with a wage bill and nothing to pay it with — not yet
    assessed; `_make_insolvent` opens the case."""
    team = Team.objects.create(name="Broke Team", code="BRK", manager=broke_manager)
    for i in range(6):
        _market_rider(f"Broke Rider {i}", team=team, weekly_salary=4_000)
    return team


@pytest.fixture
def broke_client(broke_manager) -> APIClient:
    client = APIClient()
    client.force_authenticate(user=broke_manager)
    return client


def _make_insolvent(team, week, *, strikes=1, shortfall=24_000):
    from economy.models import SolvencyCheck
    SolvencyCheck.objects.create(
        team=team, week=week, occurred_at=week.starts_at,
        balance=-1_000, shortfall=shortfall, strikes=strikes,
    )


def test_embargo_blocks_signing(broke_client, broke_team, insolvent_week):
    _make_insolvent(broke_team, insolvent_week)
    free = _market_rider("Free Agent")

    response = broke_client.post("/api/transfers/free-agents/sign/", {"rider_id": free.pk})

    assert response.status_code == 409
    assert "insolvent" in response.data["detail"]
    free.refresh_from_db()
    assert free.team_id is None


def test_embargo_blocks_bidding(broke_client, broke_team, insolvent_week):
    _make_insolvent(broke_team, insolvent_week)
    seller = Team.objects.create(name="Seller", code="SEL")
    listed = _market_rider("Listed", team=seller)
    from transfers.services import list_for_auction
    auction = list_for_auction(seller, listed.pk, at=now())

    response = broke_client.post(
        f"/api/transfers/auctions/{auction.pk}/bid/", {"amount": auction.reserve_price},
    )

    assert response.status_code == 409
    assert Bid.objects.count() == 0


def test_embargo_blocks_hiring(broke_client, broke_team, insolvent_week, pool_trainer):
    _make_insolvent(broke_team, insolvent_week)
    make_ledger_entry(broke_team, "starting_balance", STARTING_BALANCE, now(), "Test")

    response = broke_client.post("/api/staff/trainer/hire/", {"trainer_id": pool_trainer.pk})

    assert response.status_code == 409
    pool_trainer.refresh_from_db()
    assert pool_trainer.team_id is None


def test_embargo_blocks_opening_a_development_squad(broke_client, broke_team, insolvent_week):
    _make_insolvent(broke_team, insolvent_week)
    make_ledger_entry(broke_team, "starting_balance", STARTING_BALANCE, now(), "Test")

    response = broke_client.post("/api/development-squad/open/", {"level": 1})

    assert response.status_code == 409
    assert not DevelopmentSquad.objects.filter(team=broke_team).exists()


def test_embargo_blocks_upgrading_a_development_squad(broke_client, broke_team, insolvent_week):
    _make_insolvent(broke_team, insolvent_week)
    make_ledger_entry(broke_team, "starting_balance", STARTING_BALANCE, now(), "Test")
    DevelopmentSquad.objects.create(team=broke_team, level=1, opened_at=now())

    response = broke_client.post("/api/development-squad/level/", {"level": 2})

    assert response.status_code == 409
    assert DevelopmentSquad.objects.get(team=broke_team).level == 1


def test_embargo_blocks_promoting_a_squad_rider(broke_client, broke_team, insolvent_week):
    """Promotion starts a salary, so it is a cost like signing (#27, #34)."""
    _make_insolvent(broke_team, insolvent_week)
    squad_row = DevelopmentSquad.objects.create(team=broke_team, level=1, opened_at=now())
    prospect = Rider.objects.create(
        name="Prospect", development_squad=squad_row, intake_at=now(),
        climb=40, sprint=40, flat=40, resistance=40, positioning=40,
    )

    response = broke_client.post(f"/api/development-squad/riders/{prospect.pk}/promote/")

    assert response.status_code == 409
    assert "insolvent" in response.data["detail"]
    prospect.refresh_from_db()
    assert prospect.team_id is None
    assert prospect.development_squad_id == squad_row.pk


def test_embargo_allows_discarding_a_squad_rider(broke_client, broke_team, insolvent_week):
    _make_insolvent(broke_team, insolvent_week)
    squad_row = DevelopmentSquad.objects.create(team=broke_team, level=1, opened_at=now())
    prospect = Rider.objects.create(
        name="Prospect", development_squad=squad_row, intake_at=now(),
        climb=40, sprint=40, flat=40, resistance=40, positioning=40,
    )

    response = broke_client.post(f"/api/development-squad/riders/{prospect.pk}/discard/")

    assert response.status_code == 204
    assert not Rider.objects.filter(pk=prospect.pk).exists()


def test_embargo_allows_levers_that_cut_cost_or_add_income(
    broke_client, broke_team, insolvent_week, pool_trainer,
):
    _make_insolvent(broke_team, insolvent_week)
    pool_trainer.team = broke_team
    pool_trainer.save()
    DevelopmentSquad.objects.create(team=broke_team, level=1, opened_at=now())
    rider = broke_team.riders.first()

    assert broke_client.post("/api/staff/trainer/fire/").status_code == 204
    assert broke_client.post("/api/development-squad/close/").status_code == 204
    assert broke_client.post("/api/transfers/riders/release/", {"rider_id": rider.pk}).status_code == 204
    other = broke_team.riders.first()
    assert broke_client.post("/api/transfers/auctions/list/", {"rider_id": other.pk}).status_code == 204


def test_embargo_allows_signing_a_sponsor(broke_client, broke_team, insolvent_week):
    from economy.services import ensure_offer_round, offers_for
    _make_insolvent(broke_team, insolvent_week)
    with override_settings(GAME_CLOCK_CLASS="world.clocks.MockClock"):
        world_services._clock = None
        try:
            ensure_offer_round(broke_team, insolvent_week.season, at=now())
            offer = offers_for(broke_team, insolvent_week.season).first()
            response = broke_client.post("/api/economy/sponsors/sign/", {"offer_id": offer.pk})
        finally:
            world_services._clock = None

    assert response.status_code == 204


def test_solvency_view_solvent_shape(broke_client, broke_team):
    response = broke_client.get("/api/economy/solvency/")

    assert response.status_code == 200
    assert response.data["insolvent"] is False
    assert response.data["paydays_left"] is None
    assert response.data["deadline"] is None
    assert response.data["roster_size"] == 6
    assert response.data["roster_floor"] == 4
    assert response.data["shortfall"] == 24_000


def test_solvency_view_insolvent_shape(broke_client, broke_team, insolvent_week):
    _make_insolvent(broke_team, insolvent_week, strikes=2, shortfall=30_000)

    response = broke_client.get("/api/economy/solvency/")

    assert response.data["insolvent"] is True
    assert response.data["strikes"] == 2
    assert response.data["target"] == 30_000
    assert response.data["shortfall"] == 24_000
    assert response.data["cut_so_far"] == 6_000
    assert response.data["paydays_left"] == 2


def test_solvency_view_without_a_team_is_the_solvent_shape(db):
    user = User.objects.create_user(email="nobody@example.com", password="s0meth1ng-good")
    client = APIClient()
    client.force_authenticate(user=user)

    response = client.get("/api/economy/solvency/")

    assert response.status_code == 200
    assert response.data["insolvent"] is False


def test_force_sell_requires_insolvency(broke_client, broke_team):
    rider = broke_team.riders.first()

    response = broke_client.post("/api/transfers/auctions/force/", {"rider_id": rider.pk})

    assert response.status_code == 409
    rider.refresh_from_db()
    assert rider.team_id == broke_team.pk


def test_force_sell_at_floor_is_409(broke_client, broke_team, insolvent_week):
    _make_insolvent(broke_team, insolvent_week)
    for rider in list(broke_team.riders.all())[:2]:
        rider.delete()                          # leaves four

    response = broke_client.post(
        "/api/transfers/auctions/force/", {"rider_id": broke_team.riders.first().pk},
    )

    assert response.status_code == 409
    assert broke_team.riders.count() == 4


def test_force_sell_success_returns_204_and_lowers_payroll(broke_client, broke_team, insolvent_week):
    from economy.services import payroll_for
    _make_insolvent(broke_team, insolvent_week)
    rider = broke_team.riders.first()
    before = payroll_for(broke_team)

    response = broke_client.post("/api/transfers/auctions/force/", {"rider_id": rider.pk})

    assert response.status_code == 204
    assert payroll_for(broke_team) == before - 4_000
    assert Auction.objects.get(rider=rider).forced is True
    assert not LedgerEntry.objects.filter(team=broke_team, kind="transfer_fee").exists()


def test_force_sell_requires_a_team(db):
    user = User.objects.create_user(email="nobody2@example.com", password="s0meth1ng-good")
    client = APIClient()
    client.force_authenticate(user=user)

    assert client.post("/api/transfers/auctions/force/", {"rider_id": 1}).status_code == 403


def test_auction_market_reports_forced(broke_client, broke_team, insolvent_week):
    _make_insolvent(broke_team, insolvent_week)
    rider = broke_team.riders.first()
    broke_client.post("/api/transfers/auctions/force/", {"rider_id": rider.pk})

    response = broke_client.get("/api/transfers/auctions/")

    assert [a["forced"] for a in response.data["auctions"]] == [True]
