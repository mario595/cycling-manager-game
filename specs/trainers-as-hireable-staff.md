# Trainers as hireable staff

**Status:** proposed
**Domain(s):** `staff/` (new)
**One-liner:** A manager hires one trainer from a shared pool into their team's
single trainer slot, for free — the trainer's five skill scores are what
weekly training (#36) reads.

## Why this exists

Weekly training (#36, already specced) assumes a trainer exists with a
speciality and describes what happens once a team has one. Nothing today lets
a team get one. This feature is the other half: it makes the trainer a real
object a manager chooses, not an assumption a later feature made.

It also gives the game its first "who gets there first" decision. Trainers
come from one pool shared by every team; a manager who wants a climb
specialist and finds one in the pool has to decide now, because another
manager might take it first.

## Player experience

A manager opens the team's Staff page. If the slot is empty, they see a list
of available trainers, each showing five skill scores on the same 0-10 scale
riders use — climb, sprint, flat, resistance, positioning — as a range rather
than an exact number, the same way a rider's own attributes are shown. One
score always reads unambiguously higher than the rest; that's the trainer's
speciality, obvious at a glance without a separate label. The manager picks
one and hires them — instantly, no cost, no confirmation beyond the click.

Once hired, the trainer moves off the list. Any other manager looking at the
pool at that moment sees one fewer option. The team's Staff page now shows
that trainer's five scores instead of a hire list, and a Fire button.

Firing is immediate and free: the trainer returns to the shared pool, visible
to every team including the one that just let them go, and the slot goes
empty again. There's no cooldown and no penalty beyond losing whatever that
trainer was good at — a manager who fires on a Sunday and expects to hire a
replacement before Monday's training rollover needs to actually do it in
time, or that week trains with no trainer at all.

The pool itself never runs dry. New trainers keep appearing across seasons so
there is always a real choice for a team with an empty slot, whether that's
their first hire or their fifth after a string of firings.

## In scope

1. Each team has exactly one trainer slot, empty or filled — never more than
   one trainer per team.
2. A shared pool of unemployed trainers, visible to every team, is the only
   source of a hire.
3. Each trainer has a score from 1-10 in each of the five rider skills
   (climb, sprint, flat, resistance, positioning), generated so exactly one
   skill is clearly the highest — that skill reads as the trainer's
   speciality, with no separate label needed.
4. A team with an empty slot can hire any trainer currently in the pool.
   Hiring is immediate, free, and removes that trainer from the pool for
   every other team.
5. A team with a filled slot can fire their trainer at any time, for free.
   The trainer returns to the shared pool immediately, hireable by any team
   including the one that fired them.
6. The pool is topped up with new trainers at every season boundary, so a
   team is never looking at an empty pool for long even after a run of
   hiring.
7. A trainer's five skill scores are shown to every manager considering
   them, as a range on the same 0-10 display scale used for rider
   attributes — not as an exact number.
8. A trainer's skill scores never change after they're generated.
9. Weekly training (#36) reads whichever trainer is filling a team's slot at
   the Monday 00:00:00 UTC rollover. Hiring or firing after that moment has
   no effect until the following week.

## Out of scope

- **Fee and recurring salary.** The brief's "upfront fee plus a recurring
  salary" needs a balance to draw from, and the ledger (#20) is deferred with
  the whole economy. **Later, tracked as [#69](https://github.com/mario595/cycling-manager/issues/69)**
  — once #20 exists, add a cost to hiring and a weekly wage to keeping a
  trainer, as a follow-up to this feature rather than bundled into it. Until
  then, hiring is a pure upgrade with no financial trade-off; the only real
  decision is which speciality to chase.
- **Poaching.** Taking an employed trainer from another team. **No** — this
  would need offers, competing bids, and a reason for the current employer
  to let go, none of which exist. A trainer can only change teams by being
  fired back into the pool first.
- **Contract length / renewal.** With no salary there's nothing to renew — a
  trainer stays until fired, indefinitely. Revisit only if fee/salary lands.
- **A trainer quality curve over time.** A trainer's scores are fixed for
  life; they don't improve or decline with age or tenure. **No** — a second
  aging system for staff on top of the unbuilt one for riders (#58) buys
  nothing yet.
- **Physio and scout slots.** Both designed alongside trainer in the original
  brain-dump, but physio needs injuries (#41, unbuilt) and scout needs
  transfers/youth intake (also unbuilt) — neither has anything to act on
  today. **Later**, each as its own spec once its dependency exists. This
  spec establishes one fixed slot per role in principle by building the
  first one, not a generic multi-role staff system.
- **AI/unmanaged teams hiring a trainer.** Unmanaged teams stay unstaffed,
  consistent with #44/#45 leaving them deliberately weak until the
  unmanaged-team AI ticket (#45) exists to make that call. **Belongs to
  #45.**
- **Exact skill numbers shown to the hiring manager.** Shown as a range,
  matching how rider attributes are displayed. **No** — showing the exact
  number turns hiring into a solved optimisation with no room for a future
  scout role to add value by narrowing the range.

## Rules and edge cases

- **Exactly one skill is the clear highest, every time a trainer is
  generated.** This is a generation guarantee, not a display trick — it's
  what lets a manager read "speciality" off the numbers with no separate
  field, and it's what #36 needs to always have an unambiguous best-skill to
  compare its focus selection against.
- **No skill ever scores at the very bottom of the range.** #36 requires
  off-speciality training to always be worth something, never zero;
  generation must guarantee every one of the five scores is high enough to
  produce a non-zero training effect.
- **Firing has no cooldown and no confirmation step beyond the click itself**
  — a manager can fire and immediately try to hire someone else from the
  pool, subject to whatever else is in the pool at that moment.
- **A trainer returned to the pool by firing is exactly as hireable as any
  other pool trainer**, including by the team that just fired them — nothing
  marks a trainer as "recently let go."
- **The pool having plenty of trainers at all times is a generation policy,
  not a hard cap** — there's no scarcity mechanic here; a team that can't
  find the speciality it wants right now can wait for the season boundary's
  top-up.
- **Hiring/firing mid-week doesn't retroactively touch that week's
  training.** #36 fixes its trainer read at Monday 00:00:00 UTC; anything
  that happens to the slot after that has to wait for the next rollover.

## Decisions taken

- No fee, no salary — hiring is free. *(Money dependency)* Reason: #20 (the
  ledger) is deferred with the whole economy; blocking this feature on it
  would leave #36 (already specced) blocked indefinitely. Revisit once #20
  ships.
- Five per-skill scores (1-10 each), not a single speciality label plus one
  quality number. *(Trainer stats)* Reason: matches the brief's "per-skill
  score" literally, and #36's "matches the trainer's speciality, smaller
  otherwise" becomes "scaled by the trainer's score in the focused skill" —
  a strictly richer rule than a binary match/mismatch. Generation guarantees
  one skill is unambiguously highest, so the speciality is still legible at
  a glance.
- One shared pool across all teams, not a private pool per team. *(Pool
  shape)* Reason: creates real contention for a good trainer with no auction
  machinery needed.
- Firing is allowed; poaching is not. *(Exit and acquisition)* Reason:
  firing is needed the moment a hire turns out wrong; poaching is a full
  transfer market for staff that belongs later, if ever.
- Pool refreshes at season boundaries and is generated generously — never a
  meaningful scarcity constraint. *(Pool volume)* Confirmed by the user.
- Skill scores are shown as a 1-10 range, not an exact number, matching
  rider attribute display. *(Visibility)* Confirmed by the user — leaves
  room for a future scout role to narrow the range, applied to riders per
  the backlog, not reused here.
- Scope is the trainer slot only; physio and scout are out entirely for this
  ticket. *(Scope width)* Confirmed by the user.

## Open questions

None outstanding.

## Deferred

- **Fee and recurring salary** — tracked as #69; once #20 (ledger) exists,
  price hiring and add a weekly wage.
- **Physio slot** — once #41 (injuries) exists to give it something to
  affect.
- **Scout slot** — once transfers/youth intake exist to give it something to
  narrow.
- **AI/unmanaged teams hiring trainers** — belongs to #45.
- **Poaching, contract renewal, trainer quality curves** — no current plan;
  revisit only if the fixed single slot itself changes.
