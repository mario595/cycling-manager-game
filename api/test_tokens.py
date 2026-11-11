"""API tokens: authentication, last-seen, throttling (#130)."""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.core.cache import cache
from django.test import override_settings
from rest_framework.test import APIClient

import world.services as world_services
from accounts.models import User
from accounts.tokens import issue_token, revoke_token
from economy.services import ensure_opening_balance
from riders.models import Rider
from staff.models import Trainer
from staff.services import hire_trainer
from teams.models import ManagerialSpell, Team
from world.clocks import MockClock
from world.services import get_clock, now, tick
from world.tests.test_inactivity import make_season_with_weeks


@pytest.fixture(autouse=True)
def _isolate():
    """Throttle counts live in the cache, which outlives a test; and the
    last-seen stamp needs a clock the test can move."""
    cache.clear()
    world_services._clock = None
    with override_settings(GAME_CLOCK_CLASS="world.clocks.MockClock"):
        yield
    world_services._clock = None
    cache.clear()


@pytest.fixture
def manager(db) -> User:
    return User.objects.create_user(email="agent@example.com", password="s0meth1ng-good")


@pytest.fixture
def team(manager) -> Team:
    team = Team.objects.create(name="Agent Team", code="AGT", manager=manager)
    # Solvent, so the inactivity tests below cannot pass on an insolvency release.
    ensure_opening_balance(team, at=now())
    Rider.objects.create(
        name="Agent Rider", team=team,
        climb=50, sprint=50, flat=50, resistance=50, positioning=50,
    )
    return team


@pytest.fixture
def key(manager) -> str:
    return issue_token(manager)


def bearer(key: str) -> APIClient:
    # enforce_csrf_checks: without it the test client skips CSRF entirely
    # and the no-CSRF test below could never fail.
    client = APIClient(enforce_csrf_checks=True)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {key}")
    return client


def test_a_token_reads_the_callers_own_roster(team, key):
    response = bearer(key).get("/api/riders/")

    assert response.status_code == 200
    assert [r["name"] for r in response.data["riders"]] == ["Agent Rider"]


def test_a_token_writes_without_a_csrf_token(team, key, manager):
    trainer = Trainer.objects.create(
        name="Coach", climb=90, sprint=40, flat=45, resistance=50, positioning=35,
    )
    hire_trainer(team, trainer.pk)

    response = bearer(key).put("/api/staff/training/", {"attribute": "climb"}, format="json")

    assert response.status_code == 204


def test_a_session_write_still_needs_csrf(team, manager):
    client = APIClient(enforce_csrf_checks=True)
    client.force_login(manager)

    response = client.put("/api/staff/training/", {"attribute": "climb"}, format="json")

    assert response.status_code == 403
    assert "CSRF" in response.data["detail"]


@pytest.mark.parametrize("header", [
    "Bearer cm_not-a-real-token",
    "Bearer",
    "Bearer two parts",
])
def test_a_bad_token_is_refused_with_json(team, key, header):
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=header)

    response = client.get("/api/riders/")

    assert response.status_code == 403
    assert response["Content-Type"].startswith("application/json")
    assert "detail" in response.data


def test_a_revoked_token_is_refused(team, key, manager):
    revoke_token(manager)

    assert bearer(key).get("/api/riders/").status_code == 403


def test_an_old_token_is_refused_after_reissue(team, key, manager):
    new_key = issue_token(manager)

    assert bearer(key).get("/api/riders/").status_code == 403
    assert bearer(new_key).get("/api/riders/").status_code == 200


def test_the_old_drf_keyword_is_not_accepted(team, key):
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Token {key}")

    assert client.get("/api/riders/").status_code == 403


def test_anonymous_is_still_a_403(db):
    assert APIClient().get("/api/riders/").status_code == 403


def test_a_token_request_stamps_last_seen(team, key, manager):
    assert manager.last_seen_at is None

    bearer(key).get("/api/riders/")

    manager.refresh_from_db()
    assert manager.last_seen_at == now()


def test_last_seen_is_stamped_at_most_once_an_hour(team, key, manager):
    clock: MockClock = get_clock()
    bearer(key).get("/api/riders/")
    first = now()

    clock.advance_by(timedelta(minutes=30))
    bearer(key).get("/api/riders/")
    manager.refresh_from_db()
    assert manager.last_seen_at == first

    clock.advance_by(timedelta(minutes=30))
    bearer(key).get("/api/riders/")
    manager.refresh_from_db()
    assert manager.last_seen_at == now()


def test_the_61st_token_request_in_a_minute_is_throttled(team, key):
    client = bearer(key)
    for _ in range(60):
        assert client.get("/api/world/clock/").status_code == 200

    response = client.get("/api/world/clock/")

    assert response.status_code == 429
    assert int(response["Retry-After"]) > 0


def test_reissuing_does_not_reset_the_throttle(team, key, manager):
    client = bearer(key)
    for _ in range(60):
        client.get("/api/world/clock/")

    assert bearer(issue_token(manager)).get("/api/world/clock/").status_code == 429


def test_sessions_are_never_throttled(team, manager):
    client = APIClient()
    client.force_login(manager)
    for _ in range(70):
        assert client.get("/api/world/clock/").status_code == 200


def test_a_token_only_agent_that_stops_playing_loses_its_team(team, key, manager):
    clock: MockClock = get_clock()
    season = make_season_with_weeks(1, now())
    clock.set(season.weeks.get(number=1).starts_at + timedelta(hours=1))
    bearer(key).get("/api/riders/")

    # Seen during week 1; weeks 2-11 then open unseen — ten of them.
    clock.set(season.weeks.get(number=12).starts_at + timedelta(hours=1))
    tick()

    team.refresh_from_db()
    assert team.manager_id is None
    assert ManagerialSpell.objects.get(manager=manager).reason == ManagerialSpell.Reason.INACTIVITY


def test_a_token_only_agent_that_keeps_playing_keeps_its_team(team, key, manager):
    clock: MockClock = get_clock()
    season = make_season_with_weeks(1, now())
    clock.set(season.weeks.get(number=1).starts_at + timedelta(hours=1))
    bearer(key).get("/api/riders/")
    clock.set(season.weeks.get(number=10).starts_at + timedelta(hours=1))
    bearer(key).get("/api/riders/")

    # Seen during week 1; weeks 2-11 then open unseen — ten of them.
    clock.set(season.weeks.get(number=12).starts_at + timedelta(hours=1))
    tick()

    team.refresh_from_db()
    assert team.manager_id == manager.pk
