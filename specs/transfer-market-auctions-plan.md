# Transfer market with rider auctions — Implementation Plan

**Spec:** `specs/transfer-market-auctions.md` · **Issue:** #28 · **Status:** proposed
**Apps touched:** `transfers/` (first models + migration), `economy/`, `world/`, `api/`, `frontend/`

## Context you need

`transfers/` today holds two pricing functions
(`transfers/pricing.py::market_value_for`, `signing_fee_for`,
`severance_fee_for`) and the free-agent market
(`transfers/services.py::free_agents`, `sign_free_agent`, `release_rider`,
`release_cost_for`) — but **no models**. This ticket gives `transfers/` its
first ones: an auction is the first thing in this app that needs to persist
across ticks (a free agent is a pure derived query — `team__isnull=True` —
with nothing to remember).

**The two closest precedents, both worth reading before touching a line:**

- **`transfers.services.sign_free_agent`** (`transfers/services.py`) — locks
  the rider row `select_for_update()` without `skip_locked`, re-checks
  availability under the lock, re-checks the roster cap under the same
  lock, then runs an **injected** `charge(rider, fee)` callback before the
  team change sticks. `transfers/` cannot import `economy/`
  (`AGENTS.md`: `transfers -> riders` only), so `api/` supplies the ledger
  write. A raise from `charge()` rolls the whole transaction back. This
  ticket's bid-placement and auction-resolution paths use the exact same
  shape — resolution needs *two* callbacks (debit the winner, credit the
  seller) instead of one.
- **`world.services._expire_free_agents`** and its caller **`tick()`**
  (`world/services.py`) — a private helper in `world/` that loops over
  something time-based and calls into `transfers/` for the per-row work.
  `_expire_free_agents` runs once per crossed **week transition**, inside
  `tick()`'s `for transition in weeks:` loop. **This ticket's resolution
  pass is different: it must NOT go in that loop.** An auction's deadline
  is a fixed real-time duration (spec, *Decisions taken*), completely
  decoupled from week boundaries — a listing made mid-week must still
  resolve on schedule even if no week transition occurs for days. The
  resolution pass is therefore its own top-level step in `tick()`,
  unconditional, run every tick regardless of what else is due — see
  *Design decision 2*.

Repo rules this plan is bound by (`AGENTS.md`):

- `transfers -> riders` is the only import `transfers/` may make. Not
  `economy/`, not `teams/`, not `world/`, not `api/`. The ledger write (both
  directions — debit buyer, credit seller) and any `schedule/`-owned week
  counting must be supplied by the caller, exactly as `sign_free_agent` and
  `_expire_free_agents` already do.
- Only `world/` and `api/` may import everything. `world/` is where the
  resolution pass is orchestrated from — same place `_expire_free_agents`
  and `_release_inactive` already live.
- `economy.services.charge_transfer_fee(team, *, amount: int, ...)`
  currently docs `amount` as **negative, debits only** — "One kind covers
  both sides of the market... there is deliberately no second Kind." An
  auction settlement needs both a debit and a credit in the same
  transaction. Reusing `charge_transfer_fee` for the credit side would
  contradict its own docstring contract; this plan adds a **second**
  function, `pay_transfer_income`, rather than silently repurposing the
  first — see *Design decision 4*.

## Goal

- A manager can list a rider from their own roster for auction and see the
  listing's reserve price before confirming.
- Any other manager can place a bid on a live auction, in real money terms
  (their current balance, checked at bid time), and see when they've been
  outbid.
- A bid placed near the deadline extends it; the auction otherwise resolves
  automatically on the next tick after its deadline passes.
- A won auction moves the rider to the winning team's roster and moves
  money both ways, atomically, with no partial states possible.
- An auction with no bids expires into a no-op: rider and money unchanged.

## Design decisions (settled — implement these, do not substitute)

1. **`Auction` and `Bid` are new models in `transfers/models.py` (new
   file).** This is `transfers/`'s first `models.py` and first real
   migration (`transfers/migrations/__init__.py` exists today only as an
   empty package). An `Auction` needs a lifecycle (`open` → `sold` /
   `unsold` / `cancelled`) and a deadline that mutates as bids arrive — a
   pure query can't represent that. `Bid` is a normal append-only history
   row (never mutated after creation), the same shape `LedgerEntry` and
   `FanbaseEntry` already use elsewhere.

2. **Resolution is a new, unconditional step inside `world.services.tick()`,
   not folded into the week-transition loop.** Add
   `_resolve_expired_auctions(at)` alongside `_expire_free_agents` and
   `_release_inactive`, but call it **once per tick, after the week loop,
   using `at` (the tick's own `now()` read) as the boundary** — not once
   per week transition. Do not reuse `weeks_opened_between` or any
   `schedule/` week-counting for auction deadlines: an auction's clock is
   wall-clock real time (`DurationField`/`DateTimeField` arithmetic), the
   one deliberately non-`schedule/`-flavoured deadline in the game, per the
   spec's *Decisions taken* ("decouples the market from the race
   calendar"). Do not gate this behind `transitions` or `weeks` being
   non-empty — a hard week with zero transitions must still resolve due
   auctions.

3. **`transfers.services.resolve_auction(auction, *, at, pay_seller=None,
   charge_buyer=None)` is the single entry point world/ calls**, mirroring
   `sign_free_agent`'s injected-callback shape but with two callbacks
   instead of one. It:
   - locks the `Auction` row (`select_for_update()`) and the `Rider` row
     together inside one `transaction.atomic()`;
   - re-checks the auction is still `open` and its (possibly-extended)
     `deadline <= at` under the lock — a concurrent bid between the tick's
     query and the lock must not resolve an auction that just got
     extended;
   - re-checks the rider is still on the seller's roster (spec's *Rules and
     edge cases*: a release or forced sale can have removed the rider
     first — whichever mechanism moves the rider first wins, the other is
     a no-op, not an error) — if the rider is gone, mark the auction
     `cancelled` and return without touching money;
   - if there is no winning bid, marks the auction `unsold` and returns —
     no calls to either callback, no money moves, rider untouched (spec
     item 11);
   - if there is a winning bid, runs `charge_buyer(winner_team, amount)`
     then `pay_seller(seller_team, amount)` — buyer debited before seller
     credited, so a `charge_buyer` raise (should never happen: balance was
     checked at bid time, but the check is not escrowed — spec's *Out of
     scope*, *Held or escrowed funds* — so a buyer who spent the money
     elsewhere between bidding and resolution is a real, accepted case)
     rolls back the whole transaction and the auction is left `open` for
     the *next* tick to retry, rather than silently cancelling a sale a
     seller was owed. This is the one place the spec's accepted overspend
     loophole actually bites — see *Risks*;
   - on success: moves `rider.team` to the winner, calls
     `riders.services.mark_team_change` (same helper `sign_free_agent` and
     `release_rider` already call), marks the auction `sold`.

4. **`economy.services.pay_transfer_income(team, *, amount: int, at,
   description: str)` is a new function**, not a repurposing of
   `charge_transfer_fee`. Same `LedgerEntry.Kind.TRANSFER_FEE` kind (the
   existing "one kind covers both sides of the market" reasoning extends
   naturally: a signing fee, a severance charge and now a sale are all
   "money moved for a transfer reason," distinguished by `description` and
   sign, not by a fourth `Kind`) — but `charge_transfer_fee`'s docstring is
   an explicit, tested contract ("`amount` is negative, debits only"), and
   changing that contract's meaning under existing callers is a correctness
   risk for zero benefit when a second three-line function says the same
   thing honestly. `pay_transfer_income` asserts `amount > 0` the same way
   `charge_transfer_fee` implicitly assumes `amount < 0` (neither function
   flips the sign for you — the caller passes the signed amount, matching
   every existing `economy/services.py` charge function).

5. **The reserve price and minimum bid increment are both fixed fractions
   of `market_value_for(rider)`, computed at listing time and frozen on the
   `Auction` row — not recomputed live.** Free agents' `signing_fee_for`
   and `severance_fee_for` (transfers/pricing.py) are recomputed on every
   read because a rider's attributes can move between reads and the fee
   should track that. An auction's reserve must NOT drift mid-auction: a
   manager who lists at a given reserve and a bidder who bids against a
   displayed price would otherwise be reasoning about numbers that could
   change under them between page loads (e.g. after a week's training
   ticks). `Auction.reserve_price` and `Auction.current_price` are
   therefore both plain `IntegerField`s captured once, at listing and at
   each bid respectively — never re-derived from `market_value_for` after
   creation. `RESERVE_RATE` lives in `transfers/pricing.py` beside
   `SIGNING_FEE_RATE`/`SEVERANCE_FEE_RATE`, following the same "the
   arithmetic constant belongs where the other pricing constants are"
   convention.

6. **Minimum bid increment is a flat fraction of the *reserve* price, not
   the current price**, and computed once at listing time alongside the
   reserve — `Auction.min_increment = round_to_nearest(reserve_price *
   MIN_INCREMENT_RATE)`. An increment that tracked the rising current price
   would make late bidding in a hot auction require ever-larger jumps,
   which has no basis in the spec and would silently punish exactly the
   contested auctions the extension mechanic (Design decision 2) is meant
   to protect. A flat, reserve-anchored increment stays legible for the
   auction's whole life.

7. **`ROSTER_CAP` (from `transfers/services.py`, currently 30) is
   re-checked at auction resolution time, under the same lock, the same
   way `sign_free_agent` checks it.** The spec's *Open questions* asks
   whether the cap applies to winning an auction; it does, using the
   existing constant — no new one. If the winning team is at or over
   `ROSTER_CAP` by the time the auction resolves (they could have signed
   free agents or won other auctions in the meantime), the sale does not
   go through: the auction is marked `unsold` (not `cancelled` — the
   listing genuinely failed to find a valid buyer, the same outcome as no
   bids at all, and the seller keeps the rider free, exactly as if nobody
   had bid), and every bidder simply lost the auction they thought they
   won. This is a rare edge case (a team would have to hit the cap via a
   *different* transaction between their winning bid and the deadline) but
   must not silently violate the cap — see *Risks*.

8. **Bidding validates against the bidder's CURRENT balance at the moment
   of the bid API call**, exactly mirroring `sign_free_agent`'s `charge`
   callback pattern in `api/views.py` — no new affordability concept.
   Unlike a free-agent sign, placing a bid does **not** call
   `economy.services` at all (no money moves until the auction resolves —
   spec item 5 is a refusal check, not a charge). The check is therefore a
   plain read: `api/views.py`'s `PlaceBidView` calls
   `economy.services.balance_for(team)` and compares before calling
   `transfers.services.place_bid`.

9. **A team cannot bid on its own listing** (spec, *Rules and edge cases*)
   — enforced in `transfers.services.place_bid`, not just the frontend,
   since `transfers/services.py` is the only place that can see both
   `auction.seller_team` and the bidding team under lock.

## Data model

New file `transfers/models.py`, new migration `transfers/migrations/0001_auction.py`.

```python
class Auction(TimeStampedModel):
    class Status(models.TextChoices):
        OPEN = "open", "Open"
        SOLD = "sold", "Sold"
        UNSOLD = "unsold", "Unsold"
        CANCELLED = "cancelled", "Cancelled"

    rider = models.ForeignKey("riders.Rider", on_delete=models.CASCADE, related_name="auctions")
    seller_team = models.ForeignKey("teams.Team", on_delete=models.CASCADE, related_name="listed_auctions")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.OPEN)
    reserve_price = models.PositiveIntegerField(help_text="Frozen at listing time; never recomputed from market value.")
    current_price = models.PositiveIntegerField(help_text="reserve_price until the first bid, then the highest bid amount.")
    min_increment = models.PositiveIntegerField(help_text="Frozen at listing time: reserve_price * MIN_INCREMENT_RATE.")
    deadline = models.DateTimeField(help_text="Game time. Mutated forward by a qualifying late bid (Design decision 2).")
    listed_at = models.DateTimeField(help_text="Game time the listing was made. Distinct from created_at (wall clock).")
    resolved_at = models.DateTimeField(null=True, blank=True, help_text="Game time this auction left OPEN. Null while open.")

    class Meta:
        ordering = ["-listed_at", "-pk"]
        indexes = [
            models.Index(fields=["status", "deadline"], name="auction_open_deadline_idx"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["rider"],
                condition=models.Q(status="open"),
                name="one_open_auction_per_rider",
            ),
        ]


class Bid(TimeStampedModel):
    auction = models.ForeignKey(Auction, on_delete=models.CASCADE, related_name="bids")
    bidder_team = models.ForeignKey("teams.Team", on_delete=models.CASCADE, related_name="transfer_bids")
    amount = models.PositiveIntegerField()
    placed_at = models.DateTimeField(help_text="Game time.")

    class Meta:
        ordering = ["-placed_at", "-pk"]
        indexes = [models.Index(fields=["auction", "-amount"], name="bid_auction_amount_idx")]
```

- **`one_open_auction_per_rider`** is the DB-level backstop for spec item
  12 ("a rider can only be listed ... only once at a time") — a partial
  unique constraint on `status="open"` lets the same rider be listed again
  after a prior auction resolves, but never twice concurrently. This is
  the same `condition=models.Q(...)` pattern `LedgerEntry`'s
  `one_wage_entry_per_team_per_week` and `FanbaseEntry`'s
  `one_fanbase_entry_per_team_per_week` already use.
- **No FK from `Auction` to a "winner" team.** The winner is derivable as
  the highest `Bid` on a `SOLD` auction — storing it redundantly invites
  drift, the same reasoning `economy/README.md` gives for never storing a
  cached balance.
- **`Bid` rows are never deleted or mutated** — same append-only discipline
  as `LedgerEntry`/`FanbaseEntry`. The full bid history exists in the
  database even though the spec keeps it off the UI (*Out of scope*,
  *Bidder identity, bid history*) — nothing here contradicts that; the
  rows are simply not serialized to a bidder-identifying view yet.
- `teams.Team`, `riders.Rider` imported as strings in the FK declaration
  only if needed to avoid a circular import; `transfers -> riders` is
  already a real import (`from riders.models import Rider` — matches
  `transfers/services.py`'s existing style), so `Rider` can be a direct FK
  target; `teams.Team` must be declared as the string `"teams.Team"` since
  `transfers/` does not import `teams/` anywhere today and must not start.

## transfers/pricing.py (extend the existing file)

```python
#: Reserve price as a fraction of market_value_for — the auction's
#: starting bid. Design decision 5.
RESERVE_RATE = 0.50

#: Minimum bid increment as a fraction of the FROZEN reserve price, not
#: the live current price. Design decision 6.
MIN_INCREMENT_RATE = 0.05


def reserve_price_for(rider) -> int:
    """RESERVE_RATE of this rider's market value, rounded the same way
    market_value_for rounds (nearest 1,000)."""
    return _round_to_nearest_1000(RESERVE_RATE * market_value_for(rider))


def min_increment_for(reserve_price: int) -> int:
    """MIN_INCREMENT_RATE of a frozen reserve_price, rounded to the
    nearest 1,000. Takes the already-computed reserve, not a rider, so it
    stays correct even though reserve_price is frozen on the Auction row
    and never re-derived (Design decision 5)."""
    return max(1000, _round_to_nearest_1000(MIN_INCREMENT_RATE * reserve_price))
```

`RESERVE_RATE = 0.50` sits below `SIGNING_FEE_RATE` (0.60): a seller
choosing to auction accepts a lower guaranteed floor than a buyer would pay
to sign the same rider as a free agent outright, in exchange for the chance
of a higher price through competition — the auction's whole value
proposition. Calibrate against `test_average_value_is_about_one_season_of_wages`'s
population the same way #29's rates were tuned (W2's test additions, below).

## transfers/services.py (extend the existing file)

```python
class AuctionNotOpen(TransferError):
    """That auction is not open for bidding — already resolved, or gone."""

class BidTooLow(TransferError):
    """The bid does not clear the current price plus the minimum increment."""

class SelfBid(TransferError):
    """A team cannot bid on its own listing."""

class AuctionAlreadyExists(TransferError):
    """That rider already has an open auction."""


#: How close to the deadline a bid must land to extend it, and by how
#: much the deadline moves when it does. Symmetric by design — see spec,
#: *Rules and edge cases*, "Deadline extension is bounded by nothing
#: except itself."
EXTENSION_WINDOW = timedelta(hours=1)
AUCTION_DURATION = timedelta(days=3)


def list_for_auction(team, rider_id: int, *, at) -> Auction:
    """Create an OPEN auction for one of `team`'s own riders.

    Locks the rider row, re-checks team ownership under the lock (mirrors
    release_rider's ownership check), computes and freezes reserve_price
    and min_increment from CURRENT market_value_for (Design decision 5 —
    frozen from this point on), and relies on the
    one_open_auction_per_rider partial unique constraint as the final
    guard against a race with a second concurrent listing of the same
    rider (IntegrityError -> AuctionAlreadyExists).
    """

def place_bid(auction_id: int, team, amount: int, *, at) -> Auction:
    """Record a Bid against an OPEN auction, raising SelfBid,
    AuctionNotOpen or BidTooLow. Locks the Auction row; re-checks status
    and current_price/min_increment under the lock (the same
    check-after-lock shape sign_free_agent uses for teamlessness).
    Updates current_price to `amount`. If `at` falls within
    EXTENSION_WINDOW of `deadline`, extends `deadline` by
    EXTENSION_WINDOW (Design decision 2 / spec item 6) — NOT reset to
    `at + EXTENSION_WINDOW`; always `deadline += EXTENSION_WINDOW`, so
    repeated late bids compound predictably rather than each resetting to
    a fixed offset from `now`.

    Does NOT touch economy/ — affordability is checked by the caller
    (api/) against balance_for before this is even called (Design
    decision 8); this function only validates the bid is structurally
    valid (open, not self, clears the increment) and records it.
    """

def resolve_auction(auction, *, at, pay_seller=None, charge_buyer=None) -> Auction:
    """... (Design decision 3, in full) ..."""

def due_auctions(at) -> QuerySet[Auction]:
    """OPEN auctions whose deadline is at or before `at` — what
    world._resolve_expired_auctions iterates. A plain filter, not a lock:
    the lock happens per-row inside resolve_auction."""
    return Auction.objects.filter(status=Auction.Status.OPEN, deadline__lte=at)
```

## economy/services.py (extend the existing file)

```python
def pay_transfer_income(team, *, amount: int, at, description: str) -> LedgerEntry:
    """Credit `team` income from a transfer-market sale. Returns the row.

    Same Kind as charge_transfer_fee (TRANSFER_FEE) — a sale is still
    "money moved for a transfer reason," told apart by description and
    sign, not a fourth Kind (Design decision 4). `amount` is POSITIVE
    here, the mirror image of charge_transfer_fee's negative-only
    contract — this function exists specifically so that contract is
    never silently violated by a caller passing a positive amount into
    charge_transfer_fee instead.
    """
    return LedgerEntry.objects.create(
        team=team,
        kind=LedgerEntry.Kind.TRANSFER_FEE,
        amount=amount,
        occurred_at=at,
        description=description,
    )
```

## world/services.py (extend the existing file)

```python
def _resolve_expired_auctions(at) -> tuple[int, int, str]:
    """Resolve every auction whose deadline has passed as of `at`.

    Called ONCE per tick, unconditionally, OUTSIDE the week-transition
    loop (Design decision 2) — an auction's deadline is wall-clock real
    time, decoupled from week boundaries, so this must not wait for one.

    Supplies resolve_auction's two callbacks, since transfers/ cannot
    import economy/: charge_buyer debits the winner via
    charge_transfer_fee (negative amount), pay_seller credits the seller
    via pay_transfer_income (positive amount) — same transaction, same
    shape sign_free_agent's injected `charge` uses.

    Returns (sold_count, unsold_count, accumulated error text) for the
    TickRun counters, mirroring _release_inactive's (int, str) return
    (TickRun does not exist yet at this point in tick(), same reason
    _release_inactive returns rather than writes).
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
```

Wired into `tick()`:

```python
    reclaimed = _reclaim_unfinished()
    claimed = _claim(limit=max(0, max_races - len(reclaimed)), at=at)
    capped = len(reclaimed) + len(claimed) >= max_races

    # After the week loop, before TickRun is created: unconditional, once
    # per tick, on wall-clock deadlines — never inside `for transition in
    # weeks:` (Design decision 2).
    auctions_sold, auctions_unsold, auction_error = _resolve_expired_auctions(at)

    run = TickRun.objects.create(
        ...
        auctions_sold=auctions_sold,
        auctions_unsold=auctions_unsold,
        error=inactivity_error + auction_error,
    )
```

Placed after race claiming and before `TickRun.objects.create` — it does
not touch a race row, so (like the week loop's economy calls) it does not
need to run inside `_claim`'s transaction, and by running after claiming a
race's own squad is already locked in before any roster changes from a won
auction could interfere with it.

**`TickRun` gets two new counters**: `auctions_sold =
models.PositiveIntegerField(default=0)`, `auctions_unsold =
models.PositiveIntegerField(default=0)` (`world/migrations/000X_...py`,
new migration) — same pattern as `agents_expired`.

## api/serializers.py (extend the existing file)

```python
class AuctionSerializer(serializers.Serializer):
    """One live auction as the market screen shows it: rider, price,
    time left — never the bidder (spec, Rules and edge cases,
    'Bidding is anonymous')."""
    id = serializers.IntegerField()
    rider = RiderSerializer()  # existing serializer — same visible fields as the roster
    current_price = serializers.IntegerField()
    min_next_bid = serializers.IntegerField()  # current_price + min_increment, computed in the view
    deadline = serializers.DateTimeField()
    is_own_listing = serializers.BooleanField()  # True when request.user's team == seller_team; frontend hides the Bid button


class AuctionMarketSerializer(serializers.Serializer):
    """Same both-keys-always-present shape FreeAgentPoolSerializer uses."""
    auctions = AuctionSerializer(many=True)
    balance = serializers.IntegerField()


class ListForAuctionSerializer(serializers.Serializer):
    rider_id = serializers.IntegerField()


class PlaceBidSerializer(serializers.Serializer):
    amount = serializers.IntegerField(min_value=1)


class MyBidStatusSerializer(serializers.Serializer):
    """One row for 'auctions I've bid on' — spec item 8, outbid
    visibility. is_high_bidder tells the frontend whether to show 'you're
    winning' vs 'outbid'."""
    auction_id = serializers.IntegerField()
    rider_name = serializers.CharField()
    my_last_bid = serializers.IntegerField()
    current_price = serializers.IntegerField()
    is_high_bidder = serializers.BooleanField()
    deadline = serializers.DateTimeField()
```

## api/views.py (extend the existing file)

```python
class AuctionMarketView(APIView):
    """Every open auction, plus the caller's balance. Mirrors
    FreeAgentsView exactly."""
    def get(self, request): ...


class ListForAuctionView(APIView):
    """List one of the caller's own riders. 409 for AuctionAlreadyExists /
    RiderNotOnRoster (request well-formed, world state refuses it —
    same split as SignFreeAgentView)."""
    def post(self, request): ...


class PlaceBidView(APIView):
    """Place a bid on an open auction. Balance checked here (Design
    decision 8) against economy.services.balance_for BEFORE calling
    transfers.services.place_bid — no charge happens yet, so there is no
    injected charge callback on this path, unlike sign_free_agent."""
    def post(self, request, auction_id): ...


class MyBidsView(APIView):
    """Every auction the caller's team has an active bid on, with
    is_high_bidder — backs spec item 8's outbid notice. Read-only,
    polled by the frontend the same way FreeAgentsView is."""
    def get(self, request): ...
```

## api/urls.py (extend the existing file)

```python
path("transfers/auctions/", AuctionMarketView.as_view(), name="auction-market"),
path("transfers/auctions/list/", ListForAuctionView.as_view(), name="list-for-auction"),
path("transfers/auctions/<int:auction_id>/bid/", PlaceBidView.as_view(), name="place-bid"),
path("transfers/auctions/mine/", MyBidsView.as_view(), name="my-bids"),
```

## Work items

### W1 — `transfers/`: `Auction` and `Bid` models, first migration ✅
Add `transfers/models.py` with `Auction`/`Bid` as specified in *Data model*.
Run `makemigrations transfers` for `0001_auction.py`. No service logic yet.
**Test:** `transfers/tests/test_models.py::test_one_open_auction_per_rider_constraint`
— create two `Auction` rows for the same rider both `status=open` inside a
transaction, assert `IntegrityError`; a second `Auction` for the same rider
with the first `status=sold` must succeed.

### W2 — `transfers/pricing.py`: `RESERVE_RATE`, `MIN_INCREMENT_RATE`, `reserve_price_for`, `min_increment_for` ✅
**Test:** `transfers/tests/test_pricing.py::test_reserve_price_is_half_signing_fee_rate`
(reserve_price_for(rider) == round-to-1000(0.50 * market_value_for(rider)));
`test_min_increment_is_fraction_of_reserve` (uses the passed-in
`reserve_price`, not a live `market_value_for` recompute — pass a rider
whose attributes are then mutated in-memory without saving, and assert
`min_increment_for` still matches the original reserve).

### W3 — `transfers/services.py`: `list_for_auction`, exceptions ✅
Add `AuctionNotOpen`, `BidTooLow`, `SelfBid`, `AuctionAlreadyExists`, and
`list_for_auction(team, rider_id, *, at)` per *Design decisions*. Does not
touch `place_bid` or `resolve_auction` yet.
**Test:** `transfers/tests/test_services.py::test_list_for_auction_freezes_reserve_and_increment`,
`test_list_for_auction_rejects_rider_not_on_team` (raises `RiderNotOnRoster`
— reuse the existing exception, don't invent a new one for the same
meaning), `test_list_for_auction_rejects_second_concurrent_listing` (second
call for the same rider while the first is still open raises
`AuctionAlreadyExists`).

### W4 — `transfers/services.py`: `place_bid`, `due_auctions`
**Test:** `test_place_bid_records_bid_and_updates_current_price`,
`test_place_bid_below_reserve_plus_increment_raises_bid_too_low`,
`test_place_bid_rejects_self_bid`, `test_place_bid_on_closed_auction_raises_auction_not_open`,
`test_place_bid_within_extension_window_pushes_deadline_forward_by_the_window`
(assert exact new `deadline`, not just "later than before" — this is the
mechanic the whole anti-snipe promise rests on),
`test_place_bid_outside_extension_window_does_not_move_deadline`.

### W5 — `transfers/services.py`: `resolve_auction`
The load-bearing item — implement in full per *Design decision 3*,
including the re-check-under-lock, the rider-already-moved cancellation
path, the no-bids unsold path, and the `ROSTER_CAP` re-check.
**Test:** `test_resolve_auction_with_no_bids_marks_unsold_and_touches_nothing`
(assert rider.team unchanged, zero calls to either callback — use `Mock()`
callbacks and assert `.assert_not_called()`), `test_resolve_auction_with_winning_bid_moves_rider_and_calls_both_callbacks_in_order`
(assert `charge_buyer` called before `pay_seller` via `Mock` call order),
`test_resolve_auction_cancels_when_rider_already_left_roster` (release the
rider via `release_rider` first, then resolve — assert `status=cancelled`,
no callback calls), `test_resolve_auction_marks_unsold_when_winner_at_roster_cap`
(fill the winning team to `ROSTER_CAP` via other means between the bid and
resolution, assert `status=unsold`, no callback calls, seller keeps rider),
`test_resolve_auction_is_idempotent_under_charge_buyer_failure` (raise from
`charge_buyer`, assert the whole transaction rolled back: `status` still
`open`, rider still with seller, no `Bid` state corrupted — mirrors
`sign_free_agent`'s existing `InsufficientFunds` rollback test).

### W6 — `economy/`: `pay_transfer_income`
**Test:** `economy/tests/test_services.py::test_pay_transfer_income_writes_positive_transfer_fee_entry`
(assert `kind=TRANSFER_FEE`, `amount > 0` — contrast with the existing
`charge_transfer_fee` test's negative-amount assertion, to make the sign
contract explicit in the test suite itself).

### W7 — `world/`: `_resolve_expired_auctions`, wired into `tick()`, `TickRun` counters
Add the two `TickRun` fields and their migration. Wire
`_resolve_expired_auctions` per *world/services.py* above — **unconditionally,
after the week loop, not inside it.**
**Test:** `world/tests/test_services.py::test_tick_resolves_an_expired_auction_even_with_no_week_transition`
(mock-clock: list an auction, advance the clock past its deadline WITHOUT
crossing a week boundary, tick, assert the auction resolved) — this is the
test that would fail if a future edit accidentally moved the call inside
`for transition in weeks:`. Also
`test_tick_does_not_resolve_an_auction_before_its_deadline`,
`test_tick_extends_deadline_test_still_resolves_eventually` (list, bid
near-deadline repeatedly across several ticks, assert it keeps surviving
until bids stop, then resolves).

### W8 — `api/`: serializers, views, urls
Add every class from *api/serializers.py* / *api/views.py* / *api/urls.py*
above. `PlaceBidView`'s balance check: `if balance_for(team) <
serializer.validated_data["amount"]: return Response({"detail": "..."},
status=409)` — same 409-not-400 convention `SignFreeAgentView` documents
("the request itself is well-formed — the world's state refuses it").
**Test:** `api/tests.py::test_place_bid_rejects_amount_above_balance_with_409`,
`test_list_for_auction_requires_team`, `test_auction_market_hides_bidder_identity`
(assert the response payload contains no team/user field anywhere in an
`AuctionSerializer` entry — the test that would catch someone adding
`high_bidder` to the serializer later out of habit).

### W9 — `frontend/`: Market screen (auction tab), Roster "List for auction" action, outbid notice
Follow the existing Transfers screen's free-agent tab as the pattern
(`frontend/README.md` names its location) — add a second tab or section for
live auctions, reusing the roster's rider-card component. Roster screen
gets a "List for auction" action beside the existing release action. A
lightweight poll (matches how `MyBidsView`/`FreeAgentsView` are already
polled) surfaces the outbid notice.
**Test:** frontend test per the existing convention for the Transfers
screen (see its current test file for the pattern); no new pattern needed.

## Execution order

W1 → W2 → W3 → W4 → W5 → W6 → W7 → W8 → W9.

Models and pricing constants (W1–W2) first since everything else reads
them. W3 before W4 because placing a bid needs an auction to exist. W5
(resolution) is the highest-risk item — done once bidding is solid so its
tests can exercise real `Bid` rows rather than fixtures. W6 (economy) is a
small, independent addition that both `resolve_auction`'s tests (via mocks)
and W7's wiring need — sequenced right before W7 so the real function
exists when it's wired in, not just mocked. W7 (world/tick) before W8
(api/) so the resolution path is proven against the mock clock before any
HTTP surface depends on it. W9 last, as usual for a plan that ends at the
frontend.

Stop and commit after each work item — every one leaves the suite green
(`.venv/bin/python -m pytest`) and is independently reviewable.

## Documentation update (required)

- **`transfers/README.md`** — add an *Auctions* section beside the existing
  *Free agents* one, in the same style: what `Auction`/`Bid` are, the
  reserve/increment rates and why they're frozen not live (Design decision
  5), the resolve-under-lock shape, the `ROSTER_CAP` re-check at
  resolution. Update the app's top summary ("Market for buying/selling
  riders, auctions... still to come" in `AGENTS.md`'s per-app description)
  — this ticket removes "auctions" from that still-to-come list.
- **`world/README.md`** — extend *How a tick works* with a new numbered
  step for auction resolution, explicitly calling out that it runs once
  per tick on wall-clock deadlines, unlike every other per-week step in
  that same list — this is the detail most likely to be miscopied by a
  future edit, so the README should say it as plainly as this plan does.
- **`economy/README.md`** — add `pay_transfer_income` next to
  `charge_transfer_fee`'s existing entry in *What this app owns*, noting
  the sign-direction split between the two.
- **`AGENTS.md`** — update the `transfers/` row's one-line description once
  this ships (drop "auctions... still to come").

## Verification

1. `.venv/bin/python -m pytest transfers/ economy/ world/ api/` — full
   suite for every touched app, green.
2. **Manual, via the dev server and `mock_clock`** (the tick's real
   behavior can't be proven by a fast unit test alone — the likeliest
   failure mode is the resolution step silently only running on a week
   boundary, which every unit test that also crosses a week boundary would
   fail to catch):
   - Seed two claimed teams (`seed_teams --claim-for` twice, or claim a
     second team by hand).
   - As team A, list a rider for auction.
   - As team B, place a bid.
   - `mock_clock advance --by 1h` repeatedly (NOT `--to-next`, which jumps
     to the next scheduled race and could skip past a week boundary,
     defeating the point of this check) until past the auction's deadline,
     ticking after each advance.
   - Confirm the auction resolved on a tick where `TickRun.weeks_processed
     == 0` — this is the concrete check that the resolution step is not
     accidentally nested inside the week loop.
   - Confirm the rider moved rosters and both teams' finance screens show
     the sale.
3. Confirm the anti-snipe path by hand once: bid within `EXTENSION_WINDOW`
   of the deadline, advance the mock clock to the *original* deadline, tick,
   and confirm the auction is still open.

## Risks

| Risk | Mitigation |
|---|---|
| Resolution accidentally placed inside `for transition in weeks:`, so an auction only resolves on a week boundary instead of its own deadline | W7's test explicitly advances the clock without crossing a week boundary and asserts resolution still happens; Verification step 2 repeats this by hand with the `weeks_processed == 0` check |
| `charge_buyer` fails at resolution (winner spent the money between bidding and the deadline — the accepted overspend loophole from the spec's *Out of scope*) | Whole transaction rolls back (Design decision 3); auction stays `open` and is retried on the *next* tick, not silently dropped — but note this means a permanently-unaffordable winning bid could loop forever without a human noticing. Not solved by this plan (escrow is explicitly deferred); flag this as the concrete shape the future escrow ticket (#27-adjacent) should close |
| Two concurrent bids on the same auction near the deadline | `place_bid` locks the `Auction` row `select_for_update()`; the second bid's transaction waits for the first, then re-reads `current_price`/`deadline` under its own lock — same serialization `sign_free_agent` relies on for the free-agent race |
| A rider is released or force-sold while an open auction on them exists | `resolve_auction` re-checks the rider is still on the seller's roster under lock and cancels cleanly (Design decision 3) rather than erroring; but `release_rider` itself is NOT changed by this plan to check for an open auction first — a manager could release a listed rider mid-auction, which the spec explicitly allows ("whichever mechanism moves the rider first wins") but is worth a manual check in Verification |
| `ROSTER_CAP` re-check at resolution silently strands a winning bidder who did nothing wrong (just hit the cap via unrelated activity) | Accepted per Design decision 7 as a rare edge case; the auction goes `unsold` rather than violating the cap, and the bidder sees the auction simply ended without them winning — no error surfaces, which matches the "no bids" UX already in the spec |

## Open questions

None — the spec's two open questions (exact tuning numbers; whether
`ROSTER_CAP` applies to winning) are both resolved above (`RESERVE_RATE =
0.50`, `MIN_INCREMENT_RATE = 0.05`, `AUCTION_DURATION = 3 days`,
`EXTENSION_WINDOW = 1 hour`, and yes — Design decision 7).
