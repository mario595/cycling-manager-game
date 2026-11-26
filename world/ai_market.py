"""How unmanaged teams behave in the rider auction market.

An unmanaged team plays itself: it bids on human listings it has a need for,
and it lists surplus or ageing riders. Everything here is either a pure
decision helper (rider lists in, answer out, no queries) or an orchestrator the
tick calls once per pass — see `specs/ai-transfer-market.md` and
`specs/ai-transfer-market-plan.md` for the reasoning behind each rule.

The helpers are deliberately blind to hidden rider traits: "need" is judged
by `riders.pricing.strength`, which reads visible attributes only, so a human
can never infer a rider's potential from the AI's bids.
"""

from __future__ import annotations

import traceback
from dataclasses import dataclass, field
from datetime import timedelta

from django.db.models import Exists, OuterRef

from economy.services import balance_for, charge_transfer_fee
from riders.field_level import current_field_factor
from riders.models import Rider
from riders.pricing import strength
from teams.models import Team
from teams.services import ROSTER_SIZE
from transfers.models import Auction, Bid
from transfers.pricing import reserve_price_for, signing_fee_for
from transfers.services import (
    TransferError,
    free_agents,
    list_for_auction,
    place_bid,
    sign_free_agent,
)

#: Two and a half 4-rider squads, so freshness can rotate at one race a week.
AI_MIN_ROSTER = 10
#: Stops an AI team buying up to ROSTER_CAP. With listing above ROSTER_SIZE,
#: rosters oscillate between ROSTER_SIZE and this number.
AI_MAX_ROSTER = 15
#: "Among its stronger riders for that speciality" means the top two.
AI_NEED_RANK = 2
#: Value's career horizon has fallen well below 1.0 by this age. An AI team
#: would list such a rider straight back out, so it neither buys nor keeps
#: buying them.
AI_AGEING_AGE = 33
#: An AI team never spends more than half its balance on the market.
AI_CUSHION_FRACTION = 0.5
#: Listing is staggered: roughly a quarter of the unmanaged teams list each
#: week, so the market gets a trickle of AI sellers rather than a flood.
AI_LISTING_EVERY_WEEKS = 4
#: Stops the same unsold veteran reappearing every month.
AI_RELIST_COOLDOWN = timedelta(weeks=4)


def _same_speciality(roster: list[Rider], rider: Rider) -> list[Rider]:
    return [own for own in roster if own.speciality == rider.speciality]


def _stronger_than(peers: list[Rider], rider: Rider) -> int:
    level = strength(rider)
    return sum(1 for peer in peers if strength(peer) > level)


def _is_top_of_speciality(roster: list[Rider], rider: Rider) -> bool:
    """Is this rider one of the `AI_NEED_RANK` strongest of their speciality
    on this roster? The buying rule wants the complement of this."""
    return _stronger_than(_same_speciality(roster, rider), rider) < AI_NEED_RANK


def wants_rider(roster: list[Rider], rider: Rider, *, pending_wins: int) -> bool:
    """Does this roster want this rider, ignoring price?

    The budget is the caller's job — it is the one condition that needs a
    balance, and `wants_rider` stays query-free. A thin roster (below
    `AI_MIN_ROSTER`) takes anyone it is allowed to want; otherwise the rider
    has to be among the `AI_NEED_RANK` strongest of their speciality.
    """
    if rider.age >= AI_AGEING_AGE:
        return False
    if len(roster) + pending_wins >= AI_MAX_ROSTER:
        return False
    if len(roster) < AI_MIN_ROSTER:
        return True
    return _is_top_of_speciality(roster, rider)


def buyer_rank(roster: list[Rider], rider: Rider, team_pk: int) -> tuple[int, int, int]:
    """Order teams competing for the same listing, lowest first: thin rosters
    ahead of full ones, then the team with fewest riders of that speciality,
    then pk, so the outcome is deterministic."""
    return (
        0 if len(roster) < AI_MIN_ROSTER else 1,
        len(_same_speciality(roster, rider)),
        team_pk,
    )


def pick_listing(roster: list[Rider], candidates: list[Rider]) -> Rider | None:
    """The rider this team should list, or `None` if it should list nobody.

    A roster above `ROSTER_SIZE` is in surplus and sells its weakest
    candidate. Otherwise it sells its oldest ageing rider who is not one of
    the `AI_NEED_RANK` strongest of their speciality — the veterans worth
    keeping are exactly the ones not for sale.
    """
    if not candidates:
        return None
    if len(roster) > ROSTER_SIZE:
        return min(candidates, key=lambda r: (strength(r), -r.age, r.pk))
    qualifying = [
        rider
        for rider in candidates
        if rider.age >= AI_AGEING_AGE and not _is_top_of_speciality(roster, rider)
    ]
    if not qualifying:
        return None
    return min(qualifying, key=lambda r: (-r.age, strength(r), r.pk))


def pick_free_agent(
    roster: list[Rider], candidates: list[Rider], budget: int, *, field_factor: float = 1.0,
) -> Rider | None:
    """The free agent a roster below `ROSTER_SIZE` should sign, or `None`.

    Only riders under `AI_AGEING_AGE` whose signing fee fits `budget`.
    Among those, the speciality the roster has fewest of comes first, so a
    retired climber tends to be replaced by a climber; then the strongest by
    visible attributes, then pk. Judged by `strength`, never a hidden trait,
    like every other AI decision. Fees are priced at `field_factor`, the
    caller's `current_field_factor()` (#166).
    """
    if len(roster) >= ROSTER_SIZE:
        return None
    affordable = [
        rider
        for rider in candidates
        if rider.age < AI_AGEING_AGE and signing_fee_for(rider, field_factor) <= budget
    ]
    if not affordable:
        return None
    return min(
        affordable,
        key=lambda r: (len(_same_speciality(roster, r)), -strength(r), r.pk),
    )


def headroom(balance: int, committed: int) -> int:
    """What this team may still promise the market: half its balance, less
    what its pending wins already ask for, floored at zero. Nothing is
    escrowed, so without that subtraction the same money could be committed
    to several auctions at once."""
    return max(0, int(balance * (1 - AI_CUSHION_FRACTION)) - committed)


@dataclass
class _Buyer:
    """One unmanaged team's position for the length of a bidding pass, built
    once and then updated in memory as it wins auctions: its roster does not
    change, but its commitments do."""

    team: Team
    roster: list[Rider] = field(default_factory=list)
    balance: int = 0
    committed: int = 0
    pending: int = 0


def _buyers() -> dict[int, _Buyer]:
    """Every unmanaged team, keyed by pk, with its roster, balance and pending
    commitments loaded: one roster query and one bid query each, not one per
    auction."""
    buyers: dict[int, _Buyer] = {}
    for team in Team.objects.filter(manager__isnull=True).order_by("pk"):
        bids = Bid.objects.live().filter(
            bidder_team=team, auction__status=Auction.Status.OPEN,
        ).select_related("auction")
        top = [bid for bid in bids if bid.amount == bid.auction.current_price]
        buyers[team.pk] = _Buyer(
            team=team,
            roster=list(team.riders.all()),
            balance=balance_for(team),
            committed=sum(bid.amount for bid in top),
            pending=len(top),
        )
    return buyers


def _biddable_auctions(at):
    """Open, unexpired, human listings that nobody has bid on yet.

    `~Exists` rather than an `exclude(bids__withdrawn_at__isnull=True)`: an
    isnull lookup across a reverse join also matches the empty side, which
    would drop exactly the auctions with no bids at all.
    """
    return (
        Auction.objects.filter(
            status=Auction.Status.OPEN,
            deadline__gt=at,
            seller_team__manager__isnull=False,
        )
        .filter(~Exists(Bid.objects.live().filter(auction=OuterRef("pk"))))
        .select_related("rider")
        .order_by("listed_at", "pk")
    )


def place_ai_bids(at) -> tuple[int, str]:
    """One pass of the AI over the auction market: every unmanaged team bids
    the reserve on at most one listing it wants per auction, and exactly one
    AI team bids per auction.

    Returns (bids placed, accumulated error text) — the same shape
    `world.services._release_inactive` uses, so one bad auction cannot strand
    the rest of the tick.
    """
    placed = 0
    error = ""
    buyers = _buyers()

    for auction in _biddable_auctions(at):
        wanted = [
            buyer
            for buyer in buyers.values()
            if wants_rider(buyer.roster, auction.rider, pending_wins=buyer.pending)
            and auction.reserve_price <= headroom(buyer.balance, buyer.committed)
        ]
        if not wanted:
            continue
        buyer = min(wanted, key=lambda b: buyer_rank(b.roster, auction.rider, b.team.pk))
        try:
            place_bid(auction.pk, buyer.team, auction.reserve_price, at=at)
        except TransferError:
            # Losing a race with a human, or an auction that closed under us.
            # A normal outcome, not an error.
            continue
        except Exception:
            error += f"ai bid on auction {auction.pk}:\n{traceback.format_exc()}\n"
            continue
        placed += 1
        buyer.committed += auction.reserve_price
        buyer.pending += 1

    return placed, error


def list_ai_riders(week, at) -> tuple[int, str]:
    """One pass of the AI over the auction market's sell side: every
    unmanaged team lists at most one rider, only on the weeks the stagger
    picks for it, and never while it already has an open listing.

    `week` is the last week the tick crossed, so a tick catching up three
    weeks lists once rather than three times. Returns (listings, error text).
    """
    listed = 0
    error = ""
    cooldown_from = at - AI_RELIST_COOLDOWN
    factor = current_field_factor()

    for team in Team.objects.filter(manager__isnull=True).order_by("pk"):
        if (week.number + team.pk) % AI_LISTING_EVERY_WEEKS:
            continue
        try:
            roster = list(team.riders.all())
            if len(roster) - 1 < AI_MIN_ROSTER:
                continue
            # One open listing per team at a time, so a second pass inside the
            # same window cannot put a second rider up for sale. Reached only
            # if a listing outlives its auction, since the stagger is four
            # weeks and an auction resolves in three days.
            if Auction.objects.filter(
                seller_team=team, status=Auction.Status.OPEN,
            ).exists():
                continue
            # Relisting cooldown, on top of that: an unsold rider stays off
            # the market for AI_RELIST_COOLDOWN rather than reappearing every
            # time the team's week comes round.
            blocked = set(
                Auction.objects.filter(
                    seller_team=team,
                    status=Auction.Status.UNSOLD,
                    resolved_at__gte=cooldown_from,
                ).values_list("rider_id", flat=True)
            )
            candidates = [
                rider
                for rider in roster
                if rider.pk not in blocked and reserve_price_for(rider, factor) > 0
            ]
            rider = pick_listing(roster, candidates)
            if rider is None:
                continue
            list_for_auction(team, rider.pk, at=at)
            listed += 1
        except TransferError:
            # A concurrent listing won the race for this rider. Next pass.
            continue
        except Exception:
            error += f"ai listing for team {team.pk}:\n{traceback.format_exc()}\n"

    return listed, error


def sign_ai_free_agents(week, at) -> tuple[int, str]:
    """One pass of the AI over the free-agent pool (#157): every unmanaged
    team below `ROSTER_SIZE` signs at most one free agent, thinnest roster
    first, then pk, so the outcome is deterministic.

    Called on a tick that crossed a week, with the last week crossed. Only
    riders already unattached before that week opened are considered, so a
    rider who joined the pool this week (an intake, a release) is a human's
    to sign for a full week before the AI can take them. The fee comes out
    of the same headroom as the AI's auction bids: half the balance, less
    what its winning bids already promise. Returns (signings, error text).
    """
    signed = 0
    error = ""
    buyers = _buyers()
    pool = [
        rider
        for rider in free_agents()
        if rider.unattached_since is None or rider.unattached_since < week.starts_at
    ]

    factor = current_field_factor()
    for buyer in sorted(buyers.values(), key=lambda b: (len(b.roster), b.team.pk)):
        rider = pick_free_agent(
            buyer.roster, pool, headroom(buyer.balance, buyer.committed), field_factor=factor,
        )
        if rider is None:
            continue

        def charge(picked, fee, team=buyer.team):
            charge_transfer_fee(
                team, amount=-fee, at=at, description=f"Signed {picked.name}",
            )

        try:
            sign_free_agent(buyer.team, rider.pk, at=at, charge=charge)
        except TransferError:
            # Signed by a human since the pool was read, or the roster is
            # full. A normal outcome; the next team tries the next rider.
            pool.remove(rider)
            continue
        except Exception:
            error += f"ai free-agent signing for team {buyer.team.pk}:\n{traceback.format_exc()}\n"
            continue
        pool.remove(rider)
        signed += 1

    return signed, error
