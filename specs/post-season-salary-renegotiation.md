# Post-season salary renegotiation

**Status:** proposed
**Domain(s):** `riders/`, `world/`
**One-liner:** At the end of every season, every rider's wage is re-priced against who they are now, so a manager sees exactly who got more expensive, who got cheaper, and what the new wage bill looks like before the next season starts.

## Why this exists

A rider's weekly salary is set once, at generation, and frozen for the
rest of that rider's time in the game — even as their attributes grow,
decline, or their age moves them in or out of their prime. A team's best
prospect and its long-retired veteran can end up costing the same, forever,
because neither the growth curve nor ageing ever touches the number the
manager pays. That flatters an improving rider (their value goes up, their
cost never does) and lets a declining one become dead weight on the books
that never gets any cheaper.

This closes that gap: the price catches up with the rider, once a season,
at the one moment the game already treats as a boundary. It gives rider
improvement a cost, and rider decline a saving, and puts both in front of
the manager before the wage bill they'll be living with for the next
season locks back in.

## Player experience

A season ends. Alongside whatever else settles at that boundary, the
manager's roster gets re-priced: every rider's weekly wage is recalculated
from who they are today — their current attributes and age — the same way
their wage was calculated the day they were generated. Most riders move a
little; some don't move at all; a rider who had a breakout season, or one
who just aged out of their prime, moves by more.

The manager sees this as a season-close report: a list of their own
riders whose wage actually changed, each showing what they cost before and
what they'll cost from next season, and — at the top — the team's total
weekly wage bill, before and after. A rider whose price barely moved isn't
listed; the report is for decisions, not noise. The new number is simply
what the manager pays from the next season on — there's no separate step
to accept it.

Nothing forces the manager's hand immediately. If the new bill is more
than the team can comfortably carry, that's now visible, and the manager's
existing tools — release a rider, tighten training focus, whatever else
the roster screen already offers — are how they respond. If a rider is
raised into now being clearly not worth their new wage, releasing them
works exactly like it does any other week.

A rider never has any say in this. The wage moves; the manager decides
what to do about it.

## In scope

1. Every rider's weekly wage is recalculated at season close, from the
   same inputs and formula used to set it originally — nothing about how
   a wage is calculated changes, only when.
2. Recalculation happens for every rider in the game, not only rostered
   ones — a free agent sitting in the pool is re-priced too, so a rider
   signed the day after season close is priced against who they are now,
   not a stale number from last season.
3. Recalculation uses each rider's post-ageing state — the rider's age has
   already advanced for the new season by the time their wage is
   recalculated, so the wage reflects the rider they'll be for the season
   about to start, not the one who just finished the last one.
4. A rider's wage can move up or down. An improving rider gets more
   expensive; a declining or ageing-out rider gets cheaper.
5. Once recalculated, a rider's wage is frozen again for the coming
   season, exactly as before — nothing about the mid-season freeze
   changes.
6. Each manager sees a season-close report listing, for every one of
   their own current riders whose wage changed by a meaningful amount,
   the wage before and the wage after.
7. The same report states the team's total weekly wage bill before and
   after the changes listed in it.
8. A rider whose wage did not change by a meaningful amount does not
   appear in the report. "Meaningful" is deliberately not most rider's
   ordinary year-to-year drift — see *Rules and edge cases*.

## Out of scope

- **Selling a rider as part of this feature.** The manager's lever for an
  unaffordable rider is releasing them to the free agent pool, which
  already exists as its own feature. This ticket does not add a
  disposal mechanism of its own.
- **A rider refusing the new wage and leaving.** Raised in the original
  brief as an open question — decided no. A rider is a pure asset here:
  the price changes, the manager decides. A rider with a will of their
  own to walk away is a different feature (rider ambition/loyalty), and
  it would need a new hidden trait feeding a visible price, which nothing
  else in the game does.
- **Contract length.** Also raised as an open question — decided no. Wages
  stay the rolling weekly deal they are today; nothing about a rider's
  tenure changes, only the number.
- **Consequences of an unaffordable wage bill.** What happens when a team
  can't cover its bill belongs to insolvency (#27), not here. This
  feature only ever produces a bigger or smaller number and shows it —
  it never blocks, warns of, or acts on insolvency itself.
- **A history of a rider's wage (or attributes, or value) over past
  seasons.** The report shows this season's before/after only. A screen
  that lets a manager see how a specific rider's price, skills or market
  value have moved across many past seasons is a real, separate feature
  — it needs the game to start keeping a per-rider record over time,
  which nothing does today, plus a place to show it. Worth its own
  ticket once a few seasons have actually been played, the same reasoning
  that keeps season history (#43) deferred.
- **Any change to how a rider's wage is calculated.** The pricing formula
  itself — what inputs it uses, how it weights them — is untouched. This
  ticket only changes when that formula runs again.

## Rules and edge cases

**Every rider recalculates, not only ones whose attributes moved.** The
wage formula reads age as well as attributes, and every rider's age
advances at every season close — so even a rider whose skills didn't
change at all can see a small wage move purely from being a year older.
This is accepted, not a bug to design around: the alternative — comparing
against last season's frozen inputs to decide who "really" changed — adds
a second notion of what counts as change for no real benefit.

**The report exists to surface decisions, not to itemise every rider.**
Because ageing alone nudges almost every rider's wage a little, an
unfiltered report would be dozens of one-line entries that mean nothing —
noise a manager has to scan past to find the two riders whose price
actually matters. The report only lists a rider whose wage moved by more
than a small, fixed threshold — enough to filter out ordinary year-to-year
drift, small enough that a rider having a real breakout or a real decline
always clears it. Where exactly that line sits is a tuning decision for
implementation, calibrated the same way the wage formula's own constants
were: by sampling how much a representative season of growth, decline, or
ageing actually moves the number, not by guessing a round figure up front.

**A free agent is repriced with nobody watching.** Recalculation runs over
every rider regardless of whether they're on a roster, so the pool stays
priced consistently with rostered riders — but since a free agent has no
manager, there is no report entry for them. The report is generated once
per managed team, over that team's own current roster only.

**Ordering at the boundary: ageing first, then repricing.** Season close
already advances every rider's age before this feature runs. Repricing
must happen after that step, not before — the wage a manager sees for
next season has to reflect the rider they'll actually have next season,
age included. Repricing before ageing would price everyone one year
young.

**A rider who changes teams mid-season is unaffected until the next close.**
Nothing about being bought, sold, released or signed inside a season
touches this feature — it only ever runs at the season boundary, over
whoever is on a roster (or in the pool) at that moment.

**A newly claimed team's roster is priced at generation, same as ever.**
Claiming a team generates a fresh roster with wages set the normal way;
this feature doesn't change anything about that moment, only about what
happens to those wages at the next season close.

## Decisions taken

- **Trigger: recompute from the existing formula, not a rider-initiated
  demand.** Reuses the visible-attributes-only pricing rule already in
  force everywhere else; a demand mechanism would need a new hidden trait
  feeding a visible price, which the game treats as a defect everywhere
  it could happen.
- **No pending per-rider decision or deadline.** The new wage simply
  applies; the manager reacts with existing roster tools. Needing a
  decision window would require the inter-season break `specs/season.md`
  once proposed and never built — out of scope for this ticket to
  invent.
- **A season-close report is required, not silence.** The wage bill can
  move meaningfully without any visible cause otherwise; this mirrors how
  `staff.TrainingWeekReport` already surfaces a weekly rollover the
  player didn't directly trigger.
- **Riders never refuse and there is no contract length.** Both were open
  questions in the original brief; both decided no, to keep this feature
  about price, not about rider agency or tenure.
- **Salaries move in both directions.** A declining or ageing-out rider
  gets cheaper, symmetric with an improving rider getting more expensive
  — this falls out of reusing the formula unchanged and needed no
  separate decision.
- **The report is filtered by a meaningful-change threshold, not
  unfiltered.** Needed because nearly every rider drifts slightly from
  ageing alone every season; an unfiltered report would bury the two
  riders who actually matter under dozens who don't.
- **The rider-history/evolution-over-time view is a separate ticket, not
  part of this one.** It needs new persistence (a per-rider record kept
  over time) that nothing in the game has today, and its value grows with
  the number of seasons played — the same reasoning already applied to
  deferring season history (#43).

## Open questions

None — the brief's two open questions (refusal, contract length) were
resolved above.

## Deferred

- **Rider-history detail view** (salary, skills, market value over past
  seasons) — needs a new per-rider time-series record the game doesn't
  keep today, and gets more valuable the more seasons have actually been
  played. Track as its own issue.
- **Insolvency consequences of a wage bill the team can't cover** (#27) —
  this feature only ever produces and reports a number; acting on an
  unaffordable one is #27's job.
- **A disposal/selling mechanism** — the auction market (#28) and free
  agent release (#29) already are, or will be, the manager's lever here;
  this ticket adds no disposal mechanism of its own.
