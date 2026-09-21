"""The game clock: the one way any code asks what time it is, and the
machinery that finds and processes due work.

See `world/README.md` for the discipline this module enforces: game code
reads `now()`, never `timezone.now()` / `datetime.now()`, when deciding
whether something scheduled is due. `now()` reads whichever `Clock` is
configured (`settings.GAME_CLOCK_CLASS`) — real, live time in production,
a developer-controlled mock clock in dev/test.
"""

from __future__ import annotations

import traceback
from datetime import datetime

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone
from django.utils.module_loading import import_string

from competitions.services import points_by_team, prizes_by_team, score_race
from economy.services import (
    apply_weekly_fanbase,
    charge_weekly_wages,
    pay_merchandise,
    pay_race_prizes,
)
from racing.models import Race
from racing.services import riders_who_raced, simulate_race
from riders.models import Rider
from riders.services import (
    advance_ages,
    apply_weekly_growth,
    apply_weekly_recovery,
    training_deltas,
)
from schedule.models import SeasonTransition, Week
from schedule.services import process_transitions, process_week_transitions
from staff.models import Trainer, TrainingWeekReport
from staff.services import focus_for, top_up_pool

from .clocks import Clock
from .models import GameClock, TickRun

_clock: Clock | None = None


def get_clock() -> Clock:
    """The process-wide clock, resolved from `settings.GAME_CLOCK_CLASS` and
    cached. Exported (not underscore-prefixed) because `mock_clock`'s
    commands need it to call `MockClock`-only methods."""
    global _clock
    if _clock is None:
        _clock = import_string(settings.GAME_CLOCK_CLASS)()
    return _clock


def now() -> datetime:
    """The current game time. Every piece of game code asks here, never
    `timezone.now()` / `datetime.now()`."""
    return get_clock().now()


def _reclaim_unfinished() -> list[int]:
    """Race ids left `running` with no results by an interrupted run."""
    return list(
        Race.objects.filter(status=Race.Status.RUNNING, results__isnull=True)
        .order_by("starts_at")
        .values_list("pk", flat=True)
    )


def _claim(limit: int, at: datetime) -> list[int]:
    """Claim up to `limit` due races by flipping them SCHEDULED -> RUNNING
    inside a transaction holding a row lock on exactly those rows. Returns
    the claimed ids. No simulation happens here.

    A second `tick` arriving while this transaction holds the lock blocks on
    `select_for_update()`, then re-runs its own filter after this one
    commits — the rows just claimed are now RUNNING and no longer match, so
    the second claim gets nothing. This is the exactly-once guarantee; see
    world/README.md.
    """
    if limit <= 0:
        return []
    with transaction.atomic():
        ids = list(
            Race.objects.select_for_update()
            .filter(status=Race.Status.SCHEDULED, starts_at__isnull=False, starts_at__lte=at)
            .order_by("starts_at")
            .values_list("pk", flat=True)[:limit]
        )
        Race.objects.filter(pk__in=ids).update(status=Race.Status.RUNNING)
    return ids


def _execute(race_ids: list[int], tick: TickRun, at: datetime) -> None:
    """Simulate each claimed race outside any lock. One broken course must
    not stop the run: an exception is recorded on that race and on the
    tick, and the loop continues."""
    for race_id in race_ids:
        race = Race.objects.get(pk=race_id)
        try:
            simulate_race(race, game_time=at)
            score_race(race)
            tick.races_finished += 1
        except Exception:
            race.status = Race.Status.FAILED
            race.save(update_fields=["status"])
            tick.error += f"race {race_id}:\n{traceback.format_exc()}\n"
            continue                      # nothing to pay for a failed race

        try:
            prizes = prizes_by_team(race)
            tick.prize_entries += pay_race_prizes(
                race.pk, race_name=race.name, at=race.finished_at,
                prizes_by_team=prizes,
            )
        except Exception:
            # The race ran and scored; a payout failure must not rewrite
            # that into a failed race. Record it and move on.
            tick.error += f"race {race_id} prizes:\n{traceback.format_exc()}\n"


def _completed_week(week) -> Week | None:
    """The week just before `week` in the same season, or None.

    A `WeekTransition` is written when a week *opens* (`schedule/README.md`,
    *Week transitions*), and `tick()` applies training before claiming the
    races due now. So the races of the week being entered are not yet known
    at the moment its growth/training runs. The races a boundary can
    account for are the ones from the week that just completed — entering
    week N therefore rewards week N-1's racing. Week 1 has no preceding
    week, and cross-season carry-over is out of scope (see
    world/README.md, *How a tick works*).
    """
    if week.number <= 1:
        return None
    return Week.objects.filter(season=week.season, number=week.number - 1).first()


def _apply_training_week(week) -> int:
    """One week's growth, training and freshness recovery, settled together.

    Iterated per week rather than collapsed into a count because each
    week has its own focus, its own races and its own racers — see the
    plan's Design decision 3. Growth and the resulting report are keyed
    to `week` (the rollover just crossed, preserving
    #58's one-growth-week-per-season-week cadence); the *race* half reads
    the week that just completed, since this week's races have not run
    yet. Freshness recovery follows the same shape: it runs once per
    week, excluding riders who raced in the week being settled — see the
    plan's Design decision 6. Returns how many riders had a *displayed*
    value change, for TickRun.riders_trained.
    """
    raced_week = _completed_week(week)
    raced = riders_who_raced(raced_week) if raced_week is not None else {}
    extra: dict[int, dict[str, float]] = {}
    focus_by_team: dict[int, str] = {}

    for trainer in Trainer.objects.filter(team__isnull=False).select_related("team"):
        focus = focus_for(trainer.team)
        if focus is None:
            continue
        focus_by_team[trainer.team_id] = focus
        skill = getattr(trainer, focus)
        for rider in trainer.team.riders.all():
            extra[rider.pk] = training_deltas(
                rider, focus=focus, trainer_skill=skill,
                raced_attributes=raced.get(rider.pk, []),
            )

    # Riders whose team has no trainer still get the race effect.
    for rider in Rider.objects.exclude(pk__in=extra):
        attrs = raced.get(rider.pk, [])
        if attrs:
            extra[rider.pk] = training_deltas(
                rider, focus=None, trainer_skill=None, raced_attributes=attrs,
            )

    changes = apply_weekly_growth(weeks=1, extra_deltas=extra)
    _write_training_reports(week, changes, focus_by_team)
    # `raced` is the {rider_id: [...]} of riders who finished a race in the
    # week being settled; those riders skip recovery (Design decision 6).
    apply_weekly_recovery(exclude_ids=set(raced))
    return len(changes)


def _write_training_reports(week, changes, focus_by_team) -> int:
    """One TrainingWeekReport per team that has a trainer, holding that
    week's visible changes (an empty list is normal).

    Each insert runs inside its own `transaction.atomic()` with an
    IntegrityError caught, the same per-row shape `process_transitions`
    uses and for the same reason: an IntegrityError poisons an enclosing
    transaction. The WeekTransition row is the real exactly-once
    guarantee; the (team, week) constraint is a second line of defence.
    """
    by_team: dict[int, list[dict]] = {}
    for change in changes:
        by_team.setdefault(change["team_id"], []).append(change)

    written = 0
    for team_id, focus in focus_by_team.items():
        with transaction.atomic():
            try:
                TrainingWeekReport.objects.create(
                    team_id=team_id, week=week, attribute=focus,
                    changes=by_team.get(team_id, []),
                )
                written += 1
            except IntegrityError:
                pass
    return written


def tick() -> TickRun:
    """Find and process whatever is due, exactly once. The only entry point
    cron — or a developer, after moving the mock clock with `mock_clock` —
    ever calls."""
    max_races = GameClock.load().catch_up_max_races
    at = now()

    # Transitions before race claiming: a race in week 1 of a season that
    # has just opened should be processed in a world that has already
    # recorded the opening.
    transitions = process_transitions(at)

    # One top-up per crossed boundary. Idempotent for free: a
    # SeasonTransition row is written at most once ever (unique on
    # (season, kind)), so a tick that runs twice, or catches up three weeks
    # late, cannot double-fill the pool.
    for _ in transitions:
        top_up_pool()

    # Ageing before growth, so a rider who turned 33 at this boundary is
    # evaluated against their new age this same tick.
    closed = [t for t in transitions if t.kind == SeasonTransition.Kind.CLOSED]
    riders_aged = 0
    for _ in closed:
        riders_aged = advance_ages()

    weeks = process_week_transitions(at)
    riders_trained = 0
    wage_entries = 0
    merchandise_entries = 0
    fanbase_entries = 0
    for transition in weeks:            # per week, NOT weeks=len(weeks)
        week = transition.week
        riders_trained += _apply_training_week(week)
        wage_entries += charge_weekly_wages(week)

        # Fanbase reads the week that just COMPLETED, not the one opening:
        # this loop runs before _claim()/_execute(), so `week`'s own races
        # have not been simulated yet (economy/README.md, *Fanbase reads the
        # completed week*). Same reason _apply_training_week uses
        # _completed_week().
        raced_week = _completed_week(week)
        points = points_by_team(raced_week) if raced_week is not None else {}
        fanbase_entries += apply_weekly_fanbase(week, points_by_team=points)
        merchandise_entries += pay_merchandise(week)

    reclaimed = _reclaim_unfinished()
    claimed = _claim(limit=max(0, max_races - len(reclaimed)), at=at)
    capped = len(reclaimed) + len(claimed) >= max_races

    run = TickRun.objects.create(
        races_started=len(claimed),
        seasons_opened=sum(1 for t in transitions if t.kind == SeasonTransition.Kind.OPENED),
        seasons_closed=sum(1 for t in transitions if t.kind == SeasonTransition.Kind.CLOSED),
        weeks_processed=len(weeks),
        riders_aged=riders_aged,
        riders_trained=riders_trained,
        wage_entries=wage_entries,
        merchandise_entries=merchandise_entries,
        fanbase_entries=fanbase_entries,
    )
    _execute(reclaimed + claimed, run, at=at)
    run.capped = capped
    # Real time regardless of which clock is active: this records when the
    # check itself ran on the host, not game time. The one other sanctioned
    # real-time read alongside RealClock.now() itself.
    run.finished_at = timezone.now()
    run.save(update_fields=["races_finished", "capped", "error", "finished_at"])
    return run
