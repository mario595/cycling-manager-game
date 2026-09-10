# Frontend

The React SPA. Currently a **scaffold**: it reproduces the mockup in
`design/` and proves navigation works. No screen talks to the database.

## What exists

| Route | Screen | State |
|-------|--------|-------|
| `/` | Dashboard | Built — full layout from the design, fixture data |
| `/roster` | Roster | Built — filter, sort and rider detail panel all work |
| everything else | `Placeholder` | Renders the route name and path |

Every sidebar item routes somewhere real. Items without a screen land on
`Placeholder`, which prints the path it resolved — so a click that "does
nothing" is visibly distinguishable from a broken route. That is deliberate:
the alternative (falling back to the dashboard, as the mockup does) hides
whether routing worked at all.

Adding a screen is one line: write the component and register it in `SCREENS`
in `src/App.tsx`. Its placeholder disappears automatically.

## Where the data comes from

`src/placeholderData.ts` — **all of it invented**, copied from the mockup.
There is no API yet. Keeping every fake value in one module means the screens
already have their real shapes, and wiring them up later is a matter of
replacing that module with fetches rather than hunting literals through JSX.

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

The mockup also contains a third screen, **Race day**, which is not built here:
`race_player/` already exists as a separate visualizer, and folding the two
together is its own decision.
