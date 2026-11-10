# Transfers

## What this app owns

Two pricing functions (`transfers/pricing.py`) and the two write paths the
market needs (`transfers/services.py`): the free-agent market and rider
auctions.

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
  `services.place_bid`, `services.resolve_auction`,
  `services.withdraw_bids` and `services.cancel_listings`. See *Auctions* and
  *Withdrawal and cancellation on claim* below.
  Buying and selling riders outright and contracts still to come. **Who the
  other bidders are** — unmanaged teams playing themselves — belongs to
  `world/`, not here: `world/README.md`, *The AI market (#30)*.

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
`Rider.objects.active().filter(team__isnull=True, development_squad__isnull=True)`,
ordered by name. Retired riders are never returned, and neither are
development squad riders (#33) — a `team = NULL` rider with
`development_squad` set is still in a squad, not the market, and
`sign_free_agent` refuses one under the rider lock the same way it refuses a
retired rider. A squad rider reaches the pool one way only, and only having
served their full spell: as a **graduate**, released by a closing squad, a
lapsed decision window or an unsold auction, each of which stamps
`unattached_since` on the way out (`riders/README.md`, *Youth triage*) — the
same stamp every other released or unsigned rider carries, so a youth nobody
wants expires by the same rule as anyone else. A rider still *in* the squad is
never in the pool: closing discards them. Two actions
move riders in and out of the pool, both
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

**"Own" is `belongs_to(rider, team)`, not `rider.team == team` (#34).** The
sale side was written when the only thing a manager could sell was a rider on
their senior roster, so the roster check *was* the ownership check. A squad
graduate (`riders/README.md`, *Youth triage*) is sellable and is **not** on
that roster — they carry `development_squad` and no `team` — so the comparison
is now `riders.youth_triage.belongs_to`, which is true for a roster rider
*and* for a graduate of the team that owns them. Every caller that used to ask
"is this rider on that team?" asks `belongs_to` instead: `list_for_auction`
and `resolve_auction`. `transfers -> riders` is allowed, so this is an import,
not a callback.

**A graduate can therefore be listed without occupying a roster place.** This
was the point of the split: the squad's `places` are for riders it is still
developing, and a finished rider who is taking one is blocking the intake
that would replace them. Listing a rider *in* a squad is still refused — they
are not a product yet, and `belongs_to` is false for them, which is the same
rule doing the work rather than a new check.

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
- **`forced`** (#27) is a flag on `Auction`: a sale under insolvency (see
  *Forced sales* below). Existing listings are all `False`.
- **`Bid`** — `auction`, `bidder_team`, `amount`, `placed_at`,
  `withdrawn_at`. Append-only **except** that one field: a claim stamps
  `withdrawn_at` and never clears it, so a withdrawn bid stays in the
  history as a record while reading as never having happened
  (see *Withdrawal and cancellation on claim* below). **Every reader of bids must call
  `Bid.objects.live()`** (or `auction.bids.live()`, which inherits it) —
  that filters `withdrawn_at IS NULL`. `Bid.objects` is an ordinary
  `BidQuerySet` manager that *provides* `.live()`; it does not apply it for
  you, so `Bid.objects.filter(...)` and a bare `auction.bids.all()` still
  hand back withdrawn bids. Call `.live()` rather than writing
  `.filter(withdrawn_at__isnull=True)` at each call site — a reader that
  forgets is exactly how a withdrawn bid ends up winning an auction.
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
  **A `SOLD` graduate leaves the squad**: the sale gives them a team, so
  `development_squad` is cleared rather than left pointing at a squad that no
  longer owns them. An `UNSOLD` one is the interesting case — the auction ends
  and the rider is still the squad's, so a graduate whose decision window has
  since closed is released to the free-agent pool in the same step
  (`riders.youth_triage.release_graduates`), stamped `unattached_since` like
  any other expiry. A graduate still **inside** their window goes back to
  being listed-or-not as the manager left them.
- **Why resolution is not a week-boundary step.** Every other per-week
  economic step in the tick (`world/README.md`, *How a tick works*) is
  keyed to a crossed `Week`. An auction's deadline is deliberately
  wall-clock real time instead — it decouples the market from the race
  calendar and stays fair to managers in different timezones — so
  resolution is its own unconditional step in `tick()`, run every tick
  regardless of what else is due, never folded into the week-transition
  loop. See `world/README.md`.
- **Cancellation** (`cancel_open_auctions`) — the other way an auction can
  end, and the one that needs no buyer
  ([#42](https://github.com/mario595/cycling-manager/issues/42)). It flips
  every `OPEN` auction of the given rider ids to `CANCELLED` in one UPDATE,
  stamping `resolved_at` and **moving no money**: a bid was never
  escrowed (see *Bidding* above — affordability is checked at bid time, not
  reserved), so there is nothing to refund, and a team whose rider is sold
  out from under it simply never got the rider. It is idempotent, so a tick
  that catches up several boundaries late can call it twice for one rider
  and the second call writes nothing.

  The one caller is a rider **retiring at the season close**
  (`riders/README.md`, *Retiring by age*): `world.services.tick()` passes
  the riders `retire_due_riders()` just released. Without it their auctions
  would keep accepting bids for a rider who is no longer in the game, and
  `resolve_auction` — which only sees "past its deadline" — would settle
  them as a sale weeks later. The alternative, a `retired_at` re-check inside
  `resolve_auction` (which already handles the released-into-the-pool case
  above), was rejected: the same re-check would silently unsell the
  rider from the selling team's roster mid-season, which is a different bug
  with a different fix, and it would leave the auction open — visibly
  bidding — until its deadline. Both functions run in one transaction with
  the retirement itself, so there is no window in which the rider has left
  and the auction is still open.
- **`cancel_unowned_listings(seller_team, *, at)`** — cancellation for the
  case where the team can no longer sell what it listed, rather than where the
  *rider* has gone
  ([#34](https://github.com/mario595/cycling-manager/issues/34)). It cancels
  every `OPEN` auction the team is selling whose rider no longer passes
  `belongs_to` for that team, and nothing else: a listing of a rider the team
  still owns is left alone.

  Its one caller is **closing a development squad**, which releases the
  squad's graduates to the pool. Their auctions would otherwise stay biddable
  until the deadline — managers would keep bidding on a rider already in the
  free-agent pool, and the winner would be refused at resolve time by the very
  ownership check that would have caught it days earlier.

  **Forced sales are excluded** (`forced=False` in its query). A forced sale
  takes the rider off the roster at listing (#27), so `belongs_to` is false
  for them by design; without the exclusion, closing a squad would cancel a
  sale the insolvent team is owed.

  A **claim** does not come here. It cancels every listing the team holds —
  graduates', roster riders' and forced sales alike — through
  `cancel_listings`, which keys on `seller_team` alone
  ([#114](https://github.com/mario595/cycling-manager/issues/114); see
  *Withdrawal and cancellation on claim* below). #34 originally fixed #114 a
  second time, by calling `cancel_unowned_listings` from the claim too; the
  two fixes met in the merge with master and the claim kept `cancel_listings`,
  the one that also catches forced sales. No money moves here either, so an
  auction cancelled with bids standing refunds nothing — the same property as
  `cancel_open_auctions`.

  There are **three callers** of cancellation, differing only in what they
  key on: `cancel_open_auctions(rider_ids, *, at)` for retirement,
  `cancel_listings(team, *, at)` for a claim, and
  `cancel_unowned_listings(seller_team, *, at)` for a squad close. All end in
  one conditional UPDATE moving no money, so every reader that filters on an
  `OPEN` auction drops the cancelled ones without any further change.

## Withdrawal and cancellation on claim

A team that nobody manages can hold live bids from when it was managed (or
before). When a manager claims that team they must not inherit an
in-progress purchase, so the claim withdraws them —
`withdraw_bids(team, *, at)`,
[#30](https://github.com/mario595/cycling-manager/issues/30):

- It withdraws **every** live bid the team holds on an `OPEN` auction, not
  just the leading one, and whoever placed it. A non-top bid can never win
  anyway, and "every" avoids having to decide "which is top" under a lock.
- Each affected auction's `current_price` is reset to its highest remaining
  live bid, or to the reserve if none remain, so the auction reads exactly
  as if those bids had never been made.
- **Deadlines are left alone.** Undoing an anti-snipe extension would need a
  record of which extension each bid caused, and a slightly longer auction
  harms nobody.
- Rows are locked in pk order, so two claims touching overlapping auctions
  take the same locks in the same order and cannot deadlock.
- `api/`'s `ClaimTeamView` calls it **inside the claim's own transaction**
  (`api/README.md`), so a claimed team can never exist with its old bids
  still live and have a tick resolve one to the new manager in between.

### The sale side

The other half of the same sentence — a new manager must not inherit an
auction the team was running — is `cancel_listings(team, *, at)`,
[#114](https://github.com/mario595/cycling-manager/issues/114): every `OPEN`
auction `team` is selling becomes `CANCELLED` with `resolved_at = at`, and no
money moves, on the same reasoning as `cancel_open_auctions` above.

It is keyed by **`seller_team`**, not by rider ids, and that is the load-bearing
detail. By the time `api/`'s `ClaimTeamView` calls it, `claim_team` has already
detached the old roster, so "the team's riders" is the *new* roster — collecting
ids from `team.riders` and handing them to `cancel_open_auctions` would cancel
nothing at all, silently. The listing belongs to the seller, so it is keyed by
the seller, the same shape as `withdraw_bids` beside it.

The **bids are not withdrawn**. `withdrawn_at` records that a claim took a
bid back; these bids were not taken back, the auction ended. They stay as
history, and every reader that counts them filters on an `OPEN` auction — the
AI's committed headroom, `MyBidsView`, `AuctionMarketView` — so they stop
counting without being stamped. Both calls sit **inside the claim's own
transaction**, so a claim that fails cancels nothing.

`seed_teams --claim-for` and `release_team` deliberately do neither: seeding
runs on fresh teams with no listings, `release_team` touches nothing but the
manager link by design, and `teams/` may not import `transfers/`. Those notes
live with the claim itself, in `teams/README.md`.

## Forced sales

A team under the insolvency ladder (`economy/README.md`, *Insolvency*) can sell
a rider it cannot afford (#27). `force_list_for_auction(team, rider_id, *,
at)` is the write path; `api/`'s `ForceSellView` gates it on the team being
embargoed.

- **The rider leaves the roster at listing.** `team` becomes `NULL` at once,
  so the wage stops at once (`charge_weekly_wages` sums by `team`) and every
  roster-shaped query drops the rider with no other change. The alternative —
  keeping the rider on the roster and excluding them from payroll — needs every
  such query to remember the exclusion, and one that forgot would charge or
  race a rider the manager has already given up.
- **A limbo rider is not a free agent.** `free_agents()` excludes any rider
  with an open forced auction, and `sign_free_agent` refuses one under its lock
  ("That rider is being sold"). Once the auction stops being `OPEN`, an unsold
  rider is an ordinary free agent.
- **`resolve_auction` has one forced branch.** "Still available" means
  `team IS NULL and not retired`, instead of "still on the seller's roster".
  Sold, the buyer is charged, the seller paid, and the rider moves; unsold
  (no bid, or the winner at `ROSTER_CAP`) touches no rider.
- **No severance, and no way back.** There is no charge callback at all, and
  the listing cannot be withdrawn. This is the point: an unsold rider is a
  sale at zero, so a desperate manager always has a lever, and one cannot list
  their best rider hoping for a rescue bid.
- **A rider already on voluntary auction is converted**, not duplicated: the
  existing row gets `forced = True`, keeping its reserve, deadline and bids.
  `one_open_auction_per_rider` forbids a second row, and cancelling would
  throw away the seller's bids.
- **The roster floor.** A forced sale is refused (`RosterAtFloor`) when the
  roster is at `FORCED_SALE_ROSTER_FLOOR` (4) or fewer. It equals
  `racing.models.SQUAD_SIZE`, duplicated because `transfers/` may not import
  `racing/`; a test pins the equality. The whole roster is locked, in pk
  order, **before** it is counted: two concurrent forced sales from five riders
  must not both pass and leave three.
- `withdraw_bids` is also called when a case opens (`world/`), so an insolvent
  team never carries an in-progress purchase.

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

**`_MIN_AGE` dropped from 18 to 17 alongside the model's own age floor
(#33)** — youth intake generates riders as young as 17, and `career_horizon`
duplicates the model's age validators the same way `riders.pricing`'s own
`_MIN_AGE`/`_MAX_AGE` do, so both had to move together or a 17-year-old's
value would compute against a floor the model no longer enforces.
`career_horizon` is flat below `_PEAK_VALUE_AGE` (23) regardless, so the
change is for consistency with the model rather than a behaviour change at
17 itself.

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
second to land, after free agents, and AI bidding (#30) the third:

- **Forced sales under insolvency.** **Done** — see *Forced sales* above
  (#27). They run as auctions with the ordinary reserve, so no separate price
  was needed.
- **Season-boundary salary renegotiation.** [#26](https://github.com/mario595/cycling-manager/issues/26)
  needs a value to renegotiate a rider's salary against.

The Roster screen shows `market_value_for` directly (`api/README.md`,
`frontend/README.md`); inside this app the free-agent signing/severance
fees and the auction reserve/increment are the arithmetic that builds on
it.
