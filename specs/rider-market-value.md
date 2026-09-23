# Rider market value

**Status:** proposed
**Domain(s):** `transfers/` (new)
**One-liner:** Every rider has a visible market value — what the game thinks they're worth — separate from what they cost to keep.

## Why this exists

Salary ([#25](https://github.com/mario595/cycling-manager/issues/25)) tells a
manager what a rider costs to run. It says nothing about what that rider is
*worth* — what another team should have to pay to take them. Without that
number, nobody building the transfer market has anything to build against:
an AI team ([#30](https://github.com/mario595/cycling-manager/issues/30)) has
no basis for deciding what to bid, and a thin auction
([#28](https://github.com/mario595/cycling-manager/issues/28)) — one bidder,
or none — has no floor stopping a strong rider selling for next to nothing.
Market value is designed to serve both: an AI team's bidding logic reads it
directly, and it's the natural candidate for an auction's reserve price later.
Neither is built here — this ticket only produces the number other systems
will need.

It also gives the player something they don't have today: a sense of whether
their roster is an asset growing in value or a wage bill quietly outrunning
what it's worth.

## Player experience

A manager opens their roster and sees, next to each rider, what that rider
is worth on the market — a second dollar figure alongside the weekly salary
they already see. A young rider having a strong season is worth visibly more
than they were a few weeks ago, without the manager having done anything
except watch them train and race well. An ageing rider who's past their peak
is worth less than their salary might suggest, even if their attributes
haven't dropped much yet — value already prices in how little time they have
left. The roster also shows one total: what the whole squad is worth,
sitting next to the weekly wage bill Finances already shows, so a manager
can see at a glance whether their squad is an appreciating asset or a
depreciating one.

Nothing can be done with this number yet. A rider can't be sold for it, and
no other team can see it. It's a number a manager checks and reasons about,
not a button.

## In scope

1. Every rider has a market value, visible on the roster screen next to
   that rider's salary.
2. The roster screen shows one squad-value total, alongside the existing
   wage-bill total.
3. Value is derived from the same visible inputs salary already uses — the
   five engine attributes and age — nothing hidden feeds it. Two riders who
   look identical on the roster page are worth the same.
4. Value weighs age much more heavily than salary does: a young rider with
   room ahead of them is worth far more than an old rider of equal current
   ability, even though the two might cost about the same to keep.
5. Value recalculates continuously — it always reflects the rider's current
   attributes and age, unlike salary, which is fixed for the season. A
   rider who improves through training or a good season is worth more the
   next time the roster is checked, with no separate action required.

## Out of scope

- **Selling a rider for their market value, or any other transaction.**
  That's the transfer market itself ([#28](https://github.com/mario595/cycling-manager/issues/28)),
  not this ticket. Value is informational only here.
- **Any team seeing another team's riders' value.** Rosters outside your own
  aren't browsable today. Whether and how a rival's value is shown belongs
  to whatever ticket makes rosters browsable ([#28](https://github.com/mario595/cycling-manager/issues/28)/[#29](https://github.com/mario595/cycling-manager/issues/29)).
- **A reserve price, or any auction mechanic.** Value is built to be usable
  as one later, but no floor, percentage, or bidding rule is defined here —
  that's [#28](https://github.com/mario595/cycling-manager/issues/28)'s decision.
- **AI bidding logic.** [#30](https://github.com/mario595/cycling-manager/issues/30)
  will read this value to decide what to bid; deciding how it bids is not
  this ticket.
- **Feeding next season's salary.** Whether a rider's value at season end
  changes what they cost to keep is [#26](https://github.com/mario595/cycling-manager/issues/26)'s
  decision, not this one's.
- **A range or estimate band.** Value is shown as a single number, the same
  way salary is — not a "$380k–$450k" spread.
- **Recency or form-based valuation** — a hot streak or a bad race doesn't
  move value beyond however it already moved the rider's attributes. There
  is no separate "in-form" bonus.

## Rules and edge cases

- **A freshly generated rider has a value the moment they exist**, the same
  way they have a salary the moment they exist — there's no rider without
  one.
- **Value never uses a hidden trait.** `potential`, `peak_age`,
  `decline_rate` and the rest stay invisible to pricing, the same rule
  salary already follows and for the same reason: pricing off a hidden
  trait would silently expose it through a number the player can already
  see. Two riders who look the same on the roster page must be worth the
  same, even if one has more room to grow.
- **Value and salary are allowed to diverge, and are expected to.** A young,
  promising rider can be cheap to keep (salary tracks current ability) but
  worth a lot (value weighs their age heavily) — that gap is the point:
  it's what should make a manager want to hold onto a promising young rider
  rather than treat the roster as interchangeable.
- **Value is not a stored, frozen number like salary.** It's read fresh
  every time it's shown, off the rider's attributes and age at that moment.
  A rider who trains well one week is worth more the next time anyone
  looks, with nothing needing to run to make that true.
- **An old, declined rider's value can fall close to zero.** Nothing floors
  it above some minimum — a rider far past their best, with little season
  left, is worth very little, and the number should say so plainly rather
  than being propped up to look respectable.

## Decisions taken

- Value reuses the same visible inputs as salary (attributes + age), not an
  independent formula — keeps "identical riders cost/are worth the same"
  consistent across both numbers. Decided in scoping.
- Value is shown as an exact number, own roster only — matches how salary
  is already shown, and rival rosters aren't browsable yet regardless.
  Decided in scoping.
- Value recomputes live rather than being frozen at season start or
  recalculated only at the weekly tick — the whole point is that it moves
  when the rider does. Decided in scoping.
- The roster screen also shows a squad-value total, mirroring the
  wage-bill total already on Finances. Decided in scoping.
- Value does nothing mechanical in this ticket — purely informational,
  consumed later by #28 (reserve price), #30 (AI bidding), #27 (forced
  sales) and #26 (renegotiation). Decided in scoping.
- The spec names "usable as a future auction reserve" as one of the reasons
  this exists, even though no reserve mechanic is built here, so #28 doesn't
  have to re-derive where its floor price comes from. Decided in scoping.

## Open questions

None — the scoping round settled every open question raised on the issue.

## Deferred

- **Reserve price / minimum auction price.** Value is built to support this,
  but the mechanism — whether it's the full value or a percentage of it,
  whether it's shown to bidders — is [#28](https://github.com/mario595/cycling-manager/issues/28)'s
  decision.
- **AI bidding logic.** Reads this value once it exists.
  [#30](https://github.com/mario595/cycling-manager/issues/30).
- **Selling a rider for their value, or any transaction.**
  [#28](https://github.com/mario595/cycling-manager/issues/28)/[#29](https://github.com/mario595/cycling-manager/issues/29).
- **Value feeding a season-boundary salary renegotiation.**
  [#26](https://github.com/mario595/cycling-manager/issues/26).
- **Showing value for riders outside your own roster.** Waits on rosters
  becoming browsable at all.
