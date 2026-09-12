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
- `GET`/`PUT /api/racing/races/<race_id>/squads/<team_id>/` — a team's squad
  for one race (`SquadSerializer`, `SquadWriteSerializer`, `SquadView`). `GET`
  returns the team's saved selection if it has one, else a suggestion from
  `racing.services.suggested_squad` (`saved: false`). `PUT` replaces it via
  `racing.services.set_squad` and returns the same shape; a `SquadError` (wrong
  size, a rider from another team, no single leader, or a race that has
  already started) becomes a 400. `candidates` is the team's whole roster,
  each flagged `selected`/`is_leader`, so one response gives the squad screen
  everything it draws. See `racing/README.md`, *Squads*.

## URL ordering

`config/urls.py` includes `api/urls.py` **above** the SPA catch-all
(`<path:unused>`). The catch-all matches any path, so an API route listed
after it would silently return the SPA's `index.html` instead of JSON.

## Authentication

The project default (`REST_FRAMEWORK["DEFAULT_PERMISSION_CLASSES"]` in
`config/settings/base.py`) is `IsAuthenticated`. The clock endpoint
deliberately overrides this with `AllowAny`: the world's date is not
private, and there is no login flow in the SPA yet — an authenticated
endpoint would render the feature invisible. Any future endpoint here should
default to the project's `IsAuthenticated` unless it has the same reason the
clock does not.

**The squad endpoint is a known, deliberate exception, and a bigger one.**
`SquadView` is `AllowAny` with the team id in the URL rather than derived
from the caller — squad selection is inherently per-manager, but there is no
login flow to derive "which manager" from. This means anyone can currently
edit anyone's squad. It is not a stopgap awaiting an imminent fix: `specs/
roadmap.md` places accounts (#50) two phases after squad selection, and is
explicit that a single-manager world is what the phases before it are
deliberately testing. **Both this hole and the endpoint's CSRF story close
in [#50](https://github.com/mario595/cycling-manager/issues/50):**
`<team_id>` becomes `request.user.team`, the permission class drops back to
the project default, and the frontend's `?team=` query parameter goes away.

**CSRF, in the meantime:** DRF's `SessionAuthentication` enforces CSRF only
for *authenticated* sessions, so the squad endpoint's anonymous `PUT` passes
`CsrfViewMiddleware` untouched — no token, no `@csrf_exempt`, nothing to do
here until #50 makes the session authenticated.
