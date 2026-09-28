from __future__ import annotations

import random

from django.db import IntegrityError, transaction
from django.db.models import Count, QuerySet, Sum
from django.db.models.functions import Coalesce
from teams.models import Team

from .models import (
    FANBASE_PER_POINT,
    MERCHANDISE_FANBASE_PER_CREDIT,
    MINIMUM_FANBASE,
    SPONSOR_FANBASE_PER_CREDIT,
    STARTING_BALANCE,
    STARTING_FANBASE,
    WEEKLY_FANBASE_DECAY,
    FanbaseEntry,
    LedgerEntry,
    SalaryReviewReport,
    SponsorContract,
    SponsorOffer,
)
from .sponsors import PROFILES, payment_for as _payment_for
from .sponsors import offer_terms as _offer_terms

#: Sponsor company names, rolled at offer generation. Flavour only, matching
#: staff.generation's _roll_name — not a game system in itself.
_SPONSOR_NAMES = (
    "Velocore", "Ridgeline Bikes", "Pinnacle Sports", "Northwind Gear",
    "Solaris Nutrition", "Ironclad Components", "Meridian Finance",
    "Apex Hydration", "Cobblestone Coffee", "Skyline Insurance",
)


def balance_for(team) -> int:
    """A team's balance: the sum of its ledger entries. The balance is
    derived, never stored — see economy/README.md, *The ledger is
    append-only*."""
    return (
        LedgerEntry.objects.filter(team=team).aggregate(total=Sum("amount"))["total"] or 0
    )


def entries_for(team) -> QuerySet[LedgerEntry]:
    """A team's ledger entries, newest first (the model default)."""
    return LedgerEntry.objects.filter(team=team)


def fanbase_for(team) -> int:
    """A team's fanbase: the sum of its FanbaseEntry deltas. Derived,
    never stored — same discipline as balance_for."""
    return (
        FanbaseEntry.objects.filter(team=team).aggregate(total=Sum("delta"))["total"] or 0
    )


def fanbase_entries_for(team) -> QuerySet[FanbaseEntry]:
    """A team's fanbase history, newest first (the model default)."""
    return FanbaseEntry.objects.filter(team=team)


def ensure_starting_fanbase(team, *, at) -> FanbaseEntry:
    """Give `team` its starting fanbase, once.

    Idempotent (`get_or_create` on `kind=STARTING`), so a second call —
    re-running `seed_teams`, a reclaimed team — never double-credits a team.
    Mirror of `ensure_opening_balance`; `at` is game time, passed by the
    caller (economy/ may not import world/, AGENTS.md).
    """
    entry, _ = FanbaseEntry.objects.get_or_create(
        team=team,
        kind=FanbaseEntry.Kind.STARTING,
        defaults={
            "delta": STARTING_FANBASE,
            "occurred_at": at,
            "description": "Starting fanbase",
        },
    )
    return entry


def reset_fanbase(team, *, at) -> FanbaseEntry | None:
    """Bring `team`'s fanbase back to STARTING_FANBASE with a `takeover`
    row. Returns None when it already is STARTING_FANBASE.

    `at` is game time, the moment the takeover completes — the caller
    passes `world.services.now()` itself. See `reset_to_starting_balance`."""
    delta = STARTING_FANBASE - fanbase_for(team)
    if delta == 0:
        return None
    return FanbaseEntry.objects.create(
        team=team,
        kind=FanbaseEntry.Kind.TAKEOVER,
        delta=delta,
        occurred_at=at,
        description="Team taken over",
    )


def ensure_opening_balance(team, *, at) -> LedgerEntry:
    """Give `team` its starting balance, once.

    Idempotent (`get_or_create` on `kind=STARTING_BALANCE`), so a second
    call — re-running `seed_teams`, a reclaimed team — never double-credits
    a team.

    `at` is game time, the moment the balance is granted — the caller
    (world/, api/, or `teams/`'s seed command) passes `world.services.now()`
    itself. economy/ may not import world/ (AGENTS.md).
    """
    entry, _ = LedgerEntry.objects.get_or_create(
        team=team,
        kind=LedgerEntry.Kind.STARTING_BALANCE,
        defaults={
            "amount": STARTING_BALANCE,
            "occurred_at": at,
            "description": "Starting balance",
        },
    )
    return entry


def reset_to_starting_balance(team, *, at) -> LedgerEntry | None:
    """Bring `team`'s balance back to STARTING_BALANCE with a `takeover`
    entry — the append-only ledger's own idiom for a correction (economy/
    README.md, *The ledger is append-only*). Returns None when the balance
    already is STARTING_BALANCE, so a team claimed at exactly the starting
    amount does not get a meaningless zero-credit row.

    `at` is game time, the moment the takeover completes — the caller
    passes `world.services.now()` itself. See `ensure_opening_balance`."""
    delta = STARTING_BALANCE - balance_for(team)
    if delta == 0:
        return None
    return LedgerEntry.objects.create(
        team=team,
        kind=LedgerEntry.Kind.TAKEOVER,
        amount=delta,
        occurred_at=at,
        description="Team taken over",
    )


def payroll_for(team) -> int:
    """This team's current weekly wage bill: the sum of its riders' actual
    salaries, never a flat per-head rate (#25). 0 for an empty roster, not
    None — same Coalesce reasoning as charge_weekly_wages, below."""
    return (
        Team.objects.filter(pk=team.pk)
        .annotate(payroll=Coalesce(Sum("riders__weekly_salary"), 0))
        .values_list("payroll", flat=True)
        .get()
    )


def charge_weekly_wages(week) -> int:
    """Debit every team one combined wage entry for `week`. Returns how
    many entries were written.

    Called once per crossed week boundary from world.services.tick(),
    inside the loop over WeekTransition rows. Exactly-once comes from that
    WeekTransition row (unique on `week`, written before this runs); the
    (team, week) constraint below is a second line of defence.

    The charge is the sum of each team's riders' actual weekly_salary, not
    WEEKLY_WAGE_PER_RIDER times a head count (#25) — that constant now only
    anchors the calibration in riders.pricing. Sum() returns None for a
    team with no riders; Coalesce(..., 0) is what keeps that team's entry a
    real zero rather than a crash.

    One atomic() per create, never one around the loop: an IntegrityError
    poisons the enclosing transaction in Django. Same shape as
    schedule.services.process_transitions and staff's
    _write_training_reports, for the same reason.
    """
    totals = Team.objects.annotate(
        n=Count("riders"),
        payroll=Coalesce(Sum("riders__weekly_salary"), 0),
    ).values_list("pk", "n", "payroll")
    written = 0
    for team_id, rider_count, payroll in totals:
        with transaction.atomic():
            try:
                LedgerEntry.objects.create(
                    team_id=team_id,
                    kind=LedgerEntry.Kind.WAGES,
                    amount=-payroll,
                    occurred_at=week.starts_at,
                    week=week,
                    rider_count=rider_count,
                    description="Weekly wages",
                )
                written += 1
            except IntegrityError:
                continue          # already charged; correct outcome, not an error
    return written


def pay_race_prizes(race_id: int, *, race_name: str, at,
                    prizes_by_team: dict[int, list[tuple[int, int]]]) -> int:
    """Credit every team its prize money for one race. Returns rows written.

    Takes the race as an id plus the amounts already computed by
    competitions.services.prizes_by_team — economy/ may not import
    racing/ or competitions/ (AGENTS.md), so it never reads a RaceResult
    itself. The identical shape apply_weekly_fanbase takes points_by_team.

    Idempotent through the (team, race, position) constraint, not an
    early return: a partial payout (interrupted mid-loop) must be
    completable on retry, unlike score_race's early return which only
    ever needs to check for the presence of one row per team.
    """
    written = 0
    description = f"Prize money — {race_name}"[:120]
    for team_id, placements in prizes_by_team.items():
        for position, amount in placements:
            with transaction.atomic():
                try:
                    LedgerEntry.objects.create(
                        team_id=team_id,
                        kind=LedgerEntry.Kind.PRIZE_MONEY,
                        amount=amount,
                        occurred_at=at,
                        race_id=race_id,
                        position=position,
                        description=description,
                    )
                    written += 1
                except IntegrityError:
                    continue      # already paid; correct outcome, not an error
    return written


def apply_weekly_fanbase(week, *, points_by_team: dict[int, int]) -> int:
    """Adjust every team's fanbase for `week`. Returns rows written.

    The week each team is scored against is the caller's job: this function
    takes the points as a plain dict — economy/ may not import competitions/
    (AGENTS.md). `world/services.py` passes the week that just completed,
    never the one opening (D2) — see economy/README.md, *Fanbase reads the
    completed week*.

    The delta is clamped so the resulting fanbase never falls below
    MINIMUM_FANBASE, and the *clamped* delta is what is stored (D4): the
    sum of rows is the fanbase, so clamping on read would make history and
    displayed value disagree. Called once per crossed week boundary from
    world.services.tick(); exactly-once comes from that WeekTransition row,
    the (team, week) constraint below being a second line of defence.
    """
    current = dict(
        FanbaseEntry.objects.values("team_id").annotate(total=Sum("delta"))
        .values_list("team_id", "total")
    )
    written = 0
    for team_id in Team.objects.values_list("pk", flat=True):
        points = points_by_team.get(team_id, 0)
        now_at = current.get(team_id) or 0
        raw = points * FANBASE_PER_POINT - WEEKLY_FANBASE_DECAY
        # Clamp the RESULT, store the delta that gets there (D4).
        delta = max(now_at + raw, MINIMUM_FANBASE) - now_at
        with transaction.atomic():
            try:
                FanbaseEntry.objects.create(
                    team_id=team_id,
                    kind=FanbaseEntry.Kind.WEEKLY,
                    delta=delta,
                    occurred_at=week.starts_at,
                    week=week,
                    points=points,
                    description="Weekly fanbase change",
                )
                written += 1
            except IntegrityError:
                continue          # already applied; correct outcome, not an error
    return written


def pay_merchandise(week) -> int:
    """Credit every team its merchandise income for `week`, computed off its
    current fanbase. Returns entries written.

    Called from world.services.tick() right after apply_weekly_fanbase —
    merchandise is paid on the *now-updated* fanbase (D7). It recomputes each
    team's fanbase from the rows rather than accepting a number, so the two
    functions stay independently testable and a re-run cannot pay on a stale
    figure. Once per week, same exactly-once shape as charge_weekly_wages.
    """
    current = dict(
        FanbaseEntry.objects.values("team_id").annotate(total=Sum("delta"))
        .values_list("team_id", "total")
    )
    written = 0
    for team_id in Team.objects.values_list("pk", flat=True):
        fanbase = max(current.get(team_id) or 0, 0)
        amount = fanbase // MERCHANDISE_FANBASE_PER_CREDIT
        with transaction.atomic():
            try:
                LedgerEntry.objects.create(
                    team_id=team_id,
                    kind=LedgerEntry.Kind.MERCHANDISE,
                    amount=amount,
                    occurred_at=week.starts_at,
                    week=week,
                    description="Merchandise revenue",
                )
                written += 1
            except IntegrityError:
                continue          # already paid; correct outcome, not an error
    return written


class SponsorshipError(Exception):
    """Base class for a sponsorship change that cannot proceed."""


class OfferNotAvailable(SponsorshipError):
    """That offer is not this team's, or no longer exists."""


class AlreadySponsored(SponsorshipError):
    """The team already has an active contract for that season."""


def offers_for(team, season) -> QuerySet[SponsorOffer]:
    """This team's unsigned offers for `season`, ordered by profile
    (the model default, `pk` order — a round is always generated together,
    so pk order matches generation order, one per PROFILES entry)."""
    return SponsorOffer.objects.filter(team=team, season=season)


def active_contract(team, season) -> SponsorContract | None:
    """The team's non-voided contract for `season`, or None."""
    return SponsorContract.objects.filter(
        team=team, season=season, voided_at__isnull=True,
    ).first()


def ensure_offer_round(team, season, *, at, rng=None) -> list[SponsorOffer]:
    """Generate one offer per profile for (team, season), once.

    No-ops and returns [] if the team already has offers for that season or
    an active contract — the idempotence that lets this be called from both
    world/'s season-open loop and the API's lazy-generation path without
    ever duplicating a round. `at` is game time from the caller — economy/
    may not import world/ (AGENTS.md), same as ensure_opening_balance.

    Sized off fanbase_for(team) at THIS moment (economy/README.md, *Rules
    and edge cases*: fanbase moving later does not reprice an existing
    round). `rng` is injectable for deterministic tests, matching
    staff.services.top_up_pool's rng parameter.
    """
    if offers_for(team, season).exists() or active_contract(team, season) is not None:
        return []

    rng = rng or random.Random()
    fanbase = fanbase_for(team)
    names = rng.sample(_SPONSOR_NAMES, k=len(PROFILES))
    offers = [
        SponsorOffer(
            team=team,
            season=season,
            profile=profile.key,
            sponsor_name=name,
            **_offer_terms(profile, fanbase, fanbase_per_credit=SPONSOR_FANBASE_PER_CREDIT),
        )
        for profile, name in zip(PROFILES, names)
    ]
    return SponsorOffer.objects.bulk_create(offers)


def sign_offer(team, offer_id: int, *, at) -> SponsorContract:
    """Sign one of this team's offers into an active contract.

    Copies the offer's terms onto the contract rather than pointing at them
    (economy/README.md, D2) — the rest of the round is deleted once one
    offer is signed, so a contract that read its terms through `offer`
    would go blind the moment its round is regenerated elsewhere.

    Locks the offer row WITHOUT skip_locked, re-checking ownership and
    availability AFTER the lock — same shape and reason as
    staff.services.hire_trainer: the loser of a concurrent double-sign
    arrives here and is told, rather than silently overwriting the winner.
    The partial unique constraint on SponsorContract is the second line of
    defence.
    """
    with transaction.atomic():
        try:
            offer = SponsorOffer.objects.select_for_update().get(pk=offer_id)
        except SponsorOffer.DoesNotExist:
            raise OfferNotAvailable("That offer is no longer available.")
        if offer.team_id != team.pk:
            raise OfferNotAvailable("That offer is not yours.")
        if active_contract(team, offer.season) is not None:
            raise AlreadySponsored("Your team already has a sponsor this season.")

        contract = SponsorContract.objects.create(
            team=team,
            season=offer.season,
            offer=offer,
            profile=offer.profile,
            sponsor_name=offer.sponsor_name,
            weekly_base=offer.weekly_base,
            floor_amount=offer.floor_amount,
            ceiling_amount=offer.ceiling_amount,
            sensitivity=offer.sensitivity,
            signed_at=at,
        )
        # The signed offer is kept (the contract FKs it for provenance);
        # the rest of the round goes, so the screen has nothing stale left
        # to render.
        SponsorOffer.objects.filter(team=team, season=offer.season).exclude(pk=offer.pk).delete()
    return contract


def void_sponsorship(team, *, at) -> None:
    """End whatever sponsorship situation `team` is in: mark any active
    contract voided (never delete it — it is financial history, economy/
    README.md, D7) and clear unsigned offers, for every season.

    Called from teams.services.claim_team, which imports this function
    inside its own body — teams/ must not import economy/ at module scope
    (AGENTS.md). Does not generate a new round: claim_team has no Season to
    hand it, and teams/ may not import schedule/ either. The API generates
    the fresh round lazily on next read (SponsorsView), the same way a
    freshly claimed team's offers appear on first visit even before any
    season exists.
    """
    SponsorContract.objects.filter(team=team, voided_at__isnull=True).update(voided_at=at)
    SponsorOffer.objects.filter(team=team).delete()


def _season_average_points(team_id, season, current_week) -> float | None:
    """Mean race points per already-settled week this season, for the team
    with `team_id`. Read from the team's own FanbaseEntry rows rather than
    RacePoints — economy/ may not import competitions/ (AGENTS.md), and
    FanbaseEntry already stores `points` per week (economy/README.md).

    Returns None when no prior week has settled this season, which
    payment_for treats as "pay weekly_base" (D3).
    """
    values = list(
        FanbaseEntry.objects.filter(
            team_id=team_id, kind=FanbaseEntry.Kind.WEEKLY,
            week__season=season, week__number__lt=current_week.number,
        ).values_list("points", flat=True)
    )
    return (sum(values) / len(values)) if values else None


def pay_sponsorship(week, *, points_by_team: dict[int, int]) -> int:
    """Credit each team with an active contract its sponsorship for `week`.
    Returns entries written.

    A team with no active contract gets NO row — unlike wages, this is not
    a zero-amount entry (economy/README.md, spec: "not a zero-amount row").
    Called from world.services.tick() inside the per-week loop, after
    apply_weekly_fanbase — _season_average_points reads FanbaseEntry rows
    for weeks before this one, so it wants fanbase already settled for the
    week being paid. `points_by_team` is the same dict world/ already built
    for apply_weekly_fanbase (economy/ may not import competitions/).

    Per-row atomic() with IntegrityError caught and skipped, same shape as
    charge_weekly_wages and for the same reason.
    """
    written = 0
    contracts = (
        SponsorContract.objects.filter(season=week.season, voided_at__isnull=True)
        .select_related("team")
    )
    for contract in contracts:
        points = points_by_team.get(contract.team_id, 0)
        average = _season_average_points(contract.team_id, week.season, week)
        amount = _payment_for(
            weekly_base=contract.weekly_base,
            floor_amount=contract.floor_amount,
            ceiling_amount=contract.ceiling_amount,
            sensitivity=contract.sensitivity,
            points=points,
            average_points=average,
        )
        with transaction.atomic():
            try:
                LedgerEntry.objects.create(
                    team_id=contract.team_id,
                    kind=LedgerEntry.Kind.SPONSORSHIP,
                    amount=amount,
                    occurred_at=week.starts_at,
                    week=week,
                    description=f"Sponsorship — {contract.sponsor_name}",
                )
                written += 1
            except IntegrityError:
                continue          # already paid; correct outcome, not an error
    return written


def charge_trainer_salaries(week, *, salary_by_team: dict[int, int]) -> int:
    """Debit every team with a trainer its trainer's weekly salary for
    `week`. Returns entries written.

    `salary_by_team` maps team pk to that team's trainer's weekly salary —
    world/ (which may import staff/ and economy/) builds it; economy/
    derives nothing from staff/ (AGENTS.md). Same exactly-once shape as
    charge_weekly_wages: one atomic() per create so an IntegrityError on an
    already-charged team cannot poison the loop.
    """
    written = 0
    for team_id, salary in salary_by_team.items():
        with transaction.atomic():
            try:
                LedgerEntry.objects.create(
                    team_id=team_id,
                    kind=LedgerEntry.Kind.TRAINER_SALARY,
                    amount=-salary,
                    occurred_at=week.starts_at,
                    week=week,
                    description="Trainer salary",
                )
                written += 1
            except IntegrityError:
                continue          # already charged; correct outcome, not an error
    return written


def charge_trainer_fee(team, *, amount: int, at, description: str) -> LedgerEntry:
    """Debit `team` the one-off fee for hiring a trainer. Returns the row.

    `amount` is negative (debits only), `at` is game time, `description`
    names the trainer. The caller — api/StaffView, or the day an AI team
    hires (world/) — passes both itself, per the custom-`at` convention used
    across this module. No IntegrityError handling here: unlike the weekly
    charges the fee has no (team, week) constraint (that one-salary rule is
    W2's by design — a team may pay several fees over a season).
    """
    return LedgerEntry.objects.create(
        team=team,
        kind=LedgerEntry.Kind.TRAINER_FEE,
        amount=amount,
        occurred_at=at,
        description=description,
    )


def charge_transfer_fee(team, *, amount: int, at, description: str) -> LedgerEntry:
    """Debit `team` a one-off free-agent transfer amount. Returns the row.

    One kind covers both sides of the market: a signing fee and a severance
    charge are the same shape of transaction (money out, no week attached),
    distinguished by `description` ("Signed X" vs "Released X") — there is
    deliberately no second Kind (Design decision 7).
    `amount` is negative, `at` is game time, `description` names the rider.
    The caller — api/'s free-agent views — passes both itself, per the
    custom-`at` convention used across this module. No (team, week)
    constraint: a team may sign and release several times a season.
    """
    return LedgerEntry.objects.create(
        team=team,
        kind=LedgerEntry.Kind.TRANSFER_FEE,
        amount=amount,
        occurred_at=at,
        description=description,
    )


def charge_development_squad_costs(week, *, cost_by_team: dict[int, tuple[int, str]]) -> int:
    """Debit every team in `cost_by_team` its development squad's weekly cost
    for `week`. Returns entries written.

    `cost_by_team` maps team pk to `(weekly_cost, level_name)` — the name as
    well as the figure because it goes straight into the row's
    `description` ("Development squad — National"), and a team is never
    charged for a level it is not at. world/ (which may import both riders/ and
    economy/) builds the map from open squads; economy/ never looks up
    `riders.development_squad.LEVELS` itself, exactly as it takes a trainer's
    salary from world/ rather than reading staff/ (AGENTS.md).

    Same exactly-once shape as charge_trainer_salaries: one atomic() per
    create so an IntegrityError on an already-charged team cannot poison the
    loop. A team absent from the map gets no row — that is how a team with no
    open squad is expressed.
    """
    written = 0
    for team_id, (cost, level_name) in cost_by_team.items():
        with transaction.atomic():
            try:
                LedgerEntry.objects.create(
                    team_id=team_id,
                    kind=LedgerEntry.Kind.DEVELOPMENT_SQUAD,
                    amount=-cost,
                    occurred_at=week.starts_at,
                    week=week,
                    description=f"Development squad — {level_name}",
                )
                written += 1
            except IntegrityError:
                continue          # already charged; correct outcome, not an error
    return written


def charge_development_squad_fee(team, *, amount: int, at, description: str) -> LedgerEntry:
    """Debit `team` the one-off fee for opening, upgrading or reopening its
    development squad. Returns the row.

    `amount` is negative, `at` is game time, `description` names the level
    and the move. The caller — api/'s squad views, via the `charge` callback
    riders.development_squad.open_squad and change_level take — passes both
    itself, per the custom-`at` convention used across this module. The caller
    also runs this inside its own transaction, so an InsufficientFunds raised
    after this call rolls the fee row back with the squad write it precedes
    (riders/README.md, *Development squad*).

    No IntegrityError handling and no (team, week) constraint, unlike
    charge_development_squad_costs: a team may pay several fees in one week —
    an upgrade on Monday, a close and reopen on Tuesday — and each is its own
    row, which is the point of the append-only ledger.
    """
    return LedgerEntry.objects.create(
        team=team,
        kind=LedgerEntry.Kind.DEVELOPMENT_SQUAD_FEE,
        amount=amount,
        occurred_at=at,
        description=description,
    )


def pay_transfer_income(team, *, amount: int, at, description: str) -> LedgerEntry:
    """Credit `team` income from a transfer-market sale. Returns the row.

    Same Kind as charge_transfer_fee (TRANSFER_FEE) — a sale is still
    "money moved for a transfer reason," told apart by description and
    sign, not a fourth Kind (Design decision 4). `amount` is POSITIVE
    here, the mirror image of charge_transfer_fee's negative-only
    contract — a separate function so that contract is never silently
    violated by a caller passing a positive amount into
    charge_transfer_fee instead.
    """
    return LedgerEntry.objects.create(
        team=team,
        kind=LedgerEntry.Kind.TRANSFER_FEE,
        amount=amount,
        occurred_at=at,
        description=description,
    )


def write_salary_reviews(season, changes: list[dict]) -> int:
    """One SalaryReviewReport per managed team for a closed season.

    `changes` is riders.services.reprice_all()'s return, already filtered
    by threshold. Each insert runs inside its own transaction.atomic()
    with IntegrityError caught — the same per-row shape
    process_transitions() uses, and for the same reason: an
    IntegrityError poisons an enclosing transaction (plan D6).

    A managed team with no qualifying changes still gets a report, with an
    empty `changes` list and payroll_before == payroll_after. Returns how
    many rows were written.

    `payroll_before` is derived, not captured: `payroll_after` minus the
    net of the listed changes. That is exact only because sub-threshold
    changes are excluded from `changes` but included in `payroll_after` —
    a deliberate imprecision, "what the bill was counting only the
    movements we are showing you", instead of a second per-team query for
    a number that differs by at most a rounding step per rider (plan D7).
    """
    by_team: dict[int, list[dict]] = {}
    for change in changes:
        if change["team_id"] is None:      # free agent: repriced, not reported
            continue
        by_team.setdefault(change["team_id"], []).append(change)

    written = 0
    for team in Team.objects.filter(manager__isnull=False):
        team_changes = by_team.get(team.pk, [])
        after = payroll_for(team)
        before = after - sum(c["to"] - c["from"] for c in team_changes)
        with transaction.atomic():
            try:
                SalaryReviewReport.objects.create(
                    team=team, season=season,
                    changes=[
                        {k: v for k, v in c.items() if k != "team_id"}
                        for c in team_changes
                    ],
                    payroll_before=before, payroll_after=after,
                )
                written += 1
            except IntegrityError:
                pass            # already written; correct outcome, not an error
    return written


def latest_salary_review(team) -> SalaryReviewReport | None:
    """This team's most recent salary review, newest season first, or None.

    Mirrors staff.services.latest_report(team) for TrainingWeekReport.
    """
    return (
        SalaryReviewReport.objects.filter(team=team)
        .order_by("-season__starts_at")
        .first()
    )
