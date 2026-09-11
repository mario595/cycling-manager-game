# API

## What lives here

DRF routers and serializers that aggregate other apps' data for the SPA.
`api/` owns no models of its own — it translates, it does not persist.

## What exists

One endpoint: `GET /api/world/clock/`, returning the world's current game
time (`GameClockSerializer` in `api/serializers.py`, `ClockView` in
`api/views.py`). See `world/README.md` for what the clock is.

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
