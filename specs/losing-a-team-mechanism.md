# Losing a team: the mechanism

**Status:** proposed
**Domain(s):** `teams/`, `accounts/`, `frontend/`
**One-liner:** A team can be taken from its manager and returned to the unmanaged pool, ready for someone else to claim.

## Why this exists

Right now nothing in the game can remove a manager from a team — no
inactivity check, no insolvency, no account deletion. `teams/README.md`
already flags the gap: an abandoned team has nowhere to go. Two features
that are coming — a manager who has stopped playing (#63) and a team that
can't pay its bills (#27) — both end the same way: the team stops being
managed and goes back into the pool. Neither of those triggers exists yet,
but the mechanism they'll both call should exist now, so each trigger is
just "decide when," not "also invent how."

This also closes a question `specs/claiming-a-team.md` left open when
claiming was built: what happens to a team after it's lost, and does it
reset the same way a claim does.

## Player experience

A manager who has been playing for a while stops paying attention, or the
game decides — for reasons this ticket doesn't cover — that their team
should go back into circulation. The next time they log in, instead of
landing on their dashboard, they're told plainly: their team is no longer
theirs, and why. From there they're in the same position as a brand-new
player — sent to claim a team, with a fresh roster and a clean slate,
exactly as if they'd just signed up.

The team itself doesn't notice anything happened. It keeps racing, keeps
its results, keeps its place in the standings — it simply doesn't have a
manager anymore, the same as any of the unmanaged teams a new player might
claim. Someone else logs in, claims a team, and might end up with this
exact one — new name, new colours, fresh roster, same history underneath.

The player who lost it isn't erased. Somewhere on their account, they can
still see the team they used to run — its name, how long they had it, and
why it ended. A setback with a story, not a wiped slate.

## In scope

1. A team with a manager can be returned to the unmanaged pool: the
   manager link is cleared and nothing else about the team changes — not
   its roster, not its balance, not its fanbase, not its results or
   standing.
2. Once released, a team is claimable through the exact same path as any
   other unmanaged team (#46) — whoever claims it gets a new name, new
   code, and a fresh roster; the released riders become free agents at
   that point, same as any claim.
3. The ex-manager's account keeps a private record of the team they lost:
   its name at the time, the period they managed it, and why it ended.
   This record does not change later if someone else claims and renames
   the same team.
4. The next time the ex-manager logs in, they are told clearly which team
   they lost and why, and are sent to claim a new one — the same screen
   and the same process a first-time signup goes through.
5. An operator can release a specific team by hand, for testing and for
   any manual intervention this ticket doesn't otherwise provide a trigger
   for.
6. A manager can hold at most one team, same as today — releasing a team
   simply returns them to holding none.

## Out of scope

- **What causes a release.** Inactivity (#63) and insolvency (#27) are
  separate tickets that call this mechanism; neither is decided here.
  This ticket has no automatic trigger — only the operator action in
  scope item 5.
- **A grace period or warning before release.** Belongs to whichever
  trigger fires it — #63 warns in advance, #27 has its own multi-week
  ladder. Building a grace window into the mechanism itself would leave
  two clocks disagreeing about when a team is actually lost.
- **Voluntary resignation.** A manager choosing to give up their own team
  is a different feature with its own abuse questions (rage-quit, reroll
  for a better starting roster). Not asked for here.
- **A general notification/inbox system.** The "told clearly" requirement
  in scope item 4 is met with a message on the screen the ex-manager
  already lands on, not a persistent message centre.
- **A public record of who used to manage a team.** The record in scope
  item 3 is visible only to the account it belongs to.
- **The team's final league position, or any other snapshot of
  competitions/ data, on the record.** That data already lives in and is
  computed by `competitions/`; freezing a copy of it at release time is
  a second, staler source of the same fact.
- **A cooldown before an ex-manager can claim again.** Re-claiming is
  mechanically identical to a first-time signup — no penalty, no
  advantage, no waiting period.
- **Excluding the lost team from being re-claimed by its former manager.**
  They go through the same claim path as anyone else, which may or may
  not hand them back the same team; nothing here changes that.

## Rules and edge cases

- Releasing a team that already has no manager does nothing observable
  and writes no record — there is no ex-manager to notify or record
  anything about.
- A release is a single all-or-nothing action: the manager link is
  cleared and the record is written together, or neither happens. A team
  with its link cleared but no record (or the reverse) must never be
  observable.
- The record is written every time a team is released, regardless of what
  caused it — there is no such thing as an untracked release, including
  the operator action in scope item 5.
- The record captures the team's name as it was at the moment of release,
  not a live reference to the team. If the team is later claimed and
  renamed, every past manager's record of it keeps the name they knew it
  by.
- An account can accumulate more than one such record over time, if it
  claims, loses, and claims again across multiple teams.
- Because a manager can hold only one team, losing a team always leaves
  the account holding none — there is no case of losing one team while
  still managing another.
- The message an ex-manager sees on their next login names the team they
  lost and states why (in line with whatever fixed set of reasons the
  eventual triggers define — this ticket itself only produces "released
  by an operator"). It is shown once, at the point they'd otherwise land
  on a dashboard they no longer have.

## Decisions taken

- **Re-claiming confers no advantage and no penalty over a first-time
  signup.** Mechanically identical: assigned team, fresh roster, same
  starting position. (From the original ticket, 2026-09-15.)
- **The account keeps a record of teams previously managed**, so losing a
  team is a setback with a story, not an erasure. (From the original
  ticket, 2026-09-15.)
- **The record is minimal and private.** Team name, managed-from,
  managed-until, and the reason it ended. Visible only to the account it
  belongs to. No league position or other competitions/ snapshot — that
  data is already owned and computed elsewhere.
- **Notification is a message on the ex-manager's next login**, shown on
  the same screen that sends them to claim a new team. No new inbox
  concept.
- **The team keeps racing without interruption.** Once unmanaged, it's
  handled exactly like any other unmanaged team (#44's default squad
  selection) — release changes only who manages it, nothing about how it
  plays.
- **Until #63 or #27 exist, an operator is the only thing that can call
  this.** This ticket ships the mechanism and one manual way to invoke
  it, not an automatic trigger — that's deliberately left to the tickets
  that are actually deciding *when*.
- **A manager holds at most one team at a time**, unchanged from today.

## Open questions

None outstanding — the original ticket's open questions are answered
above, except the ones that belong to #63 and #27 themselves (how long is
"inactive," what counts as insolvency) and are left for those specs.

## Deferred

- **Richer record content** (seasons managed, final standings) — wait
  until there's a reason to look back at more than "what team, when, and
  why."
- **Public managerial history** — wait until there's a profile screen or
  other reason for other players to see it.
- **A real notification/message centre** — wait until there's a second
  feature that needs one; building it for a single message here is early.
- **Voluntary resignation** — wait until it's actually requested; it's a
  different feature with its own design questions.
