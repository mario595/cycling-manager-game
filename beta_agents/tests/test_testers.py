import pytest

from beta_agents import testers


def test_no_two_testers_share_an_hour():
    for hour in range(24):
        assert len(testers.due(hour)) <= 1
    assert sum(len(testers.due(h)) for h in range(24)) == 4 * 3 + 1  # 13 visits a day


def test_casual_visits_once_a_day():
    hours = [h for h in range(24) if testers.get("casual") in testers.due(h)]
    assert hours == [3]


def test_each_regular_tester_visits_every_eight_hours():
    for tester in testers.TESTERS:
        if tester.period == 8:
            assert [h for h in range(24) if tester.is_due(h)] == list(range(tester.offset, 24, 8))


def test_names_and_secrets():
    youth = testers.get("youth")
    assert youth.email == "beta-youth@velodra.test"
    assert youth.secret_name == "BETA_KEY_YOUTH"
    assert len({t.slug for t in testers.TESTERS}) == 5


def test_unknown_tester():
    with pytest.raises(KeyError):
        testers.get("nobody")
