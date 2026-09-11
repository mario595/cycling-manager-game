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
    path = write_season_file(tmp_path, races=[{"name": "Tour de Something"}])

    call_command("load_season", path)

    out = capsys.readouterr().out
    assert "races" in out
    assert Season.objects.filter(number=1).exists()
