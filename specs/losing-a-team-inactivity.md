# Losing a team: inactivity

**Status:** proposed
**Domain(s):** `accounts/`, `teams/`, `world/`
**One-liner:** A manager who hasn't logged in for ten game-weeks loses their team, which returns to the unmanaged pool for someone else to claim.

## Why this exists

A Division holds a fixed number of teams. A manager who stops playing keeps
one of those places occupied indefinitely — their team doesn't leave, it just
sits there fielding a default squad forever (`#44`), racing but never
improving, while a stranger who wants to play has nowhere to go once every
team is spoken for. This gives the game a way to notice that a manager is
gone and act on it, so an abandoned place eventually becomes available again.

The mechanism for taking a team away and returning it to the pool already
exists (`#62`) — `teams.services.release_team()`. This feature is only the
missing half: deciding *when* inactivity is the reason to call it.

## Player experience

A manager plays for a while, then stops — they simply never log in again.
Nothing happens to them immediately; there is no countdown they can watch,
no warning email. Ten game-weeks after their last login, if a Season is
running, their team is quietly returned to the unmanaged pool. It keeps
racing exactly as it did the day before — same roster, same results, same
place in the table — it simply no longer belongs to them.

If that manager ever comes back, logging in tells the whole story at once:
they land on the claim screen instead of their old dashboard, with a message
naming the team they lost and why ("Manager inactive"). From there they claim
a new team and start again, exactly like a first-time signup.

A manager who logs in even once during those ten weeks — even without
touching anything else — is safe. The clock resets the moment they're seen
again, whether or not they picked a squad, changed training, or did anything
else while they were there.

## In scope

1. A manager who has not logged in for ten consecutive game-weeks, while a
   Season is running, loses their team: it is returned to the unmanaged pool
   and can be claimed by anyone.
2. Logging in at all resets the count, regardless of what the manager does
   or doesn't do afterward during that session.
3. Weeks in which no Season is running do not count toward the ten.
4. The manager finds out what happened the next time they log in, via the
   mechanism `#62` already provides — the claim screen names the team and
   says why.
5. A manager who has never logged in since registering is exempt from this
   trigger — there is no "last login" to measure from, and a brand-new
   account should not be able to lose a team it was only just given.

## Out of scope

- **Any warning before removal.** With no email (`#51` deferred), a warning
  cannot reliably reach someone who has stopped opening the game — building
  one now would be effort spent on the one audience it can't reach. Revisit
  once `#51` exists; a natural shape then is a warning at week six or eight,
  but that is not decided here.
- **Distinguishing "logged in" from "actually did something."** A manager
  who logs in weekly but never picks a squad is treated as active. `#44`
  already fields a default squad for a team with no input, so a passive
  manager's team is no worse off than an unmanaged one — there's nothing
  this trigger needs to protect against by demanding more than a login.
- **Any grace period beyond the ten weeks themselves, or a second warning
  window.** `#62`'s mechanism has no grace period built in by design; this
  trigger doesn't add one either. Ten weeks *is* the grace period.
- **Changing the threshold per Division, per player, or over time.** One
  fixed number, everywhere.
- **What happens to a team while no Season is running, beyond "the clock
  doesn't move."** The team's off-season state isn't touched by this
  feature at all.
- **Insolvency as a trigger.** That's `#27`, a separate ladder with its own
  timeline, sharing only the `#62` mechanism this also calls.

## Rules and edge cases

- The count is in **game weeks**, the same unit `world/`'s tick already
  uses for training and growth — not calendar days. In development, where
  the game clock can run compressed, ten game-weeks is not ten real days.
- The count only advances while a Season is open. A manager who goes quiet
  for the last three weeks of a Season and the first seven of the next one
  has not been inactive for ten consecutive weeks of *play* — only for
  however many of those weeks fell inside a running Season.
- A login is a login — there's no minimum time spent, no page that must be
  visited beyond signing in. This is deliberately the most forgiving
  interpretation available, per *Out of scope*.
- Because a manager holds at most one team, losing a team to inactivity
  always leaves the account holding none — never a partial loss.
- If a manager's team is released for inactivity, then they log in the very
  next moment, they still see the "you lost your team" message and go
  through claiming again — logging in after the fact doesn't undo a release
  that already happened, only prevents the next one.
- A team release for this reason is recorded with the same "Manager
  inactive" explanation every time — no distinguishing detail (how long they
  were actually gone, whether they'd logged in but never acted) beyond what
  `#62`'s record already keeps.

## Decisions taken

- **Activity = any login**, not a squad pick or other action. Simple, uses
  what the account already tracks, and consistent with `#44`'s default
  squad meaning a passive team is never actually neglected on the pitch.
- **Threshold = 10 game-weeks of no login**, counted only while a Season is
  running. Long enough that a holiday or a busy month never triggers it;
  short enough that a place frees up within roughly one Season of true
  absence.
- **No warning in this feature.** Deferred until email (`#51`) exists;
  in-game-only warnings can't reach the audience they're for.
- **Off-season time doesn't count.** There's nothing to be absent from
  between Seasons.
- **A never-logged-in account cannot lose a team this way.** Sidesteps a
  degenerate case (a claimed-but-abandoned-at-birth team) that doesn't need
  its own rule.

## Open questions

- Whether the check runs as part of the existing tick (at each week
  transition, alongside training and growth) or as its own scheduled pass —
  a technical decision for the plan, not a product one.
- Exactly how "ten consecutive game-weeks, only while a Season is running"
  is measured when a manager's inactivity spans a season boundary — the
  rule above states the intent; the counting mechanics are for the plan.

## Deferred

- **A warning before removal** — wait for `#51` (email).
- **A softer signal short of full removal** (e.g., a public "inactive" flag
  visible to the manager or others) — no current reason to build it; revisit
  if removal alone proves too abrupt in practice.
