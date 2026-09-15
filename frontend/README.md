# Frontend

The React SPA. Currently a **scaffold**: it reproduces the mockup in
`design/` and proves navigation works. No screen talks to the database.

## What exists

| Route | Screen | State |
|-------|--------|-------|
| `/` | Dashboard | Built — full layout from the design, fixture data |
| `/roster` | Roster | Built — filter, sort and rider detail panel, from the API, no fixture data |
| `/calendar` | Calendar | Built — twelve weeks from the API, no fixture data |
| `/race/:raceId` | Race | Built — squad selection, no fixture data |
| `/login`, `/register` | Login, Register | Built — real accounts, no fixture data |
| everything else, including the `/race` sidebar item itself | `Placeholder` | Renders the route name and path |

`/race/:raceId` is the first **parameterised** route, so it is registered as
an explicit `<Route>` in `App.tsx` rather than through `SCREENS` — that map
generates one route per nav item by path, which has nowhere to put a
`:raceId`. The sidebar's own `/race` item still lands on `Placeholder`;
`Race.tsx` is reached only by clicking a race on the calendar. `/login` and
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
one. A team-less `me` (anonymous, or logged in but not managing a team —
see `specs/player-accounts.md`) is not an error state: the race screen
shows a plain "you do not manage a team" message instead of an empty
picker, `Roster.tsx` does the same instead of an empty grid, and the
sidebar shows "No team / SPECTATING" instead of a team name.

**Writes need a CSRF token.** DRF's `SessionAuthentication` enforces CSRF
for authenticated sessions, so any `POST`/`PUT` issued while logged in must
carry `X-CSRFToken`, or it 403s — a case nothing hit before login existed,
because every write used to run anonymously. `api.ts`'s `writeJson` (used by
`register`, `login`, `logout`, and `putSquad`) handles this: `ensureCsrfToken`
reads the `csrftoken` cookie, fetching `/api/accounts/me/` first if it isn't
set yet (that endpoint's `@ensure_csrf_cookie` guarantees it will be after).
Anything that issues a write should go through `writeJson`, not a bare
`fetch`.

Every sidebar item routes somewhere real. Items without a screen land on
`Placeholder`, which prints the path it resolved — so a click that "does
nothing" is visibly distinguishable from a broken route. That is deliberate:
the alternative (falling back to the dashboard, as the mockup does) hides
whether routing worked at all.

Adding a screen is one line: write the component and register it in `SCREENS`
in `src/App.tsx`. Its placeholder disappears automatically.

## Where the data comes from

`src/placeholderData.ts` — **all of it invented**, copied from the mockup.
`Dashboard.tsx` is now the main consumer; keeping every fake value in one
module means the screens already have their real shapes, and wiring them up
later is a matter of replacing that module with fetches rather than hunting
literals through JSX.

`TEAM` is now **partly real**: `Layout.tsx`/`Sidebar.tsx` read team identity
(name, code) and the manager's name from `useAuth()`'s `me` when a session
exists, and only fall back to `TEAM`'s fake values for fields nothing
real supplies yet — budget (`economy/` doesn't exist) and tier
(`competitions/` doesn't exist). A future economy/competitions feature
replaces those two fields the same way this one replaced the rest.

The rider half of this file (`Rider`, `RIDER_SEEDS`, `SQUAD`, `SPEC_FILTERS`,
`SortKey`, `SORT_OPTIONS`, `WAGE_BILL`) is **gone**, not just unused —
`/roster` reads real riders via `src/useRoster.ts` and `GET /api/riders/`
(see `api/README.md`), and the fixture shape it used to have (an invented
"overall rating", form, condition, wage) does not exist in the real data
at all; see `specs/rider-attributes.md`, which cuts an overall rating
outright.

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
