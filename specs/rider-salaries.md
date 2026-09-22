# Rider salaries paid weekly

**Status:** proposed
**Domain(s):** `riders/`, `economy/`
**One-liner:** Every rider costs a different weekly wage, known upfront, instead of the same flat rate for everyone on the roster.

## Why this exists

Today every rider costs the same flat weekly wage. A twelve-rider roster is a
head count, not a budget — there is no decision to make about *which* riders
to carry, only how many. Real salaries make roster composition a real
trade-off: a manager can carry one expensive star and fill the rest of the
squad with cheap depth, or spread the budget evenly across a dozen
journeymen. It's also the prerequisite for every future money decision that
needs to know what a rider is worth — renegotiating a contract, selling a
rider, judging whether a signing was a bargain.

This does not fix the game's economy. Income today is a small merchandise
trickle against a large wage bill, and every team is already burning its
starting balance faster than it earns. This ticket keeps that true — it
redistributes who drains the fastest, and leaves fixing the shortfall to
prize money and sponsorship.

## Player experience

A manager opens their roster and sees, next to each rider, what that rider
costs per week. A promising all-rounder in their prime costs noticeably
more than a bit-part rider — roughly ten times more, at the extremes — and
a manager can look at two riders with similar visible ability and see they
cost about the same, because the price is read directly off the numbers
already on screen: how good the rider is right now, and how old they are.

The Finances screen shows the weekly wage bill as a single total, the same
way it shows the balance — "this is what leaves every week" — and the
weekly wages entry in the ledger history still reads as one line, now
summing whatever each rider actually costs instead of a fixed rate.

A salary is set the moment a rider exists — generated fresh for a new team,
or assigned once to every rider already on a roster — and then holds steady
for the rest of the season. A rider who has a breakout season, or one who
fades, keeps costing what they cost until the season turns over; what
happens to their salary at that point is a separate, later decision.

Nothing about how a manager picks a race squad changes. Salary is paid
whether a rider races that week or sits out, so it plays no part in that
choice.

## In scope

1. Every rider has a weekly salary, visible on the roster screen next to
   that rider.
2. The salary is derived from attributes and information the player can
   already see for that rider — nothing hidden feeds it. Two riders who
   look the same on the roster page cost about the same.
3. A rider near the top of what's realistic for their age costs roughly ten
   times a bare-minimum rider of the same age.
4. A rider's salary is fixed once set. It does not move week to week as the
   rider's attributes grow or decline over a season.
5. Every rider that exists today, on every team, gets a salary the first
   time this feature runs — nobody is left without one.
6. A newly generated rider (a fresh squad for a newly claimed team, or any
   other roster generation) gets a salary at the moment it's created.
7. The weekly wage charge a team pays is the sum of what its actual riders
   cost that week, not a flat rate times a head count.
8. The Finances screen's weekly wage bill reflects the same sum.
9. An empty roster still costs nothing and is still charged a real,
   visible zero — consistent with how the flat-rate wage bill behaves
   today.

## Out of scope

- **Salary changing when a rider's ability changes mid-season.** Frozen for
  the season (see *Rules and edge cases*). Recomputing it live would make
  the weekly bill a moving target the player can't plan against, and would
  quietly do the renegotiation ticket's job ahead of time.
- **What happens at season end.** Whether a salary is recalculated, whether
  a manager can choose to keep or release a rider at a new price — that's
  [#26](https://github.com/mario595/cycling-manager/issues/26), post-season
  renegotiation. This ticket only decides that a salary holds *within* a
  season.
- **Salary as an input to a rider's market value.** Belongs to
  [#31](https://github.com/mario595/cycling-manager/issues/31), which this
  ticket unblocks but does not build.
- **Any consequence of an unaffordable wage bill.** A negative balance is
  already visible and already unenforced — see `economy/README.md`. That
  stays unchanged; consequences belong to
  [#27](https://github.com/mario595/cycling-manager/issues/27), insolvency.
- **A hidden trait (e.g. potential) feeding the price.** Deliberately
  excluded — see *Rules and edge cases*. Two riders with identical visible
  ability cost the same even if one has far more room to grow. That's a
  known, accepted imprecision, not an oversight.
- **Contract length, signing bonuses, or a wage budget/cap.** None of these
  exist as a concept yet; each is a transfer-market feature wearing this
  one's coat, and belongs there if it gets built at all.
- **Rebalancing the overall economy so teams stop losing money.** The
  average roster's total wage bill stays roughly what a flat-rate roster
  costs today. This ticket does not attempt to fix the shortfall between
  income and wages — that's prize money
  ([#19](https://github.com/mario595/cycling-manager/issues/19)) and
  sponsorship's job.
- **Salary shown on the squad-selection screen.** A rider is paid whether
  or not they're picked to race, so it has no bearing on that choice and
  would just be noise there.
- **Trainer salaries.** A separate ticket
  ([#69](https://github.com/mario595/cycling-manager/issues/69)) on the
  same footing; not this one.

## Rules and edge cases

- **What decides the price.** A rider's salary is driven by how good they
  are right now, on the same visible attributes the roster page already
  shows, and by their age. No hidden trait — not potential, not any other
  hidden number — feeds it. This means a young rider with huge room to
  grow costs exactly what an older rider with no room left costs, as long
  as they look the same today. That's intentional: the alternative would
  put a number on screen that silently reveals a hidden trait, which the
  game's design elsewhere treats as a defect, not a convenience.
- **The spread.** Salaries should span roughly a 10x range from the
  cheapest realistic rider to the most expensive, so that carrying a star
  is a felt cost, not a rounding error against today's flat rate.
- **Frozen for the season.** A salary does not change once set, regardless
  of how much the rider's attributes move during the season, including
  through the age curve or training. It only ever changes at a season
  boundary, and only if a later feature says so.
  ([#26](https://github.com/mario595/cycling-manager/issues/26) decides
  that; this ticket does not.)
- **Backfilling existing riders.** Every rider that exists in the database
  before this feature ships needs a salary assigned once, using the same
  derivation a newly generated rider gets. No rider should ever be found
  without one.
- **Zero-rider teams.** A team with no riders is charged a real wage entry
  of zero, same as today — not skipped, not hidden.
- **Total cost stays roughly where it is today.** An average full roster's
  combined weekly salary should land close to what that roster costs under
  today's flat rate. Some teams will pay more, some less, but the game-wide
  average shouldn't quietly get harder or easier to survive — that's a
  separate decision for prize money and sponsorship to make later.
- **Interaction with existing wage machinery.** The wage bill is still
  charged once per crossed week boundary, still dated to the week's own
  start, still exactly-once, still charged to every team whether managed
  or not. None of that changes — only what number gets summed changes.

## Decisions taken

- Salary basis: derived from visible attributes and age, not hidden traits
  and not market value. Keeps the price always explicable from what's
  already on the roster screen.
- Salary drift: frozen for the season. Predictable weekly bill; renegotiation
  is [#26](https://github.com/mario595/cycling-manager/issues/26)'s job, not
  this ticket's.
- Spread: roughly 10x between cheapest and most expensive, so roster
  composition becomes a real trade-off.
- Visibility: shown per rider on the roster screen, and as a total weekly
  bill on the Finances screen. Not shown on squad selection (salary is paid
  regardless of who races) and not broken down per-rider on the ledger
  entry (the roster column already answers that).
  average.
- Overall cost: kept roughly average-neutral against today's flat rate,
  deliberately not used to rebalance the economy — that's prize money
  ([#19](https://github.com/mario595/cycling-manager/issues/19)) and
  sponsorship's job, and this ticket ships ahead of both on the roadmap.

## Open questions

None. The brief's original open question — where the initial salary comes
from — is answered above (visible attributes and age).

## Deferred

- Post-season renegotiation — [#26](https://github.com/mario595/cycling-manager/issues/26).
  Needs this ticket's salary to exist before it can decide what changes it.
- Salary feeding market value — [#31](https://github.com/mario595/cycling-manager/issues/31).
  Same reason.
- Insolvency consequences — [#27](https://github.com/mario595/cycling-manager/issues/27).
  A negative balance already exists unenforced; this ticket doesn't change
  that.
- Trainer salaries on the same footing — [#69](https://github.com/mario595/cycling-manager/issues/69).
  Separate role, separate ticket.
