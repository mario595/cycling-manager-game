# Frontend

The React SPA, served by Django from `frontend/dist/`: seven built screens,
all reading the real API. No screen renders invented data.

## What exists

| Route | Screen | State |
|-------|--------|-------|
| `/` | Dashboard | Built — season, standings, next race and squad status from the API, no fixture data |
| `/roster` | Roster | Built — filter, sort and rider detail panel, from the API, no fixture data |
| `/staff` | Staff | Built — hire/fire a trainer, from the API, no fixture data |
| `/calendar` | Calendar | Built — twelve weeks from the API, no fixture data |
| `/race/:raceId` | Race | Built — squad selection, no fixture data |
| `/league` | League | Built — season standings table from the API, no fixture data |
| `/results` | Results | Built — the most recently finished race's order and points, from the API, no fixture data |
| `/login`, `/register` | Login, Register | Built — real accounts, no fixture data |
| `/claim` | ClaimTeam | Built — real claim, no fixture data |
| anything else | — | Redirects to `/` |

`/race/:raceId` is the first **parameterised** route, so it is registered as
an explicit `<Route>` in `App.tsx` rather than through `SCREENS` — that map
generates one route per nav item by path, which has nowhere to put a
`:raceId`. It is reached by clicking a race on the calendar or the next-race
card on the dashboard. `/login` and
`/register` are explicit routes for the same reason: neither is a nav item,
so neither belongs in the sidebar.

## Identity

`useAuth.tsx`'s `AuthProvider` learns who is logged in **once**, on mount,
via `GET /api/accounts/me/`, and shares it through `useAuth()` — the
sidebar, the race screen, the roster screen, and the login/register screens
all read the same `me` rather than each fetching it themselves. This is
also what makes a session survive a page reload: the browser still holds
the session cookie, so `getMe()` on the next mount re-learns the same
identity without the player logging in again.

`me.team` is what used to be the `?team=<id>` URL parameter described in an
earlier version of this file. That parameter is gone — squad selection and
the roster both derive the team from the session on the server
(`api/README.md`), so neither `Race.tsx` nor `Roster.tsx` needs to pass
one.

**An unknown visitor and a team-less manager are both bounced out of the
app chrome by `Layout.tsx`.** Two guards compose there, in a fixed order,
and `loading` gates both:

```tsx
if (loading) return null          // identity not yet established — redirect nothing
if (!me?.authenticated && !ANON_ALLOWED_PATHS.has(pathname)) {
  return <Navigate to="/login" replace state={{ from: pathname }} />
}
if (me?.authenticated && !me.team && !TEAM_LESS_ALLOWED_PATHS.has(pathname)) {
  return <Navigate to="/claim" replace />
}
```

Order is load-bearing. `useAuth` starts with `me === null, loading === true`,
so on the very first render of a hard page refresh `!me?.authenticated` is
true for *everyone*, including a logged-in manager. Without the `loading`
check first, a refresh would bounce a logged-in manager to `/login` before
`getMe()` returns. A failed `getMe()` leaves `me === null` after loading
settles, which correctly falls through to the login redirect.

`ANON_ALLOWED_PATHS` (`/login`, `/register`) is the escape hatch for
visitors, and `TEAM_LESS_ALLOWED_PATHS` (`/login`, `/register`, `/claim`)
for managers with no team — `/claim` must stay reachable or its own
redirect bounces back to itself. See `teams/README.md`, *Claiming a team*.
The guard passes the attempted path to the login screen in router location
state (`state: { from: pathname }`), and `Login.tsx` reads it, so login
returns the manager where they were headed; someone who visits `/login`
directly has no `from` and lands on `/`.

**Writes need a CSRF token.** DRF's `SessionAuthentication` enforces CSRF
for authenticated sessions, so any `POST`/`PUT` issued while logged in must
carry `X-CSRFToken`, or it 403s — a case nothing hit before login existed,
because every write used to run anonymously. `api.ts`'s `writeJson` (used by
`register`, `login`, `logout`, and `putSquad`) handles this: `ensureCsrfToken`
reads the `csrftoken` cookie, fetching `/api/accounts/me/` first if it isn't
set yet (that endpoint's `@ensure_csrf_cookie` guarantees it will be after).
Anything that issues a write should go through `writeJson`, not a bare
`fetch`.

Every sidebar item routes somewhere real, and an unknown path redirects to
`/` — there is no `Placeholder` screen left to catch one. The redirect is
deliberate: the alternative (trying to render a non-existent screen) is a
blank page that hides whether routing worked at all.

Adding a screen is one line: write the component and register it in `SCREENS`
in `src/App.tsx`.

## Where the data comes from

`src/placeholderData.ts` is **gone** — it was the mockup's invented values,
and this ticket deleted it along with the last screen that consumed it. No
screen renders an invented value. `Dashboard.tsx` composes the same live
hooks everyone else uses: `useSeason` for the week label, `useStandings` for
the manager's own rank and points, `useCalendar` (via `src/nextRace.ts`) for
the next race, and `useNextRaceSquad` for whether that race's squad is set.

`/calendar` and `/roster` render nothing while loading or on error, rather
than inventing a shape — `src/useCalendar.ts` and `src/useRoster.ts` both
follow the discipline `useSeason.ts` established: a screen showing invented
data mid-fetch is indistinguishable from a real one with a bug in it.

## How it is served

Django serves the SPA rather than a separate host. `config/urls.py` has a
catch-all that renders `index.html` for any path outside `/admin/` and `/api/`,
so client-side routing and browser refreshes both work.

Template resolution order (`TEMPLATES["DIRS"]` in `config/settings/base.py`):

1. `frontend/dist/` — the real Vite build, when it exists.
2. `frontend/templates/` — the committed placeholder, so a fresh clone runs
   before anyone has built the frontend.

`frontend/dist/` is gitignored build output; `frontend/templates/` is source.

### The `/static/` prefix

Django picks `dist/` up **twice**: as a template directory (for `index.html`)
and via `STATICFILES_DIRS` (so WhiteNoise serves `dist/assets/*` under
`/static/`). `vite.config.ts` therefore sets `base: '/static/'` for builds, so
the asset URLs Vite writes into `index.html` match where WhiteNoise actually
serves them. Under `vite dev` there is no Django and no prefix, so `base`
stays `/`. Changing one without the other gives a blank page and 404s on the
JS bundle.

## Running it

Dev server with hot reload, on **5174** (`race_player` owns 5173):

```bash
npm --prefix frontend run dev
```

`/api` and `/admin` proxy to Django on :8000, so this works against the real
backend once endpoints exist.

To check it the way it actually ships — built, served by Django:

```bash
npm --prefix frontend run build && .venv/bin/python manage.py runserver
```

## Conventions

- **Styling is inline `style={{}}`**, matching the design export. No CSS
  framework. `src/index.css` holds only the global reset and the handful of
  hover rules, which inline styles cannot express.
- **Colours come from `src/theme.ts`**, never as literals in components. The
  design repeats its hex codes inline; they are named once there instead.
- **`src/navigation.ts` is the single source of truth** for the sidebar and
  the router both. A nav item cannot exist without a route.

## Testing

Vitest + React Testing Library + jsdom, configured in `vite.config.ts`'s
`test` block (jsdom environment, `@testing-library/jest-dom` matchers via
`src/setupTests.ts`). Tests live beside the code as `*.test.ts`/`*.test.tsx`
in the flat `src/` layout. Run them with:

```bash
npm --prefix frontend test
```

The four hooks outside the components are pure or near-pure, which is
deliberate: `src/nextRace.ts` is tested as a function with no rendering,
`src/setupTests.ts` stubs `window.matchMedia`, and screens mock their data
hooks rather than the `api.ts` fetch layer.

## Relationship to `design/`

`design/Cycling Manager UI.dc.html` is the Claude Design export this was built
from — the reference for spacing, colour and copy. It is a mockup in a custom
template DSL, not runnable source, and it is not a build input. When it is
re-exported, reconcile `src/theme.ts` against it first.

The mockup's **Race day** screen is now **partly** built, as `Race.tsx` —
folding it together with `race_player/` (the separate tick-by-tick
visualizer) is still its own undecided question (#47). What is built is only
the squad-selection widget the mockup shows, and only what `specs/squad-
selection.md` (now folded into `racing/README.md`) actually specifies.
Deliberately dropped, because the spec doesn't cover it: the mockup's
eight-rider squads (the spec fixes four), per-rider suitability scores
(course-aware assessment is #45), `INJURED`/`FATIGUED` states (#41), the
course profile SVG, terrain/temperature/wind/tier/points facts, and the
final classification table for a past race. `Race.tsx` shows only name,
date, distance and status, and reuses the mockup's checkbox-row and
★-to-set-leader interaction for the part that is in scope.

The mockup's **Calendar** screen additionally shows things this feature does
not have — multiple season cards with a switcher, win/podium/points stats, a
"Next up" highlight state, race terrain/class metadata, and result positions
that link through to a race-detail screen (#47, not built). `Calendar.tsx`
matches the mockup's per-season card and week-row structure, but shows one
season only (there is no multi-season history yet) and drops anything that
needs standings or a detail screen that does not exist.

`Staff.tsx` has **no mockup to build from at all** — `design/` was exported
before staff existed as a domain. It follows `Roster.tsx`'s existing
card-and-bar composition (the same `Card`, `Bar`, `barColor` primitives, the
same rider-card layout) rather than inventing a new visual language, so the
screen looks consistent with the rest of the app even without a reference
export.
