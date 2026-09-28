# Development squad

**Status:** implemented
**Domain(s):** `riders`, `economy`, `teams`
**One-liner:** A team can pay to run a development squad — a paid facility that, once youth intake exists, is where young riders arrive and grow before joining the senior roster.

## Why this exists

Every rider a team has today either came with the team or was bought or signed
on the transfer market — nothing is ever *grown*. The development squad is the
facility that makes growing your own possible: a standing, paid commitment a
manager takes on ahead of any payoff, the same shape as hiring a trainer. It
does not, by itself, produce a single rider — that is youth intake (#33),
deliberately deferred. What this spec defines is the facility itself: opening
it, choosing how much to invest in it, paying for it, and what a manager sees
for their money.

Because the game has no live players yet, the facility can ship ahead of youth
intake without a placeholder message. A team that opens a squad today spends
money for nothing until #33 lands — an acceptable state prelaunch, not one
this spec has to soften.

## Player experience

A manager opens the Development squad panel from the team's facilities. It is
closed by default. Three levels are on offer, each shown with its name, what
it costs to open, its ongoing weekly cost, and — done once, plainly, so no one
has to do the arithmetic — what that weekly cost adds up to across a full
season. The manager reads it the same way they'd read a subscription: pay now,
pay every week after, for as long as it stays open.

They pick a level and open the squad. The opening fee is taken immediately,
and from that week on the weekly cost appears in the finances history as its
own line, distinct from wages, trainer costs, or anything else. The panel now
shows the squad as open at that level.

Later, the manager decides to invest more and upgrades to a higher level. They
pay the difference between the two levels' opening fees; the weekly cost
switches to the new level's rate starting that week. If they instead downgrade,
it takes effect immediately, no fee, no refund of what they already paid to
reach the higher level — a downgrade is a decision to spend less from now on,
not a chance to recover past spending.

If the manager decides the squad isn't worth it, they close it. The weekly
cost stops. If they change their mind later, they pay to open it again, in
full, at whichever level they choose — the same as hiring a trainer who was
let go.

A team that changes managers keeps its squad exactly as it was left — closing
it is not part of what happens when a team is released to the pool. Only when
a new manager claims that team does the squad close, the same moment the
roster and balance reset. A new manager never inherits a facility they didn't
pay for.

Right now, none of this produces a rider. The panel doesn't say so and doesn't
need to — the manager pays for a facility, sees it reflected in their
finances, and youth riders will begin arriving through it once #33 ships.

## In scope

1. A team can open a development squad at one of three levels, each with its
   own opening fee and weekly cost, higher levels costing more at both.
2. Opening the squad charges its level's opening fee immediately and starts
   the weekly cost from that week.
3. A team cannot open or upgrade the squad if its balance doesn't cover the
   fee being charged.
4. A team can upgrade to a higher level, paying the difference between the
   old and new level's opening fees; the weekly cost changes to the new
   level's rate from that point on.
5. A team can downgrade to a lower level with no fee and no refund; the
   weekly cost changes to the new level's rate from that point on.
6. A team can close an open squad; its weekly cost stops from that point on.
7. Reopening a closed squad charges the full opening fee for whichever level
   is chosen, same as opening for the first time.
8. The Development squad panel shows, for every level, its opening fee,
   weekly cost, and cost over a full season, plus which level (if any) the
   team currently has open.
9. The opening/upgrade fee and each week's ongoing cost each appear in the
   team's finances history as their own distinct entries.
10. A team's development squad closes when the team is claimed by a new
    manager, the same moment its roster and balance reset. It is unaffected
    by a team being released back to the unmanaged pool.

## Out of scope

- **Youth riders actually arriving, their quality, and how squad level
  affects intake.** That is #33. This spec only promises that a higher level
  will matter once #33 exists — see *Rules and edge cases*.
- **Promoting, retaining, or discarding intake riders.** That is #34; there
  is nothing to triage until #33 exists.
- **Any effect of how long a squad has been open, or its level, beyond what
  #33 decides.** Not defined here.
- **Unmanaged (AI-run) teams opening or running a development squad.**
  Deferred to the heuristic AI (#45) — an unmanaged team has no reason to
  invest in one until something decides that for it.
- **Refunding any part of an opening or upgrade fee.** Never — a refund on
  downgrade or close would make the fee toothless as the thing that makes
  this a commitment rather than a toggle.
- **Any special treatment for a new manager or a first-time team** —
  no discount, no gate, no guidance beyond the panel itself.
- **A cap on how many riders the squad can hold.** #33's concern once intake
  exists.

## Rules and edge cases

- **Three levels, ascending cost.** Each level's opening fee and weekly cost
  are both strictly higher than the level below it — there's no level that
  costs more to open but less to run, or vice versa.
- **A closed squad has no level.** Level is only meaningful while the squad
  is open; closing does not "remember" the last level for a discounted
  reopen.
- **Upgrading mid-level cannot be cheaper than opening at the target level
  directly.** The difference-in-fees rule guarantees this as long as fees
  rise with level, which the level-ordering rule above guarantees.
- **Downgrading and upgrading are both instant** — no notice period, no
  waiting for a week boundary. The finances history is the record of what
  happened and when.
- **Affordability is checked at the moment of the fee only.** Nothing stops
  a team's balance from later going negative under the ongoing weekly cost —
  that consequence belongs to insolvency (#27), not to this feature.
- **The weekly cost is charged to every week the squad is open**, including
  a week where it was also opened, upgraded, or downgraded — the same
  once-per-week guarantee wages and trainer salaries already give.
- **This spec does not promise the squad will ever be full**, ever
  produce a rider of any particular quality, or that level changes anything
  observable before #33 ships. What it promises is only that #33 must make
  a higher level mean better and/or more intake on average — never
  guaranteed for any single batch, and never a mechanism players can defeat
  by, say, upgrading for one week and downgrading immediately after (#33's
  problem to close, informed by this constraint).

## Decisions taken

- **Scope is #32 only** — youth intake (#33) and triage (#34) stay separate
  tickets. Decided because #32's payoff is invisible without them, and the
  game isn't live yet, so shipping the facility ahead of its payoff is
  acceptable.
- **Levels, not binary on/off, from day one.** A flat on/off facility gives a
  manager no decision beyond "yes or no"; levels make the investment size
  itself a choice.
- **Intake cadence is "one every few weeks," not weekly.** Recorded here for
  #33 to inherit — a steady trickle through the season, not a weekly flood
  requiring a hard cap and constant triage, and not a single once-a-season
  event either.
- **Paid for with an opening fee plus a weekly cost**, mirroring the
  trainer's hire fee + salary shape already in the game. The up-front fee is
  what stops a manager toggling the squad on right before an intake and off
  right after to dodge the running cost.
- **No refunds on downgrade or close.** Keeps the opening fee meaningful as a
  real commitment rather than a reversible toggle.
- **No gating for new managers.** The price and the season-cost display are
  the only signal a new manager gets; nothing blocks them from opening one on
  day one if they choose to.
- **Ship without any "coming soon" messaging**, even though the squad
  produces nothing until #33 lands. The game has no live players yet, so a
  half-finished payoff is acceptable and does not need to be flagged to the
  player.
- **Closing a squad is not part of what happens when a team is released to
  the pool.** Release already deliberately touches nothing but the
  manager link (`teams/README.md`); a squad only closes when the next
  manager claims the team, alongside the roster and balance reset.

## Open questions

None — the questions raised in #32 (binary vs. levelled) and the review round
above are settled in *Decisions taken*. The remaining unknowns (batch size,
per-level quality/volume bias, squad capacity) belong to #33's own spec.

## Deferred

- **Unmanaged teams opening or running a squad** — waits on heuristic AI
  (#45) to decide whether and when an AI-run team should invest.
- **Any interaction between squad tenure/level and insolvency (#27)** —
  waits on #27 to define what going broke actually does.
