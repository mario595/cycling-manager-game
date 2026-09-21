# Trainer hiring fee and recurring salary

**Status:** proposed
**Domain(s):** `staff/`, `economy/`
**One-liner:** hiring a trainer costs an upfront fee and a recurring weekly
salary, both scaled to how good the trainer is.

## Why this exists

Trainers ([#35](https://github.com/mario595/cycling-manager/issues/35)) are
free today, deliberately — the ledger they'd need to debit from didn't exist
yet. It does now ([#20](https://github.com/mario595/cycling-manager/issues/20)),
and the weekly tick already charges every team a wage bill. A trainer with no
cost is a hire with no decision behind it: every team should have the best
trainer available, forever, and firing one costs nothing. Pricing the slot
turns "who do I hire" into a real budget call, and gives firing a reason not
to be reflexive.

## Player experience

Browsing the pool, a manager sees each trainer's five skills as today, plus
two new numbers: what it costs to hire them, and what they'll cost every
week after that. A trainer who's clearly better in the manager's chosen
speciality also costs more — both to bring on and to keep. The team's
current balance is visible on the same screen, so the comparison is
immediate: can I afford this one, and can I afford to keep them?

Clicking Hire on a trainer the team can't afford does nothing but explain
why — the fee is shown, the balance is shown, the gap is obvious. Hiring
one the team can afford debits the fee immediately and the trainer starts
working that week.

From then on, the team's weekly finances show a "Trainer salary" line
alongside "Weekly rider wages" — its own row, not folded into the existing
one, so the manager can see exactly what staff is costing them. A team
with no trainer has no such row at all; it isn't lurking in the history
as a weekly zero.

Firing the trainer is unchanged in every other way — instant, no
cooldown — except the salary stops being charged from that week on. The
fee already paid is not returned. If the manager regrets it, hiring
someone else means paying a fee again.

A team that can't cover a week's salary isn't stopped from having one —
the salary is charged anyway and the balance goes negative, the same way
rider wages already behave. Nothing about a persistently negative balance
happens yet; that's a separate, already-tracked problem
([#27](https://github.com/mario595/cycling-manager/issues/27)).

## In scope

1. Every trainer in the hiring pool displays two figures alongside their
   skills: the fee to hire them, and the weekly salary to keep them.
2. Both figures are derived from the trainer's speciality score — a
   trainer who is clearly better at their best skill costs more, in both
   the fee and the salary.
3. A team's current balance is visible on the same screen as the pool.
4. Hiring a trainer the team cannot afford (fee exceeds current balance)
   is refused, with the reason shown to the player. No partial hire, no
   IOU.
5. Hiring a trainer the team can afford debits the fee from the team's
   balance immediately, as a dated entry in the team's financial history.
6. Once hired, the team is charged the trainer's weekly salary every game
   week the slot stays filled, on the same cadence as rider wages.
7. The salary appears in the team's financial history as its own line,
   distinguishable from rider wages.
8. A team with no trainer produces no salary entry for that week — not a
   zero-amount one.
9. Firing a trainer stops the salary from the week of firing onward. The
   fee already paid is never refunded, and firing itself costs nothing
   extra.
10. If the team cannot afford a week's salary, it is charged anyway; the
    balance can go negative. No hire is blocked and no trainer is
    auto-fired for this.
11. A trainer's price never changes while they're in the pool or employed
    — the same trainer costs the same fee and salary the whole time,
    because their skills never change once generated.

## Out of scope

- **Price based on the trainer's full skill profile**, not just their
  speciality. Considered — a well-rounded trainer arguably should cost
  more than a one-trick specialist at the same peak — but it makes the
  price harder for the player to read off the card at a glance, and the
  speciality is already the number the player cares about most. **No.**
- **Severance pay, or any other cost to firing.** The ticket didn't ask
  for it, and the sunk fee already makes churning trainers unattractive
  without a second rule to balance. **No.**
- **Refunding any part of the fee on firing.** Would remove the one real
  consequence this ticket adds. **No.**
- **Prorating a partial week's salary on hire or fire.** The game clock
  resolves to whole weeks; a hire mid-week is charged a full week the
  same as everything else on this cadence. **No.**
- **Trainer wages for unmanaged/AI teams.** They don't hire trainers at
  all yet — belongs to [#45](https://github.com/mario595/cycling-manager/issues/45).
  **Later**, and not this ticket's problem until #45 exists.
- **What a persistently negative balance does to a team, including
  whether staff salary is part of what insolvency sheds first.** That's
  [#27](https://github.com/mario595/cycling-manager/issues/27) in full,
  and #27 is blocked on transfers existing — deciding its ladder here
  would be writing a rule nobody can test yet. **Belongs to #27.**
- **A visible payroll total** (rider wages + trainer salary summed on the
  finances screen). Each cost is visible as its own line; a rollup is
  presentation work on top, not required for the decision to be legible.
  **Later.**
- **Contract length, renewal, or poaching.** Not asked for, no player-
  facing need yet. **No**, matches staff/README's existing "no current
  plan" on this.

## Rules and edge cases

- Every trainer in the pool has a price the moment they're generated —
  there is no unpriced trainer state a player can see.
- The fee and salary move together: a more expensive trainer to hire is
  also more expensive to keep, never one without the other.
- Affordability is checked once, at the moment of hiring, against the
  fee only. The weekly salary is never checked for affordability at hire
  time or at any later charge.
- A team can go from solvent to a negative balance purely from staff
  salary, the same as it already can from rider wages. This spec adds no
  new behaviour for that state.
- Losing a trainer (fired) and having never had one look the same going
  forward: no salary line either way, from that week on.
- Re-hiring the same trainer after firing them is a fresh hire — a new
  fee applies, exactly as with any other trainer in the pool.

## Decisions taken

- Price scales with the trainer's speciality score, not their full
  five-skill profile. A flat price for every trainer would make cost a
  tax rather than a choice; scaling the whole profile makes the price
  unreadable from the card.
- Hiring is blocked outright when the fee isn't affordable; the weekly
  salary is never blocked and can overdraw the balance, matching how
  rider wages already work. Reacting to a negative balance is #27's job.
- The salary gets its own line in the team's financial history, separate
  from rider wages, so the player can see what staff costs them.
- Firing stays free and instant; the fee is never refunded. That sunk
  cost is the deterrent against churning trainers, without inventing a
  second penalty.
- Staff's place in insolvency (#27) is explicitly left to that ticket.
- A team with no trainer gets no weekly entry at all for that — not a
  zero-amount row — unlike rider wages, because an empty staff slot is
  the normal long-run state for most teams, not a temporary gap.

## Open questions

- The exact formula mapping a speciality score to a fee and a salary
  number — left to the implementation plan, which should also check the
  fee lands comfortably above a handful of weeks' salary (so firing to
  dodge one bad week and rehiring later doesn't pay off), and that
  `STARTING_BALANCE`'s "~34 weeks" comment in `economy/models.py` gets
  corrected once a real number is chosen.

## Deferred

- Trainer pricing for AI/unmanaged teams — until #45.
- A visible payroll total on the finances screen — presentation, once
  there's more than two cost lines to sum.
- Staff's treatment under insolvency — until #27.
