# Development squad

**Status:** implemented
**Domain(s):** `riders`, `economy`, `teams`
**One-liner:** A team can pay to run a development squad — a paid facility that, once youth intake exists, is where young riders arrive and grow before joining the senior roster.
**Amended:** 2026-09-28, before merge — the squad became a ladder climbed one level at a time, with no downgrade. See *Amendment* at the end; every numbered rule below is as amended.

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
closed by default. Three levels are on offer, each shown with its name, what it
costs to reach, its ongoing weekly cost, and — done once, plainly, so no one
has to do the arithmetic — what that weekly cost adds up to across a full
season. Only the lowest level can be opened; the levels above it are shown
locked, each saying what would unlock it. The manager reads the panel the way
they'd read a ladder: the price of the first rung, then the price of each one
above it.

They open the squad at the lowest level. That level's fee is taken immediately,
and from that week on the weekly cost appears in the finances history as its
own line, distinct from wages, trainer costs, or anything else. The panel now
shows the squad as open at that level, with the level above it unlocked.

Later, the manager decides to invest more and upgrades to the next level up.
They pay that level's own fee in full — the panel quotes the same figure it
will charge — and the weekly cost switches to the new level's rate starting
that week. There is no way to step back down: the levels above the one held
stay locked until it is reached.

If the manager decides the squad isn't worth it, they close it. The weekly
cost stops, and the only way to reduce what they are paying is this. Closing
is a drastic measure rather than a cheaper setting, so it is priced like one:
nothing is refunded, and it forgets which level it was at. If they change
their mind later they start again at the bottom, paying the lowest level's fee
in full, and climb back up from there.

A team that changes managers keeps its squad exactly as it was left — closing
it is not part of what happens when a team is released to the pool. Only when
a new manager claims that team does the squad close, the same moment the
roster and balance reset. A new manager never inherits a facility they didn't
pay for.

Right now, none of this produces a rider. The panel doesn't say so and doesn't
need to — the manager pays for a facility, sees it reflected in their
finances, and youth riders will begin arriving through it once #33 ships.

## In scope

1. A team can open a development squad at the lowest of three levels, and can
   upgrade it one level at a time from there. Each level has its own fee and
   weekly cost, higher levels costing more at both.
2. Opening the squad charges that level's fee immediately and starts the
   weekly cost from that week. Opening above the lowest level is refused
   however rich the team is.
3. A team cannot open or upgrade the squad if its balance doesn't cover the
   fee being charged.
4. A team can upgrade to the level directly above the one it holds, paying
   that level's full fee; the weekly cost changes to the new level's rate
   from that point on. Skipping a level is refused.
5. A team cannot move to a lower level. The only way to spend less is to
   close the squad, which stops the weekly cost from the next week.
6. A team can close an open squad; its weekly cost stops from that point on.
7. Reopening a closed squad opens it at the lowest level again, charging that
   level's fee in full — the same as opening for the first time, and with no
   memory of the level it used to be at.
8. The Development squad panel shows, for every level, the fee to reach it,
   its weekly cost, and that weekly cost over a full season; which level the
   team has open, if any; and, for every level it cannot currently take, that
   it is locked and what would unlock it.
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
- **Refunding any part of a fee, or resuming a squad where it left off.**
  Never — a refund, or a reopen that remembered the old level, would make the
  fee toothless as the thing that makes this a commitment rather than a
  toggle, and would turn closing into a cheap way to pause.
- **Any special treatment for a new manager or a first-time team** —
  no discount, no gate, no guidance beyond the panel itself.
- **A cap on how many riders the squad can hold.** #33's concern once intake
  exists.

## Rules and edge cases

- **Three levels, ascending cost.** Each level's fee and weekly cost are both
  strictly higher than the level below it — there's no level that costs more
  to reach but less to run, or vice versa. That is what makes the top of the
  ladder worth having and the rungs below it worth buying, rather than a set
  of differently-named subscriptions.
- **A level above the one held is locked, and a level below it is locked
  differently.** A manager needs to be able to tell "not yet" from "already
  behind", because the second one's only remedy is closing the squad. Both are
  shown on the panel; neither is a move.
- **A closed squad has no level.** Level is only meaningful while the squad is
  open, and closing does not "remember" it for a discounted or resumed reopen.
- **Upgrading is instant**, with no notice period and no waiting for a week
  boundary. The finances history is the record of what happened and when.
- **Affordability is checked at the moment of the fee only.** Nothing stops
  a team's balance from later going negative under the ongoing weekly cost —
  that consequence belongs to insolvency (#27), not to this feature.
- **The weekly cost is charged to every week the squad is open**, including
  a week where it was also opened or upgraded — the same once-per-week
  guarantee wages and trainer salaries already give.
- **This spec does not promise the squad will ever be full**, ever
  produce a rider of any particular quality, or that level changes anything
  observable before #33 ships. What it promises is only that #33 must make
  a higher level mean better and/or more intake on average — never
  guaranteed for any single batch. The ladder cannot be gamed for free
  either: every rung is paid for in full, and there is no ratchet that lets a
  team bank a level and come down to it when the money runs out (#33's
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
- **No refunds on close, and no resuming where it left off.** Keeps the fee
  meaningful as a real commitment rather than a reversible toggle, and keeps
  closing a real decision rather than a pause button.
- **One step up, or all the way down.** The squad is a ladder: it opens at the
  bottom and is upgraded one level at a time, and the only way to spend less
  is to close it entirely. Decided because the two jobs a level has — a
  commitment that grows, and an emergency release valve — are in tension, and
  a downgrade that let a manager trim the weekly cost a rung at a time would
  blunt the commitment without ever being the drastic gesture. Closing *is*
  the drastic gesture: it is the move a team makes when it cannot afford to
  run the squad at all, and the price of it — nothing back, and the whole
  climb again from Regional — is what keeps it from being a strategy for
  paying less in a bad week. See *Amendment*.
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
above are settled in *Decisions taken*, as is the ladder question settled in
the *Amendment*. The remaining unknowns (batch size, per-level quality/volume
bias, squad capacity) belong to #33's own spec.

## Amendment

**2026-09-28, before the ticket was merged.** The first build opened a squad
at any of the three levels and priced an upgrade as the difference between
two levels' fees, with a free downgrade as the way back down. That was
reviewed and replaced. What changed:

- **Opening is only possible at the lowest level.** A level above the one held
  stays locked until it is reached, and skipping one is refused. There is no
  door into the upper floors at any price, so the rungs below are never
  pointless to buy.
- **A level's fee is what reaching it costs**, not the difference against the
  level already held. The quoted figure and the charged figure are therefore
  the same number, and the climb costs every fee on the way: 30,000 + 75,000 +
  150,000 = 255,000 to reach Elite, against a 500,000 starting balance and
  72,000 of Elite weekly costs over a season. That is a much heavier
  commitment than the difference rule implied, and it is deliberate — see
  *Decisions taken*.
- **There is no downgrade.** Closing is the only way to reduce the weekly
  cost, and it is a reset rather than a pause: reopening starts at the lowest
  level again, for its fee in full.
- **The panel shows each level's fee to reach it** — the increment the
  manager would actually pay, labelled by the rung it buys — and marks every
  unavailable level as locked, with the reason. The "opening fee" a locked
  level quotes was a figure no player would ever pay, since the only way to
  get there is to upgrade into it.

Two reasons the numbers came out where they did. Elite is now 65% of a
starting balance to open and run for a season, against 44% under the
difference rule, which is at the edge of unaffordability for a team without
prize money or sponsorship behind it — the price of making the top of the
ladder a real decision rather than a rounding error. And the weekly costs
still rise strictly with level, which is the invariant that actually matters
now that fees are per-rung: a level that cost the same to run would never be
worth upgrading to, and one that cost less would be an upgrade that saved
money.

## Deferred

- **Unmanaged teams opening or running a squad** — waits on heuristic AI
  (#45) to decide whether and when an AI-run team should invest. It will have
  to climb the ladder in order, like anyone else, and be free to close one.
- **Any interaction between squad tenure/level and insolvency (#27)** —
  waits on #27 to define what going broke actually does. Closing the squad is
  the lever a team in trouble reaches for first, and #27 should know that.
