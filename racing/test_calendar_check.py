"""The calendar balance check (racing/calendar_check.py, #139).

Database-free: the field is unsaved riders and nothing is written, so none
of these tests ask for `db`.
"""

from __future__ import annotations

from schedule.loaders import parse_season_file

from racing.calendar_check import (
    Day,
    DayResult,
    calendar_days,
    generate_field,
    judge,
    run_day,
)

FLAT = [{"length": 3000, "gradient": 0.0}]


def _season(**extra):
    return parse_season_file({"number": 1, "starts_at": "2027-03-01T00:00:00Z", **extra})


def test_calendar_days_are_in_calendar_order_with_stages_expanded():
    declaration = _season(
        races=[
            {"week": 2, "day": "sunday", "time": "14:00", "name": "Late", "course": FLAT},
            {"week": 1, "day": "sunday", "time": "14:00", "name": "Early", "course": FLAT},
        ],
        stage_races=[{
            "name": "Tour", "week": 1, "start_day": "tuesday", "time": "14:00",
            "stages": [{"course": FLAT}, {"course": [{"length": 3000, "gradient": 5.0}]}],
        }],
    )

    days = calendar_days(declaration)

    assert [d.label for d in days] == ["Tour — Stage 1", "Tour — Stage 2", "Early", "Late"]
    # A tour's squads are picked once, for stage 1, as in the game.
    assert days[1].pick_course == FLAT


def test_generate_field_is_reproducible_and_seed_teams_sized():
    teams_a, rosters_a = generate_field(7)
    _, rosters_b = generate_field(7)

    assert len(teams_a) == 16
    assert all(len(r) == 12 for r in rosters_a.values())
    assert [r.name for r in rosters_a[1]] == [r.name for r in rosters_b[1]]
    pks = [r.pk for roster in rosters_a.values() for r in roster]
    assert len(set(pks)) == len(pks)


def test_run_day_reports_a_winner_from_the_field():
    day = Day(label="Short", course=FLAT, markers=[], wind_enabled=False, wind_band=None)

    result = run_day(day, field_seed=1, race_seed=1)

    assert result.winner_speciality in {"climber", "sprinter", "rouleur", "puncheur", "domestique"}
    assert len(result.top_three) == 3


def _result(speciality, seed=1):
    day = Day(label="x", course=FLAT, markers=[], wind_enabled=False, wind_band=None)
    return DayResult(day=day, field_seed=seed, winner_speciality=speciality,
                     winner_name="", top_three=[])


def test_judge_passes_a_spread_of_winners():
    results = [_result(s) for s in ["climber"] * 3 + ["sprinter"] * 3
               + ["rouleur"] * 2 + ["puncheur"] * 2]

    assert judge(results).ok


def test_judge_fails_a_speciality_with_too_few_wins():
    results = [_result(s) for s in ["climber"] * 4 + ["sprinter"] * 4 + ["rouleur"] * 4
               + ["puncheur"]]

    verdict = judge(results)

    assert not verdict.ok
    assert any("puncheur" in f for f in verdict.failures)


def test_judge_fails_a_speciality_that_wins_too_much():
    results = [_result(s) for s in ["sprinter"] * 5 + ["climber"] * 2 + ["rouleur"] * 2
               + ["puncheur"] * 2]

    verdict = judge(results)

    assert any("sprinter" in f and "%" in f for f in verdict.failures)


def test_judge_averages_wins_over_seasons():
    # Two seasons, a puncheur win in each: one a season, below the minimum
    # of two, even though the total is two.
    results = []
    for seed in (1, 2):
        results += [_result(s, seed) for s in ["climber"] * 3 + ["sprinter"] * 3
                    + ["rouleur"] * 3 + ["puncheur"]]

    assert any("puncheur" in f for f in judge(results).failures)


def test_judge_asks_rouleurs_for_one_win_a_season():
    # Until time trials exist, a rouleur's minimum is one (see MIN_WINS_BY_SPECIALITY).
    results = [_result(s) for s in ["climber"] * 3 + ["sprinter"] * 3
               + ["puncheur"] * 3 + ["rouleur"]]

    assert judge(results).ok


def _write(tmp_path, races):
    import json

    path = tmp_path / "season.json"
    path.write_text(json.dumps({"number": 1, "starts_at": "2027-03-01T00:00:00Z", "races": races}))
    return str(path)


def test_command_fails_an_unbalanced_calendar(tmp_path, capsys):
    import pytest
    from django.core.management import call_command
    from django.core.management.base import CommandError

    path = _write(tmp_path, [
        {"week": 1, "day": "sunday", "time": "14:00", "name": "Only Race", "course": FLAT},
    ])

    with pytest.raises(CommandError, match="not balanced"):
        call_command("check_calendar", path, "--seeds", "1")

    out = capsys.readouterr().out
    assert "Only Race" in out


def test_command_only_runs_matching_days_and_skips_the_verdict(tmp_path, capsys):
    from django.core.management import call_command

    path = _write(tmp_path, [
        {"week": 1, "day": "sunday", "time": "14:00", "name": "Keep Me", "course": FLAT},
        {"week": 2, "day": "sunday", "time": "14:00", "name": "Skip Me", "course": FLAT},
    ])

    call_command("check_calendar", path, "--seeds", "1", "--only", "keep")

    out = capsys.readouterr().out
    assert "Keep Me" in out and "Skip Me" not in out
