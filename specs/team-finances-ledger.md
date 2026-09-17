# Team finances ledger

**Status:** proposed
**Domain(s):** `economy` (new)
**One-liner:** Every team has a running balance, built from an append-only history of what came in and went out, starting with the one thing that goes out every week: wages.

## Why this exists

The game currently has no money at all. That gap is now blocking finished
work rather than sitting quietly: trainers were shipped free because pricing
them ([#69](https://github.com/mario595/cycling-manager/issues/69)) has
nothing to plug into; claiming a team was specced to reset its money to a
standard amount but that decision has never been implementable; and
insolvency ([#27](https://github.com/mario595/cycling-manager/issues/27))
has been designed in detail on paper with nothing yet to make it real.

This ticket gives every team a balance and a weekly cost. It adds the first
outgoing — a flat wage per rider, debited every week — and shows the player
where their money went. It deliberately adds no income and no way to spend:
those are separate, better-scoped tickets, and this one exists to prove the
ledger itself, not the whole economy at once.

## Player experience

A manager opens a new "Finances" screen and sees a balance — the same
starting amount every team in the game has, managed or not. Below it, a
list of every transaction that has touched the team's account, newest
first: when it happened, what it was, how much, and the balance afterward.

Each game week, when the world's clock crosses into a new week, every team
is charged its wage bill in one line: "Weekly wages — 14,400 credits,"
dated to that week. A team with twelve riders pays for twelve riders; a
team that has just released half its roster pays less next week. If the
clock has been fast-forwarded through several weeks at once, the player
sees one dated entry per week that was skipped, not one lump sum and not
nothing.

If a team's balance goes negative, the finances screen shows it plainly —
the number goes red, or carries a warning — but nothing else happens yet.
Wages are still paid in full. There is no penalty, no locked features, no
team taken away. That is deliberate: what happens to an insolvent team is
its own feature, not an afterthought bolted onto this one.

When a player claims an unmanaged team, its balance resets to the standard
starting amount, the same way its roster resets. The team's financial
history from before the claim is not erased — it stays visible below a new
entry marking the handover — the same way a claimed team keeps its past
race results while starting fresh on the roster.

## In scope

1. Every team — managed or unmanaged — has a single running balance.
2. The balance is never stored directly; it is always the sum of a
   complete, ordered history of transactions. Nothing about a team's
   finances is true unless it is in that history.
3. A newly created team starts with the same fixed balance as every other
   team.
4. Claiming an unmanaged team resets its balance to that same standard
   starting amount. The team's prior transaction history remains visible,
   with a new entry marking the takeover and the balance change it caused.
5. Every rider on a team's roster costs the same flat weekly wage.
6. Once each game week, every team is charged the combined wage bill for
   its current roster, as a single transaction dated to that week.
7. If the game clock advances through more than one week at once, a
   separate, correctly dated wage transaction is recorded for each week
   that passed — never a single combined charge, never a skipped week.
8. A team's balance can go below zero. Wages are charged in full
   regardless of whether the team can afford them.
9. A player can view their team's current balance and its full
   transaction history, newest first.
10. A negative balance is visibly flagged to the player as a warning.
11. Every transaction states what happened, when, how much, and the
    resulting balance — enough for a player to reconstruct their financial
    history without a separate audit.

## Out of scope

- **Any source of income** (prize money, sponsorship, merchandise,
  transfers) — belongs to
  [#19](https://github.com/mario595/cycling-manager/issues/19),
  [#21](https://github.com/mario595/cycling-manager/issues/21),
  [#22](https://github.com/mario595/cycling-manager/issues/22)/[#23](https://github.com/mario595/cycling-manager/issues/23).
  After this ticket, every team's balance only goes down — expected and
  acceptable while the game has no live players yet.
- **Wages that vary by rider.** Every rider costs the same flat amount
  here. Salaries derived from a rider's attributes or performance belong to
  [#25](https://github.com/mario595/cycling-manager/issues/25).
- **Trainer salaries.** Hiring a trainer stays free until
  [#69](https://github.com/mario595/cycling-manager/issues/69).
  [#69](https://github.com/mario595/cycling-manager/issues/69) is what
  points a trainer's cost at this ledger.
- **Consequences of a negative balance** beyond the warning — no
  transfer embargo, no forced sales, no losing the team. That whole
  escalation belongs to
  [#27](https://github.com/mario595/cycling-manager/issues/27), which
  already has its own design.
- **Any way for a player to spend or move money.** This ticket is a
  readout. The first thing worth spending on arrives with
  [#69](https://github.com/mario595/cycling-manager/issues/69) or the
  transfer market.
- **A projection or "runway" ("N weeks of money left") calculation.**
  Worth adding once there is an income stream to make it interesting;
  today it would just restate the wage bill.
- **Development squad and transfer-fee outgoings.** Neither feature
  exists yet.
- **Per-rider line items in the transaction history.** A week's wages are
  one entry, not one per rider — see *Rules and edge cases*.

## Rules and edge cases

- **Wages are charged once per week boundary, computed off whoever is on
  the roster at that moment.** A rider bought, sold, or released between
  wage days does not get pro-rated; they are simply on the roster or not
  when wages next run.
- **A team with zero riders is charged nothing that week** — the wage bill
  is a sum over the current roster, and an empty roster sums to zero. This
  is not expected to happen in practice today, but the rule falls out
  naturally rather than needing a special case.
- **A week's wage bill is always one transaction, not one per rider.** A
  twelve-rider team produces one "Weekly wages" entry for the combined
  amount, not twelve identical-looking entries. The total is derivable
  from the roster at the time; the history does not need to restate it
  rider by rider.
- **A caught-up clock produces one wage entry per week skipped, each
  correctly dated to its own week** — never a single lump sum covering
  several weeks, and never silently dropped weeks. A manager returning
  after being away sees exactly what they missed.
- **The ledger is append-only.** Nothing about a team's balance is ever
  corrected by editing or deleting a past entry — a mistake or a design
  change is corrected by adding a new entry that adjusts the balance, the
  same way a real accounting ledger works. Claiming a team's reset (rule
  4) is the first example of this: it is a new entry, not a deletion of
  the old ones.
- **Unmanaged teams accrue wages the same as managed ones.** The economy
  applies uniformly; there is no special case today for a team with no
  human behind it. (A later feature may give unmanaged teams AI-driven
  income or spending — out of scope here.)
- **Negative balances are unbounded below.** There is no floor, no clamp
  to zero, and no automatic action. The number is simply shown as a
  warning.

## Decisions taken

- **This ticket ships the ledger plus exactly one outgoing — the flat
  weekly wage bill** — rather than the ledger alone or the ledger plus
  income. A ledger nothing writes to is invisible to the player; pulling
  in prize money as well would fold a second, separately-designed feature
  (#19) into this one.
- **The manager can take no action on their finances in this ticket.** No
  budget allocation, no spending screen. The ledger is a consequence of
  decisions made elsewhere (roster size), not itself a decision point.
- **A negative balance is shown and survivable, not prevented or
  punished.** Wages are always paid in full; the balance can go negative;
  the only consequence here is a visible warning. The full escalation
  ladder is #27's job, already designed — this ticket must not invent a
  competing, undesigned punishment.
- **Currency is an abstract whole-number "credit," not a real-world
  currency and never a decimal.** Avoids implying real-world scale, sidesteps
  rounding, and needs no localisation.
- **Every team starts at the same fixed balance**, and claiming a team
  resets it to that same amount via a new ledger entry (never a deletion).
  This is [#46](https://github.com/mario595/cycling-manager/issues/46)'s
  already-recorded decision, finally implementable now the ledger exists.
- **Wages are flat per rider in this ticket**, not derived from attributes.
  #20 proves the mechanism (a recurring per-roster charge); #25 owns making
  the amount meaningful.
- **A whole season's worth of wages does not need to be affordable from
  the starting balance** — the game has no live players yet, and the point
  of this ticket is to make the drain visible, not to balance the economy
  end-to-end. That balancing work happens once #19 exists.
- **History is one entry per event, not one per rider paid.** A week's
  wage run is a single dated entry for the total; per-rider detail is not
  needed to answer "where did my money go."

## Open questions

None — the one open question the originating ticket flagged (what happens
when a team goes broke) is answered above: it is out of scope, and belongs
entirely to [#27](https://github.com/mario595/cycling-manager/issues/27).

## Deferred

- **Prize money, sponsorship, merchandise** — no income exists until
  [#19](https://github.com/mario595/cycling-manager/issues/19),
  [#21](https://github.com/mario595/cycling-manager/issues/21),
  [#22](https://github.com/mario595/cycling-manager/issues/22)/[#23](https://github.com/mario595/cycling-manager/issues/23)
  land; this ticket is deliberately one-directional.
- **Per-rider salaries** — [#25](https://github.com/mario595/cycling-manager/issues/25),
  waiting on this ledger to exist.
- **Trainer pricing** — [#69](https://github.com/mario595/cycling-manager/issues/69),
  same reason.
- **Insolvency consequences** — [#27](https://github.com/mario595/cycling-manager/issues/27),
  already designed, waiting on this ledger and on wages.
- **Runway projection** — worth adding once income exists to make the
  projection meaningful.
- **Development squad and transfer-fee outgoings** — wait on
  [#32](https://github.com/mario595/cycling-manager/issues/32) and
  [#28](https://github.com/mario595/cycling-manager/issues/28).
