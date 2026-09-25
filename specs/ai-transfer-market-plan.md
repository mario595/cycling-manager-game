# AI teams participating in the transfer market — Implementation Plan

**Spec:** `specs/ai-transfer-market.md` · **Issue:** #30 · **Status:** proposed
**Apps touched:** `world/` (new module `ai_market.py`), `transfers/`, `api/`

## Context you need

Auctions shipped in #28 (`transfers/README.md`, *Auctions*). A manager lists a
roster rider (`transfers.services.list_for_auction`), which freezes a
`reserve_price` (50% of `market_value_for`) and a `min_increment`. Bids go
through `transfers.services.place_bid`, which locks the `Auction` row and
accepts the reserve as the opening bid, then `current_price + min_increment`
after that. Every tick, `world.services._resolve_expired_auctions(at)` resolves
due auctions through `transfers.services.resolve_auction`, and the highest
`Bid` wins. Money only moves at resolution, through callbacks `world/` passes
in: `economy.services.charge_transfer_fee` and `pay_transfer_income`.

Today only a human can list or bid, because only `api/` views call those
functions, and each view needs `team_for(request.user)`. Unmanaged teams
(`Team.manager IS NULL`) never trade. They still pay weekly wages and earn
merchandise and prize money, but they never sign a sponsor
(`economy/README.md`, *Sponsorship*).

Facts this plan relies on, all checked against the code:

- `teams.services.claim_team` locks an unmanaged team, stamps
  `managed_since`, **releases its whole roster to the free-agent pool**,
  generates a fresh 12-rider roster (`teams.services.ROSTER_SIZE = 12`) and
  resets the balance to `STARTING_BALANCE` ($500,000). Its only callers are
  `api.views.ClaimTeamView` and `seed_teams --claim-for`.
- `Bid` is documented as append-only: "never mutated or deleted after
  creation" (`transfers/models.py`).
- `resolve_auction` never checks the buyer's balance. It charges whatever the
  winning bid was.
- `racing.models.SQUAD_SIZE = 4`, and the example season runs 12 races in 12
  weeks.
- **The spec's open question about balances, answered.** A generated
  12-rider roster costs about $14,200 a week in wages (mean over 200 sampled
  rosters). Merchandise brings in about $400 a week at the starting fanbase
  of 10,000. An unmanaged team therefore ends season 1 with roughly
  $330,000, before prize money. AI buying power holds for about three
  seasons, so this ticket does **not** need to pull sponsorship forward from
  #45. Rider values are small by comparison: median $12,000, p90 $28,000.

Repo rules this work is bound by:

- **`transfers/` may import only `riders/`.** All AI decision-making needs
  balances (`economy/`) and manager status (`teams/`), so it lives in
  `world/`, the app `AGENTS.md` already names as the home of "AI team
  decisions". `transfers/` gains one new write path, `withdraw_bids`, which
  needs nothing outside `riders/`.
- **`teams/` may not import `transfers/`.** So claim-time bid withdrawal is
  wired in `api/` (the caller), not inside `claim_team`.
- Game code reads `world.services.now()`, never `timezone.now()`.
- Tests are pytest. `world/tests/conftest.py` forces `MockClock`.

## Goal

1. Every tick, each unmanaged team considers every open auction listed by a
   **managed** team that has **no live bid yet**, and places at most one bid
   at the reserve price when the rider fills a need and the team can afford
   it while keeping a cash cushion.
2. On each tick that crosses a week boundary, a staggered subset of unmanaged
   teams each list at most one surplus or ageing rider, and never shrink
   below a racing minimum.
3. Claiming a team withdraws every live bid that team holds in open
   auctions. Each affected auction's price and history then read as if those
   bids had never been placed.
4. No new screen and no frontend change. AI activity appears through the
   existing market endpoints.

## Design decisions (settled — implement these, do not substitute)

1. **An AI team bids only on an auction with no live bids, and only at the
   reserve.** The spec's in-scope item 2 says "at the current asking price".
   Its *Rules and edge cases* and *Decisions taken* are more specific: a bid
   "that only ever matches the reserve, never exceeds it". With no bids on
   the auction, the asking price *is* the reserve, so both statements hold.
   Do **not** let the AI bid `current_price + min_increment` on an auction a
   human has already bid on. That would put the AI above the reserve and
   reopen the buy-from-AI, sell-to-AI flip the spec closed.
   **Load-bearing:** the "no live bids" check is read without a lock, but
   `place_bid` enforces it again for free. Once any bid exists, the minimum
   becomes `current_price + min_increment`, so a reserve-priced AI bid that
   lost a race with a human raises `BidTooLow`. Catch it and move on. Do not
   add a separate lock.

2. **The AI never bids on an auction listed by an unmanaged team.** This is
   the spec's cut of AI-to-AI trading, and it also guarantees the AI never
   hits `SelfBid`. Check the seller's `manager_id` at decision time.

3. **All AI logic lives in a new module, `world/ai_market.py`.** It holds
   pure decision helpers (rider lists in, answers out, no queries) and two
   orchestrators that `world.services.tick()` calls. Do not put the rules in
   `transfers/`, which cannot read a balance or a manager, and do not put
   them in `teams/`.

4. **"Need" is judged by `riders.pricing.strength`, which reads visible
   attributes only.** This follows the same never-a-hidden-trait rule as
   market value (`transfers/README.md`, *Never a hidden trait*). Never read
   `potential`, `peak_age` or any other hidden field. If the AI bid on
   hidden potential, a human could watch AI bids to learn which riders will
   grow.

5. **Buying rule.** Unmanaged team T wants listed rider R when all of the
   following hold:
   - R is younger than `AI_AGEING_AGE`. Otherwise T would buy a rider its
     own selling rule would list straight back out.
   - T's roster count plus its pending wins (live bids that are currently
     the top bid on an open auction) is below `AI_MAX_ROSTER`.
   - Either T is **thin** (roster count below `AI_MIN_ROSTER`), or fewer
     than `AI_NEED_RANK` of T's riders with R's speciality are stronger than
     R. That second test is the spec's "would be among its stronger riders
     for that speciality".
   - `R`'s reserve is at most T's headroom (Design decision 6).

   When several teams want the same auction, the bid goes to one of them,
   ranked by `(not thin, count of T's riders with R's speciality, T.pk)`
   ascending: thin teams first, then the team with fewest riders of that
   speciality. Once a team bids, the auction has a live bid and no other AI
   team considers it.

6. **Budget.** A team's headroom is `balance_for(T) * (1 - AI_CUSHION_FRACTION)`
   minus the sum of T's pending wins (its current top bids on open
   auctions), floored at 0. This is a fraction of the balance, as the spec
   requires, not a fixed amount. Pending wins are subtracted because nothing
   is escrowed: without that, one team could commit the same money to five
   auctions at once. A team with a zero or negative balance has zero
   headroom and never bids.

7. **Selling rule.** It runs once per tick that crosses at least one week
   boundary, using the **last** crossed week. A tick catching up three weeks
   lists once, not three times. An unmanaged team T is considered only when
   all of these hold:
   - `(week.number + T.pk) % AI_LISTING_EVERY_WEEKS == 0`. This staggers the
     teams so that roughly a quarter of them are eligible each week.
   - T has no `OPEN` auction as seller.
   - T's roster count minus one is at least `AI_MIN_ROSTER`.

   The candidate riders are T's riders that:
   - have no open auction,
   - have no auction resolved `UNSOLD` within `AI_RELIST_COOLDOWN`,
   - and have `reserve_price_for(rider) > 0`, since a worthless rider only
     clogs the market.

   From the candidates:
   - If T's roster is above `teams.services.ROSTER_SIZE` (surplus), list the
     weakest candidate: lowest `strength`, then highest age, then lowest pk.
   - Otherwise, list the oldest candidate aged `AI_AGEING_AGE` or more who is
     **not** among the top `AI_NEED_RANK` of T's riders of their speciality
     by strength. Break ties by lowest strength, then lowest pk.
   - Otherwise list nothing.

   The stagger is deterministic on purpose: no randomness, so tests are exact
   and a tick re-run gives the same result. `list_for_auction` sets the price
   and deadline exactly as it does for a human listing.

8. **Claim-time withdrawal adds a `withdrawn_at` timestamp; it never deletes
   a `Bid`.** The spec requires the auction to read "exactly as if the AI
   had never bid", and the model requires bid history to stay append-only.
   A nullable `Bid.withdrawn_at` satisfies both: the row stays as history,
   and every reader filters it out. This is the **one** permitted mutation
   of a `Bid`, and it is one-way: null becomes a timestamp and never goes
   back. Record the reason in the model docstring.
   Rejected: deleting the row, which destroys the history the append-only
   rule exists to protect. Also rejected: *deriving* withdrawal from
   `placed_at < bidder_team.managed_since`. It breaks when the team is later
   released, because `managed_since` goes back to null and the dead bid
   comes back to life.

9. **Withdraw every live bid the claimed team holds in `OPEN` auctions,
   whoever placed it**, not only the top bid. A non-top bid can never win,
   so withdrawing it changes nothing a player sees, and withdrawing all of
   them avoids a "which bid is top" read under a lock. "Whoever placed it"
   covers this case: a human bids, is released for inactivity, and the team
   is then claimed by someone else. The new manager must not inherit that
   in-progress purchase either (spec, *A human claiming a team never
   inherits an in-progress purchase*). The reverse direction, release to the
   unmanaged pool, withdraws nothing.

10. **Withdrawal runs in the same transaction as the claim.**
    `ClaimTeamView` wraps `claim_team(...)` and `withdraw_bids(team, at=at)`
    in one outer `transaction.atomic()`. `claim_team`'s own `atomic()` then
    becomes a savepoint. Without this, a claimed team could exist with its
    old bids still live, and a tick in between would resolve an auction to
    the new manager. `seed_teams --claim-for` does **not** call
    `withdraw_bids`: it is a dev seeding command run on fresh teams, and
    `teams/` may not import `transfers/`. It is recorded in *Risks*.

11. **"Live" is a queryset method, `Bid.objects.live()`**, which filters
    `withdrawn_at__isnull=True`, and it is the default manager. Django's
    related managers inherit it, so `auction.bids.live()` works. Every
    reader of bids switches to it. Do not rely on callers remembering to add
    `.filter(withdrawn_at__isnull=True)`: that is exactly how a withdrawn bid
    ends up winning an auction.

12. **AI bidding runs every tick; AI listing runs only on ticks that cross a
    week.** Bidding is keyed to wall-clock auctions, like resolution. Both
    run **after** `_resolve_expired_auctions(at)`, so the AI never evaluates
    an auction that this same tick is about to close. Listing runs before
    bidding. The order is harmless either way, because Design decision 2
    stops AI teams bidding on AI listings, but fixing it keeps `TickRun`
    counts deterministic.

13. **Constants live in `world/ai_market.py`**, next to the rules that use
    them, because they are AI behaviour, not transfer pricing:

    | Constant | Value | Why |
    |---|---|---|
    | `AI_MIN_ROSTER` | 10 | Two and a half 4-rider squads. That covers freshness rotation at one race a week, with slack. |
    | `AI_MAX_ROSTER` | 15 | Stops an AI team buying up to `ROSTER_CAP` (30). With listing above 12, rosters oscillate between 12 and 15. |
    | `AI_NEED_RANK` | 2 | "Among its stronger riders" means the top two of a speciality. |
    | `AI_AGEING_AGE` | 33 | About 20% of generated riders are 33 or older. Value's career horizon has fallen well below 1.0 by then. |
    | `AI_CUSHION_FRACTION` | 0.5 | Spend at most half the balance. |
    | `AI_LISTING_EVERY_WEEKS` | 4 | About 4 AI listings a week across 15 unmanaged teams: a trickle, not a flood. |
    | `AI_RELIST_COOLDOWN` | `timedelta(weeks=4)` | Stops the same unsold veteran reappearing every month. |

    `ROSTER_SIZE` is imported from `teams.services`, not duplicated.

## Data model

### `transfers.Bid` — one new field

| Field | Type | Null/blank | Default | Notes |
|---|---|---|---|---|
| `withdrawn_at` | `DateTimeField` | `null=True, blank=True` | `None` | Game time. Set once by `withdraw_bids`; never cleared. |

Custom queryset:

```python
class BidQuerySet(models.QuerySet):
    def live(self):
        return self.filter(withdrawn_at__isnull=True)

class Bid(TimeStampedModel):
    ...
    objects = BidQuerySet.as_manager()
```

No new index. Bids per auction are few, and the existing
`bid_auction_amount_idx` still serves the ordering.

Migration: **`transfers/migrations/0002_bid_withdrawn_at.py`** (new), an
`AddField` only. Existing rows get null, meaning live, which is correct.

### `world.TickRun` — two new counters

| Field | Type | Default | Notes |
|---|---|---|---|
| `ai_bids_placed` | `PositiveIntegerField` | `0` | Bids placed by unmanaged teams this tick. |
| `ai_listings_created` | `PositiveIntegerField` | `0` | Auctions opened by unmanaged teams this tick. |

Migration: **`world/migrations/0015_tickrun_ai_market.py`** (new). Add
`help_text` in the same style as `auctions_sold`.

## `transfers/models.py`

Add `BidQuerySet`, `Bid.objects`, and `Bid.withdrawn_at` as above. Rewrite the
`Bid` docstring: append-only **except** the one-way `withdrawn_at` stamp, with
the reason (Design decision 8).

## `transfers/services.py`

### Switch every bid reader to `live()`

- `place_bid`: `auction.bids.exists()` becomes `auction.bids.live().exists()`.
  Without this, an auction whose only bid was withdrawn would still demand
  `reserve + increment`.
- `resolve_auction`: `auction.bids.order_by(...)` becomes
  `auction.bids.live().order_by("-amount", "-placed_at").first()`.
  **This is the change that stops a withdrawn bid winning.**

### New: `withdraw_bids`

```python
def withdraw_bids(team, *, at) -> int:
    """Withdraw every live bid `team` holds in an OPEN auction, and reset each
    affected auction's current_price to its highest remaining live bid (or the
    reserve if none remain). Returns bids withdrawn. Deadlines are left as
    they are."""
    withdrawn = 0
    with transaction.atomic():
        auction_ids = list(
            Bid.objects.live()
            .filter(bidder_team=team, auction__status=Auction.Status.OPEN)
            .values_list("auction_id", flat=True)
            .distinct()
        )
        # Lock in pk order: two concurrent claims touching overlapping
        # auctions then take locks in the same order and cannot deadlock.
        for auction in (
            Auction.objects.select_for_update().filter(pk__in=auction_ids).order_by("pk")
        ):
            if auction.status != Auction.Status.OPEN:
                continue                      # resolved between the read and the lock
            withdrawn += auction.bids.live().filter(bidder_team=team).update(withdrawn_at=at)
            top = auction.bids.live().order_by("-amount", "-placed_at").first()
            auction.current_price = top.amount if top else auction.reserve_price
            auction.save(update_fields=["current_price", "updated_at"])
    return withdrawn
```

Leaving the deadline alone is deliberate. Rolling back an anti-snipe
extension would need a record of which extension each bid caused, and a
slightly longer auction harms nobody.

## `world/ai_market.py` (new)

Imports: `economy.services.balance_for`, `riders.models.Rider`,
`riders.pricing.strength`, `teams.models.Team`, `teams.services.ROSTER_SIZE`,
`transfers.models.Auction, Bid`, `transfers.pricing.reserve_price_for`,
`transfers.services.list_for_auction, place_bid, TransferError`.

Constants as in Design decision 13.

### Pure helpers (no queries; testable with unsaved `Rider` instances)

```python
def wants_rider(roster: list[Rider], rider: Rider, *, pending_wins: int) -> bool
def buyer_rank(roster: list[Rider], rider: Rider, team_pk: int) -> tuple[int, int, int]
def pick_listing(roster: list[Rider], candidates: list[Rider]) -> Rider | None
def headroom(balance: int, committed: int) -> int
```

- `wants_rider` covers every part of Design decision 5 except the budget,
  which the orchestrator checks.
- `buyer_rank` returns `(0 if thin else 1, same_speciality_count, team_pk)`.
- `pick_listing` applies Design decision 7's surplus-then-ageing choice. It
  receives the already-filtered `candidates` and the whole `roster` (for
  ranking), and returns `None` if nothing qualifies. It does **not** check
  `AI_MIN_ROSTER`; the orchestrator gates that before calling.
- `headroom` returns `max(0, int(balance * (1 - AI_CUSHION_FRACTION)) - committed)`.

### Orchestrators

```python
def place_ai_bids(at) -> tuple[int, str]:
    """One pass over biddable auctions. Returns (bids placed, error text)."""

def list_ai_riders(week, at) -> tuple[int, str]:
    """One pass over unmanaged teams for `week`. Returns (listings, error text)."""
```

Both return `(count, error)` and catch per item, the same shape as
`_release_inactive` and `_resolve_expired_auctions`: one bad team or auction
must not strand the rest of the tick.

`place_ai_bids` outline:

1. Load unmanaged teams (`Team.objects.filter(manager__isnull=True)`). For
   each, build an in-memory state once per pass:
   - `roster`: its riders, as a list;
   - `committed` and `pending`: the sum and count of its live bids where
     `amount == auction.current_price` on `OPEN` auctions (that is, it is
     currently the top bidder);
   - `balance`: `balance_for(team)`.
2. Biddable auctions:

   ```python
   Auction.objects.filter(
       status=Auction.Status.OPEN, deadline__gt=at,
       seller_team__manager__isnull=False,
   ).filter(
       ~Exists(Bid.objects.live().filter(auction=OuterRef("pk")))
   ).select_related("rider").order_by("listed_at", "pk")
   ```

   **Use `~Exists`, not `.exclude(bids__withdrawn_at__isnull=True)`.** An
   `isnull` lookup across a reverse join also matches the empty side of the
   join, so the `exclude` form risks dropping auctions that have no bids at
   all, which are exactly the ones the AI should consider. `~Exists`
   expresses "no live bid" with no ambiguity (W5 tests both directions).
3. For each auction: gather the teams where `wants_rider(...)` holds and
   `auction.reserve_price <= headroom(balance, committed)`. Pick `min` by
   `buyer_rank`. Then call
   `place_bid(auction.pk, team, auction.reserve_price, at=at)`.
   - On success, update that team's in-memory state: `committed +=
     reserve`, `pending += 1`. Its roster does not change; the rider arrives
     only at resolution.
   - On `TransferError`, which covers `BidTooLow` after losing a race with a
     human and `AuctionNotOpen`, skip the auction silently. That is a normal
     outcome, not an error.
   - On any other exception, append it to the error text.

`list_ai_riders` outline:

1. For each unmanaged team, ordered by pk, check the stagger condition. Skip
   the team if it has an `OPEN` auction as seller, or if its roster count
   minus one is below `AI_MIN_ROSTER`.
2. Candidates: roster riders that have no `OPEN` auction, no `UNSOLD`
   auction with `resolved_at >= at - AI_RELIST_COOLDOWN`, and
   `reserve_price_for(rider) > 0`.
3. Call `pick_listing(roster, candidates)`. If it returns a rider, call
   `list_for_auction(team, rider.pk, at=at)`. Catch `TransferError` (for
   example `AuctionAlreadyExists` from a concurrent listing) and skip.

Use one query per team for the roster and one for the auction exclusions.
There are about 15 teams of about 12 riders; no further optimisation is
needed.

## `world/services.py`

- `from .ai_market import list_ai_riders, place_ai_bids`.
- In `tick()`, straight after `_resolve_expired_auctions(at)`:

```python
ai_listings, ai_list_error = (
    list_ai_riders(weeks[-1].week, at) if weeks else (0, "")
)
ai_bids, ai_bid_error = place_ai_bids(at)
```

- Pass `ai_bids_placed=ai_bids`, `ai_listings_created=ai_listings` into
  `TickRun.objects.create(...)`, and append both error strings to `error`.

## `world/models.py`

Add the two `TickRun` counters (Data model above).

## `api/views.py`

- `ClaimTeamView.post`: wrap the claim and the withdrawal in one outer
  transaction (Design decision 10). Keep the existing `except` clauses
  **outside** the `with` block, so an exception rolls back both calls:

```python
at = now()
try:
    with transaction.atomic():
        team = claim_team(request.user, name=..., code=..., at=at)
        withdraw_bids(team, at=at)
except NoTeamAvailable as exc: ...
```

- `AuctionMarketView`: change the `Prefetch("bids", queryset=Bid.objects.select_related("bidder_team"))`
  queryset to `Bid.objects.live().select_related("bidder_team")`. A withdrawn
  bid then disappears from history and from the `min_next_bid` computation.
- `MyBidsView`: base both querysets on live bids.
  - `my_bids = Bid.objects.live().filter(bidder_team=team)...`
  - The auctions filter becomes
    `Auction.objects.filter(status=OPEN, bids__bidder_team=team, bids__withdrawn_at__isnull=True)`.
    Keep both conditions in **one** `filter()` call so they apply to the same
    bid row.

  Without this, a newly claimed manager would see the previous AI's bids as
  "my bids".

Import `withdraw_bids` from `transfers.services` and `transaction` from
`django.db`, if they are not already imported.

## Work items

### W1 — `transfers/models.py`, migration 0002: `Bid.withdrawn_at` and `live()` ✅
Add the field, `BidQuerySet` and the manager, and update the docstring. Run
`makemigrations transfers`, then rename the migration to
`0002_bid_withdrawn_at.py`.
**Test:** `transfers/tests/test_models.py::test_live_excludes_withdrawn_bids`,
and `::test_related_manager_supports_live` (`auction.bids.live()`).

### W2 — `transfers/services.py`: live-bid readers and `withdraw_bids` ✅
Switch `place_bid` and `resolve_auction` to `live()`, and add `withdraw_bids`.
**Load-bearing:** `resolve_auction`'s winning-bid query.
**Tests** in `transfers/tests/test_services.py`:
- `test_withdraw_bids_resets_current_price_to_next_live_bid`
- `test_withdraw_bids_resets_to_reserve_when_no_bid_remains`
- `test_withdraw_bids_ignores_resolved_auctions`
- `test_withdraw_bids_leaves_other_teams_bids_live`
- `test_withdrawn_bid_never_wins_resolution`: A bids, B outbids, B's bids are
  withdrawn, the auction resolves to A at A's amount.
- `test_withdrawn_only_bid_resolves_unsold`
- `test_opening_bid_after_withdrawal_accepts_reserve`

### W3 — `api/views.py`: claim withdraws bids; market views read live bids ✅
**Tests** in `api/tests.py`:
- `test_claim_withdraws_the_claimed_teams_standing_bids`: seed an unmanaged
  team's bid, claim through the endpoint, assert `withdrawn_at` is set and
  the auction's `current_price` is back to the reserve.
- `test_claim_rolls_back_withdrawal_when_claim_fails` (no team available
  means no bid is touched).
- `test_auction_market_hides_withdrawn_bids`
- `test_my_bids_excludes_withdrawn_bids`

### W4 — `world/ai_market.py`: pure helpers ✅
Constants and the four helpers, with no orchestrators yet.
**Tests** in `world/tests/test_ai_market.py` (new), using unsaved `Rider`
objects:
- `test_wants_a_rider_stronger_than_its_second_best_of_that_speciality`
- `test_does_not_want_a_rider_weaker_than_two_of_that_speciality`
- `test_thin_roster_wants_any_rider`
- `test_does_not_want_an_ageing_rider`
- `test_does_not_want_when_roster_plus_pending_reaches_max`
- `test_buyer_rank_prefers_thin_then_fewest_of_speciality_then_pk`
- `test_pick_listing_surplus_lists_weakest`
- `test_pick_listing_lists_oldest_ageing_non_top_rider`
- `test_pick_listing_never_lists_a_top_rider_of_their_speciality`
- `test_pick_listing_returns_none_when_nothing_qualifies`
- `test_headroom_keeps_the_cushion_and_subtracts_commitments`
- `test_headroom_is_zero_for_negative_balance`

### W5 — `world/ai_market.py`: `place_ai_bids` ✅
**Tests** in `world/tests/test_ai_market.py`, database-backed. Give teams a
balance with `economy.services.ensure_opening_balance(team, at=...)`.
- `test_ai_bids_reserve_on_a_needed_human_listing`
- `test_ai_ignores_listing_by_unmanaged_team`
- `test_ai_ignores_auction_that_already_has_a_live_bid`
- `test_ai_bids_on_auction_whose_only_bid_was_withdrawn`: proves the
  `~Exists` filter counts only live bids.
- `test_only_one_ai_team_bids_per_auction`
- `test_ai_skips_when_reserve_exceeds_headroom`
- `test_ai_commitments_reduce_headroom_within_one_pass`: two auctions; the
  team can afford one but not both.
- `test_ai_never_raises_after_being_outbid`: run the pass again after a
  human outbids; no new AI bid.
- `test_ai_skips_auction_past_deadline`

### W6 — `world/ai_market.py`: `list_ai_riders`
**Tests** in `world/tests/test_ai_market.py`:
- `test_ai_lists_surplus_rider_when_roster_above_normal`
- `test_ai_lists_ageing_rider_on_its_stagger_week_only`
- `test_ai_never_lists_below_min_roster`
- `test_ai_lists_at_most_one_open_auction_per_team`
- `test_ai_does_not_relist_rider_unsold_within_cooldown`
- `test_ai_skips_zero_reserve_rider`
- `test_managed_team_is_never_listed_for`

### W7 — `world/services.py`, `world/models.py`, migration 0015: wire into the tick
**Tests** in `world/tests/test_tick.py`:
- `test_tick_places_ai_bids_without_a_week_transition`: no season declared;
  a human listing receives an AI bid, and `run.ai_bids_placed == 1`.
- `test_tick_lists_ai_riders_once_when_catching_up_several_weeks`
- `test_tick_resolves_before_ai_bids`: an auction due this tick with no bid
  resolves `UNSOLD`, and the AI does not rescue it by bidding first.
- `test_ai_won_auction_moves_rider_and_money_end_to_end`: list, tick (AI
  bids), move the clock past the deadline, tick; the rider is on the AI
  team and both ledger rows exist.

### W8 — Documentation (see below); set spec and plan to `implemented`; archive both

## Execution order

1. **W1, then W2.** Pure data and service changes, fully covered by
   `transfers/` tests. W2's `resolve_auction` change is the correctness core;
   landing it first means everything after it builds on the safe reader.
   Commit after each.
2. **W3.** The claim path is the only way a bid gets withdrawn in
   production; proving it through the API before any AI exists isolates the
   concern. Commit.
3. **W4.** Pure helpers first: they hold every product rule, and they are
   the cheapest place to get those rules exactly right. Commit.
4. **W5, then W6.** Orchestrators on top of the proven helpers. Commit after
   each.
5. **W7.** Wiring and the migration last, once each piece works alone. Run
   the full suite (`/home/mario/dev/cycling-manager/.venv/bin/python -m pytest`)
   and commit.
6. **W8**, then open the PR.

Every commit leaves the suite green. W1–W3 change no behaviour until
something calls `withdraw_bids`, and W4–W6 add code that nothing calls until
W7.

## Documentation update (required, not optional)

- **`transfers/README.md`**
  - *What this app owns*: add `withdraw_bids`. Move AI trading from "still to
    come" to a line pointing at `world/README.md`.
  - *Auctions*, under the **`Bid`** bullet: `withdrawn_at` is the one
    permitted mutation, and why (Design decision 8); `Bid.objects.live()`
    is how every reader must query.
  - A new bullet, **Withdrawal on claim**: what `withdraw_bids` does, that it
    resets `current_price` but not the deadline, and that `api/` calls it
    inside the claim transaction.
  - *Future work*: remove the AI bidding item.
- **`world/README.md`**
  - *What this app owns*: replace "no AI decisions" with the AI market.
  - *How a tick works*: add a step after **Auctions** covering AI listing (on
    week-crossing ticks, last week only) and AI bidding (every tick), in that
    order, both after resolution.
  - New section, **The AI market (#30)**: the buying rule, the selling rule,
    the constants table, reserve-only bidding and its flip-proof reasoning,
    and the no-AI-to-AI rule.
  - Record that unmanaged balances were checked: about $330,000 left at the
    end of season 1, and about three seasons before AI buying dries up. That
    is the trigger for #45's sponsorship.
- **`api/README.md`**: the claim endpoint now withdraws the team's standing
  bids atomically, and the market and my-bids views show live bids only.
- **`AGENTS.md`**: the `world/` row gains "unmanaged teams bid on and list
  riders in the auction market"; the `transfers/` row drops "AI trading"
  from what is still to come, if it is listed there.
- **`specs/roadmap.md`**: mark #30 done in Part 1's *Transfers* row, and
  remove it from 2.3.
- `specs/ai-transfer-market.md` and this plan: `Status: implemented`, then
  move both to `specs/archive/`.

## Verification

Beyond the suite, prove it in a seeded world under `MockClock`:

```bash
export GAME_CLOCK_CLASS=world.clocks.MockClock
PY=/home/mario/dev/cycling-manager/.venv/bin/python
$PY scripts/dev_db.py && $PY manage.py migrate
$PY manage.py seed_user
$PY manage.py seed_teams --claim-for test@mail.com
$PY manage.py load_season seasons/season-1.example.json
$PY manage.py mock_clock set <season-1 starts_at>
$PY manage.py tick
```

1. **An AI bids on a human listing.** Log in as `test@mail.com`. On the
   Transfers screen, list the demo team's strongest young rider, whose
   reserve is well under an AI team's headroom. Run `tick`. The market shows
   one bid at the reserve, placed by an unmanaged team's name, and the
   latest `TickRun` has `ai_bids_placed >= 1`.
2. **The AI doesn't chase.** Outbid it from a second account (or place the
   bid through `place_bid` in a shell), then run `tick` again. No new AI
   bid appears.
3. **An AI wins.** On a fresh listing that only the AI bids on, run
   `mock_clock set` past the deadline, then `tick`. The rider is on the AI
   team, and Finances shows the income row.
4. **AI listings appear.** Run `mock_clock advance` a week and `tick`,
   repeated four times. The market shows a handful of listings from
   unmanaged teams, each an ageing or surplus rider, and at most one open
   listing per team.
5. **A claim withdraws bids.** With an AI bid leading an auction, register a
   second user and claim that exact team: claim takes the lowest-pk
   unmanaged team, so arrange for the bidder to be that team. The auction
   reverts to the reserve with no bids in its history, and `MyBidsView`
   for the new manager is empty.

**The likeliest failure** is a bid reader still using `auction.bids` or
`Bid.objects` without `.live()`, which lets a withdrawn bid win or show up.
Two checks catch it:

- `test_withdrawn_bid_never_wins_resolution` fails if `resolve_auction` is
  wrong. Before trusting it, confirm it fails with the `.live()` removed.
- After W3, run
  `grep -rn "\.bids\.\|Bid\.objects" --include=*.py api transfers world`.
  Every hit outside migrations and tests must read `live()`, or be the
  withdrawal `update` itself.

## Risks

| Risk | Mitigation |
|---|---|
| A bid reader misses `.live()`, so a withdrawn bid wins or shows as "my bid". | Design decision 11 (queryset method); the grep in *Verification*; one test per reader (W2, W3). |
| The implementer lets the AI bid `current_price + min_increment` on auctions with human bids, "to be more competitive". | Design decision 1 is explicit, and `test_ai_ignores_auction_that_already_has_a_live_bid` pins it. Doing this reopens the flip exploit the spec closed. |
| The "no live bid" filter is written as `.exclude(bids__withdrawn_at__isnull=True)`, which can also drop auctions with no bids. | The plan requires `~Exists(...)`. `test_ai_bids_reserve_on_a_needed_human_listing` (no bids), `test_ai_bids_on_auction_whose_only_bid_was_withdrawn` and `test_ai_ignores_auction_that_already_has_a_live_bid` cover all three cases. |
| The AI overcommits the same money across several auctions. | Pending top bids are subtracted from headroom within a pass and across ticks (Design decision 6); `test_ai_commitments_reduce_headroom_within_one_pass`. |
| The claim and the withdrawal land in separate transactions, and a tick in between resolves an auction to the new manager. | One outer `atomic()` in `ClaimTeamView` (Design decision 10); `test_claim_rolls_back_withdrawal_when_claim_fails`. |
| `seed_teams --claim-for` does not withdraw bids. | Accepted. It is a dev seeding command, normally run before any AI bid exists; `teams/` may not import `transfers/`. Note it in `teams/README.md` beside the claim section. |
| Unmanaged balances drain over several seasons, and AI demand silently stops. | Measured: about three seasons of headroom. `world/README.md` records the number and names #45's sponsorship as the fix when it bites. |
| AI rosters inflate until wage bills accelerate the drain. | `AI_MAX_ROSTER = 15` combined with surplus listing above 12. |
| AI listings flood the market. | The 4-week stagger, one open listing per team, and the 4-week relist cooldown. Verification step 4 is the eyeball check. |

## Open questions

None blocking. The constants in Design decision 13 are first calibrations.
Retune them after real play by editing the table and its tests together.
