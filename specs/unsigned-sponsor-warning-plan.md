# Warn a manager who has not signed a sponsor — Implementation Plan

**Status:** approved
**Spec:** `specs/unsigned-sponsor-warning.md` (#161)

## Context you need

- `economy/README.md`, *Sponsorship*: one contract per `(team, season)`,
  `active_contract()` and `offers_for()` in `economy/services.py`,
  `ensure_offer_round()` is idempotent and safe on every read.
- `api/views.py`'s `MeView` is the boot call of the SPA and the first call
  of every LLM tester visit. `SponsorsView` already generates a round lazily.
- `schedule.services.current_position(now())` returns a `Position` whose
  `state` is `in_season`, `off_season` or `no_season`.
- `frontend/src/useAuth.tsx` fetches `me` once and shares it, and
  `frontend/src/components/SolvencyBanner.tsx` is the existing dashboard banner.

## Goal

`GET /api/accounts/me/` tells a manager whose team has no sponsor this
season, with the smallest waiting offer's weekly amount. The dashboard shows
a banner and the sidebar's Sponsors entry shows a dot while it is so. The
players' guide says so.

## Design decisions (settled — implement these, do not substitute)

- **D1. The fact lives on `me.team`**, as `sponsor_missing` (bool) and
  `smallest_offer_weekly` (int or null, the smallest `weekly_base` among
  the waiting offers). It sits on `team` because it is a fact about the team.
  A user with no team has `team: null` and so no field to misread.
- **D2. Only `in_season` warns.** Off season and no season give
  `sponsor_missing: false`. In the off season the finished season's contract
  is history and the next round comes at season open.
- **D3. `MeView` calls `ensure_offer_round`** before reading, as
  `SponsorsView` does. A claimed team mid-season then gets its amount on the
  very first read, without opening Sponsors first. The call is a two-query
  no-op once a round or contract exists.
- **D4. One helper in `economy/services.py`**, `sponsor_gap(team, season)`,
  returning `None` when the team has an active contract, otherwise the
  smallest waiting offer's `weekly_base` or `0` if there are none. `MeView`
  maps `0` to `smallest_offer_weekly: null`. `economy/` stays free of
  `schedule/`'s position logic: the caller passes the season.
- **D5. The SPA refreshes `me`.** `AuthProvider` gains `refresh()` and polls
  `getMe` every 60 seconds, the same cadence as `useSponsors` and
  `useSolvency`. It only calls `setMe` when the JSON has changed, so the poll
  does not re-render the app. The Sponsors screen calls `refresh()` after
  signing, so the banner and dot go at once (spec item 4).
- **D6. No dismiss, no ledger change, no tick change.**

## Data model

None.

## `economy/services.py`

`sponsor_gap(team, season) -> int | None`, next to `active_contract`.

## `api/serializers.py`, `api/views.py`

`MeTeamSerializer` gains `sponsor_missing = BooleanField()` and
`smallest_offer_weekly = IntegerField(allow_null=True)`, both described in
the schema. `MeView.get` builds them through a small `_sponsor_fields(team)`.
The `get_me` operation description mentions the new fields.

## Frontend

- `api.ts`: `MeTeam` gains the two fields.
- `useAuth.tsx`: `refresh()`, the 60 s poll with change check.
- `components/SponsorBanner.tsx`: renders nothing unless
  `me.team.sponsor_missing`, otherwise a warning card with a link to
  `/sponsors`. On the dashboard, under `SolvencyBanner`.
- `Sidebar.tsx`: a dot after the Sponsors label while `sponsor_missing`.
- `screens/Sponsors.tsx`: call `refresh()` after a successful sign.

## Work items

### W1 — `economy`: `sponsor_gap` and its tests
### W2 — `api`: the fields on `me`, with API tests (signed, unsigned with offers, unsigned claimed mid-season, off season, no team)
### W3 — `frontend`: banner, dot, refresh, with component tests
### W4 — Docs: `economy/README.md`, `api/README.md`, `frontend/README.md`, `beta_agents/PLAYERS_GUIDE.md`; archive spec and plan

## Execution order

W1 → W2 → W3 → W4.

## Documentation update (required, not optional)

- `economy/README.md`, *Sponsorship*: `sponsor_gap` and who reads it.
- `api/README.md`: the two new `me.team` fields.
- `frontend/README.md`: the banner, the dot, and `me` now polling.
- `beta_agents/PLAYERS_GUIDE.md`: sign a sponsor each season; unsigned weeks pay nothing; `team.sponsor_missing` on `me`.

## Verification

`pytest economy api`, the frontend `npm test` and `npm run build`, then the
full backend suite.

## Risks

- `MeView` is `AllowAny` and now writes offers for a team that lacks them.
  Only for an authenticated manager in season, and the write is the same
  idempotent round `SponsorsView` already makes on read.

## Open questions

None.
