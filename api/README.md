# API

## What lives here

DRF routers and serializers that aggregate other apps' data for the SPA.
`api/` owns no models of its own — it translates, it does not persist.

## What exists

- `GET /api/world/clock/` — the game's current time (`ClockSerializer`,
  `ClockView`, serializing `world.services.now()` directly — there is no
  model instance behind this response, since in production there is
  nothing stored to read). See `world/README.md` for what the clock is.
- `GET /api/schedule/position/` — where the world is in its season
  (`PositionSerializer`, `PositionView`, serializing
  `schedule.services.current_position(now())`). One of three shapes,
  discriminated by `state`: `in_season` (with `season`, `week`,
  `week_ends_at`), `off_season` (with `season` — the one that just
  finished — and `week`/`week_ends_at` null), or `no_season` (everything
  null, before any season has ever been declared). See
  `schedule/README.md` for what a season is.
- `GET /api/schedule/calendar/` — the current season's whole calendar
  (`CalendarSerializer`, `CalendarView`). Same `state` vocabulary as the
  position endpoint. `weeks` is always exactly twelve entries when
  `in_season`, each with a `races` list — zero to seven entries, since the
  calendar's rule is at most one race per *day*, not per week — never a
  shorter list and never `null`, so an empty week is visible as one rather
  than looking like missing data. Outside `in_season`, `weeks` is `[]`.
  `status` on a race is `Race.status` verbatim (including `failed`);
  mapping it to player-facing words is the SPA's job. See
  `schedule/README.md`, *The race calendar*.
- `GET`/`PUT /api/racing/races/<race_id>/squad/` — the **caller's own**
  team's squad for one race (`SquadSerializer`, `SquadWriteSerializer`,
  `SquadView`). No team id in the URL: the team is always
  `request.user.team`, via the `team_for()` helper below. `GET` returns the
  team's saved selection if it has one, else a suggestion from
  `racing.services.suggested_squad` (`saved: false`). `PUT` replaces it via
  `racing.services.set_squad` and returns the same shape; a `SquadError` (wrong
  size, a rider from another team, no single leader, or a race that has
  already started) becomes a 400, and a caller with no team becomes a 403.
  `candidates` is the team's whole roster, each flagged `selected`/
  `is_leader`, so one response gives the squad screen everything it draws.
  Its five engine attributes are the 0-10 display scale, same as the riders
  endpoint below — see `racing/README.md`, *Squads*. Each candidate also
  carries `freshness` on that same 0-10 display scale; the hidden
  `recovery_rate` behind it never appears in this or any other payload — see
  `riders/README.md`, *Freshness*.
- `GET /api/riders/` — the **caller's own** team's roster (`RiderSerializer`,
  `RiderListView`). Same `team_for()` pattern as the squad endpoint: no team
  id in the URL, a caller with no team gets a 403. Attributes and freshness
  are shipped through `riders.display.to_display_scale` (0-10, never the
  stored 1-100); the hidden traits (`potential`, `peak_age`, `decline_rate`,
  `injury_proneness`, `training_affinity`) and the hidden `recovery_rate`
  never appear in this or any other payload — see `riders/README.md`.
- `GET /api/racing/races/<race_id>/` — one race's own facts
  (`RaceDetailSerializer`, `RaceDetailView`): id, name, status, starts_at,
  distance and the raw `{length, gradient}` course segments. Readable by any
  authenticated manager regardless of team — the contrast with `SquadView`
  below, which 403s a caller with no team. No status filter: a `scheduled`,
  `running`, `finished` or `failed` race all return `200`; the status is in
  the payload and the SPA decides what to draw.
- `GET /api/racing/races/<race_id>/results/` — a finished race's finishing
  order plus each team's points from it (`RaceResultsSerializer`,
  `RaceResultsView`). A race that has not reached `FINISHED` is a `404`, not
  a `200` with an empty list — "no results yet" and "no such race" would
  otherwise look the same to the SPA. `points` carries one row per team that
  started, scoring teams first ordered by position and then the rest by
  name, with `position: null` and `points: 0` for a team that scored
  nothing — the starter set comes from `RaceSquad`, not from which teams
  recorded a result (see `racing/README.md`, *Squads*). `IsAuthenticated`,
  the project default.
- `GET /api/competitions/standings/` — the current season's points table
  (`StandingsSerializer`, `StandingsView`, serializing
  `competitions.services.standings`). Same `state` vocabulary as
  `PositionView`/`CalendarView`: `in_season`, `off_season` (the season that
  just finished, with its final table), or `no_season` (`standings: []`).
  `rank` is computed server-side from the sorted order — two teams level on
  points and countback are genuinely joint, and the server is where that is
  known. `IsAuthenticated`, like every endpoint the SPA reads.
- `POST /api/accounts/register/`, `POST /api/accounts/login/`,
  `POST /api/accounts/logout/` — owned by `accounts/`, included here under
  `/api/accounts/`. See `accounts/README.md`.
- `POST /api/teams/claim/` (`ClaimTeamSerializer`, `ClaimTeamView`) — assigns
  the caller an unmanaged team, renamed and recoded to their choosing
  (`name`, `code` in the body; a lowercase code is uppercased, not rejected).
  Plain `IsAuthenticated`. Returns the new team (`id`/`name`/`code`, the same
  shape as `me`'s `team`) with 201. A caller who already manages a team, or a
  world with no unmanaged team left, both return 409 — the request is
  well-formed but the world's state refuses it. A malformed code or a name
  already taken returns 400. See `teams/README.md`, *Claiming a team*.
- `GET /api/staff/` (`StaffSerializer`, `StaffView`) — the **caller's own**
  team's staff: `trainer` (null when the slot is empty), `pool` (every
  unemployed trainer, but only populated when the slot is empty — a team
  with a trainer has nothing to hire, so the pool is `[]`), and the team's
  `balance` so the SPA can grey out a hire it cannot afford. Same `team_for()`
  pattern as the squad and roster endpoints: no team id in the URL, a
  caller with no team gets a 403. A trainer's five skills are shipped
  through `to_display_scale`, same as a rider's attributes, alongside the
  two prices derived from their speciality (`hire_fee`, `weekly_salary`) —
  see `staff/README.md`, *What a trainer costs*.
- `GET /api/economy/finances/` (`FinancesSerializer`, `FinancesView`) — the
  **caller's own** team's finances: `balance` (the sum of the ledger, never
  a stored column) and `entries`, newest first, each with `kind`,
  `description`, `amount`, `occurred_at`, `rider_count` and a `balance_after`
  running total computed in Python as the list is walked. Same `team_for()`
  pattern as the staff endpoint: no team id in the URL. Unlike `staff/`, a
  caller with no team gets `{"balance": 0, "entries": []}` — the screen has
  an empty state, not an error. See `economy/README.md`.
- `POST /api/staff/trainer/hire/` (`HireTrainerSerializer`,
  `HireTrainerView`) — hire the pool trainer named by `trainer_id` into the
  caller's empty slot, debiting the hire fee from the team's ledger. `204`
  on success. `409` (not `400`) when that trainer was hired by someone else
  a moment earlier, when the caller's slot is already filled, or when the
  team cannot afford the fee — the request is well-formed, but the world's
  state refuses it, the same split `ClaimTeamView` documents. The debit and
  the affordability check both run **inside** `hire_trainer`'s transaction
  (the injected `charge` callback, `staff/README.md`), so a refused or
  failed hire leaves no fee row and the trainer in the pool.
- `POST /api/staff/trainer/fire/` (`FireTrainerView`) — return the caller's
  trainer to the shared pool. `204` on success, `409` if the caller has no
  trainer to fire. `POST`, not `DELETE`: nothing is destroyed, the trainer
  survives in the pool.
- `GET /api/accounts/me/` (`MeSerializer`, `MeView`) — whether anyone is
  logged in, their display name, and their team (`id`/`name`/`code`, or
  `null`). Lives here rather than in `accounts/` because answering "does
  this user have a team" needs both `accounts` and `teams`, and `accounts/`
  may import neither — see `accounts/README.md`, *What `accounts/` may
  import*. `@ensure_csrf_cookie`: this is the request the SPA relies on to
  guarantee it holds a CSRF token before it ever issues a write (see
  *Authentication*, below).

## URL ordering

`config/urls.py` includes `api/urls.py` **above** the SPA catch-all
(`<path:unused>`). The catch-all matches any path, so an API route listed
after it would silently return the SPA's `index.html` instead of JSON.

## Authentication

The project default (`REST_FRAMEWORK["DEFAULT_PERMISSION_CLASSES"]` in
`config/settings/base.py`) is `IsAuthenticated`. The game exposes nothing to
an anonymous visitor: the clock, season position and calendar endpoints used
to override the default with `AllowAny`, but that is **deliberately
reversed** — a visitor who is not logged in gets a 403 from every data
endpoint here. If a future landing page wants shop-window world data for
visitors again, reopen that deliberately, not by assuming today's
auth-on-everything is an oversight.

`MeView` is the single exception, and it **must remain** `AllowAny`. It is
the endpoint that answers "nobody is logged in": the SPA fetches it on mount
and the route guard depends on that answer, so making it `IsAuthenticated`
would 403 the one request that tells the app to show the login screen, and
the app would never boot for a visitor. Its `@ensure_csrf_cookie` is
likewise load-bearing for writes (see *CSRF* below).

`SquadView` and `RiderListView` are both plain `IsAuthenticated`, with the
team always `request.user.team` rather than a URL parameter or query string —
see `team_for()` in `api/views.py`, and `accounts/README.md` for why that
helper lives here instead of in `accounts/`. Neither has an "anyone can view
or edit anyone's squad/roster" hole; a caller with no team gets a 403, not
someone else's data.

**CSRF.** DRF's `SessionAuthentication` enforces CSRF only for
*authenticated* sessions — an anonymous request passes `CsrfViewMiddleware`
untouched, which is why the squad endpoint needed no CSRF handling before
login existed. Now that `SquadView` requires authentication, its `PUT`
enforces CSRF like every other authenticated write, and the SPA sends
`X-CSRFToken` on all of them (`frontend/src/api.ts`'s `writeJson`). The
token itself comes from the `csrftoken` cookie, which `GET
/api/accounts/me/`'s `@ensure_csrf_cookie` guarantees is set before the SPA
issues its first write — see `frontend/README.md`.
