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
    charge_trainer_salaries,
    charge_transfer_fee,
    charge_weekly_wages,
    ensure_offer_round,
    pay_merchandise,
    pay_race_prizes,
    pay_sponsorship,
    pay_transfer_income,
    write_salary_reviews,
)
from racing.models import Race, RaceResult
from racing.services import riders_who_raced, riders_who_started, simulate_race
from riders.models import Rider
from riders.services import (
    advance_ages,
    apply_weekly_growth,
    apply_weekly_recovery,
    record_week_snapshots,
    reprice_all,
    retire_riders,
    training_deltas,
)
from schedule.models import SeasonTransition, Week
from schedule.services import process_transitions, process_week_transitions, weeks_opened_between
from staff.models import Trainer, TrainingWeekReport
from staff.pricing import weekly_salary
from staff.services import focus_for, top_up_pool
from teams.models import ManagerialSpell, Team
from teams.services import release_team
from transfers.models import Auction
from transfers.pricing import market_value_for
from transfers.services import (
    EXPIRY_VALUE_PERCENTILE,
    EXPIRY_WEEKS,
    due_auctions,
    free_agents,
    resolve_auction,
)

from .clocks import Clock
from .models import GameClock, TickRun

_clock: Clock | None = None

#: Consecutive in-season game-weeks with no login before a manager's team is
#: released (#63). A game-balance constant, not per-environment
#: configuration — contrast GameClock.catch_up_max_races, which exists to be
#: raised temporarily during an incident; this one does not.
INACTIVITY_WEEKS = 10


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


def _release_inactive(week) -> tuple[int, str]:
    """Release the team of every manager inactive for INACTIVITY_WEEKS
    in-season weeks as of this week boundary (#63).

    Counted in game-time weeks that actually opened, so off-season gaps
    contribute nothing. A null last_seen_at is exempt: the account has
    never logged in.

    Returns (teams released, accumulated error text) rather than writing
    directly onto a TickRun — tick() has not created its TickRun row yet at
    the point in the week loop where this runs.
    """
    boundary = week.starts_at
    released = 0
    error = ""
    managed = Team.objects.filter(
        manager__isnull=False, manager__last_seen_at__isnull=False,
    ).select_related("manager")

    for team in managed:
        if weeks_opened_between(team.manager.last_seen_at, boundary) < INACTIVITY_WEEKS:
            continue
        try:
            # release_team returns None for an already-unmanaged team
            # (teams/README.md, Releasing a team) — keeps this count honest
            # if a concurrent tick got there first.
            if release_team(team, reason=ManagerialSpell.Reason.INACTIVITY, at=boundary) is not None:
                released += 1
        except Exception:
            # One bad release must not strand this week's wages or
            # training — same shape as _execute's per-race guard.
            error += f"release team {team.pk}:\n{traceback.format_exc()}\n"
    return released, error


def _expire_free_agents(week) -> tuple[int, int]:
    """Retire or delete every free agent unattached EXPIRY_WEEKS+ in-season
    weeks as of this week boundary, and priced at or below the pool's
    EXPIRY_VALUE_PERCENTILE at that moment. Returns (retired, deleted).

    Mirrors _release_inactive's shape: counts Week rows via
    schedule.services.weeks_opened_between — world/ just provides the
    boundary; schedule/ owns week counting (AGENTS.md's dependency
    direction) — and is called once per week transition in the same loop.
    The percentile is computed fresh from the whole pool's value on each
    pass — value is never stored, so there is nothing to have gone stale. A
    pool too small for a meaningful bottom EXPIRY_VALUE_PERCENTILE expires
    nobody (Design decision 5): a bottom quintile of one or two riders is
    not a signal. A null `unattached_since` (pre-migration riders) is
    excluded, never treated as "unattached since the beginning of time."

    A selected rider with at least one RaceResult is retired and keeps its
    history. A selected rider with no RaceResult is deleted. Both outcomes
    return rider counts, never delete()'s cascaded-row total.
    """
    pool = list(free_agents())
    # Truncation is the small-pool guard (Design decision 5): a floor leaves
    # a 2-rider pool pointing at a "bottom" quintile of one rider.
    bottom_count = int(len(pool) * EXPIRY_VALUE_PERCENTILE)
    if bottom_count == 0:
        return 0, 0
    value_by_rider = {rider.pk: market_value_for(rider) for rider in pool}
    values = sorted(value_by_rider.values())
    cutoff = values[bottom_count - 1]

    boundary = week.starts_at
    # weeks_opened_between(since, boundary) is monotone in `since`, so
    # "opened EXPIRY_WEEKS+ weeks" has a single cutoff: the EXPIRY_WEEKS-th
    # newest in-season week opening before `boundary`, and a rider qualifies
    # iff its unattached_since is at or before that. One query for the whole
    # pool instead of one COUNT per rider.
    opened = list(
        Week.objects.filter(starts_at__lt=boundary)
        .order_by("-starts_at")
        .values_list("starts_at", flat=True)[:EXPIRY_WEEKS]
    )
    if len(opened) < EXPIRY_WEEKS:
        return 0, 0
    expiry_cutoff = opened[EXPIRY_WEEKS - 1]
    doomed = [
        rider.pk
        for rider in pool
        if rider.unattached_since is not None
        and rider.unattached_since <= expiry_cutoff
        and value_by_rider[rider.pk] <= cutoff
    ]
    raced = set(
        RaceResult.objects.filter(rider_id__in=doomed)
        .values_list("rider_id", flat=True)
        .distinct()
    )
    retired = retire_riders(raced, at=boundary)
    never_raced = [pk for pk in doomed if pk not in raced]
    Rider.objects.filter(pk__in=never_raced, team__isnull=True).delete()
    return retired, len(never_raced)


def _apply_training_week(week) -> int:
    """One week's growth, training and freshness recovery, settled together.

    Iterated per week rather than collapsed into a count because each
    week has its own focus, its own races and its own racers — see the
    plan's Design decision 3. Growth and the resulting report are keyed
    to `week` (the rollover just crossed, preserving
    #58's one-growth-week-per-season-week cadence); the *race* half reads
    the week that just completed, since this week's races have not run
    yet. Freshness recovery follows the same shape: it runs once per
    week, excluding riders who started a race in the week being settled
    — see the plan's Design decision 6, and the broom-wagon-time-cut
    spec's In scope 5 (a rider cut by the time limit costs a race's worth
    of fatigue same as a finisher). Returns how many riders had a
    *displayed* value change, for TickRun.riders_trained.
    """
    raced_week = _completed_week(week)
    raced = riders_who_raced(raced_week) if raced_week is not None else {}
    started = riders_who_started(raced_week) if raced_week is not None else set()
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
    for rider in Rider.objects.active().exclude(pk__in=extra):
        attrs = raced.get(rider.pk, [])
        if attrs:
            extra[rider.pk] = training_deltas(
                rider, focus=None, trainer_skill=None, raced_attributes=attrs,
            )

    changes = apply_weekly_growth(weeks=1, extra_deltas=extra)
    _write_training_reports(week, changes, focus_by_team)
    if changes:
        record_week_snapshots(
            sorted({change["rider_id"] for change in changes}), week_id=week.pk,
        )
    # `started` is every rider with a RaceResult in the week being settled,
    # finisher or cut by the time limit; those riders skip recovery
    # (Design decision 6).
    apply_weekly_recovery(exclude_ids=started)
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


def _resolve_expired_auctions(at) -> tuple[int, int, str]:
    """Resolve every auction whose deadline has passed as of `at`.

    Called ONCE per tick, unconditionally, OUTSIDE the week-transition
    loop (plan's Design decision 2) — an auction's deadline is wall-clock
    real time, decoupled from week boundaries, so this must not wait for
    one: a hard week with zero transitions must still resolve due
    auctions.

    Supplies resolve_auction's two callbacks, since transfers/ cannot
    import economy/: charge_buyer debits the winner via
    charge_transfer_fee (negative amount), pay_seller credits the seller
    via pay_transfer_income (positive amount) — same transaction, same
    shape sign_free_agent's injected `charge` uses.

    Returns (sold_count, unsold_count, accumulated error text) for the
    TickRun counters, mirroring _release_inactive's (int, str) return
    (TickRun does not exist yet at this point in tick()).
    """
    sold = unsold = 0
    error = ""
    for auction in due_auctions(at):
        try:
            def charge_buyer(team, amount):
                charge_transfer_fee(
                    team, amount=-amount, at=at,
                    description=f"Won auction for {auction.rider.name}",
                )

            def pay_seller(team, amount):
                pay_transfer_income(
                    team, amount=amount, at=at,
                    description=f"Sold {auction.rider.name} at auction",
                )

            result = resolve_auction(
                auction, at=at, charge_buyer=charge_buyer, pay_seller=pay_seller,
            )
            if result.status == Auction.Status.SOLD:
                sold += 1
            elif result.status == Auction.Status.UNSOLD:
                unsold += 1
        except Exception:
            # One bad resolution must not strand the rest of the tick's
            # auctions or the race claim step after it — same per-item
            # guard _release_inactive and _execute already use.
            error += f"resolve auction {auction.pk}:\n{traceback.format_exc()}\n"
    return sold, unsold, error


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
    riders_repriced = 0
    salary_reviews = 0
    for transition in closed:
        riders_aged = advance_ages()
        # Repricing AFTER ageing: next season's wage must reflect the rider a
        # manager will actually have, age included (spec, *Ordering at the
        # boundary*).
        changes = reprice_all()
        riders_repriced += len(changes)
        salary_reviews += write_salary_reviews(transition.season, changes)

    # One offer round per team per crossed season open — ensure_offer_round
    # is idempotent per (team, season) itself (economy/README.md, D8), so a
    # tick that runs twice, or catches up late, cannot double-generate.
    opened = [t for t in transitions if t.kind == SeasonTransition.Kind.OPENED]
    for transition in opened:
        for team in Team.objects.all():
            ensure_offer_round(team, transition.season, at=at)

    weeks = process_week_transitions(at)
    riders_trained = 0
    wage_entries = 0
    merchandise_entries = 0
    fanbase_entries = 0
    sponsorship_entries = 0
    trainer_salary_entries = 0
    teams_released = 0
    agents_expired = 0
    agents_retired = 0
    inactivity_error = ""

    # Built once, outside the loop: a trainer's skill does not move between
    # weeks within one tick (no hires happen mid-tick), so the same salary
    # map is correct for every missed week. The *charge* still happens
    # inside the loop, one dated row per week.
    salary_by_team = {
        trainer.team_id: weekly_salary(trainer)
        for trainer in Trainer.objects.filter(team__isnull=False)
    }
    for transition in weeks:            # per week, NOT weeks=len(weeks)
        week = transition.week
        riders_trained += _apply_training_week(week)
        wage_entries += charge_weekly_wages(week)
        trainer_salary_entries += charge_trainer_salaries(
            week, salary_by_team=salary_by_team,
        )

        # Fanbase reads the week that just COMPLETED, not the one opening:
        # this loop runs before _claim()/_execute(), so `week`'s own races
        # have not been simulated yet (economy/README.md, *Fanbase reads the
        # completed week*). Same reason _apply_training_week uses
        # _completed_week().
        raced_week = _completed_week(week)
        points = points_by_team(raced_week) if raced_week is not None else {}
        fanbase_entries += apply_weekly_fanbase(week, points_by_team=points)
        merchandise_entries += pay_merchandise(week)
        # After fanbase: pay_sponsorship's season-to-date average reads
        # settled weeks only (economy/README.md, D3), so it wants fanbase
        # already current for this week, the same ordering pay_merchandise
        # already relies on.
        sponsorship_entries += pay_sponsorship(week, points_by_team=points)

        # After the economy calls: releasing a team must not change what
        # this week's wages/training/fanbase already charged it for.
        released, error = _release_inactive(week)
        teams_released += released
        inactivity_error += error

        # After the release-inactive call, so `teams_released` and
        # `agents_expired` reflect the same, most-settled world state for
        # this week: a rider pooled by this week's release is never
        # expired the same pass (their unattached_since postdates the
        # boundary). Expiry only touches unattached riders, so it cannot
        # change what this week already charged anyone.
        retired, expired = _expire_free_agents(week)
        agents_retired += retired
        agents_expired += expired

    reclaimed = _reclaim_unfinished()
    claimed = _claim(limit=max(0, max_races - len(reclaimed)), at=at)
    capped = len(reclaimed) + len(claimed) >= max_races

    # After the week loop, before TickRun is created: unconditional, once
    # per tick, on wall-clock deadlines — never inside `for transition in
    # weeks:` above (plan's Design decision 2).
    auctions_sold, auctions_unsold, auction_error = _resolve_expired_auctions(at)

    run = TickRun.objects.create(
        races_started=len(claimed),
        seasons_opened=sum(1 for t in transitions if t.kind == SeasonTransition.Kind.OPENED),
        seasons_closed=sum(1 for t in transitions if t.kind == SeasonTransition.Kind.CLOSED),
        weeks_processed=len(weeks),
        riders_aged=riders_aged,
        riders_trained=riders_trained,
        riders_repriced=riders_repriced,
        salary_reviews=salary_reviews,
        wage_entries=wage_entries,
        merchandise_entries=merchandise_entries,
        fanbase_entries=fanbase_entries,
        sponsorship_entries=sponsorship_entries,
        trainer_salary_entries=trainer_salary_entries,
        teams_released=teams_released,
        agents_expired=agents_expired,
        agents_retired=agents_retired,
        auctions_sold=auctions_sold,
        auctions_unsold=auctions_unsold,
        error=inactivity_error + auction_error,
    )
    _execute(reclaimed + claimed, run, at=at)
    run.capped = capped
    # Real time regardless of which clock is active: this records when the
    # check itself ran on the host, not game time. The one other sanctioned
    # real-time read alongside RealClock.now() itself.
    run.finished_at = timezone.now()
    run.save(update_fields=["races_finished", "capped", "error", "finished_at"])
    return run
