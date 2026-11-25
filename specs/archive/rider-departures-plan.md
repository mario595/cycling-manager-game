# Rider departures, and the graduate's deadline — Implementation Plan

**Spec:** `specs/archive/rider-departures.md` · **Issues:** #158, #162 · **Status:** implemented
**Apps touched:** `riders/`, `transfers/`, `api/`, `frontend/`

## Context

Three things take a rider away from a team without a click in that moment:

- `riders.services.retire_due_riders(at=)`. `world.services.tick()` calls it at each season close, before `advance_ages()`, dated to the closing season's final week. It is one conditional UPDATE that clears `team`, so the team is lost unless it is read first.
- `riders.youth_triage.release_graduates(ids, at=)`. It has three callers: the tick's window step (`world.services._release_expired_graduates`), an unsold auction (`transfers.services._resolve_unsold`), and `riders.development_squad.close_squad`. The last is a manager action.
- `transfers.services.resolve_auction`, on its SOLD path. For a forced sale (#27), the rider left the roster when they were listed, so the seller is `auction.seller_team`, not `rider.team`.

The graduate's countdown already exists: `api.views._weeks_left` feeds `weeks_left` on `DevelopmentSquadGraduateSerializer`, and the squad screen shows "Decide within N weeks".

## Design decisions

1. **`riders.Departure` is the record.** It lives in `riders/`, because both writers (`riders/` itself and `transfers/`) can import it there without breaking the dependency direction (`transfers -> riders`, `riders -> core, teams`). `world/` needs no change.
2. **The record is written where the rider leaves, not by the tick.** Each of the three call sites writes its own rows in the same transaction as the move. A departure therefore cannot be lost to a crash between the move and the record, and the record cannot exist for a move that rolled back.
3. **It stores a snapshot of the rider (name, speciality, age) and a nullable rider FK (`SET_NULL`).** Free-agent expiry deletes riders who never raced. A released graduate who never raced can be deleted that way, but the manager should still see their name.
4. **`at` is game time and the season and week are derived when read**, through `schedule.services.current_position`, exactly as `api.rider_profile.retired_payload` does. `riders/` cannot reference `schedule.Week`. A retirement's `at` is the final week's `starts_at`, so it resolves to "Season N, Week 12".
5. **`release_graduates` takes a keyword-only `record: bool`, with no default.** The window step and the unsold path pass `True`, and `close_squad` passes `False`. Having no default makes each caller state its choice, so a future caller cannot record, or fail to record, by accident.
6. **One read endpoint, `GET /api/riders/departures/`**, returns the caller's team's full history, newest first. The screens filter it in the client. The history is small (a few rows a season), so neither paging nor a server-side window is needed.
7. **Each graduate gets `decision_due: {season, week} | null`.** It is the `GRADUATE_WINDOW_WEEKS`-th declared week whose `starts_at` is after `graduated_at`. That week's opening tick is the one that releases them, so the value counts exactly what `weeks_ago_cutoff` counts. It is null when that week is not declared yet. One query covers the whole squad.
8. **`Position` gains `weeks_in_season`** (`schedule.models.SEASON_WEEKS`), so the dashboard can tell "the last two weeks" apart without hard-coding 12.
9. **The dashboard composes the three cues from existing hooks** (`useRoster`, `useDevelopmentSquad`, `useSeason`) plus a new `useDepartures`. "The last two game weeks" is `now - at < 14 game days`, using `useClock`'s game time.

## Data model

`riders/models.py`, migration `riders/00xx_departure`:

```
Departure(TimeStampedModel)
  team        FK teams.Team, CASCADE, related_name="departures"
  rider       FK Rider, SET_NULL, null, related_name="departures"
  rider_name  CharField(100)
  speciality  CharField (same choices as Rider)
  age         PositiveSmallIntegerField
  kind        TextChoices: retired | released | sold
  at          DateTimeField (game time)
  buyer       FK teams.Team, SET_NULL, null, related_name="+"   (sold only)
  fee         PositiveIntegerField, null                         (sold only)
  Meta: ordering ("-at", "-id"); index (team, -at)
```

## Changes by file

- `riders/departures.py` (new): `record_departures(riders, *, team_by_rider, kind, at)` builds the snapshot rows with one `bulk_create`. `record_sale(rider, *, seller, buyer, fee, at)` writes one row.
- `riders/services.py` `retire_due_riders`: inside one transaction, read `(pk, team_id)` for the due riders that have a team, run the UPDATE, then record those as `retired`. Squad riders (a backstop only) are not recorded.
- `riders/youth_triage.py` `release_graduates(..., record)`: `select_related("development_squad")` on the locked rows. When `record` is set, record each released rider as `released` against `development_squad.team_id`, before the unlink.
- `riders/development_squad.py` `close_squad`: pass `record=False`.
- `transfers/services.py`: `_resolve_unsold` passes `record=True`. The SOLD path calls `record_sale(rider, seller=auction.seller_team, buyer=winner, fee=amount, at=at)` after the rider moves.
- `world/services.py` `_release_expired_graduates`: pass `record=True`.
- `api/serializers.py`: `DepartureSerializer` (id, kind, at, season, week, rider {id or null, name, speciality, age}, buyer {id, name, code} or null, fee or null). `decision_due` on `DevelopmentSquadGraduateSerializer`, and `weeks_in_season` on `PositionSerializer`.
- `api/views.py`: `DeparturesView`, with an OpenAPI description in game terms. `graduate_deadlines` context in the development squad view. The development squad description mentions `decision_due` and the release.
- `api/urls.py`: `riders/departures/`, placed before `riders/<int:rider_id>/`.
- `frontend/src/api.ts`: `Departure`, `getDepartures`, `decision_due`, `weeks_in_season`.
- `frontend/src/useDepartures.ts` (new), with the same polling shape as `useRoster`.
- `frontend/src/departures.ts` (new, pure): `departureSentence(d)` and `isRecent(d, now)`.
- `frontend/src/components/DepartureList.tsx` (new): one row per departure, with the profile link, speciality and age.
- `frontend/src/screens/Dashboard.tsx`: `RecentDeparturesCard`, `GraduatesCue` and `RetirementCue`.
- `frontend/src/screens/Roster.tsx`: a "Departures" card for this season plus the last close's retirements.
- `frontend/src/screens/DevelopmentSquad.tsx`: the deadline sentence on each graduate, and a "Released this season" list.

## Work items

1. Model, migration, `riders/departures.py`, and the recording in `retire_due_riders`, `release_graduates` and `close_squad`. Tests: a retirement records its team, age and kind, and a teamless retiree records nothing. A window release records against the squad's team, and `record=False` records nothing. Closing a squad records nothing.
2. `transfers/`: recording on sale and on an unsold graduate. Tests: a sale records buyer and fee against the seller, a forced sale records against the seller team, an unsold graduate is recorded as released, and an unsold roster rider records nothing.
3. `world/`: the window step passes `record=True`. Test: a tick that closes a graduate's window leaves one `released` departure.
4. `api/`: the departures endpoint (scoped to the caller's team, newest first, season and week resolved, a deleted rider still named, 403 without a team), `decision_due` (in-season, across a season boundary, null when undeclared) and `weeks_in_season`.
5. `frontend/`: types, hook, list component, and the dashboard, roster and squad screens, with tests for the sentences and the three dashboard cues.
6. Docs: `riders/README.md` (a *Departures* section), `transfers/README.md`, `api/README.md`, `frontend/README.md`, `AGENTS.md`'s riders row, and `beta_agents/PLAYERS_GUIDE.md`. Then archive the spec and plan as implemented.

## Verification

The full backend suite, `npm test` and `npm run build` in `frontend/`. Seed a world, set the mock clock, and tick across a season close and a graduate window: the API should list the departures.

## Risks

- `release_graduates` now has a required keyword, so any caller missed raises `TypeError` in tests rather than failing silently. That is the intent.
- A sale's record is written inside `resolve_auction`'s transaction. If `charge_buyer` raises, the record rolls back along with the move.
