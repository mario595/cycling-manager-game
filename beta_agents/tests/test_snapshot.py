from beta_agents import snapshot
from beta_agents.game_api import GameAPI

from .conftest import FakeTransport

TEAM = {"id": 7, "name": "Velo Turbo", "code": "VTR"}


def routes(overrides=None):
    base = {
        ("GET", "/api/accounts/me/"): (200, {"authenticated": True, "team": TEAM, "lost_team": None}),
        ("GET", "/api/schedule/position/"): (200, {"state": "in_season", "season": 3, "week": 5}),
        ("GET", "/api/economy/finances/"): (200, {"balance": 441908, "weekly_wage_bill": 14250, "fanbase": 5200, "entries": []}),
        ("GET", "/api/riders/"): (200, {"riders": [{"id": 1, "name": "Ana Ruiz"}, {"id": 2, "name": "Luis Alonso"}], "squad_value": 0}),
        ("GET", "/api/competitions/standings/"): (
            200,
            {"standings": [{"rank": 1, "team": {"id": 3}, "points": 90}, {"rank": 14, "team": {"id": 7}, "points": 16}]},
        ),
    }
    base.update(overrides or {})
    return base


def take(overrides=None):
    return snapshot.take(GameAPI("http://g", "k", transport=FakeTransport(routes(overrides))))


def test_a_full_reading():
    assert take() == {
        "team": TEAM,
        "state": "in_season",
        "season": 3,
        "week": 5,
        "balance": 441908,
        "weekly_wage_bill": 14250,
        "fanbase": 5200,
        "riders": {"1": "Ana Ruiz", "2": "Luis Alonso"},
        "rank": 14,
        "points": 16,
    }


def test_a_failing_part_is_recorded_and_the_rest_is_read():
    reading = take({("GET", "/api/competitions/standings/"): (500, "Server Error")})
    assert "rank" not in reading and reading["balance"] == 441908
    assert reading["errors"]["standings"].startswith("GET /api/competitions/standings/ answered 500")
    lines = snapshot.describe_changes(take(), reading)
    assert any(line.startswith("standings: could not be read") for line in lines)


def test_with_no_team_only_the_account_and_the_season_are_read():
    transport = FakeTransport(routes({("GET", "/api/accounts/me/"): (200, {"team": None})}))
    reading = snapshot.take(GameAPI("http://g", "k", transport=transport))
    assert reading == {"team": None, "state": "in_season", "season": 3, "week": 5}
    assert [url.split("/api/")[1] for _, url, _, _ in transport.requests] == ["accounts/me/", "schedule/position/"]


def test_the_changes_since_last_visit():
    before = take()
    after = take(
        {
            ("GET", "/api/schedule/position/"): (200, {"state": "in_season", "season": 3, "week": 7}),
            ("GET", "/api/economy/finances/"): (200, {"balance": 429927, "weekly_wage_bill": 14250, "fanbase": 5150}),
            ("GET", "/api/riders/"): (200, {"riders": [{"id": 2, "name": "Luis Alonso"}, {"id": 9, "name": "Pedro Rodriguez"}]}),
            ("GET", "/api/competitions/standings/"): (200, {"standings": [{"rank": 12, "team": {"id": 7}, "points": 34}]}),
        }
    )
    assert snapshot.describe_changes(before, after) == [
        "Season 3 Week 5 → Season 3 Week 7",
        "balance: $441,908 → $429,927 (-$11,981)",
        "weekly wage bill: $14,250 → $14,250 (+$0)",
        "fanbase: 5,200 → 5,150 (-50)",
        "league points: 16 → 34 (+18)",
        "league position: 14th → 12th",
        "roster: 2 → 2 riders; joined: Pedro Rodriguez (9); left: Ana Ruiz (1)",
    ]


def test_no_previous_reading_gives_the_team_as_it_is():
    lines = snapshot.describe_changes(None, take())
    assert lines[0].startswith("No reading from your last visit")
    assert "balance $441,908, weekly wage bill $14,250, fanbase 5,200" in lines
    assert "league: 14th, 16 points" in lines


def test_a_change_of_team_is_not_compared():
    before = take()
    after = dict(before, team={"id": 8, "name": "Casa", "code": "CAS"}, balance=1)
    lines = snapshot.describe_changes(before, after)
    assert lines[0] == "You managed Velo Turbo (VTR, id 7) last visit, and now Casa (CAS, id 8), so nothing is compared. The team now:"
    assert not any("→" in line for line in lines)
