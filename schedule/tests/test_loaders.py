from __future__ import annotations

import pytest

from schedule.loaders import SeasonFileError, parse_season_file

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
