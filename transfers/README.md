# Transfers

## What this app owns

Two pricing functions (`transfers/pricing.py`) and the free-agent market
(`transfers/services.py`):

- **Market value** — `pricing.market_value_for(rider)`, a rider's worth in
  whole credits. **No models, no migrations, no stored field.** Value is a
  pure function of a rider's visible attributes and age, recomputed on every
  read, never persisted. This is deliberate, not an early-stage gap: the
  spec ([#31](https://github.com/mario595/cycling-manager/issues/31))
  requires value to move the instant a rider's attributes move, and a stored
  column would be a cache that drifts from the arithmetic it summarizes.
- **Fees** — `pricing.signing_fee_for` / `pricing.severance_fee_for`, the
  two one-off prices that attach to a free-agent transfer (see *Free
  agents* below).
- **The free agent market** — `services.free_agents()`, the pool,
  `services.release_cost_for()` and the two locked write paths
  `sign_free_agent` / `release_rider`.
- **Rider auctions** ([#28](https://github.com/mario595/cycling-manager/issues/28))
  — `models.Auction` / `models.Bid`, `services.list_for_auction`,
  `services.place_bid` and `services.resolve_auction`. See *Auctions*
  below. Buying and selling riders outright, contracts and AI trading
  ([#30](https://github.com/mario595/cycling-manager/issues/30)) still to
  come.

`transfers/` owns one `models.py` — `Auction` and `Bid`, added for
auctions (#28), the first thing in this app that needs to persist across
ticks. Free agents still need no models of their own: the schema they need
lives on `Rider` itself (nullable `team`, plus the `joined_team_at` /
`unattached_since` stamps `riders/`'s `mark_team_change` writes), and the
pool is a pure derived query
(`Rider.objects.active().filter(team__isnull=True)`) with nothing to
remember.

## Free agents

The first built slice of the transfer market (#29). A **free agent** is any
active `Rider` with no team; the pool is
`Rider.objects.active().filter(team__isnull=True)`, ordered by name. Retired
riders are never returned. Two actions move riders in and out of it, both
row-locked write paths in `transfers/services.py` that charge an **injected**
`charge(rider, fee)` callback the way `hire_trainer` does — `transfers/` may
not import `economy/` (AGENTS.md), so the caller (`api/`) supplies the ledger
write (`economy.services.charge_transfer_fee`, a `TRANSFER_FEE` ledger entry
whose description records the rider and the direction).

- **Signing** (`sign_free_agent`) — a free agent comes in for
  `signing_fee_for(rider)` (60% of market value). The rider row is locked
  WITHOUT `skip_locked` (the caller wants this specific rider), teamlessness
  and active status are re-checked under the lock, then `ROSTER_CAP` (30) is
  re-checked under the same lock, then `charge()` runs. The whole thing is
  one transaction: a `charge()` raise rolls back the team move, keeping
  roster and ledger in step. A retired rider raises `RiderNotAvailable` and
  cannot be signed for any fee.
- **Releasing** (`release_rider`) — a roster rider goes out, charging
  `release_cost_for(team, rider, weeks_opened=...)`: full severance (30% of
  market value) for everyone **except** the claim-cooldown exemption.
- **Claim-cooldown exemption** — a rider who joined at the exact instant of
  the team's most recent claim (`joined_team_at == managed_since`, i.e. the
  roster `claim_team` generated, not someone signed in afterward) releases
  for **$0** while fewer than `CLAIM_COOLDOWN_WEEKS` (1) in-season weeks
  have opened since. `weeks_opened` is counted by the caller, never inside
  `transfers/` — counting `schedule/`'s `Week` rows would break the
  `transfers -> riders` only rule, so the caller passes the number both for
  the roster GET (`api/`) and for a release action (the same `now()`-to-
  boundary Week-row count `world/` uses). A team with no `managed_since` has
  no cooldown, so nothing is exempt.
- **Expiry** — every weekly tick, `world.services._expire_free_agents`
  selects active free agents that have been unattached for at least
  `EXPIRY_WEEKS` (8) in-season weeks **and** are priced at or below the
  bottom `EXPIRY_VALUE_PERCENTILE` (0.20) of the pool's values at that
  moment. A selected rider with at least one race result is **retired**,
  kept frozen with their history intact, and never returns to the pool. A
  selected rider who never raced is **deleted**. Value is never stored, so
  the cutoff is recomputed fresh each pass; a pool too small to have a
  meaningful bottom quintile simply expires nobody.

The pool, balances and costs reach the player through `api/`: the market
screen (`frontend/`) signs riders; the Roster shows each rider's current
`release_cost` — 0 when the cooldown shields them, severance after — on the
rider's detail panel.

## Auctions

The second built slice of the transfer market (#28) — the first thing in
this app that persists across ticks, hence `transfers/`'s first
`models.py` and migration. A manager lists any rider on their own roster;
other managers bid over a few real days; the highest bid at the deadline
buys the rider.

- **`Auction`** — `rider`, `seller_team`, `status` (`open` / `sold` /
  `unsold` / `cancelled`), `reserve_price`, `current_price`,
  `min_increment`, `deadline`, `listed_at`, `resolved_at`.
  **`reserve_price` and `min_increment` are frozen at listing time and
  never recomputed** from `market_value_for` — a manager reasoning about a
  displayed price must never be reasoning about a number that could move
  under them mid-auction, the way free agents' fees deliberately do
  recompute on every read. `current_price` starts at `reserve_price` and
  moves to the highest bid as they arrive. `one_open_auction_per_rider` (a
  partial unique constraint on `status="open"`) is the DB-level guard that
  a rider can only be listed once at a time — the same
  `condition=models.Q(...)` pattern `economy/`'s ledger constraints use.
  There is no FK to a winning team: the winner is derivable as the highest
  `Bid` on a `SOLD` auction, the same "don't cache what you can derive"
  reasoning `economy/README.md` gives for never storing a balance.
- **`Bid`** — `auction`, `bidder_team`, `amount`, `placed_at`. Never
  mutated or deleted after creation, the same append-only discipline
  `LedgerEntry`/`FanbaseEntry` use.
- **Pricing** (`pricing.py`) — `reserve_price_for(rider)` is
  `RESERVE_RATE` (50%) of `market_value_for(rider)`, rounded the same way
  every other price here rounds (nearest 1,000). 50% sits below
  `SIGNING_FEE_RATE` (60%): a seller choosing to auction accepts a lower
  guaranteed floor than a buyer would pay to sign the same rider outright,
  in exchange for the chance of a higher price through competition.
  `min_increment_for(reserve_price)` is `MIN_INCREMENT_RATE` (5%) of the
  **frozen** reserve, not the live current price — an increment that
  tracked the rising price would make late bidding in a hot auction
  require ever-larger jumps, punishing exactly the contested auctions the
  deadline extension exists to protect.
- **Listing** (`list_for_auction`) — locks the rider row, re-checks team
  ownership under the lock (mirrors `release_rider`'s ownership check),
  freezes the reserve and increment, and relies on
  `one_open_auction_per_rider` as the final guard against a race with a
  second concurrent listing (`IntegrityError` → `AuctionAlreadyExists`).
  `AUCTION_DURATION` (3 days) sets the deadline from the listing moment.
- **Bidding** (`place_bid`) — locks the `Auction` row, re-checks status and
  price under the lock, and requires the bid clear `current_price` (before
  any bid) or `current_price + min_increment` (once one exists). A team
  cannot bid on its own listing (`SelfBid`) — the one place in the game
  that can see both sides of a transaction and must refuse it itself,
  since nothing else stops a team transacting with itself. **Anti-snipe:**
  a bid landing within `EXTENSION_WINDOW` (1 hour) of the deadline pushes
  it forward by that same window — always `deadline += EXTENSION_WINDOW`,
  never reset to `at + EXTENSION_WINDOW`, so repeated late bids compound
  predictably rather than each resetting to a fixed offset. Bidding never
  touches `economy/` — no money moves until resolution; affordability is a
  plain `balance_for` read the caller (`api/`) makes before calling this at
  all, the same shape `sign_free_agent`'s `charge` callback checks, just
  without a callback since nothing is charged yet.
- **Bidding is not anonymous.** Every `Bid` row already carries
  `bidder_team`, and `api/`'s `AuctionMarketView` serializes each
  auction's full history — every bid, newest first, with the bidding
  team's name — not just the current leader. The original scoping
  decision was to keep it anonymous (a coordination-risk concern in a
  thin, early market with few human players); revisited before this
  ticket shipped, in favour of transparency. See the archived spec's
  *Rules and edge cases* for both sides of that call.
- **Resolution** (`resolve_auction`) — the one entry point `world/` calls,
  once per tick, on every auction `due_auctions(at)` returns (`OPEN` and
  past its deadline). Locks the `Auction` and `Rider` rows together and:
  re-checks the auction is still due (a bid can have extended it between
  the tick's query and this lock — then this is a no-op, left for a later
  tick); cancels with no money moved if the rider has already left the
  seller's roster some other way (a release, say — whichever mechanism
  moves the rider first wins, spec's *Rules and edge cases*); goes
  `UNSOLD` with no callback calls if there is no bid; re-checks `ROSTER_CAP`
  against the winning bidder's **current** roster and goes `UNSOLD` rather
  than violate it if they have since filled up; otherwise runs
  `charge_buyer` then `pay_seller` (buyer debited before seller credited,
  so a `charge_buyer` raise — the accepted overspend loophole, since a bid
  checks the balance only at bid time, never escrowed — rolls the whole
  transaction back and leaves the auction `OPEN` for the next tick to
  retry rather than silently losing a sale the seller was owed), moves the
  rider, and marks the auction `SOLD`. `transfers/` may not import
  `economy/`, so both callbacks are injected exactly the way
  `sign_free_agent`'s `charge` is — `world/README.md` has the wiring.
- **Why resolution is not a week-boundary step.** Every other per-week
  economic step in the tick (`world/README.md`, *How a tick works*) is
  keyed to a crossed `Week`. An auction's deadline is deliberately
  wall-clock real time instead — it decouples the market from the race
  calendar and stays fair to managers in different timezones — so
  resolution is its own unconditional step in `tick()`, run every tick
  regardless of what else is due, never folded into the week-transition
  loop. See `world/README.md`.

## Value vs salary

The game already prices riders once: `riders.pricing.weekly_salary_for`,
what a rider costs to keep, stored at generation and frozen for the
season. Market value is a **second** price — what a rider is worth — and
the two share one input but not their shape:

- **Shared:** `riders.pricing.strength(rider)`, the five engine attributes
  weighted by speciality. Both prices import it unchanged — one definition
  of "how good is this rider".
- **Not shared:** age. Salary's `age_multiplier` is a mild, symmetric ±15%
  penalty around a 24-32 prime band — a wage cares about current fitness
  for the job. Value's `career_horizon` is monotonically decreasing from
  age 23 onward, because a valuation prices in years of career remaining,
  not current form. A 22-year-old and a 30-year-old of identical ability
  have near-identical salaries but very different values — that gap is the
  point (see the spec's *Rules and edge cases*).

**Never express value as a multiple of salary** (`weekly_salary_for(rider)
× k`). That would inherit salary's wrong-shaped age curve and couple the
two prices together, so a future salary retune
([#26](https://github.com/mario595/cycling-manager/issues/26)) would
silently move every valuation. Keep two formulas over the same `strength()`,
not one wrapping the other.

Rounding also differs: salary rounds to the nearest 50 (right for a weekly
figure in the hundreds); value rounds to the nearest 1,000 (`_round_to_nearest_1000`,
local to this app — a capital sum in the hundreds of thousands rounded to 50
reads as false precision).

## Never a hidden trait

Like salary, market value reads only visible fields — the five engine
attributes and `age`. `potential`, `peak_age`, `decline_rate`,
`injury_proneness`, `training_affinity`, `recovery_rate` and `growth_debt`
are never read here. Pricing off a hidden trait would silently expose it
through a number the player can already see, which `riders/README.md`'s
*Visible vs hidden* treats as a defect everywhere it could happen. Two
riders identical on the roster page must be worth the same, even if one has
more room to grow. `transfers/tests/test_pricing.py::test_no_hidden_trait_is_read`
guards this directly.

## Calibration

`VALUE_AT_MIN_STRENGTH` and `VALUE_AT_MAX_STRENGTH` were picked by sampling
`riders.generation.generate_rider` over a large seeded population, the same
method `riders/pricing.py`'s own constants use — not by reasoning about the
theoretical 1-100 range, since a generated rider's attributes cluster well
under it in practice. The anchor: an average generated rider's market value
lands at roughly one twelve-week season of their own wages
(`transfers/tests/test_pricing.py::test_average_value_is_about_one_season_of_wages`).
A second calibration test pins that value's spread across a generated
population is wider than salary's, proving the age skew actually does
something rather than just rescaling the same curve
(`test_generated_roster_value_spans_wider_than_salary`).

**Retuning the formula means re-running these two tests until they pass
again, not eyeballing the constants.** If `riders.pricing.strength()` or
`riders.generation.generate_rider`'s quality spread ever changes, both
salary's and value's calibration tests should be re-checked together —
they are sampling the same population.

## What `transfers/` may import

Only `riders/` (`AGENTS.md`'s dependency direction: `transfers -> riders`).
Not `economy/`, not `teams/`, not `world/`, not `api/`. `api/` is the only
app that imports `transfers/`, the same one-way rule every other domain
follows.

## Future work / possible improvements

Market value was built to serve four consumers; auctions (#28) is the
second to land, after free agents:

- **AI bidding logic.** [#30](https://github.com/mario595/cycling-manager/issues/30)
  needs some number to decide what to bid and when to stop; market value
  is it.
- **Forced sales under insolvency.** [#27](https://github.com/mario595/cycling-manager/issues/27)
  needs a price when there is no auction to discover one.
- **Season-boundary salary renegotiation.** [#26](https://github.com/mario595/cycling-manager/issues/26)
  needs a value to renegotiate a rider's salary against.

The Roster screen shows `market_value_for` directly (`api/README.md`,
`frontend/README.md`); inside this app the free-agent signing/severance
fees and the auction reserve/increment are the arithmetic that builds on
it.
