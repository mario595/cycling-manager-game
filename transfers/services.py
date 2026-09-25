"""Free agents: the pool, the cost of releasing one, and the two actions
that move riders across the state machine.

The pure reads (`free_agents`, `release_cost_for`) back the market screen
and the Roster's release-cost column; `sign_free_agent` and `release_rider`
are the locked write paths, charging an injected `charge(rider, fee)`
callback exactly the way `hire_trainer` does — `transfers/` may not import
`economy/` (AGENTS.md), and the caller (`api/`) supplies the ledger write.

`transfers/` may import only `riders/`, which is also why the
claim-cooldown exemption receives its in-season week count from the caller
instead of counting `schedule/`'s Week rows itself — see `transfers/README.md`,
*Free agents*.
"""

from __future__ import annotations

from datetime import timedelta

from django.db import IntegrityError, transaction
from django.db.models import QuerySet

from riders.models import Rider
from riders.services import mark_team_change

from .models import Auction, Bid
from .pricing import (
    min_increment_for,
    reserve_price_for,
    severance_fee_for,
    signing_fee_for,
)

#: In-season weeks a claimed roster keeps its claim-cooldown exemption: a
#: rider inherited from the most recent claim releases for free while fewer
#: than this many in-season weeks have opened since it. The caller counts
#: the weeks (api/), this module only compares (Design decision 2).
CLAIM_COOLDOWN_WEEKS = 1

#: Roster ceiling enforced at signing time only (Design decision 4): a
#: team already over the cap can still race, train and release.
ROSTER_CAP = 30

#: In-season weeks a free agent may sit unattached before becoming
#: *eligible* for expiry (Design decision 5). The week count itself is
#: computed by the caller (`world/`, via the same Week-row rule
#: `schedule.services.weeks_opened_between` uses) — `transfers/` may not
#: import `schedule/`
#: (AGENTS.md). Exported here, not local to the caller, because it is a
#: transfer-balance decision, not a world-mechanics one.
EXPIRY_WEEKS = 8

#: An eligible free agent must also be priced at or below this percentile
#: of every free agent's value at that moment — the pool's bottom quintile
#: (Design decision 5). Value is never stored, so the percentile is
#: computed fresh on every pass.
EXPIRY_VALUE_PERCENTILE = 0.20

#: How long a new listing runs before it can resolve, from the moment it
#: is listed.
AUCTION_DURATION = timedelta(days=3)

#: How close to the deadline a bid must land to extend it, and by how
#: much the deadline moves when it does. Symmetric by design — see spec,
#: *Rules and edge cases*, "Deadline extension is bounded by nothing
#: except itself."
EXTENSION_WINDOW = timedelta(hours=1)


class TransferError(Exception):
    """Base class for a free-agent action that cannot proceed."""


class RiderNotAvailable(TransferError):
    """That rider is not a free agent — signed by someone else, or never was."""


class RosterFull(TransferError):
    """Signing would put the team over ROSTER_CAP."""


class InsufficientFunds(TransferError):
    """The team cannot afford the fee."""


class RiderNotOnRoster(TransferError):
    """That rider is not on the caller's team."""


class AuctionAlreadyExists(TransferError):
    """That rider already has an open auction."""


class AuctionNotOpen(TransferError):
    """That auction is not open for bidding — already resolved, or gone."""


class BidTooLow(TransferError):
    """The bid does not clear the current price plus the minimum increment."""


class SelfBid(TransferError):
    """A team cannot bid on its own listing."""


def free_agents() -> QuerySet[Rider]:
    """Every active rider with no team — retired riders are never in the pool."""
    return Rider.objects.active().filter(team__isnull=True).order_by("name")


def release_cost_for(team, rider: Rider, *, weeks_opened: int) -> int:
    """What releasing `rider` from `team` would currently charge, without
    changing anything — the figure the roster screen shows per rider,
    including 0. Pure read; safe to call for every rider on a GET.

    A rider inherited from the team's most recent claim is exempt while the
    claim cooldown holds (Design decision 2); everyone else — including a
    rider signed in afterward — pays severance_fee_for. `weeks_opened` is
    the in-season weeks that have opened between `team.managed_since` and
    the relevant boundary (now on a roster GET, `at` on a release), counted
    by the caller.
    """
    if _claim_cooldown_exempt(team, rider, weeks_opened):
        return 0
    return severance_fee_for(rider)


def _claim_cooldown_exempt(team, rider: Rider, weeks_opened: int) -> bool:
    """Whether `rider` is fee-exempt to release *right now*.

    The rider must have joined `team` at the exact instant of its most
    recent claim (`joined_team_at == managed_since`) — the roster claim_team
    generated, not a rider signed in afterward, whose `at` is later — and
    fewer than CLAIM_COOLDOWN_WEEKS in-season weeks must have opened since.
    A team that was never claimed has no cooldown, so nothing is exempt.
    """
    if team.managed_since is None:
        return False
    if rider.joined_team_at != team.managed_since:
        return False
    return weeks_opened < CLAIM_COOLDOWN_WEEKS


def sign_free_agent(team, rider_id: int, *, at, charge=None) -> Rider:
    """Move a free agent onto `team`, subject to the roster cap and an
    injected `charge(rider, fee)` callback (transfers/ may not import
    economy/ — see Design decision 7).

    Locks the rider row WITHOUT skip_locked (the caller asked for this
    specific rider — the same choice hire_trainer makes, staff/README.md),
    re-checks the rider is still teamless under the lock, then re-checks
    the roster cap under the same lock before running charge(). A raise
    from charge() rolls the whole transaction back, keeping team and
    ledger in step.
    """
    with transaction.atomic():
        try:
            rider = Rider.objects.select_for_update().get(pk=rider_id)
        except Rider.DoesNotExist:
            raise RiderNotAvailable("That rider is not available.")

        # Re-checked AFTER the lock, not before it — the line that makes
        # two simultaneous signings of the same free agent safe: the loser
        # arrives here with team_id already set and is told so, rather
        # than overwriting the winner's signing.
        if rider.team_id is not None:
            raise RiderNotAvailable("That rider has already been signed.")

        if rider.retired_at is not None:
            raise RiderNotAvailable("That rider has retired.")

        # Roster-cap COUNT under the RIDER's lock, not the team's — an
        # accepted narrowing race (Design decision 8): two concurrent
        # signings for the same team can both pass the check and land the
        # team at ROSTER_CAP + 1. Deliberate: the team lock would serialize
        # every signing through a whole-transaction lock for a one-rider
        # push that the weekly tick's single sweep makes unlikely to clash.
        if Rider.objects.filter(team=team).count() >= ROSTER_CAP:
            raise RosterFull(f"Your team already has {ROSTER_CAP} riders.")

        if charge is not None:
            charge(rider, signing_fee_for(rider))

        rider.team = team
        mark_team_change([rider], team_now=team, at=at)
        rider.save(update_fields=["team", "updated_at"])
    return rider


def release_rider(team, rider_id: int, *, at, weeks_opened: int, charge=None) -> Rider:
    """Send one of `team`'s riders to the free agent pool.

    Locks the rider row (membership of `team` checked under the lock) and
    charges release_cost_for — 0 while the claim-cooldown exemption
    applies (Design decision 2), severance otherwise — via the injected
    `charge(rider, fee)` callback. `charge` is still called for a $0 fee,
    so the release path is uniform whatever the cost; writing a row for a
    0 fee is the caller's call (api/ skips it). A raise from charge()
    rolls the whole transaction back.
    """
    with transaction.atomic():
        try:
            rider = Rider.objects.select_for_update().get(pk=rider_id)
        except Rider.DoesNotExist:
            raise RiderNotOnRoster("That rider is not on your team.")

        if rider.team_id != team.pk:
            raise RiderNotOnRoster("That rider is not on your team.")

        fee = release_cost_for(team, rider, weeks_opened=weeks_opened)
        if charge is not None:
            charge(rider, fee)

        rider.team = None
        mark_team_change([rider], team_now=None, at=at)
        rider.save(update_fields=["team", "updated_at"])
    return rider


def list_for_auction(team, rider_id: int, *, at) -> Auction:
    """Create an OPEN auction for one of `team`'s own riders.

    Locks the rider row and re-checks team ownership under the lock
    (mirrors release_rider's ownership check), computes and freezes
    reserve_price and min_increment from the rider's CURRENT
    market_value_for — never recomputed after this point (Design decision
    5). The one_open_auction_per_rider partial unique constraint is the
    final guard against a race with a second concurrent listing of the
    same rider: the create runs in its own nested transaction so an
    IntegrityError there does not poison the row lock's transaction.
    """
    with transaction.atomic():
        try:
            rider = Rider.objects.select_for_update().get(pk=rider_id)
        except Rider.DoesNotExist:
            raise RiderNotOnRoster("That rider is not on your team.")

        if rider.team_id != team.pk:
            raise RiderNotOnRoster("That rider is not on your team.")

        reserve = reserve_price_for(rider)
        increment = min_increment_for(reserve)

        try:
            with transaction.atomic():
                auction = Auction.objects.create(
                    rider=rider,
                    seller_team=team,
                    reserve_price=reserve,
                    current_price=reserve,
                    min_increment=increment,
                    deadline=at + AUCTION_DURATION,
                    listed_at=at,
                )
        except IntegrityError:
            raise AuctionAlreadyExists("That rider already has an open auction.")
    return auction


def place_bid(auction_id: int, team, amount: int, *, at) -> Auction:
    """Record a Bid against an OPEN auction.

    Locks the Auction row and re-checks its status and current price under
    the lock — the same check-after-lock shape sign_free_agent uses for
    teamlessness. The minimum valid bid is the reserve price itself before
    any bid exists, and current_price + min_increment once one does
    (spec item 4). A bid landing within EXTENSION_WINDOW of the deadline
    (on either side — a late-arriving bid, one placed after the deadline
    has technically passed but before a tick has resolved the auction,
    still counts) pushes the deadline to `max(deadline, at) +
    EXTENSION_WINDOW` — relative to whichever of the two is later, never
    just the old deadline, so a late-arriving bid can't compute a new
    deadline that is already in the past. Never reset to a fixed `at +
    EXTENSION_WINDOW` either, so repeated on-time late bids still compound
    predictably (Design decision 2 / spec item 6).

    Does NOT touch economy/ — affordability is checked by the caller
    (api/) against balance_for before this is even called (Design
    decision 8); this only validates the bid is structurally valid (open,
    not self, clears the increment) and records it.
    """
    with transaction.atomic():
        try:
            auction = Auction.objects.select_for_update().get(pk=auction_id)
        except Auction.DoesNotExist:
            raise AuctionNotOpen("That auction does not exist.")

        if auction.status != Auction.Status.OPEN:
            raise AuctionNotOpen("That auction is no longer open.")

        if team.pk == auction.seller_team_id:
            raise SelfBid("You cannot bid on your own listing.")

        minimum = auction.current_price
        if auction.bids.exists():
            minimum += auction.min_increment
        if amount < minimum:
            raise BidTooLow(f"Bid must be at least {minimum}.")

        Bid.objects.create(auction=auction, bidder_team=team, amount=amount, placed_at=at)

        auction.current_price = amount
        if auction.deadline - at <= EXTENSION_WINDOW:
            # max(deadline, at), not just deadline: a bid that arrives
            # after the deadline has already passed (the auction is still
            # OPEN because no tick has resolved it yet) must extend from
            # `at`, not from the stale deadline — extending from the old
            # value alone can land the new deadline in the past when a
            # tick is late by more than EXTENSION_WINDOW, which resolves
            # the auction to this bid on the very next tick with nobody
            # else able to respond: exactly the snipe this mechanic exists
            # to prevent.
            auction.deadline = max(auction.deadline, at) + EXTENSION_WINDOW
        auction.save(update_fields=["current_price", "deadline", "updated_at"])
    return auction


def due_auctions(at) -> QuerySet[Auction]:
    """OPEN auctions whose deadline is at or before `at` — what
    world._resolve_expired_auctions iterates. A plain filter, not a lock:
    the lock happens per-row inside resolve_auction."""
    return Auction.objects.filter(status=Auction.Status.OPEN, deadline__lte=at)


def resolve_auction(auction, *, at, pay_seller=None, charge_buyer=None) -> Auction:
    """Resolve one due auction: sold, unsold or cancelled.

    Re-fetches and locks the Auction row (the caller's instance may be
    stale, from a plain `due_auctions` filter with no lock of its own),
    then re-checks it is still OPEN and its deadline has actually passed
    — a concurrent bid can have extended it between the tick's query and
    this lock, in which case this is a no-op: the auction is due again on
    a later tick, once its new deadline actually passes.

    Then locks the Rider row and re-checks it is still on the seller's
    roster: a release or forced sale can have moved it away first, in
    which case the auction is CANCELLED and no money moves (whichever
    mechanism moves the rider first wins — spec's *Rules and edge
    cases*).

    With no bids, the auction goes UNSOLD — no callback calls, rider
    untouched (spec item 11). With a winning bid (the highest amount,
    ties broken by latest `placed_at` — can't happen today, since each
    bid must clear the last by `min_increment`, but the ordering is
    fixed either way), the winner's roster is re-checked against
    ROSTER_CAP under the same lock (Design decision 7): if they are at or
    over it by now, the auction goes UNSOLD rather than violating the
    cap, exactly as if nobody had bid.

    Otherwise charge_buyer(winner, amount) runs before pay_seller(seller,
    amount) — buyer debited before seller credited, so a charge_buyer
    raise (the accepted overspend loophole, spec's *Out of scope*) rolls
    the whole transaction back and leaves the auction OPEN for the next
    tick to retry, rather than cancelling a sale the seller was owed.
    `transfers/` may not import `economy/`, so both callbacks are
    injected by the caller (world/), the same shape sign_free_agent's
    `charge` callback uses.
    """
    with transaction.atomic():
        auction = Auction.objects.select_for_update().get(pk=auction.pk)

        if auction.status != Auction.Status.OPEN or auction.deadline > at:
            return auction

        rider = Rider.objects.select_for_update().get(pk=auction.rider_id)

        if rider.team_id != auction.seller_team_id:
            auction.status = Auction.Status.CANCELLED
            auction.resolved_at = at
            auction.save(update_fields=["status", "resolved_at", "updated_at"])
            return auction

        winning_bid = auction.bids.order_by("-amount", "-placed_at").first()
        if winning_bid is None:
            auction.status = Auction.Status.UNSOLD
            auction.resolved_at = at
            auction.save(update_fields=["status", "resolved_at", "updated_at"])
            return auction

        winner = winning_bid.bidder_team
        if Rider.objects.filter(team=winner).count() >= ROSTER_CAP:
            auction.status = Auction.Status.UNSOLD
            auction.resolved_at = at
            auction.save(update_fields=["status", "resolved_at", "updated_at"])
            return auction

        amount = winning_bid.amount
        if charge_buyer is not None:
            charge_buyer(winner, amount)
        if pay_seller is not None:
            pay_seller(auction.seller_team, amount)

        rider.team = winner
        mark_team_change([rider], team_now=winner, at=at)
        rider.save(update_fields=["team", "updated_at"])

        auction.status = Auction.Status.SOLD
        auction.resolved_at = at
        auction.save(update_fields=["status", "resolved_at", "updated_at"])
    return auction
