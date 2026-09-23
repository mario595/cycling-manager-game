# Teams

## What this app owns

`Team` — name, code, colours, and the `manager` link to `accounts.User`.
`services.claim_team()` and `services.release_team()`, the two writers of
that link. The `seed_teams` and `release_team` management commands. Not
rosters (`riders/` owns `Rider`), not standings (`competitions/`), not money
(`economy/` owns the ledger).

## Claiming a team

A registered user with no team calls `claim_team(user, name=..., code=..., at=...)`
(exposed as `POST /api/teams/claim/`, `api/README.md`). One transaction:

1. Locks the lowest-`pk` unmanaged team with `select_for_update(skip_locked=True)`
   — deterministic and testable, and `skip_locked` means a concurrent claimer
   takes the *next* free team instead of blocking on this one.
2. Sets `manager`, `name`, `code` on it, and calls `full_clean(exclude=["manager"])`
   before saving — **`team_code_validator` is a field validator and does not
   run on `.save()`**; without the explicit `full_clean()` a malformed code
   would reach the database.
3. Releases every rider currently on the team (`team.riders.update(team=None)`)
   — they become free agents, not deleted. Deleting them would cascade-delete
   their `racing.RaceResult` and `racing.RaceSquadRider` rows, silently
   erasing the team's race history.
4. Generates a fresh roster via `riders.generation.generate_roster()` and
   assigns it to the team.
5. Writes a ledger `takeover` entry that brings the team's balance back to
   `STARTING_BALANCE`, and a fanbase `takeover` row that brings its fanbase
   back to `STARTING_FANBASE` (#21) — `reset_to_starting_balance(team, at=...)`
   and `reset_fanbase(team, at=...)`, both imported **inside `claim_team`**
   (see *What `teams/` may import*). The team's financial and fanbase history
   is never deleted; each takeover is a *new* row on top of it —
   `economy/README.md`, *The ledger is append-only* and *Fanbase is derived
   too*. The `at` (game time) is passed in by the caller — `api/`'s view and
   `seed_teams` supply `world.services.now()` — because `teams/` must not
   import `world/`.
6. Voids any sponsorship contract in force and clears unsigned offers —
   `economy.services.void_sponsorship(team, at=...)`, same lazy import as
   step 5 (#22; see `economy/README.md`, *Sponsorship*). A new manager is
   never handed a contract they never agreed to; the API generates them a
   fresh offer round on their first visit to the Sponsors screen.

The claim also stamps `Team.managed_since = at` — the moment `release_team`
(below) reads when the spell it records ends, and clears when the team is
released.

If no unmanaged team exists, `claim_team` raises `NoTeamAvailable`. A second
claim by an already-managing user is not checked here — `Team.manager` is a
`OneToOneField`, so it raises `IntegrityError`; the caller
(`api.views.ClaimTeamView`) checks first via `team_for()` so the happy path
never relies on that exception. See `specs/claiming-a-team.md` (deleted once
this closed — see git history) for the product reasoning: the team's
position, points and race history carry over unchanged (inherit the past),
while its roster does not (reset the present).

**A claim is atomic or it does not happen.** A half-claimed team — renamed
but with no roster — must never be observable. Everything above runs inside
one `transaction.atomic()`.

## Releasing a team

`release_team(team, *, reason, at)` (#62) is `claim_team`'s counterpart:
it returns a managed team to the unmanaged pool. It is **not** claim's
inverse, and deliberately so — it clears `Team.manager` and
`Team.managed_since` and writes one `ManagerialSpell` (below), and touches
**nothing else**: not the roster, not the ledger, not the fanbase, not the
sponsorship. A released team must be indistinguishable from a team that was
never managed, because #44's default squad selection has to pick it up
exactly as it would any other unmanaged team. All of the *resetting* — fresh
roster, balance, fanbase, voided sponsorship — happens on the *next* claim,
the same as it always has; release does none of it.

Locks the row with `select_for_update()`, **without** `skip_locked` — the
opposite of `claim_team`'s lock. `claim_team` is shopping for any free team
and should move on to the next one if this row is contended; `release_team`
acts on one specific, named team and must not silently no-op just because
another transaction happens to hold it. Re-reading the row under the lock
(rather than trusting the `team` instance the caller passed in) is what
makes the "does this team still have a manager" check honest against a
concurrent release.

Returns `None`, and writes nothing, if the team already has no manager —
not an exception. Both of the tickets expected to call this (#63, #27) will
be scanning many teams and can race each other; "already released" is a
normal outcome for them, not a failure.

`ManagerialSpell.Reason.INACTIVITY` is now reachable (#63) — `world.services.tick()`
calls `release_team` for every manager who has gone ten in-season game-weeks
without logging in (see `world/README.md`, *How a tick works*). `ADMIN`
remains the manual path, for testing and any hand intervention:

```bash
python manage.py release_team <team-id-or-name> [--reason admin]
```

## Managerial spells

`ManagerialSpell` is the record of one completed period during which a user
managed a team — written by `release_team`, never by `claim_team`. It
carries `team_name`/`team_code` **snapshotted at release**, not read live
through its `team` FK: #46 lets the next claimer rename the team, and a live
read would silently rewrite an ex-manager's own history the moment a
stranger renames the team they used to run. The FK itself is kept (nullable,
`SET_NULL`) only so the row survives the team being deleted outright (e.g.
`seed_teams --reset`).

It lives here, in `teams/`, rather than in `accounts/` — despite being "the
account's record of teams previously managed" in player-facing terms —
because `accounts/` imports nothing and sits at the root of `AGENTS.md`'s
dependency graph (`accounts/README.md`). A model there with a FK to
`teams.Team` would invert that. The record is about a team's managerial
history; `teams/` already may import `accounts`, so the FK to
`accounts.User` runs the correct way.

`acknowledged_at` is what makes the ex-manager's "you lost this team" message
show exactly once: `GET /api/accounts/me/` reports the caller's most recent
spell with `acknowledged_at IS NULL` as `lost_team` (only when the caller
currently has no team), and `POST /api/teams/spells/<id>/acknowledge/` sets
it — see `api/README.md`. This is real time (`django.utils.timezone.now()`,
like `world.TickRun.finished_at`), not game time — it records when a person
actually saw a screen, which has nothing to do with the game's clock.
`started_at`/`ended_at` are game time, from `Team.managed_since` and the
caller's `at`.

## Codes are not unique

`Team.code` has **no** `unique=True` constraint. A code is a display label,
not the team's identity — `Team.pk` is the identity everywhere it matters
(FKs, the manager relationship). Two teams may share a code; a player is
never told their choice is taken.

This is deliberate, not an oversight: forcing uniqueness on a manager-chosen
three-letter code means asking a new player to guess which of ~17,576
combinations are free, for a field whose only job is being a short label
next to a name.

**The cost of this decision is [#56](https://github.com/mario595/cycling-manager/issues/56)**,
not yet built: two teams sharing a code in the same Group is confusing in a
classification table or a race startlist. The fix belongs at *display* time —
whatever renders a clashing pair of codes disambiguates them (`MGO-A`,
`MGO-B`), and the stored code is never mutated to do it. A stored suffix
would go stale the moment Group membership changed (promotion, relegation,
another team renaming), and race logs bake a team's code in at simulation
time as a permanent record — `racing/README.md` — so writing a suffix into
one would freeze a collision into history that may no longer exist.

`Team.name` **is** still unique — the fairness argument for dropping
uniqueness is specific to a three-letter label with a small combination
space; a world with two teams both named the same thing is a worse and
different problem, and names are the primary identifier everywhere they
appear.

## What `teams/` may import

`core`, `accounts`, and **`riders`** — widened by claiming, which generates
and assigns a roster. See `AGENTS.md`'s dependency graph.

This does not create a cycle with `riders -> core, teams`: that edge is a
**model-level** string reference (`Rider.team = ForeignKey("teams.Team", ...)`),
and `riders.generation` (what `teams/services.py` actually imports) only
imports `riders.models` — no module that imports `teams/` at runtime. If this
ever changes, the suite catches it immediately: a real cycle surfaces as an
`ImportError` at Django startup, not a subtle bug.

### A special case: `economy/`

`teams/` may import exactly the `economy/` functions it writes inside
**function bodies, never at module scope**: `reset_to_starting_balance`,
`reset_fanbase` and `void_sponsorship` in `claim_team`, plus
`ensure_opening_balance`, `ensure_starting_fanbase` and (when a season
exists) `ensure_offer_round` in `seed_teams`' `handle()`. This is the same
entry-point pattern as `seed_teams` importing `racing.models` inside
`handle()` — `AGENTS.md`'s dependency graph says `economy -> teams`, and a
module-scope `from economy.services import ...` would import `economy/` (and
through it `teams/`) the moment `teams/models.py` loads, creating a cycle.
Importing inside the function keeps the edge real but lazy. See
`economy/README.md`.

## `seed_teams` — populating a claimable world

```bash
python manage.py seed_teams [--count=16] [--per-team=12] [--reset]
```

Creates `--count` unmanaged teams, each with a freshly generated `--per-team`
roster via `riders.generation.generate_roster`. Without `--reset` it *adds*
teams; with `--reset` it first deletes every **unmanaged** team (and their
riders, results and squads).

**Never touches a managed team, `--reset` or not.** Filters strictly on
`manager__isnull=True` throughout — a `--reset` that could orphan a real
player's account by deleting their team is a footgun this command refuses to
be.

Names and codes come from a fixed list in the command (seed data, not game
logic); once `--count` exceeds the list, names and codes get a generation
suffix (`"Ardennes Racing 2"`, code `"ARX"` — a letter, not a digit, since
`team_code_validator` requires three uppercase letters).

Every team `seed_teams` creates or leaves in place gets a ledger opening
balance via `economy.services.ensure_opening_balance(team, at=...)` and a
starting fanbase via `ensure_starting_fanbase(team, at=...)` (#21; both
imported inside `handle()`, same entry-point rule as `racing.models` —
see *What `teams/` may import*). The `at` is the current game time — the
command reads `world.services.now()` itself, like `schedule/`'s `load_season`
does. If a season is currently under way (`schedule.services.current_position(at)`
resolves one), every team also gets a sponsor offer round via
`economy.services.ensure_offer_round(team, season, at=...)` (#22); `seed_teams`
normally runs before `load_season` (`AGENTS.md`'s seeding order), so a fresh
world simply has no season yet and this step is skipped — re-running
`seed_teams` once a season exists, or letting `world.services.tick()` cross
the season's open boundary, is what actually populates offers. The claim
block runs **after** that loop, so the team a `--claim-for` takes out of the
pool already sits at `STARTING_BALANCE` and `STARTING_FANBASE`; `claim_team`'s
takeovers then compute zero deltas and write nothing, leaving the claimed
team at the standard figures with exactly one `starting_balance` entry and
one starting fanbase row — no double credit. A team claimed later, once
wages have drained it and its fanbase has moved, gets the takeover row
instead (`economy/README.md`). `claim_team` also voids whatever sponsorship
round the loop above may have generated and the API replaces it with a
fresh one on the new manager's first visit — see *Claiming a team*.

Imports `racing.models` inside `handle()`, not at module scope — same rule
and reason as `riders/management/commands/reset_riders.py`: a management
command is an entry point, and `teams/`'s library code (`models.py`,
`services.py`) must not import `racing/`.

## Future work / possible improvements

- **Team-code disambiguation.** [#56](https://github.com/mario595/cycling-manager/issues/56),
  see *Codes are not unique* above.
- **Resetting a claimed team's money to a fixed starting amount.** **Done** —
  claiming writes a `takeover` ledger entry that brings the balance back to
  `STARTING_BALANCE` without deleting history. See *Claiming a team* above
  and `economy/README.md`.
- **Inheriting a claimed team's classification position and Season points.**
  Same story: decided, but there is no standings table for it to apply to
  until `competitions/` exists.
- **A manager choosing the team's colours at claim time.** Currently the
  claimed team's jersey colours carry over unchanged; changing them is a
  team-settings feature, not part of claiming.
- **What happens when a player abandons a team.** **Done** — see *Releasing
  a team* and *Managerial spells* above (#62). What is still missing is
  anything that actually *decides when*: #63 (inactivity) and #27
  (insolvency) are the tickets expected to call `release_team`; until
  either lands, only the `release_team` management command can.
