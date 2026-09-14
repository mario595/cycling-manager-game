# Player accounts: register, log in, log out

**Status:** proposed
**Domain(s):** `accounts/`, `frontend/`, `api/`
**One-liner:** A visitor can create an account and log in; a logged-in user without a team can still watch the world.

## Why this exists

Right now nobody can become a player. `accounts.User` exists as a model, but
the only way to create one is `createsuperuser` or the Django admin — there
is no registration, no login, no logout, and the SPA has no idea who, if
anyone, is using it. Every feature that assumes "a user signs up" (claiming a
team, mid-Season placement, anything team-specific) is standing on ground
that doesn't exist yet.

It also closes a workaround that has been sitting in the codebase without a
ticket: the API's world-facing endpoints are marked `AllowAny` specifically
because there was no login flow to gate them behind. That reason disappears
once this ships, so the public/private line on those endpoints becomes a
deliberate choice instead of a placeholder.

One of those workarounds is no longer hypothetical. Squad selection (#37)
shipped with the team a manager is picking for taken from a `?team=` URL
parameter rather than from who is logged in, and its endpoint is `AllowAny`
with the team id caller-supplied — so today, anyone can edit anyone's squad.
`api/README.md` and `frontend/README.md` both already name this feature as
what closes it. This spec inherits that as a concrete, player-visible
requirement, not just an abstract "endpoints can stop opting out."

## Player experience

A visitor opens the game and sees the world as it stands today — the
calendar, the current week, results as they come in — with no login wall in
front of any of it. Somewhere in the SPA is a way to register or log in.

Registering asks for an email, a password, and a display name — the name
other managers will see. Submitting it creates the account and logs the
player in immediately; there is no confirmation email to wait for and no
separate first step.

Once logged in, the player sees their own name somewhere in the interface
and a way to log out. If they don't yet manage a team — which, today, is
every new registrant, since claiming a team is a separate piece of work
still being built — the game does not block them or show them an empty
error. They get the same read-only view of the world a visitor gets, just
now clearly *as themselves*: logged in, watching, with nothing to manage
yet. Nothing about this state is a wall waiting to be knocked down later; a
manager who later loses their team (a case outside this feature, decided
elsewhere) lands in the exact same place.

Logging out returns them to the visitor view. Closing the browser and coming
back later, or just reloading the page, keeps them logged in — they are not
asked to log in again every visit.

If a player does manage a team — by the time this ships, that may already be
possible via #46's claim flow — the screens that are specific to their team
(picking a race squad, today's example) know that without being told: the
player doesn't type in or select which team they're managing, the game
already knows, because they're logged in as themselves.

Logging in with the wrong password, or registering with an email already in
use, tells the player plainly what went wrong. Nothing here asks a player to
solve a puzzle to prove they're human.

## In scope

1. A visitor can register with an email, a password, and a display name.
2. Registering logs the player in immediately — no separate confirmation
   step, no verification email.
3. A registered player can log in with their email and password.
4. A logged-in player can log out.
5. The SPA can tell, at all times, whether the current visitor is logged in,
   and if so, their display name.
6. Login state survives a page reload and a return visit — the player is not
   asked to log in again just because they closed the tab.
7. A logged-in player who manages no team sees the same world data a
   logged-out visitor sees (calendar, results, current week), clearly
   presented as their own logged-in view rather than an error or a dead end.
8. A failed login (wrong password, unknown email) and a failed registration
   (email already registered) each produce a message that says what went
   wrong, not a generic failure.
9. Registration has no gate — no invite code, no approval step. Anyone can
   create an account.
10. The world-facing read endpoints that are public today (clock, season
    position, calendar) stay public after this ships. Their `AllowAny` is
    no longer a workaround for "no login flow exists" — it's a deliberate
    choice, because that data is the game's shop window and should be
    visible before anyone signs up.
11. A logged-in player managing a team never has to tell the game which team
    that is. Screens that act on "my team" (squad selection is the existing
    example) work from who is logged in, not from a team picked in the URL
    or a form field.

## Out of scope

- **Claiming a team, or anything about what a team-less player does next.**
  That belongs to #46, which is deciding what a claim hands over. This
  feature stops at "logged in, no team, watching" — it does not build a
  claim button or a team-assignment flow, even a stub one.
- **Password reset, change password, change email, delete account.** Split
  into #51 already; not touched here. Losing a password is a dead end in
  this feature — a player would need a new account.
- **Email verification.** Collected but not confirmed. Verifying it needs
  email delivery, a deployment/cost decision `CLAUDE.md` marks TBD — bundling
  it here would make this feature block on infrastructure it doesn't need.
  A player can register with an email nobody checks.
- **Invite-only or gated registration.** Considered and rejected — with one
  Division and no deployment yet, a gate is a second feature that buys
  nothing today.
- **Locking down `world`/`schedule` endpoints beyond what exists today.**
  This feature adds no new `IsAuthenticated` requirement to the clock,
  position, or calendar endpoints. The squad endpoint is the one named
  exception — see "in scope" above — because it is already documented as
  this feature's job to close, not a new ask.
- **Redesigning squad selection itself.** Only how the game identifies which
  team a request is acting for changes (from a URL parameter to the logged-
  in user). The screen, the selection rules, and everything else `racing/
  README.md` specifies about squads is untouched.
- **Anything visible to other managers beyond a display name.** No profile
  page, no player-to-player messaging, no manager directory.

## Rules and edge cases

- A player registers with an email already in use: registration is refused,
  and the message says the email is taken — it does not say whether it
  belongs to someone else's password guess.
- A player logs in with a correct email but wrong password, or an email that
  isn't registered at all: both produce the same "email or password is
  wrong" message. The game does not confirm or deny whether an email is
  registered.
- A team-less logged-in player and a logged-out visitor see the same world
  data. The only difference is that the logged-in player's own identity
  (their display name, a logout control) is visible somewhere in the
  interface; nothing about the world view itself changes based on whether
  they manage a team.
- Session persistence is indefinite in the sense that a normal visit doesn't
  expire it — a player is not logged out just because time passed between
  visits. (This feature does not define an explicit session lifetime;
  whatever Django's default session behavior gives is what ships.)
- A player who is already logged in and opens the register or login screen
  again is not asked to authenticate twice — the game already knows who they
  are, so both screens are a no-op state for them.
- A logged-in player tries to view or change a squad for a team they don't
  manage: refused. Nobody but a team's own manager can act on its squad,
  regardless of what team id a request names.

## Decisions taken

- **Registration does not create a team.** Settled 2026-09-12 on the issue:
  a new user claims an unmanaged team rather than creating one from scratch.
- **The claim is not built in this feature.** #46 (in progress) is deciding
  what a claim hands over; #50 stops at the team-less logged-in state so it
  doesn't wait on or duplicate that decision.
- **A team-less logged-in user is a spectator, not a blocked state.** They
  see the same world data a visitor sees, clearly as themselves. This is
  also the shape of the answer for a manager who later loses a team — one
  state handles both "never had a team" and "no longer has one."
- **Login identifier is email; display name is what's shown publicly.**
  Email is unique and doesn't collide; `display_name` already exists on the
  `User` model and is the field meant to be shown to other managers.
- **Registration is open, not invite-gated.** No abuse risk yet at this
  scale, and a gate is a separate feature.
- **No email verification at registration.** Verification needs email
  delivery, which is explicitly deferred to #51 as an infrastructure/cost
  decision, not a game-design one.
- **World-facing read endpoints (clock, position, calendar) stay `AllowAny`
  after this ships.** The reason changes from "no login flow exists" to
  "this data is meant to be visible before signup," but the access level
  doesn't change.
- **Squad selection stops taking the team as caller-supplied input.** #37
  shipped it with `?team=` in the URL and an `AllowAny` endpoint as a
  documented placeholder for this feature. Closing that placeholder is
  in scope here, not deferred, since it's the one concrete case today of
  "an endpoint that can stop opting out."

## Open questions

None outstanding for this feature. (Questions the issue raised that are now
answered elsewhere: the claim flow and what it hands over → #46; mid-Season
placement → #14; password reset and the rest → #51.)

## Deferred

- **Claiming a team from the spectator state** — #46 first; wire in once
  that spec lands.
- **Email verification** — #51, pending an email-delivery decision.
- **Password reset, change password, change email, delete account** — #51.
- **Invite-only registration** — no case for it yet; revisit only if open
  registration turns out to be a real problem at playtest scale.
