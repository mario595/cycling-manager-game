from __future__ import annotations

from datetime import datetime, time, timedelta, timezone as dt_timezone

import pytest

from schedule.loaders import (
    RaceDeclaration,
    SeasonFileError,
    StageRaceDeclaration,
    create_races,
    create_stage_races,
    parse_season_file,
)
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
    from racing.services import create_race

    days = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
    declarations = [
        RaceDeclaration(
            week=12, day=day, time=time(12, 0),
            name=f"{day.title()} Race", course=[SEGMENT],
            wind_enabled=True, wind_band=None, seed=None,
        )
        for day in days
    ]

    created = create_races(season, declarations, create_race=create_race)

    for race_obj in created:
        race_obj.full_clean()


LONG_COURSE = {"length": 10000.0, "gradient": 0.0}


def marked_race(**overrides):
    data = {
        "week": 1,
        "day": "sunday",
        "time": "14:00",
        "name": "Marked Race",
        "course": [LONG_COURSE],
        "markers": [
            {"kind": "sprint", "name": "First", "distance": 2000},
            {"kind": "mountain", "name": "Top", "distance": 9000.5},
        ],
    }
    data.update(overrides)
    return data


def test_parses_markers_on_a_race():
    decl = parse_season_file({**BASE, "races": [marked_race()]})

    assert decl.races[0].markers == [
        {"kind": "sprint", "name": "First", "distance": 2000.0, "weight": "standard"},
        {"kind": "mountain", "name": "Top", "distance": 9000.5, "weight": "standard"},
    ]


def test_markers_absent_or_null_gives_empty_list():
    decl = parse_season_file({**BASE, "races": [marked_race(markers=None)]})

    assert decl.races[0].markers == []


def test_rejects_markers_that_are_not_a_list():
    with pytest.raises(SeasonFileError, match=r"races\[0\]\.markers must be a list"):
        parse_season_file({**BASE, "races": [marked_race(markers="sprint")]})


def test_rejects_a_marker_that_is_not_an_object():
    with pytest.raises(SeasonFileError, match=r"races\[0\]\.markers\[0\]"):
        parse_season_file({**BASE, "races": [marked_race(markers=["sprint"])]})


@pytest.mark.parametrize("marker", [
    {"kind": "koM", "name": "Wrong Kind", "distance": 1000},
    {"kind": "sprint", "name": "   ", "distance": 1000},
    {"kind": "sprint", "name": "N" * 101, "distance": 1000},
    {"kind": "sprint", "name": "Too Far", "distance": 0},
    {"kind": "sprint", "name": "Too Far", "distance": 10001},
    {"kind": "sprint", "name": "Not a Number", "distance": "far"},
])
def test_rejects_an_invalid_marker(marker):
    with pytest.raises(SeasonFileError, match=r"races\[0\]\.markers\[0\]"):
        parse_season_file({**BASE, "races": [marked_race(markers=[marker])]})


def test_unknown_marker_key_is_warned_and_ignored():
    decl = parse_season_file({**BASE, "races": [marked_race(markers=[
        {"kind": "sprint", "name": "N", "distance": 2000, "points": 10},
    ])]})

    assert decl.races[0].markers == [
        {"kind": "sprint", "name": "N", "distance": 2000.0, "weight": "standard"},
    ]
    assert any("ignoring unknown" in w and "points" in w for w in decl.warnings)


def test_sprint_marker_weight_is_parsed():
    decl = parse_season_file({**BASE, "races": [marked_race(markers=[
        {"kind": "sprint", "name": "N", "distance": 2000, "weight": "major"},
    ])]})

    assert decl.races[0].markers[0]["weight"] == "major"


def test_missing_weight_defaults_to_standard():
    decl = parse_season_file({**BASE, "races": [marked_race(markers=[
        {"kind": "sprint", "name": "N", "distance": 2000},
    ])]})

    assert decl.races[0].markers[0]["weight"] == "standard"


def test_rejects_unknown_weight():
    with pytest.raises(SeasonFileError, match=r"races\[0\]\.markers\[0\]\.weight"):
        parse_season_file({**BASE, "races": [marked_race(markers=[
            {"kind": "sprint", "name": "N", "distance": 2000, "weight": "huge"},
        ])]})


def test_rejects_weight_on_mountain_marker():
    with pytest.raises(SeasonFileError, match=r"races\[0\]\.markers\[0\]\.weight"):
        parse_season_file({**BASE, "races": [marked_race(markers=[
            {"kind": "mountain", "name": "N", "distance": 2000, "weight": "standard"},
        ])]})


def test_create_races_passes_markers_to_the_creator(season):
    created = []
    declarations = [
        RaceDeclaration(
            week=1, day="sunday", time=time(14, 0), name="Marked",
            course=[{"length": 5000.0, "gradient": 0.0}],
            wind_enabled=True, wind_band=None, seed=None,
            markers=[{"kind": "sprint", "name": "N", "distance": 2000.0}],
        )
    ]

    def create_race(**kwargs):
        created.append(kwargs)
        return None

    create_races(season, declarations, create_race=create_race)

    assert created[0]["markers"] == [{"kind": "sprint", "name": "N", "distance": 2000.0}]


def stage_race(**overrides):
    data = {
        "name": "Alpine Tour",
        "week": 1,
        "start_day": "monday",
        "time": "14:00",
        "stages": [
            {"course": [SEGMENT]},
            {"course": [SEGMENT]},
            {"course": [SEGMENT]},
        ],
    }
    data.update(overrides)
    return data


def test_stage_race_parsed_onto_consecutive_days():
    decl = parse_season_file({**BASE, "stage_races": [stage_race()]})

    assert len(decl.stage_races) == 1
    sr = decl.stage_races[0]
    assert sr.name == "Alpine Tour"
    assert sr.week == 1
    assert [s.day for s in sr.stages] == ["monday", "tuesday", "wednesday"]
    assert all(s.week == 1 for s in sr.stages)
    assert all(s.time == time(14, 0) for s in sr.stages)


def test_stage_race_names():
    decl = parse_season_file({**BASE, "stage_races": [stage_race(stages=[
        {"course": [SEGMENT]},
        {"course": [SEGMENT], "name": "Mountain Stage"},
    ])]})

    assert decl.stage_races[0].stages[0].name == "Alpine Tour — Stage 1"
    assert decl.stage_races[0].stages[1].name == "Alpine Tour — Stage 2: Mountain Stage"


def test_stage_race_too_few_stages():
    with pytest.raises(SeasonFileError):
        parse_season_file({**BASE, "stage_races": [stage_race(stages=[{"course": [SEGMENT]}])]})


def test_stage_race_too_many_stages():
    with pytest.raises(SeasonFileError):
        parse_season_file({**BASE, "stage_races": [
            stage_race(stages=[{"course": [SEGMENT]}] * 8)
        ]})


def test_stage_race_runs_past_sunday():
    with pytest.raises(SeasonFileError, match="runs past Sunday"):
        parse_season_file({**BASE, "stage_races": [
            stage_race(start_day="friday", stages=[{"course": [SEGMENT]}] * 4)
        ]})


def test_stage_clashes_with_one_day_race():
    with pytest.raises(SeasonFileError) as exc_info:
        parse_season_file({
            **BASE,
            "races": [race(week=1, day="tuesday", name="Tuesday Classic")],
            "stage_races": [stage_race(start_day="monday")],  # stage 2 lands on Tuesday
        })

    message = str(exc_info.value)
    assert "Tuesday Classic" in message
    assert "Alpine Tour — Stage 2" in message


def test_stage_time_overrides_default():
    decl = parse_season_file({**BASE, "stage_races": [stage_race(stages=[
        {"course": [SEGMENT]},
        {"course": [SEGMENT], "time": "09:00"},
    ])]})

    assert decl.stage_races[0].stages[0].time == time(14, 0)
    assert decl.stage_races[0].stages[1].time == time(9, 0)


def test_unknown_stage_key_warns():
    decl = parse_season_file({**BASE, "stage_races": [stage_race(stages=[
        {"course": [SEGMENT], "points": 10},
        {"course": [SEGMENT]},
    ])]})

    assert any("ignoring unknown" in w and "points" in w for w in decl.warnings)


def test_create_stage_races(season):
    declarations = [
        StageRaceDeclaration(
            name="Alpine Tour", week=1,
            stages=[
                RaceDeclaration(
                    week=1, day="monday", time=time(14, 0),
                    name="Alpine Tour — Stage 1", course=[SEGMENT],
                    wind_enabled=True, wind_band=None, seed=None,
                ),
                RaceDeclaration(
                    week=1, day="tuesday", time=time(14, 0),
                    name="Alpine Tour — Stage 2", course=[SEGMENT],
                    wind_enabled=True, wind_band=None, seed=None,
                ),
            ],
        ),
    ]
    created_races: list = []
    created_stage_races: list = []

    def create_race(**kwargs):
        created_races.append(kwargs)
        return kwargs

    def create_stage_race(**kwargs):
        created_stage_races.append(kwargs)
        return kwargs

    result = create_stage_races(
        season, declarations, create_race=create_race, create_stage_race=create_stage_race,
    )

    assert len(result) == 1
    assert created_stage_races == [{"name": "Alpine Tour", "week": season.weeks.get(number=1)}]
    assert len(created_races) == 2
    assert created_races[0]["stage_number"] == 1
    assert created_races[1]["stage_number"] == 2
    assert created_races[0]["stage_race"] == created_stage_races[0]
    assert created_races[1]["starts_at"] == created_races[0]["starts_at"] + timedelta(days=1)
