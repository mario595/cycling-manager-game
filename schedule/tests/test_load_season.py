from __future__ import annotations

import json

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from schedule.models import Season, Week


def write_season_file(tmp_path, **overrides):
    data = {"number": 1, "starts_at": "2027-03-01T00:00:00Z"}
    data.update(overrides)
    path = tmp_path / "season.json"
    path.write_text(json.dumps(data))
    return str(path)


def test_creates_a_season_and_twelve_weeks(db, tmp_path):
    path = write_season_file(tmp_path)

    call_command("load_season", path)

    season = Season.objects.get(number=1)
    assert season.starts_at.isoformat() == "2027-03-01T00:00:00+00:00"
    assert Week.objects.filter(season=season).count() == 12


def test_refuses_a_started_season_even_with_replace(db, tmp_path):
    path = write_season_file(tmp_path)
    call_command("load_season", path)
    call_command("mock_clock", "set", "2027-03-01T00:00:00")

    with pytest.raises(CommandError):
        call_command("load_season", path, "--replace")


def test_replaces_a_declared_but_unstarted_season(db, tmp_path):
    path = write_season_file(tmp_path)
    call_command("load_season", path)
    replacement = write_season_file(tmp_path, starts_at="2027-03-08T00:00:00Z")

    call_command("load_season", replacement, "--replace")

    season = Season.objects.get(number=1)
    assert season.starts_at.isoformat() == "2027-03-08T00:00:00+00:00"
    assert Week.objects.filter(season=season).count() == 12


def test_refuses_a_non_monday_start(db, tmp_path):
    path = write_season_file(tmp_path, starts_at="2027-03-02T00:00:00Z")

    with pytest.raises(CommandError):
        call_command("load_season", path)


def test_refuses_an_overlap(db, tmp_path):
    path = write_season_file(tmp_path)
    call_command("load_season", path)
    overlapping = write_season_file(
        tmp_path, number=2, starts_at="2027-03-15T00:00:00Z",
    )

    with pytest.raises(CommandError):
        call_command("load_season", overlapping)


def test_ignores_unknown_keys_with_a_warning(db, tmp_path, capsys):
    path = write_season_file(tmp_path, sponsor="Some Sponsor")

    call_command("load_season", path)

    out = capsys.readouterr().out
    assert "sponsor" in out
    assert Season.objects.filter(number=1).exists()


SEGMENT = {"length": 1000.0, "gradient": 0.0}


def race_entry(**overrides):
    data = {
        "week": 1,
        "day": "sunday",
        "time": "14:00",
        "name": "Opening Classic",
        "course": [SEGMENT],
    }
    data.update(overrides)
    return data


def test_creates_the_declared_races(db, tmp_path):
    path = write_season_file(tmp_path, races=[race_entry()])

    call_command("load_season", path)

    season = Season.objects.get(number=1)
    week_one = Week.objects.get(season=season, number=1)
    race = week_one.races.get()
    assert race.name == "Opening Classic"
    assert race.starts_at.isoformat() == "2027-03-07T14:00:00+00:00"


def test_a_malformed_race_creates_no_season_at_all(db, tmp_path):
    path = write_season_file(
        tmp_path,
        races=[race_entry(name="Good Race"), race_entry(week=13, name="Broken Race")],
    )

    with pytest.raises(CommandError):
        call_command("load_season", path)

    assert Season.objects.count() == 0


def test_replace_deletes_the_previous_races(db, tmp_path):
    from racing.models import Race

    path = write_season_file(tmp_path, races=[race_entry()])
    call_command("load_season", path)
    assert Race.objects.count() == 1

    replacement = write_season_file(tmp_path, races=[])
    call_command("load_season", replacement, "--replace")

    assert Race.objects.count() == 0


def test_replace_refuses_after_start(db, tmp_path):
    from racing.models import Race

    path = write_season_file(tmp_path, races=[race_entry()])
    call_command("load_season", path)
    call_command("mock_clock", "set", "2027-03-01T00:00:00")

    with pytest.raises(CommandError):
        call_command("load_season", path, "--replace")

    assert Season.objects.filter(number=1).exists()
    assert Race.objects.count() == 1


def test_races_key_is_optional_end_to_end(db, tmp_path):
    path = write_season_file(tmp_path)

    call_command("load_season", path)

    season = Season.objects.get(number=1)
    assert Week.objects.filter(season=season).count() == 12


def test_load_season_creates_race_markers(db, tmp_path):
    path = write_season_file(
        tmp_path,
        races=[
            race_entry(
                course=[{"length": 10000.0, "gradient": 0.0}],
                markers=[
                    {"kind": "sprint", "name": "First", "distance": 4000},
                    {"kind": "mountain", "name": "Top", "distance": 9000},
                ],
            )
        ],
    )

    call_command("load_season", path)

    race = Week.objects.get(season__number=1, number=1).races.get()
    assert list(race.markers.values_list("kind", "name", "distance")) == [
        ("sprint", "First", 4000.0),
        ("mountain", "Top", 9000.0),
    ]
