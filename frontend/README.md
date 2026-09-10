# Frontend

The React SPA lives here. It is not built yet.

## How it is served

Django serves the SPA rather than a separate host: `config/urls.py` has a
catch-all that renders `index.html` for any path outside `/admin/` and `/api/`,
so client-side routing and browser refreshes both work. WhiteNoise serves the
JS/CSS bundle.

Template resolution order (`TEMPLATES["DIRS"]` in `config/settings/base.py`):

1. `frontend/dist/` — the real Vite build, when it exists.
2. `frontend/templates/` — the committed placeholder, so a fresh clone runs
   before anyone has built the frontend.

`frontend/dist/` is gitignored build output; `frontend/templates/` is source.

## When building it

Vite, React, TypeScript — matching `race_player/`, which is already set up that
way and is the natural reference. Point Vite's `build.outDir` at `dist/` and
Django picks it up with no further configuration.
