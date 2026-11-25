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

from collections.abc import Iterable
from datetime import timedelta

from django.db import IntegrityError, transaction
from django.db.models import Exists, OuterRef, QuerySet

from riders.field_level import current_field_factor
from riders.models import Rider
from riders.services import mark_team_change
from riders.youth_triage import belongs_to, lock_rider, release_graduates

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

#: A forced sale may not take the roster below what a team needs to race.
#: Equal to racing.models.SQUAD_SIZE, duplicated because transfers/ may not
#: import racing/ (AGENTS.md); transfers/tests pins the equality.
FORCED_SALE_ROSTER_FLOOR = 4

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
    """That rider is not an available free agent — signed, retired, or
    never was."""


class RosterFull(TransferError):
    """Signing would put the team over ROSTER_CAP."""


class InsufficientFunds(TransferError):
    """The team cannot afford the fee."""


class RiderNotOnRoster(TransferError):
    """That rider is not on the caller's team."""


class RosterAtFloor(TransferError):
    """A forced sale would leave fewer riders than a team needs to race."""


class AuctionAlreadyExists(TransferError):
    """That rider already has an open auction."""


class AuctionNotOpen(TransferError):
    """That auction is not open for bidding — already resolved, or gone."""


class BidTooLow(TransferError):
    """The bid does not clear the current price plus the minimum increment."""


class SelfBid(TransferError):
    """A team cannot bid on its own listing."""


def free_agents() -> QuerySet[Rider]:
    """Every active rider with no team — retired riders and development
    squad riders (#33) are never in it. Neither is a rider being sold under
    insolvency (#27): they have no team while their forced auction runs, and
    are not signable until it ends unsold."""
    being_sold = Auction.objects.filter(
        rider=OuterRef("pk"), status=Auction.Status.OPEN, forced=True,
    )
    return Rider.objects.active().filter(
        team__isnull=True, development_squad__isnull=True,
    ).exclude(Exists(being_sold)).order_by("name")


def release_cost_for(
    team, rider: Rider, *, weeks_opened: int, field_factor: float | None = None,
) -> int:
    """What releasing `rider` from `team` would currently charge, without
    changing anything — the figure the roster screen shows per rider,
    including 0. Pure read; safe to call for every rider on a GET.

    A rider inherited from the team's most recent claim is exempt while the
    claim cooldown holds (Design decision 2); everyone else — including a
    rider signed in afterward — pays severance_fee_for. `weeks_opened` is
    the in-season weeks that have opened between `team.managed_since` and
    the relevant boundary (now on a roster GET, `at` on a release), counted
    by the caller. `field_factor` defaults to `current_field_factor()`; a
    caller pricing a whole roster reads it once and passes it (#166).
    """
    if _claim_cooldown_exempt(team, rider, weeks_opened):
        return 0
    if field_factor is None:
        field_factor = current_field_factor()
    return severance_fee_for(rider, field_factor)


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

        if rider.development_squad_id is not None:
            raise RiderNotAvailable("That rider is not available.")

        if Auction.objects.filter(
            rider=rider, status=Auction.Status.OPEN, forced=True,
        ).exists():
            raise RiderNotAvailable("That rider is being sold.")

        # Roster-cap COUNT under the RIDER's lock, not the team's — an
        # accepted narrowing race (Design decision 8): two concurrent
        # signings for the same team can both pass the check and land the
        # team at ROSTER_CAP + 1. Deliberate: the team lock would serialize
        # every signing through a whole-transaction lock for a one-rider
        # push that the weekly tick's single sweep makes unlikely to clash.
        if Rider.objects.filter(team=team).count() >= ROSTER_CAP:
            raise RosterFull(f"Your team already has {ROSTER_CAP} riders.")

        if charge is not None:
            charge(rider, signing_fee_for(rider, current_field_factor()))

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

    Locks the rider row and re-checks ownership under the lock
    (mirrors release_rider's ownership check), computes and freezes
    reserve_price and min_increment from the rider's CURRENT
    market_value_for — never recomputed after this point (Design decision
    5). The one_open_auction_per_rider partial unique constraint is the
    final guard against a race with a second concurrent listing of the
    same rider: the create runs in its own nested transaction so an
    IntegrityError there does not poison the row lock's transaction.

    **Ownership is `belongs_to`, not `team_id` (#34), so a graduate can be
    auctioned**: they belong to the squad that developed them, not to any
    roster. A rider still mid-development is refused for the same reason a
    rival's rider is — they are not the seller's to sell.
    """
    with transaction.atomic():
        rider = lock_rider(rider_id)
        if rider is None:
            raise RiderNotOnRoster("That rider is not on your team.")

        if not belongs_to(rider, team):
            raise RiderNotOnRoster("That rider is not on your team.")

        reserve = reserve_price_for(rider, current_field_factor())
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


def force_list_for_auction(team, rider_id: int, *, at) -> Auction:
    """Sell one of `team`'s riders under insolvency (#27): the rider leaves the
    roster now, so the wage stops now, and is auctioned with no severance.
    Whether or not anyone bids, they do not come back.

    The rider is left with `team = NULL` while the auction runs (kept out of
    the free-agent pool by `free_agents()`); `resolve_auction` moves them to
    the winner, or leaves them a free agent if the auction goes unsold.

    The whole roster is locked, in pk order, BEFORE it is counted: two forced
    sales from five riders must not both pass the floor check and leave three.
    pk order means two calls for one team queue rather than deadlock. A rider
    who already has an open voluntary auction has that auction converted,
    keeping its reserve, deadline and bids — one_open_auction_per_rider
    forbids a second row, and cancelling would throw away the seller's bids.
    """
    with transaction.atomic():
        roster = list(Rider.objects.select_for_update().filter(team=team).order_by("pk"))
        rider = next((r for r in roster if r.pk == rider_id), None)
        if rider is None:
            raise RiderNotOnRoster("That rider is not on your team.")
        if len(roster) <= FORCED_SALE_ROSTER_FLOOR:
            raise RosterAtFloor(
                f"A team needs at least {FORCED_SALE_ROSTER_FLOOR} riders to race."
            )

        auction = (
            Auction.objects.select_for_update()
            .filter(rider=rider, status=Auction.Status.OPEN)
            .first()
        )
        if auction is not None:
            auction.forced = True
            auction.save(update_fields=["forced", "updated_at"])
        else:
            reserve = reserve_price_for(rider, current_field_factor())
            auction = Auction.objects.create(
                rider=rider,
                seller_team=team,
                forced=True,
                reserve_price=reserve,
                current_price=reserve,
                min_increment=min_increment_for(reserve),
                deadline=at + AUCTION_DURATION,
                listed_at=at,
            )

        rider.team = None
        mark_team_change([rider], team_now=None, at=at)
        rider.save(update_fields=["team", "updated_at"])
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
        if auction.bids.live().exists():
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

    Then locks the Rider row and re-checks it still belongs to the seller:
    a release or forced sale can have moved it away first, in which case
    the auction is CANCELLED and no money moves (whichever mechanism moves
    the rider first wins — spec's *Rules and edge cases*). Ownership is
    `belongs_to`, so a graduate is the seller's while they remain in the
    squad and a listed graduate's auction survives the window step (#34).

    With no bids, the auction goes UNSOLD — no callback calls, rider
    untouched (spec item 11), except that a graduate is released to the
    free-agent pool on the way out: an unsold listing must not leave them
    invisible on the squad screen. The same release runs on the other
    UNSOLD path, the winner's roster being full (Design decision 9). With
    a winning bid (the highest amount, ties broken by latest `placed_at`
    — can't happen today, since each bid must clear the last by
    `min_increment`, but the ordering is fixed either way), the winner's
    roster is re-checked against ROSTER_CAP under the same lock (Design
    decision 7): if they are at or over it by now, the auction goes
    UNSOLD rather than violating the cap, exactly as if nobody had bid.

    Otherwise charge_buyer(winner, amount) runs before pay_seller(seller,
    amount) — buyer debited before seller credited, so a charge_buyer
    raise (the accepted overspend loophole, spec's *Out of scope*) rolls
    the whole transaction back and leaves the auction OPEN for the next
    tick to retry, rather than cancelling a sale the seller was owed.
    `transfers/` may not import `economy/`, so both callbacks are
    injected by the caller (world/), the same shape sign_free_agent's
    `charge` callback uses.

    A SOLD graduate joins the winner's roster and leaves the squad in the
    one save that sets `team`; `development_squad` is cleared alongside it
    (#34), which is a no-op for a roster rider.
    """
    with transaction.atomic():
        auction = Auction.objects.select_for_update().get(pk=auction.pk)

        if auction.status != Auction.Status.OPEN or auction.deadline > at:
            return auction

        rider = lock_rider(auction.rider_id)

        # A missing rider is unreachable — Auction.rider is CASCADE, so the
        # auction could not outlive it — but cancel rather than crash if the
        # database ever says otherwise. A forced sale takes the rider off the
        # roster at listing (#27), so "still available" means teamless and not
        # retired; anything else must still belong to the seller (#34).
        if rider is None:
            available = False
        elif auction.forced:
            available = rider.team_id is None and rider.retired_at is None
        else:
            available = belongs_to(rider, auction.seller_team)
        if not available:
            auction.status = Auction.Status.CANCELLED
            auction.resolved_at = at
            auction.save(update_fields=["status", "resolved_at", "updated_at"])
            return auction

        winning_bid = auction.bids.live().order_by("-amount", "-placed_at").first()
        if winning_bid is None:
            _resolve_unsold(auction, rider, at)
            return auction

        winner = winning_bid.bidder_team
        if Rider.objects.filter(team=winner).count() >= ROSTER_CAP:
            _resolve_unsold(auction, rider, at)
            return auction

        amount = winning_bid.amount
        if charge_buyer is not None:
            charge_buyer(winner, amount)
        if pay_seller is not None:
            pay_seller(auction.seller_team, amount)

        rider.team = winner
        rider.development_squad = None
        mark_team_change([rider], team_now=winner, at=at)
        rider.save(update_fields=["team", "development_squad", "updated_at"])

        auction.status = Auction.Status.SOLD
        auction.resolved_at = at
        auction.save(update_fields=["status", "resolved_at", "updated_at"])
    return auction


def _resolve_unsold(auction, rider, at) -> None:
    """Close one auction UNSOLD, releasing the rider first if they are a
    graduate (#34) so an unsold listing cannot strand them.

    Both UNSOLD paths share this: no bids, and a winner's full roster. The
    release goes through `release_graduates` — the same stamped,
    idempotent call `close_squad` makes — rather than repeating the
    bookkeeping, and it runs before the auction is saved so a failure
    leaves the auction OPEN for the next tick to retry.
    """
    if rider.team_id is None and rider.development_squad_id is not None:
        release_graduates([rider.pk], at=at)
    auction.status = Auction.Status.UNSOLD
    auction.resolved_at = at
    auction.save(update_fields=["status", "resolved_at", "updated_at"])


def withdraw_bids(team, *, at) -> int:
    """Withdraw every live bid `team` holds in an OPEN auction, and reset each
    affected auction's current_price to its highest remaining live bid (or the
    reserve if none remain). Returns bids withdrawn. Deadlines are left as
    they are.

    Called when a team is claimed (#30) and when a team becomes insolvent
    (#27): in both cases the team must not carry an in-progress purchase.
    """
    withdrawn = 0
    with transaction.atomic():
        auction_ids = list(
            Bid.objects.live()
            .filter(bidder_team=team, auction__status=Auction.Status.OPEN)
            .values_list("auction_id", flat=True)
            .distinct()
        )
        for auction in (
            Auction.objects.select_for_update().filter(pk__in=auction_ids).order_by("pk")
        ):
            if auction.status != Auction.Status.OPEN:
                continue
            withdrawn += auction.bids.live().filter(bidder_team=team).update(withdrawn_at=at)
            top = auction.bids.live().order_by("-amount", "-placed_at").first()
            auction.current_price = top.amount if top else auction.reserve_price
            auction.save(update_fields=["current_price", "updated_at"])
    return withdrawn


def cancel_listings(team, *, at) -> int:
    """Cancel every OPEN auction `team` is selling — no money moves (bids are
    never escrowed). Returns auctions cancelled.

    Called on a claim (#114), the sale-side counterpart to withdraw_bids: the
    claim has already released the listed riders to the free-agent pool, so a
    listing left open would show the new manager a sale they never made and
    invite bids on a rider nobody is selling. Bids are left as they are —
    they were not withdrawn, the auction ended — and every reader that counts
    them filters on an OPEN auction.
    """
    return Auction.objects.filter(
        seller_team=team, status=Auction.Status.OPEN,
    ).update(status=Auction.Status.CANCELLED, resolved_at=at)


def cancel_open_auctions(rider_ids: Iterable[int], *, at) -> int:
    """Cancel every OPEN auction of these riders — no money moves (bids are
    never escrowed). Returns auctions cancelled.

    Used when a rider retires by age at a season close (#42): resolve_auction
    would cancel these anyway once it saw the rider had left the seller's
    roster, but only at the deadline, leaving managers free to keep bidding on
    a rider who is already gone. Takes no charge or pay callback precisely
    because there is nothing to move: an auction holds no funds.
    """
    return Auction.objects.filter(
        rider_id__in=list(rider_ids), status=Auction.Status.OPEN,
    ).update(status=Auction.Status.CANCELLED, resolved_at=at)


def cancel_unowned_listings(seller_team, *, at) -> int:
    """Cancel every OPEN auction `seller_team` holds whose rider no longer
    belongs to it. Returns auctions cancelled.

    Called after closing the development squad (#34). Without it, a released
    graduate's auction stays biddable until its deadline — managers would keep
    bidding on a rider who is already in the free-agent pool, and the winner
    would be cancelled at resolve time by the same ownership check that would
    have caught it weeks earlier.

    **Forced sales are left alone** (#27): their rider is teamless by design
    while the auction runs, so `belongs_to` is false for them, yet the team is
    still owed the sale. A claim does not come here — it cancels every listing
    the team holds, forced or not, through `cancel_listings` (#114).
    """
    stale = [
        auction.rider_id
        for auction in Auction.objects.filter(
            seller_team=seller_team, status=Auction.Status.OPEN, forced=False,
        ).select_related("rider__development_squad")
        if not belongs_to(auction.rider, seller_team)
    ]
    return cancel_open_auctions(stale, at=at)
