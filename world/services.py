"""The game clock: the one way any code asks what time it is, and the
machinery that finds and processes due work.

See `world/README.md` for the discipline this module enforces: game code
reads `now()`, never `timezone.now()` / `datetime.now()`, when deciding
whether something scheduled is due. `now()` reads whichever `Clock` is
configured (`settings.GAME_CLOCK_CLASS`) — real, live time in production,
a developer-controlled mock clock in dev/test.
"""

from __future__ import annotations

import io
import traceback
from datetime import datetime

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone
from django.utils.module_loading import import_string

from competitions.services import (
    gc_prizes_by_team,
    points_by_team,
    prizes_by_team,
    score_general_classification,
    score_mountains,
    score_race,
    score_sprints,
)
from economy.services import (
    apply_weekly_fanbase,
    charge_development_squad_costs,
    charge_trainer_salaries,
    charge_transfer_fee,
    charge_weekly_wages,
    ensure_offer_round,
    pay_gc_prizes,
    pay_merchandise,
    pay_race_prizes,
    pay_sponsorship,
    pay_transfer_income,
    write_salary_reviews,
)
from economy.solvency import assess_solvency
from racing.models import Race, RaceResult, StageRace
from racing.services import riders_who_raced, riders_who_started, simulate_race
from riders.development_squad import LEVELS, weekly_cost
from riders.models import DevelopmentSquad, Rider
from riders.services import (
    advance_ages,
    apply_weekly_growth,
    apply_weekly_recovery,
    record_week_snapshots,
    reprice_all,
    retire_due_riders,
    retire_riders,
    training_deltas,
)
from riders.free_agent_intake import is_free_agent_intake_week, run_free_agent_intake
from riders.youth_intake import is_intake_week, run_intake
from riders.youth_triage import (
    GRADUATE_WINDOW_WEEKS,
    SPELL_WEEKS,
    graduate,
    release_graduates,
    squad_development_deltas,
)
from schedule.models import Season, SeasonTransition, Week
from schedule.services import (
    current_position,
    process_transitions,
    process_week_transitions,
    weeks_ago_cutoff,
    weeks_opened_between,
)
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
    cancel_open_auctions,
    due_auctions,
    free_agents,
    resolve_auction,
    withdraw_bids,
)

from .ai_management import hire_ai_trainers, set_ai_focuses, sign_ai_sponsors
from .ai_market import list_ai_riders, place_ai_bids, sign_ai_free_agents
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


def _settle_stage_race(stage_race: StageRace, tick: TickRun, at: datetime) -> None:
    """Score and pay the general classification once every stage of
    `stage_race` has run — D11, specs/archive/stage-races.md. Idempotent, and a
    failure here is recorded on the tick, never raised: called from
    `_execute` on both the success and the failure path, so a failed final
    stage still settles the GC over whichever stages actually ran.

    `is_complete()` is re-checked here rather than assumed by the caller —
    a catch-up tick can process several stages of one tour in the same
    `_execute` call, and only the last one actually completes it.
    """
    if not stage_race.is_complete():
        return
    try:
        score_general_classification(stage_race)
        final_stage = stage_race.final_stage()
        tick.prize_entries += pay_gc_prizes(
            final_stage.pk, stage_race_name=stage_race.name, at=at,
            prizes_by_team=gc_prizes_by_team(stage_race),
        )
    except Exception:
        tick.error += f"stage race {stage_race.pk} GC:\n{traceback.format_exc()}\n"


def _execute(race_ids: list[int], tick: TickRun, at: datetime) -> None:
    """Simulate each claimed race outside any lock. One broken course must
    not stop the run: an exception is recorded on that race and on the
    tick, and the loop continues.

    Stages a day apart within the same tour always run in `starts_at`
    order — `_claim` orders by it — so a later stage's carried squad
    (`racing.services.ensure_squads`) always reads an earlier stage's
    already-committed results.
    """
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
        else:
            try:
                score_sprints(race)
            except Exception:
                # The race ran and finish-scored; a sprint-scoring failure
                # must not rewrite that into a failed race. Record it and
                # move on.
                tick.error += f"race {race_id} sprint points:\n{traceback.format_exc()}\n"

            try:
                score_mountains(race)
            except Exception:
                # Same isolation as sprints, and scored after them so the
                # tick reads in the same order as the results screen.
                tick.error += f"race {race_id} mountain points:\n{traceback.format_exc()}\n"

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

        if race.stage_race_id:
            _settle_stage_race(race.stage_race, tick, at)


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


def _graduate_squad_riders(week) -> int:
    """Graduate every squad rider whose spell is complete at this week
    boundary. Returns how many graduated.

    A spell is SPELL_WEEKS long and is dated from `intake_at`, so the cutoff
    comes from `weeks_ago_cutoff` rather than a per-rider count. The
    graduates keep their squad link (`graduated_at` set instead) — they have
    left the squad's places but not its ownership of them, which is what makes
    them listable and what the window step then resolves (#34).

    Returns 0 before SPELL_WEEKS weeks have opened, so nobody graduates early
    in a first season.
    """
    cutoff = weeks_ago_cutoff(week.starts_at, SPELL_WEEKS)
    if cutoff is None:
        return 0
    due = list(
        Rider.objects.filter(
            development_squad__isnull=False, graduated_at__isnull=True,
            intake_at__lte=cutoff,
        ).values_list("pk", flat=True)
    )
    return graduate(due, at=week.starts_at)


def _release_expired_graduates(week) -> int:
    """Release every graduate whose window has closed at this boundary, to
    the free-agent pool stamped `unattached_since`. Returns how many.

    A graduate is left to decide what happens to them for GRADUATE_WINDOW_WEEKS
    after graduating — promote them, list them, or discard them. The window
    closing is what makes that a deadline rather than an open-ended limbo: at
    the boundary, and not before, they go to the market.

    **A listed graduate is skipped.** Their auction decides the outcome — sold
    means the buyer's roster, unsold means the pool — and releasing them here
    would put them in the pool mid-auction and cancel the sale at its
    deadline, which is worse for everyone than letting it finish (#34,
    Design decision 10).
    """
    cutoff = weeks_ago_cutoff(week.starts_at, GRADUATE_WINDOW_WEEKS)
    if cutoff is None:
        return 0
    expired = list(
        # The squad link is what makes a rider a graduate *now*: `graduated_at`
        # is never cleared, so without it every rider who ever graduated —
        # promoted, sold, released — would be a candidate again on every tick.
        Rider.objects.filter(
            development_squad__isnull=False,
            graduated_at__isnull=False, graduated_at__lte=cutoff,
        )
        .exclude(
            pk__in=Auction.objects.filter(status=Auction.Status.OPEN)
            .values_list("rider_id", flat=True)
        )
        .values_list("pk", flat=True)
    )
    return len(release_graduates(expired, at=week.starts_at, record=True))


def _settle_solvency(week, *, salary_by_team, squad_cost_by_team) -> tuple[int, int, str]:
    """Assess every managed team's solvency at this payday, withdraw the live
    bids of a team whose case just opened, and release any team on its
    fourth unmet payday (#27).

    Returns (checks written, teams released, accumulated error text), the same
    shape `_release_inactive` uses: TickRun does not exist yet at this point in
    the week loop. `squad_cost_by_team` is the tick's `{team: (cost, level
    name)}` map; the assessment only wants the cost.
    """
    outcome = assess_solvency(
        week,
        salary_by_team=salary_by_team,
        squad_cost_by_team={pk: cost for pk, (cost, _name) in squad_cost_by_team.items()},
    )
    error = ""
    # Only on opening: the embargo stops new bids, so after the first
    # insolvent payday there are none left to withdraw.
    for team_pk in outcome.opened:
        try:
            withdraw_bids(Team.objects.get(pk=team_pk), at=week.starts_at)
        except Exception:
            error += f"withdraw bids, team {team_pk}:\n{traceback.format_exc()}\n"
    released = 0
    for team_pk in outcome.lost:
        try:
            # release_team returns None for an already-unmanaged team, which
            # keeps this count honest if a concurrent tick got there first.
            if release_team(
                Team.objects.get(pk=team_pk),
                reason=ManagerialSpell.Reason.INSOLVENCY,
                at=week.starts_at,
            ) is not None:
                released += 1
        except Exception:
            error += f"insolvency release, team {team_pk}:\n{traceback.format_exc()}\n"
    return outcome.written, released, error


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
    yet. Squad riders' own development (#34) is folded in here too,
    since they have no roster for a trainer to work on. Freshness
    recovery follows the same shape: it runs once per week, excluding
    riders who started a race in the week being settled
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

    # Squad riders develop on top of whatever else they earned this week
    # (#34): they are not on a roster, so no trainer's loop above touched
    # them, and their extra growth is what a player's spell is paying for.
    # Merged per attribute rather than assigned, so a squad rider who ever
    # does pick up another source of extra growth keeps both.
    for rider in Rider.objects.active().filter(
        development_squad__isnull=False, graduated_at__isnull=True,
    ):
        squad_growth = squad_development_deltas(rider)
        merged = extra.setdefault(rider.pk, {})
        for attribute, gain in squad_growth.items():
            merged[attribute] = merged.get(attribute, 0) + gain

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


def _declare_next_season_if_needed(at: datetime) -> tuple[int, str]:
    """Declare the world calendar as the next season when at most one
    declared season has not yet ended at `at` (#129; world/README.md,
    *Automatic seasons*). Returns `(seasons declared, error)`.

    Only with `settings.AUTO_DECLARE_SEASONS` (production and staging), and
    only in a world that has a season at all — a fresh development database
    is left alone. At most one season per tick: the rule fires as soon as
    the last declared season is the one being played, a full season ahead.
    Guarded like the AI market: a broken calendar file must not stop races.
    """
    from . import world_setup  # it imports this module inside its functions

    if not settings.AUTO_DECLARE_SEASONS or not Season.objects.exists():
        return 0, ""
    if Season.objects.filter(ends_at__gt=at).count() > 1:
        return 0, ""
    try:
        with transaction.atomic():
            world_setup.add_season(calendar=world_setup.WORLD_CALENDAR, stdout=io.StringIO())
    except Exception:
        return 0, f"automatic season:\n{traceback.format_exc()}\n"
    return 1, ""


def tick() -> TickRun:
    """Find and process whatever is due, exactly once. The only entry point
    cron — or a developer, after moving the mock clock with `mock_clock` —
    ever calls."""
    max_races = GameClock.load().catch_up_max_races
    at = now()

    # Before transitions: after an outage that ran past the last declared
    # season's end, the next season must already exist when the close is
    # recorded, so its opening is recorded in this same tick.
    seasons_declared, season_error = _declare_next_season_if_needed(at)

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
    riders_retired = 0
    riders_repriced = 0
    salary_reviews = 0
    for transition in closed:
        # The stamp is the closing season's FINAL WEEK's starts_at, not the
        # season's ends_at: api's retired_payload resolves it through
        # current_position(), whose ranges are half-open, so ends_at would
        # resolve to the *next* season's week 1 when seasons abut (#42).
        final_week = transition.season.weeks.order_by("-starts_at").first()
        with transaction.atomic():
            retired_ids = retire_due_riders(at=final_week.starts_at)
            cancel_open_auctions(retired_ids, at=at)
        riders_retired += len(retired_ids)
        # Retiring BEFORE ageing is load-bearing: the other order would age a
        # rider into the window and retire them in the same breath, without the
        # season of warning the marker promises. It also keeps retirees out of
        # the salary review for free, and freezes their age at the one the
        # player last saw.
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
    #
    # Unmanaged teams sign straight after, so week 1 already pays them
    # (#45). Guarded like the AI market: a failed AI signing is not worth
    # losing the tick for.
    opened = [t for t in transitions if t.kind == SeasonTransition.Kind.OPENED]
    ai_sponsors_signed = 0
    ai_trainers_hired = 0
    ai_management_error = ""
    for transition in opened:
        for team in Team.objects.all():
            ensure_offer_round(team, transition.season, at=at)
        try:
            signed, error = sign_ai_sponsors(transition.season, at)
            ai_sponsors_signed += signed
            ai_management_error += error
        except Exception:
            ai_management_error += f"ai sponsors at season open:\n{traceback.format_exc()}\n"

    weeks = process_week_transitions(at)
    riders_trained = 0
    wage_entries = 0
    merchandise_entries = 0
    fanbase_entries = 0
    sponsorship_entries = 0
    trainer_salary_entries = 0
    development_squad_entries = 0
    youth_intake_riders = 0
    youth_intake_turned_away = 0
    youth_graduated = 0
    youth_graduates_released = 0
    teams_released = 0
    solvency_checks = 0
    teams_lost_to_insolvency = 0
    solvency_error = ""
    agents_expired = 0
    agents_retired = 0
    free_agents_generated = 0
    inactivity_error = ""

    # Built once, outside the loop: a trainer's skill does not move between
    # weeks within one tick (no hires happen mid-tick — the AI hires after
    # the loop, see below, for exactly this reason), so the same salary
    # map is correct for every missed week. The *charge* still happens
    # inside the loop, one dated row per week.
    salary_by_team = {
        trainer.team_id: weekly_salary(trainer)
        for trainer in Trainer.objects.filter(team__isnull=False)
    }
    # Same reasoning, and the same shape: a squad's level does not move
    # between the weeks one tick crosses (no player action happens mid-tick),
    # so one map serves every week, and economy/ takes the cost and the level
    # name from here rather than looking up LEVELS itself — it may not import
    # riders/ for the price, only for nothing. Deliberately every open squad,
    # managed or not: an unmanaged team still runs the squad it was given, and
    # its cost is real, the same way its riders still draw wages.
    squad_cost_by_team = {
        squad.team_id: (weekly_cost(squad.level), LEVELS[squad.level].name)
        for squad in DevelopmentSquad.objects.all()
    }
    for transition in weeks:            # per week, NOT weeks=len(weeks)
        week = transition.week
        # Before training: the focus set here is the one this week trains
        # on. After it, every week would train on last week's choice.
        try:
            set_ai_focuses(week)
        except Exception:
            ai_management_error += f"ai focus for week {week.pk}:\n{traceback.format_exc()}\n"
        riders_trained += _apply_training_week(week)
        wage_entries += charge_weekly_wages(week)
        trainer_salary_entries += charge_trainer_salaries(
            week, salary_by_team=salary_by_team,
        )
        development_squad_entries += charge_development_squad_costs(
            week, cost_by_team=squad_cost_by_team,
        )

        # After the week's growth, training and charges: a rider arriving
        # this week first grows at NEXT week's boundary (#33's plan, Design
        # decision 8), and this is what run_intake's idempotency check
        # compares against — dated to week.starts_at, not now(), so a late
        # tick's batch is still found on a second pass.
        #
        # Graduation and release run before intake, and the order is
        # load-bearing (#34): a rider leaving the squad and a batch arriving
        # at the same boundary must not collide on the last place. Graduation
        # after growth gives a spell rider exactly SPELL_WEEKS weeks of squad
        # development; the window's release is before intake for the same
        # reason.
        youth_graduated += _graduate_squad_riders(week)
        youth_graduates_released += _release_expired_graduates(week)
        if is_intake_week(week.number):
            intake = run_intake(at=week.starts_at)
            youth_intake_riders += intake.created
            youth_intake_turned_away += intake.turned_away

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

        # After the week's money has moved, and before inactivity: a team due
        # for both is lost to insolvency, the more specific cause.
        checked, lost, error = _settle_solvency(
            week, salary_by_team=salary_by_team, squad_cost_by_team=squad_cost_by_team,
        )
        solvency_checks += checked
        teams_lost_to_insolvency += lost
        solvency_error += error

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

        # After expiry, so a pass never weighs a batch that has only just
        # arrived against the pool it joins: the newcomers are stamped with
        # this boundary and start their EXPIRY_WEEKS from it (#157).
        if is_free_agent_intake_week(week.number):
            free_agents_generated += len(run_free_agent_intake(at=week.starts_at))

    # The AI's hires after the week loop, so salary_by_team stayed true for
    # every week above and a new trainer's first salary is charged at the
    # next boundary. Retried at every boundary, so a team that could not
    # afford one, or found the pool empty, picks one up when it can. A team
    # with no sponsor this season (a manager released mid-season) signs here.
    if weeks:
        try:
            hired, error = hire_ai_trainers(at)
            ai_trainers_hired += hired
            ai_management_error += error
            position = current_position(at)
            if position.state == "in_season":
                signed, error = sign_ai_sponsors(position.season, at)
                ai_sponsors_signed += signed
                ai_management_error += error
        except Exception:
            ai_management_error += f"ai management:\n{traceback.format_exc()}\n"

    reclaimed = _reclaim_unfinished()
    claimed = _claim(limit=max(0, max_races - len(reclaimed)), at=at)
    capped = len(reclaimed) + len(claimed) >= max_races

    # After the week loop, before TickRun is created: unconditional, once
    # per tick, on wall-clock deadlines — never inside `for transition in
    # weeks:` above (plan's Design decision 2).
    auctions_sold, auctions_unsold, auction_error = _resolve_expired_auctions(at)

    # The AI market, after resolution, so the AI never sees an auction this
    # same tick is about to close (Design decision 12). Listing first, and
    # only on a tick that crossed a week, using the LAST week crossed — a
    # tick catching up three weeks lists once, not three times. Bidding runs
    # every tick, because auction deadlines are wall-clock, not week-bound.
    #
    # The guard is wider than the per-auction and per-team ones inside
    # ai_market: building the buyer table reads every unmanaged team's ledger,
    # and a failure there would otherwise take the whole tick down with it.
    # An AI market that cannot run this tick is not worth losing the tick for.
    ai_listings_created = 0
    ai_bids_placed = 0
    ai_free_agents_signed = 0
    ai_market_error = ""
    try:
        if weeks:
            # Signing before listing: a team a signing brings back above
            # AI_MIN_ROSTER can list this same pass (#157).
            ai_free_agents_signed, ai_market_error = sign_ai_free_agents(weeks[-1].week, at)
            ai_listings_created, listing_error = list_ai_riders(weeks[-1].week, at)
            ai_market_error += listing_error
        ai_bids_placed, bid_error = place_ai_bids(at)
        ai_market_error += bid_error
    except Exception:
        ai_market_error += f"ai market:\n{traceback.format_exc()}\n"

    run = TickRun.objects.create(
        races_started=len(claimed),
        seasons_declared=seasons_declared,
        seasons_opened=sum(1 for t in transitions if t.kind == SeasonTransition.Kind.OPENED),
        seasons_closed=sum(1 for t in transitions if t.kind == SeasonTransition.Kind.CLOSED),
        weeks_processed=len(weeks),
        riders_aged=riders_aged,
        riders_retired=riders_retired,
        riders_trained=riders_trained,
        riders_repriced=riders_repriced,
        salary_reviews=salary_reviews,
        wage_entries=wage_entries,
        merchandise_entries=merchandise_entries,
        fanbase_entries=fanbase_entries,
        sponsorship_entries=sponsorship_entries,
        trainer_salary_entries=trainer_salary_entries,
        development_squad_entries=development_squad_entries,
        youth_intake_riders=youth_intake_riders,
        youth_intake_turned_away=youth_intake_turned_away,
        youth_graduated=youth_graduated,
        youth_graduates_released=youth_graduates_released,
        teams_released=teams_released,
        solvency_checks=solvency_checks,
        teams_lost_to_insolvency=teams_lost_to_insolvency,
        agents_expired=agents_expired,
        agents_retired=agents_retired,
        auctions_sold=auctions_sold,
        auctions_unsold=auctions_unsold,
        ai_bids_placed=ai_bids_placed,
        ai_listings_created=ai_listings_created,
        ai_trainers_hired=ai_trainers_hired,
        ai_free_agents_signed=ai_free_agents_signed,
        free_agents_generated=free_agents_generated,
        ai_sponsors_signed=ai_sponsors_signed,
        error=(
            season_error + inactivity_error + solvency_error + auction_error + ai_market_error
            + ai_management_error
        ),
    )
    _execute(reclaimed + claimed, run, at=at)
    run.capped = capped
    # Real time regardless of which clock is active: this records when the
    # check itself ran on the host, not game time. The one other sanctioned
    # real-time read alongside RealClock.now() itself.
    run.finished_at = timezone.now()
    run.save(update_fields=["races_finished", "capped", "error", "finished_at"])
    return run
