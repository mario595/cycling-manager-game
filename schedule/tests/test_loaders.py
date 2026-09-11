from __future__ import annotations

from datetime import datetime, time, timedelta, timezone as dt_timezone

import pytest

from schedule.loaders import RaceDeclaration, SeasonFileError, create_races, parse_season_file
from schedule.models import Season, Week

BASE = {"number": 1, "starts_at": "2027-03-01T00:00:00Z"}

SEGMENT = {"length": 1000.0, "gradient": 0.0}


def race(**overrides):
    data = {
        "week": 1,
        "day": "sunday",
        "time": "14:00",
        "name": "Test Race",
        "course": [SEGMENT],
    }
    data.update(overrides)
    return data


def test_parses_a_race_entry():
    decl = parse_season_file({**BASE, "races": [race()]})

    assert len(decl.races) == 1
    r = decl.races[0]
    assert r.week == 1
    assert r.day == "sunday"
    assert r.name == "Test Race"
    assert r.course == [{"length": 1000.0, "gradient": 0.0}]
    assert r.wind_enabled is True
    assert r.wind_band is None
    assert r.seed is None


@pytest.mark.parametrize("week", [0, 13])
def test_rejects_a_week_outside_the_season(week):
    with pytest.raises(SeasonFileError):
        parse_season_file({**BASE, "races": [race(week=week)]})


def test_rejects_an_unknown_day():
    with pytest.raises(SeasonFileError):
        parse_season_file({**BASE, "races": [race(day="funday")]})


def test_rejects_a_malformed_time():
    with pytest.raises(SeasonFileError):
        parse_season_file({**BASE, "races": [race(time="2pm")]})


def test_rejects_two_races_on_the_same_day():
    with pytest.raises(SeasonFileError) as exc_info:
        parse_season_file({
            **BASE,
            "races": [
                race(name="Morning Race"),
                race(name="Afternoon Race"),
            ],
        })

    message = str(exc_info.value)
    assert "Morning Race" in message
    assert "Afternoon Race" in message


def test_accepts_two_races_in_one_week_on_different_days():
    decl = parse_season_file({
        **BASE,
        "races": [
            race(day="saturday", name="Saturday Race"),
            race(day="sunday", name="Sunday Race"),
        ],
    })

    assert len(decl.races) == 2


def test_rejects_an_empty_course():
    with pytest.raises(SeasonFileError):
        parse_season_file({**BASE, "races": [race(course=[])]})


def test_rejects_a_non_positive_segment_length():
    with pytest.raises(SeasonFileError):
        parse_season_file({**BASE, "races": [race(course=[{"length": 0, "gradient": 0.0}])]})


def test_rejects_an_unknown_wind_band():
    with pytest.raises(SeasonFileError):
        parse_season_file({**BASE, "races": [race(wind={"band": "hurricane"})]})


def test_warns_on_non_zero_minutes():
    decl = parse_season_file({**BASE, "races": [race(time="14:30")]})

    assert any("14:30" in w for w in decl.warnings)


def test_races_key_is_optional():
    decl = parse_season_file(dict(BASE))

    assert decl.races == []


SEASON_START = datetime(2027, 3, 1, tzinfo=dt_timezone.utc)


@pytest.fixture
def season(db) -> Season:
    """A season with its twelve weeks, built the same way load_season does
    (season.starts_at + N weeks), independent of the command itself."""
    season = Season.objects.create(number=1, starts_at=SEASON_START)
    weeks = []
    for week_number in range(1, 13):
        week_start = SEASON_START + timedelta(weeks=week_number - 1)
        weeks.append(Week(
            season=season, number=week_number,
            starts_at=week_start, ends_at=week_start + timedelta(weeks=1),
        ))
    Week.objects.bulk_create(weeks)
    return season


def _stub_create_race(sink: list):
    """A stand-in for racing.models.Race.objects.create that just records
    what it was called with, proving create_races never imports racing/."""
    def create_race(**kwargs):
        sink.append(kwargs)
        return kwargs
    return create_race


def test_places_a_race_on_the_right_instant(season):
    declarations = [
        RaceDeclaration(
            week=3, day="sunday", time=time(14, 0),
            name="Sunday Classic", course=[SEGMENT],
            wind_enabled=True, wind_band=None, seed=None,
        ),
    ]
    created: list = []

    create_races(season, declarations, create_race=_stub_create_race(created))

    assert len(created) == 1
    # Hand-computed: season starts Monday 2027-03-01, week 3 starts
    # 2027-03-15, + 6 days (Sunday) + 14:00 = 2027-03-21T14:00Z.
    assert created[0]["starts_at"] == datetime(2027, 3, 21, 14, 0, tzinfo=dt_timezone.utc)


def test_every_placed_race_satisfies_its_week_containment(season):
    from racing.models import Race

    days = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
    declarations = [
        RaceDeclaration(
            week=12, day=day, time=time(12, 0),
            name=f"{day.title()} Race", course=[SEGMENT],
            wind_enabled=True, wind_band=None, seed=None,
        )
        for day in days
    ]

    created = create_races(season, declarations, create_race=Race.objects.create)

    for race_obj in created:
        race_obj.full_clean()
