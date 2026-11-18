from datetime import datetime, timedelta, timezone

import pytest

from beta_agents import testers

NOW = datetime(2026, 11, 18, 15, 17, tzinfo=timezone.utc)


def ago(hours):
    return NOW - timedelta(hours=hours)


def test_a_tester_with_no_diary_is_due():
    assert testers.get("youth").is_due(None, NOW)


def test_a_regular_tester_is_due_eight_hours_after_its_last_visit_with_half_an_hour_of_slack():
    youth = testers.get("youth")
    assert not youth.is_due(ago(7.4), NOW)
    assert youth.is_due(ago(7.5), NOW)  # its last visit started late, behind another tester
    assert youth.is_due(ago(30), NOW)  # GitHub skipped some runs


def test_casual_visits_once_a_day():
    casual = testers.get("casual")
    assert not casual.is_due(ago(23), NOW)
    assert casual.is_due(ago(24), NOW)


def test_due_lists_the_longest_waiting_first():
    last = {"youth": ago(9), "trader": ago(2), "money": None, "racer": ago(20), "casual": ago(5)}
    assert [t.slug for t in testers.due(NOW, lambda t: last[t.slug])] == ["money", "racer", "youth"]


def test_thirteen_visits_a_day_on_a_punctual_hourly_schedule():
    last = {t.slug: None for t in testers.TESTERS}
    visits_on_day_two = 0
    for hour in range(48):
        now = NOW + timedelta(hours=hour)
        for tester in testers.due(now, lambda t: last[t.slug]):
            last[tester.slug] = now
            visits_on_day_two += hour >= 24
    assert visits_on_day_two == 4 * 3 + 1


def test_names_and_secrets():
    youth = testers.get("youth")
    assert youth.email == "beta-youth@velodra.test"
    assert youth.secret_name == "BETA_KEY_YOUTH"
    assert len({t.slug for t in testers.TESTERS}) == 5


def test_unknown_tester():
    with pytest.raises(KeyError):
        testers.get("nobody")
