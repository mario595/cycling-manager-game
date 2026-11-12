"""Who wins each race of a season file, against a freshly generated field.

The balance check for a calendar (specs/archive/beta-world.md, In scope 3): does
every winning speciality have races it wins, and does none win too many?
It runs every race and every stage of a season declaration through the
engine against a seeded field of generated teams, picks each team's squad
the way an unmanaged team picks one (`course_pick_squad`'s scoring), and
reports the winner's speciality.

Deliberately **database-free**: the field is unsaved `Rider` objects with
synthetic primary keys, and nothing is written — no `Race`, no result, no
log. That keeps the check fast enough to run across several seeds and safe
to run against any database, production included. It also means it leaves
out everything a real season adds between races: fatigue, recovery,
training and transfers. It answers "what does this course reward", not
"who will win season 3".
"""

from __future__ import annotations

import random
from collections import Counter
from collections.abc import Callable, Iterable
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field
import multiprocessing

from riders.generation import generate_roster
from riders.models import Rider
from schedule.loaders import DAY_INDEX, RaceDeclaration, SeasonDeclaration
from teams.models import Team

from .adapters import run_race_via_adapter, to_engine_course_from_json, to_engine_rider, to_team_codes
from .models import SQUAD_SIZE
from .services import course_pick_order, group_times

#: The four specialities a calendar must give wins to. Domestiques are
#: support riders and are not expected to win (specs/archive/beta-world.md,
#: Decisions taken).
WINNING_SPECIALITIES = (
    Rider.Speciality.CLIMBER,
    Rider.Speciality.SPRINTER,
    Rider.Speciality.ROULEUR,
    Rider.Speciality.PUNCHEUR,
)
#: Each winning speciality must win at least this many race days a season...
MIN_WINS = 2
#: ...except rouleurs. The engine has no time trial, echelon or breakaway,
#: the three places a rouleur's flat power decides a race, so on today's
#: engine they win about one flat day in eight and lose the rest to
#: sprinters in the final. Their full share waits for time trials
#: (#89, #90). Decided on #139; see specs/archive/beta-world.md.
MIN_WINS_BY_SPECIALITY = {Rider.Speciality.ROULEUR: 1}
#: ...and no speciality may win more than this share of them.
MAX_SHARE = 0.40

DEFAULT_TEAMS = 16
DEFAULT_RIDERS_PER_TEAM = 12


@dataclass(frozen=True)
class Day:
    """One race day of the calendar: a one-day race or one stage."""

    label: str
    course: list[dict]
    markers: list[dict]
    wind_enabled: bool
    wind_band: str | None
    stage_race: str | None = None
    stage_number: int | None = None
    #: The course squads are picked for. A stage race's squad is chosen once,
    #: for stage 1, and carried through the tour, as in the game.
    pick_course: list[dict] | None = None


@dataclass
class DayResult:
    day: Day
    field_seed: int
    winner_speciality: str
    winner_name: str
    top_three: list[str]
    #: Per-rider finish group time, for the general classification.
    group_time_by_rider: dict[str, float] = field(default_factory=dict)


def calendar_days(declaration: SeasonDeclaration) -> list[Day]:
    """Every race day of the season, in calendar order (week, then day)."""
    entries: list[tuple[int, int, Day]] = []

    def _day(d: RaceDeclaration, label: str, **extra) -> Day:
        return Day(
            label=label,
            course=d.course,
            markers=list(d.markers),
            wind_enabled=d.wind_enabled,
            wind_band=d.wind_band,
            **extra,
        )

    for race in declaration.races:
        entries.append((race.week, DAY_INDEX[race.day], _day(race, race.name)))
    for tour in declaration.stage_races:
        first = tour.stages[0].course
        for n, stage in enumerate(tour.stages, start=1):
            entries.append((
                tour.week, DAY_INDEX[stage.day],
                _day(stage, stage.name, stage_race=tour.name, stage_number=n, pick_course=first),
            ))
    entries.sort(key=lambda e: (e[0], e[1]))
    return [day for _, _, day in entries]


def generate_field(
    seed: int, *, teams: int = DEFAULT_TEAMS, per_team: int = DEFAULT_RIDERS_PER_TEAM,
) -> tuple[list[Team], dict[int, list[Rider]]]:
    """Unsaved teams with generated rosters, exactly as `seed_teams` would
    roll them, but with synthetic pks so the engine can identify riders."""
    rng = random.Random(seed)
    team_rows: list[Team] = []
    rosters: dict[int, list[Rider]] = {}
    next_pk = 1
    for t in range(1, teams + 1):
        team = Team(pk=t, name=f"Team {t}", code=f"T{t:02d}")
        roster = generate_roster(per_team, rng=rng)
        for rider in roster:
            rider.pk = next_pk
            rider.team_id = t
            next_pk += 1
        team_rows.append(team)
        rosters[t] = roster
    return team_rows, rosters


def _engine_field(rosters: dict[int, list[Rider]], course: list[dict]):
    engine_riders = []
    for roster in rosters.values():
        if len(roster) < SQUAD_SIZE:
            continue
        picked = course_pick_order(roster, course)[:SQUAD_SIZE]
        leader = picked[0].pk
        engine_riders.extend(
            to_engine_rider(r, role="leader" if r.pk == leader else "support")
            for r in picked
        )
    return engine_riders


def run_day(day: Day, field_seed: int, race_seed: int) -> DayResult:
    """Simulate one race day against the field rolled from `field_seed`."""
    teams, rosters = generate_field(field_seed)
    by_pk = {str(r.pk): r for roster in rosters.values() for r in roster}
    engine_riders = _engine_field(rosters, day.pick_course or day.course)
    states, _, _ = run_race_via_adapter(
        engine_riders,
        to_engine_course_from_json(day.course, day.markers),
        None,
        race_seed,
        to_team_codes(teams),
        day.wind_enabled,
        day.wind_band,
    )
    finishers = sorted(
        (s for s in states if s.finish_time is not None),
        key=lambda s: s.finish_time,
    )
    groups = group_times([float(s.finish_time) for s in finishers])
    winner = by_pk[finishers[0].rider.id]
    return DayResult(
        day=day,
        field_seed=field_seed,
        winner_speciality=winner.speciality,
        winner_name=winner.name,
        top_three=[by_pk[s.rider.id].speciality for s in finishers[:3]],
        group_time_by_rider={s.rider.id: g for s, g in zip(finishers, groups)},
    )


def _run_day_args(args: tuple[Day, int, int]) -> DayResult:
    return run_day(*args)


def check_calendar(
    declaration: SeasonDeclaration,
    seeds: Iterable[int],
    *,
    jobs: int = 1,
    on_result: Callable[[DayResult], None] | None = None,
) -> list[DayResult]:
    """Run every race day once per seed. The race seed is derived from the
    field seed and the day's index, so a run is reproducible."""
    days = calendar_days(declaration)
    work = [
        (day, seed, seed * 1000 + i)
        for seed in seeds
        for i, day in enumerate(days)
    ]
    results: list[DayResult] = []
    if jobs <= 1:
        for args in work:
            result = _run_day_args(args)
            results.append(result)
            if on_result:
                on_result(result)
        return results

    # fork, not spawn: the children inherit the parent's configured Django,
    # which an unconfigured spawned interpreter would have to set up again.
    ctx = multiprocessing.get_context("fork")
    with ProcessPoolExecutor(max_workers=jobs, mp_context=ctx) as pool:
        for result in pool.map(_run_day_args, work):
            results.append(result)
            if on_result:
                on_result(result)
    return results


@dataclass
class Verdict:
    wins: Counter
    days_per_seed: int
    seeds: int
    failures: list[str]

    @property
    def ok(self) -> bool:
        return not self.failures


def judge(results: list[DayResult]) -> Verdict:
    """Apply the spec's rule to the results, averaged per season (seed):
    each winning speciality at least its minimum (MIN_WINS, or
    MIN_WINS_BY_SPECIALITY's lower figure for rouleurs), none above
    MAX_SHARE."""
    seeds = sorted({r.field_seed for r in results})
    wins = Counter(r.winner_speciality for r in results)
    total = len(results)
    days_per_seed = total // len(seeds) if seeds else 0
    failures = []
    for speciality in WINNING_SPECIALITIES:
        per_season = wins[speciality] / len(seeds) if seeds else 0
        needed = MIN_WINS_BY_SPECIALITY.get(speciality, MIN_WINS)
        if per_season < needed:
            failures.append(
                f"{speciality} wins {per_season:.1f} race days a season (needs {needed})"
            )
    for speciality, count in wins.items():
        share = count / total
        if share > MAX_SHARE:
            failures.append(
                f"{speciality} wins {share:.0%} of race days (limit {MAX_SHARE:.0%})"
            )
    return Verdict(wins=wins, days_per_seed=days_per_seed, seeds=len(seeds), failures=failures)


def general_classification(results: list[DayResult], stage_race: str, field_seed: int) -> str | None:
    """The winner's speciality of a stage race's GC in the check: the lowest
    summed group time among riders who finished every stage.

    The check races every stage with that stage's own course-picked squad,
    not stage 1's carried forward, so this is an approximation of the
    game's GC, good enough to see which kind of rider a tour rewards.
    """
    stages = [
        r for r in results
        if r.day.stage_race == stage_race and r.field_seed == field_seed
    ]
    if not stages:
        return None
    common = set(stages[0].group_time_by_rider)
    for s in stages[1:]:
        common &= set(s.group_time_by_rider)
    if not common:
        return None
    best = min(common, key=lambda rid: sum(s.group_time_by_rider[rid] for s in stages))
    _, rosters = generate_field(field_seed)
    by_pk = {str(r.pk): r for roster in rosters.values() for r in roster}
    return by_pk[best].speciality
