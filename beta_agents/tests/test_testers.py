import pytest

from beta_agents import testers


def test_every_hour_has_exactly_one_regular_tester():
    for hour in range(24):
        regular = [t for t in testers.due(hour) if t.period == 4]
        assert len(regular) == 1


def test_casual_visits_once_a_day():
    hours = [h for h in range(24) if testers.get("casual") in testers.due(h)]
    assert hours == [2]


def test_each_regular_tester_visits_every_four_hours():
    for tester in testers.TESTERS:
        if tester.period == 4:
            assert [h for h in range(24) if tester.is_due(h)] == list(range(tester.offset, 24, 4))


def test_names_and_secrets():
    youth = testers.get("youth")
    assert youth.email == "beta-youth@velodra.test"
    assert youth.secret_name == "BETA_KEY_YOUTH"
    assert len({t.slug for t in testers.TESTERS}) == 5


def test_unknown_tester():
    with pytest.raises(KeyError):
        testers.get("nobody")
