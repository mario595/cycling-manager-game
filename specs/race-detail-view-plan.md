# Race detail view — Implementation Plan

**Spec:** `specs/race-detail-view.md` · **Issue:** #47 · **Status:** proposed
**Apps touched:** `api/`, `frontend/`

## Context you need

`/race/:raceId` already exists (`frontend/src/screens/Race.tsx`) and already
works for one case: an upcoming race that the viewing manager's team is
entered in. It shows name, date, distance, status and the squad picker.

Everything it renders comes from **one endpoint**, `GET
/api/racing/races/<id>/squad/` (`api/views.py`'s `SquadView`), via
`frontend/src/useSquad.ts`. That endpoint is about *the caller's own team's
squad*: it returns `403` when the caller manages no team, and its payload
carries no course data. That single fact is what shapes this whole plan —
the screen currently cannot render at all for a race the manager is not in,
and cannot draw a profile because the course never reaches the browser.

What already exists and must not be rebuilt:

- **`Race.course`** (`racing/models.py`) — a JSON list of `{length, gradient}`
  segments, the engine's own config shape. Stored on every race, exposed by
  no endpoint. `api/views.py`'s `_distance_km` already sums it.
- **`GET /api/racing/races/<id>/results/`** (`RaceResultsView`) — a finished
  race's `results` (rider, team, position, `finish_time`, `finished`) and
  `points` (team, position, points). 404s for any race not `FINISHED`. The
  frontend client is `getRaceResults` in `frontend/src/api.ts`, typed as
  `RaceResults`.
- **`RaceSquad`** (`racing/models.py`) — one row per team per race, unique on
  `(race, team)`. `racing.services.ensure_squads` is called from inside
  `simulate_race`, so **every team that started a finished race has a
  `RaceSquad` row**. This is the authoritative "who started" record, and it
  is what resolves the spec's open question.
- **`LabelBar`** (`frontend/src/components/primitives.tsx`) — a label, a bar
  and the numeric value. `Race.tsx` already uses it for all five attributes.
- **Links into the screen** — `Calendar.tsx:229` and `Dashboard.tsx:86`
  already link every race row to `/race/${race.id}`.

**Two spec items are already done** and need no work; do not re-implement
them, and do not be confused when you find them:

- **Spec item 4** (numeric attribute values in the squad picker) landed with
  the rider-freshness work, which replaced the bare bars with `LabelBar`.
  Verify `Race.tsx`'s `RiderRow` renders `LabelBar` and move on.
- **Spec item 7's linking**, for the calendar and dashboard, is in place. What
  is *not* in place is those links working for a finished race — they point
  at a screen that currently 404s on the squad call and renders "Couldn't
  load this race."

Repo rules binding here: `api/` may know about every app and nothing may
import it; the 0-10 display scale (`riders/display.py`) is what leaves the
API for rider attributes, never the stored 1-100; tests are pytest, run with
`.venv/bin/python -m pytest` (369 at time of writing) and Vitest via
`npm --prefix frontend test`. See `api/README.md` and `frontend/README.md`.

## Goal

When this is done:

1. `/race/:raceId` renders for **any** race and **any** logged-in manager,
   including one with no team and one whose team did not start the race.
2. An upcoming race shows an elevation profile drawn from its course.
3. A finished race shows two tables: riders by position with time/gap, and
   team points with one row per team that started, zeros included.
4. A failed race, and a race in a transitional status, each show their own
   plain message rather than an error or a blank page.
5. `/results` and its sidebar entry no longer exist.

## Design decisions (settled — implement these, do not substitute)

**D1. A new race-detail endpoint, not an extension of the squad endpoint.**
Add `GET /api/racing/races/<race_id>/` (`RaceDetailView`), returning the
race's identity, status, date, distance and course. The obvious cheaper move
— adding `course` to `SquadView`'s payload — is **wrong**: `SquadView` 403s a
caller with no team, so the course would be unreachable for exactly the
viewers the spec says must see it. Keep `SquadView` as it is; it stays the
squad's endpoint.

**D2. The screen composes two or three independent fetches, and the squad
fetch is allowed to fail.** `Race.tsx` fetches the race detail always, the
results only when the race is finished, and the squad only when the manager
has a team and the race is not finished. A `403`/`404` from the squad call
must degrade to "no squad panel", **not** to the screen's error state. Today
`Race.tsx` treats any squad failure as a dead screen — that is the specific
behaviour being fixed.

**D3. Starters come from `RaceSquad`, not from `RaceResult` rows.** The
points table must list every team that started. Deriving that set from the
distinct teams in `results` is tempting and is what the reader will reach
for; it silently redefines "started" as "has a result row", which is a
different claim. `RaceSquad` records entry directly and
`ensure_squads` guarantees it is populated for a simulated race. Load-bearing.

**D4. The zero-filling happens in `api/`, not in `competitions/` and not in
the browser.** `competitions.services.score_race` deliberately writes only
scoring rows (`points_for(position) > 0`) and its output feeds season
standings; adding zero rows there would change what standings iterate over
for no benefit. `RaceResultsView` joins the two sets at presentation time,
which is what `api/` is for — it "translates, it does not persist"
(`api/README.md`). Do not touch `competitions/`.

**D5. The points table keeps its existing sort, with zero-scorers appended.**
Scoring teams first, ordered by `position` ascending (the existing
`order_by("position")`), then non-scoring teams by name. A team that scored
nothing has no meaningful `position`, so `position` is `null` for those rows
— not `0`, which would sort them to the front and read as "finished
zeroth".

**D6. The elevation profile is an inline SVG built in the frontend from the
raw segments.** No charting library — `frontend/` has no CSS framework and
no chart dependency, and adding one for a single read-only sparkline is out
of proportion. Cumulative altitude is the running sum of
`length * gradient` per segment, starting at zero; the polyline is scaled to
fit the viewBox. A flat course yields a flat line, which is correct and
informative, not a bug to special-case.

**D7. Time formatting lives in its own module with its own tests.** Put
`formatRaceTime` and `formatGap` in `frontend/src/raceTime.ts`, beside
`raceStatus.ts`. They are pure functions over a number of seconds, which is
where the edge cases are (a `+0:00` gap, an hour boundary, a null time), and
testing them through a rendered component would be the slow way to prove
something arithmetic.

**D8. `Results.tsx` is deleted, not repurposed.** Its `latestFinishedRace`
helper and `pointsByPosition` map both encode the presentation this ticket
exists to remove. Write the new tables fresh in `Race.tsx`.

## Data model

**No model changes. No migrations.** Every field this feature needs —
`Race.course`, `RaceResult.finish_time`, `RaceSquad.team` — already exists.

## `api/views.py`

### `RaceDetailView` (new)

```python
class RaceDetailView(APIView):
    """One race's own facts — identity, status, when, how far, and the
    course profile. Unlike SquadView this is not about the caller's team:
    any authenticated manager may read any race, including one their team
    did not start. See specs/race-detail-view-plan.md, D1.
    """

    def get(self, request, race_id: int):
        race = get_object_or_404(Race, pk=race_id)
        payload = {
            "id": race.pk,
            "name": race.name,
            "status": race.status,
            "starts_at": race.starts_at,
            "distance_km": _distance_km(race),
            "course": race.course,
        }
        return Response(RaceDetailSerializer(payload).data)
```

Reuses the module-level `_distance_km`. No status filter: a `scheduled`,
`running`, `finished` or `failed` race all return `200` — the status is in
the payload and the SPA decides what to draw. This is deliberately unlike
`RaceResultsView`, which 404s a non-finished race because "no results yet"
and "no such race" must stay distinguishable there.

### `RaceResultsView` (changed)

The `points` list gains a row per non-scoring starter. Replace the existing
`points` comprehension with:

```python
        scored = {p.team_id: p for p in points}
        starters = (
            Team.objects
            .filter(race_squads__race=race)
            .distinct()
            .order_by("name")
        )
        points_payload = [
            {
                "team": {"id": p.team.pk, "name": p.team.name, "code": p.team.code},
                "position": p.position,
                "points": p.points,
            }
            for p in points
        ] + [
            {
                "team": {"id": t.pk, "name": t.name, "code": t.code},
                "position": None,
                "points": 0,
            }
            for t in starters
            if t.pk not in scored
        ]
```

`points` is already `race.points.select_related("team").order_by("position")`,
so scoring teams keep their order and the zero rows follow, name-ordered
(D5). `RaceResultPointsEntrySerializer.position` must become
`allow_null=True`.

`Team` is already imported at `api/views.py:30`; no new import is needed.

## `api/serializers.py`

```python
class CourseSegmentSerializer(serializers.Serializer):
    length = serializers.FloatField()
    gradient = serializers.FloatField()


class RaceDetailSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    status = serializers.CharField()
    starts_at = serializers.DateTimeField(allow_null=True)
    distance_km = serializers.FloatField()
    course = CourseSegmentSerializer(many=True)
```

And one change: `RaceResultPointsEntrySerializer.position` →
`serializers.IntegerField(allow_null=True)`.

## `api/urls.py`

```python
    path("racing/races/<int:race_id>/", RaceDetailView.as_view(), name="race-detail"),
```

Register it **above** the `squad/` and `results/` paths or below — Django
matches on the full path, so order is not load-bearing here, but keep it
grouped with the other `racing/races/` routes for readability.

## `frontend/src/api.ts`

```ts
export interface CourseSegment {
  length: number
  gradient: number
}

export interface RaceDetail {
  id: number
  name: string
  status: string
  starts_at: string | null
  distance_km: number
  course: CourseSegment[]
}

export async function getRaceDetail(raceId: number): Promise<RaceDetail>
```

`RaceResultPointsEntry.position` becomes `number | null`.

## `frontend/src/useRaceDetail.ts` (new)

Follows `useSquad.ts`'s shape — fetch on mount and on `raceId` change, no
polling, `{ race, loading, error }`. No save path; this is read-only.

## `frontend/src/useRaceResults.ts` (new)

Same shape, `{ results, loading, error }`, but **takes an `enabled` flag** so
the screen can hold off until it knows the race is finished:

```ts
export function useRaceResults(raceId: number, enabled: boolean): RaceResultsState
```

When `enabled` is false the hook stays in a settled, non-loading, empty
state — it must not fire the request and must not report an error. This is
what keeps the screen from calling an endpoint that 404s by design for an
upcoming race.

## `frontend/src/raceTime.ts` (new)

```ts
/** Total elapsed time: `3h 23m 14s`, dropping the hour under an hour. */
export function formatRaceTime(seconds: number): string

/** Gap behind the winner: `+0:42`, `+1:02:03` past an hour. Zero is `+0:00`. */
export function formatGap(seconds: number): string
```

Both take whole or fractional seconds and floor to the second. `formatGap`
is called with the difference from the winner's `finish_time`, computed by
the caller.

## `frontend/src/components/CourseProfile.tsx` (new)

```tsx
export function CourseProfile({ course }: { course: CourseSegment[] }): JSX.Element
```

Builds cumulative `(distance, altitude)` points — altitude accumulating
`length * gradient` — normalises both axes into the viewBox, and renders a
filled polygon plus a stroked polyline. Uses `color` from `../theme`, never
hex literals (`frontend/README.md`, *Conventions*). Returns a flat line for
a zero-gradient course without special-casing.

## `frontend/src/screens/Race.tsx`

Restructured. The component becomes:

1. `useRaceDetail(raceId)` — always.
2. `useRaceResults(raceId, race?.status === 'finished')`.
3. `useSquad(raceId)` — its error is now non-fatal (D2).

Then branch on `race.status`:

- `finished` → `<RiderResultsTable>` and `<TeamPointsTable>`.
- `failed` → a card saying the race did not run.
- `running` → a card saying the race is being simulated.
- anything else (`scheduled`) → `<CourseProfile>`, the stat tiles, and the
  squad panel **only if** `squad` loaded.

The existing `SquadPanel` and `RiderRow` stay as they are. The stat tiles and
`PageHeading` move to read from `race` rather than `squad`.

`RiderResultsTable` computes the winner's time once (the first entry with
`finished === true`) and renders each row's gap against it. A rider with
`finished === false` renders a dash in the position column and "DNF" in the
time column.

## Work items

### W1 — `api/`: add the race-detail endpoint

✅ Done — `RaceDetailSerializer` and `CourseSegmentSerializer` added, `RaceDetailView` and its `/api/racing/races/<int:race_id>/` route registered, three tests green.

New `RaceDetailSerializer` and `CourseSegmentSerializer`
(`api/serializers.py`), new `RaceDetailView` (`api/views.py`), new route
(`api/urls.py`). No changes to existing endpoints.

**Test** (`api/tests.py`): `test_race_detail_returns_course_and_distance` —
a scheduled race with two segments returns `200`, the right `distance_km`,
and `course` as a two-element list. `test_race_detail_available_without_a_team`
— a user managing no team gets `200` (the contrast with `SquadView`'s 403 is
the point of the endpoint). `test_race_detail_requires_login` — anonymous
gets `403`.

### W2 — `api/`: zero-fill the points table

✅ Done — `RaceResultsView` appends non-scoring starters from `RaceSquad`; `RaceResultPointsEntrySerializer.position` is `allow_null=True`; `test_points_include_teams_that_scored_nothing` green.

`RaceResultsView`'s `points` payload gains non-scoring starters;
`RaceResultPointsEntrySerializer.position` becomes nullable.

**Load-bearing:** the starter set comes from `RaceSquad` (D3).

**Test** (`api/tests.py`): `test_points_include_teams_that_scored_nothing` —
extend the `finished_race_with_points` fixture pattern with a second team
that has a `RaceSquad` for the race and either no result or a non-scoring
one; assert its row is present with `points == 0` and `position is None`.
Existing `test_race_results_returns_order_and_points` must still pass
unchanged — the scoring team stays first.

### W3 — `frontend/`: the API client and the two hooks

`getRaceDetail` and the `RaceDetail`/`CourseSegment` types in `api.ts`;
`RaceResultPointsEntry.position` widened to `number | null`; new
`useRaceDetail.ts` and `useRaceResults.ts`.

**Test** (`frontend/src/useRaceResults.test.ts`, new):
`does not fetch when disabled` — assert the fetch stub is never called and
the hook reports neither loading nor error.

### W4 — `frontend/src/raceTime.ts`: time and gap formatting

**Test** (`frontend/src/raceTime.test.ts`, new): a winner's time under an
hour and over an hour; a gap of exactly zero renders `+0:00` (**not** an
empty string — spec, *Rules and edge cases*); a gap crossing a minute and an
hour boundary.

### W5 — `frontend/src/components/CourseProfile.tsx`: the elevation profile

**Test** (`frontend/src/components/CourseProfile.test.tsx`, new): a course
with a climbing segment renders a `polyline` whose points are not all at the
same y; a flat course renders without throwing.

### W6 — `frontend/src/screens/Race.tsx`: the four states

The restructure described above: detail-driven header and tiles, the profile
on an upcoming race, the two tables on a finished one, plain cards for
`failed` and `running`, and a squad panel that is absent rather than fatal
when the squad call fails.

**Load-bearing:** a squad `403` must not blank the screen (D2).

**Test** (`frontend/src/screens/Race.test.tsx`, new, mocking the three hooks
the way `Dashboard.test.tsx` mocks its own):
- `renders the course profile for an upcoming race`
- `renders both tables for a finished race` — assert a rider name and a team
  with zero points both appear
- `renders without a squad panel when the manager has no team` — squad hook
  in its error state, screen still shows the race name
- `renders a plain message for a failed race`

### W7 — `frontend/`: delete `/results`

Remove `frontend/src/screens/Results.tsx`, its entry in `App.tsx`'s
`SCREENS`, and the `{ path: '/results', name: 'Results' }` item from
`navigation.ts`'s `RACING` section. `getRaceResults` stays — `useRaceResults`
is now its only caller.

Two existing tests name the deleted page and will fail until they are
updated — this is expected, not a regression:

- `frontend/src/navigation.test.ts:7` — `BUILT_SCREENS` contains `/results`.
  Remove it from that set.
- `frontend/src/App.test.tsx:20` — mocks `./screens/Results`. Remove the
  mock.

`App.test.tsx` already covers unknown-path redirection, so `/results`
falling through to `/` is asserted behaviour once the route is gone. Do not
add a new test for it.

## Execution order

W1 → W2 → W3 → W4 → W5 → W6 → W7.

The two backend items come first and are independently verifiable with
`pytest` alone, so the data the screen needs is proven to exist before any
component is restructured. W3–W5 build the three pieces W6 composes — each
is a small, separately-testable unit, and doing them before the screen keeps
W6 a wiring change rather than a wiring-plus-arithmetic change. W7 is last
because deleting the old page before the new one renders a finished race
would leave the app with no way to see a result at all.

Commit after each work item. The repo is green at every one.

## Documentation update (required, not optional)

**`api/README.md`** — add `GET /api/racing/races/<race_id>/` to *What
exists*, stating that it is readable by any authenticated manager regardless
of team (the contrast with `SquadView`), and that it carries the raw course
segments. Amend the existing `results/` bullet to say `points` now carries
one row per starting team, with `position: null` and `points: 0` for teams
that did not score, and that starters come from `RaceSquad`.

**`frontend/README.md`** — update the route table: `/race/:raceId` is no
longer "squad selection" but the full race screen; delete the `/results`
row. In *Relationship to `design/`*, the **Race day** screen is now built
apart from the deliberate exclusions — update that paragraph to list what
remains dropped (per-rider suitability #45, wind/temperature/tier, other
teams' entrants) and remove the course-profile and result-table items, which
now exist. Note that the `race_player/` question is answered for now:
deliberately not folded in (spec, *Out of scope*).

**`racing/README.md`** — one line under *Squads*: `RaceSquad` is the record
of which teams started a race, and the results API reads it to list
non-scoring teams.

Per `AGENTS.md`, delete `specs/race-detail-view.md` and
`specs/race-detail-view-plan.md` before opening the pull request.

## Verification

```bash
.venv/bin/python -m pytest
npm --prefix frontend test
npm --prefix frontend run build
```

Then seed a world and look at it — this is a display feature, so the tests
prove the data and only the browser proves the screen:

```bash
.venv/bin/python scripts/dev_db.py
.venv/bin/python manage.py migrate
.venv/bin/python manage.py seed_user
.venv/bin/python manage.py seed_teams --claim-for test@mail.com
.venv/bin/python manage.py seed_trainers
.venv/bin/python manage.py load_season seasons/season-1.example.json
GAME_CLOCK_CLASS=world.clocks.MockClock .venv/bin/python manage.py mock_clock set <season start>
GAME_CLOCK_CLASS=world.clocks.MockClock .venv/bin/python manage.py tick
```

Ticking past a race week gives a finished race to open. Check, in order:

1. An **upcoming** race shows a profile whose shape differs between a flat
   and a hilly race in the season file. A profile that looks identical for
   both means the gradient accumulation is wrong — the likeliest bug in W5,
   and one that unit tests pass straight through if they only assert that a
   `polyline` exists.
2. A **finished** race shows a winner with a full time and the rest with
   `+` gaps, and a points table containing a team with `0`.
3. **Log out of the demo account's team and open a finished race** — or
   simpler, open a race in a week where the demo team's squad call fails.
   The page must still render. This is the failure named in *Risks*.
4. `/results` redirects to `/` and the sidebar has no Results item.

## Risks

| Risk | Mitigation |
|---|---|
| The squad fetch's failure is left fatal, so the screen still dies for a team-less manager or a finished race — the exact bug this ticket fixes, and easy to miss because the demo account always has a team | W6's `renders without a squad panel when the manager has no team` test, plus verification step 3 |
| Starters derived from `RaceResult` rows rather than `RaceSquad`, quietly changing what "started" means (D3) | W2's test uses a team with a squad and no scoring result — a results-derived implementation fails it |
| `position: null` breaks the existing points serializer or the League screen | `allow_null=True` in W2; `test_race_results_returns_order_and_points` must pass unchanged, and standings read `RacePoints` directly, not this payload |
| The elevation profile renders but is wrong (flat for every course), since a `polyline` existing is not proof it has shape | W5 asserts varying y-values; verification step 1 compares two courses by eye |
| `useRaceResults` fires for an upcoming race and its by-design 404 surfaces as an error state | The `enabled` flag, and W3's `does not fetch when disabled` test |

## Open questions

None. The spec's one open item — how to list teams that started but did not
score — is resolved by D3/D4: `RaceSquad` is the record, and `api/` joins it
to the scoring rows at presentation time.
