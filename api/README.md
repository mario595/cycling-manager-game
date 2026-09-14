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
  See `racing/README.md`, *Squads*.
- `POST /api/accounts/register/`, `POST /api/accounts/login/`,
  `POST /api/accounts/logout/` — owned by `accounts/`, included here under
  `/api/accounts/`. See `accounts/README.md`.
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
`config/settings/base.py`) is `IsAuthenticated`. Three endpoints override it
with `AllowAny`, **by design, not as a placeholder**: the clock, the season
position, and the calendar. World data like this is the game's shop window —
meant to be visible to a visitor deciding whether to sign up — so it stays
public even though a login flow now exists. Any future endpoint here should
default to the project's `IsAuthenticated` unless it has the same reason
these three don't.

`SquadView` is the opposite case, and used to be the exception: it is now
plain `IsAuthenticated`, with the team always `request.user.team` rather
than a URL parameter — see `team_for()` in `api/views.py`, and
`accounts/README.md` for why that helper lives here instead of in
`accounts/`. There is no more "anyone can edit anyone's squad" hole; a
caller with no team gets a 403, not someone else's squad.

**CSRF.** DRF's `SessionAuthentication` enforces CSRF only for
*authenticated* sessions — an anonymous request passes `CsrfViewMiddleware`
untouched, which is why the squad endpoint needed no CSRF handling before
login existed. Now that `SquadView` requires authentication, its `PUT`
enforces CSRF like every other authenticated write, and the SPA sends
`X-CSRFToken` on all of them (`frontend/src/api.ts`'s `writeJson`). The
token itself comes from the `csrftoken` cookie, which `GET
/api/accounts/me/`'s `@ensure_csrf_cookie` guarantees is set before the SPA
issues its first write — see `frontend/README.md`.
