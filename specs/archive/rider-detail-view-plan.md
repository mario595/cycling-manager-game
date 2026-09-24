# Rider detail view — Implementation Plan

**Spec:** `specs/rider-detail-view.md` · **Issue:** #96 · **Status:** implemented
**Apps touched:** `api/`, `frontend/` (no model changes, no migrations)

## Context you need

The game already stores everything this page shows; nothing serializes most
of it yet.

- **Riders** (`riders/models.py`, `Rider`): the five engine attributes are
  stored 1-100 and shown 0-10 through `riders.display.to_display_scale`, which
  floors, and is the only place that mapping may happen (`riders/README.md`,
  *Display scale*). A rider also carries a set of **hidden** traits that must
  never reach a payload (`riders/README.md`, *Visible vs hidden*). The
  roster's `api.serializers.RiderSerializer` is the existing, audited list of
  what is safe to ship.
- **Attribute history** (#95, `riders.models.RiderAttributeSnapshot`): already
  stored as 0-10 display values. There is one baseline row per rider with
  `week=None`, written at creation or backfilled. After that, a row is written
  only for a week in which a displayed value moved. `riders/README.md`,
  *Attribute history*, names this ticket as the consumer.
- **Race results** (`racing.models.RaceResult`): one row per rider per
  finished race, with `position` and `finish_time`. **Every** starter is
  given a position, including riders who did not finish. Only
  `finish_time is None` marks a DNF (`racing.services.riders_who_raced`
  documents the same rule).
- **Which team a rider raced for** is recorded only by the squad:
  `RaceSquad(race, team)` → `RaceSquadRider(squad, rider)`. `simulate_race`
  builds the field exclusively from squad members, so every `RaceResult` has
  exactly one matching `RaceSquadRider`. `Rider.team` is the **current** team
  and changes when a rider is released or signed (#29). Releasing never
  deletes squad rows.
- **Race points and prize money are team awards, not individual ones** — one
  `competitions.models.RacePoints` row per team per race (its best classified
  finisher only), and prize money summed from a team's placed riders'
  `LedgerEntry` rows. The spec deliberately excludes both from this page for
  exactly that reason (*Out of scope*); this plan does not touch
  `competitions/` or the ledger at all.
- **API** (`api/README.md`): only `api/` and `world/` may import across every
  app (`AGENTS.md`, *Dependency direction*). Every endpoint is
  `IsAuthenticated` by default. `RaceDetailView` is the precedent for
  "readable by any authenticated manager, not scoped to the caller's team".
- **Frontend** (`frontend/README.md`): inline styles, colours from
  `src/theme.ts`, money through `src/format.ts`'s `formatMoney`. Screens mock
  their data hooks in tests. Parameterised routes are explicit `<Route>`s in
  `App.tsx`, like `/race/:raceId`. There is **no chart library** and
  `race_player`'s course chart is hand-written SVG. Continue that way.

## Goal

1. `GET /api/riders/<id>/` returns one rider's visible profile to any
   authenticated manager. That profile is identity, current team, freshness,
   salary, market value, attributes on the 0-10 scale, attribute history,
   race history (team raced for, position, time) and career totals (starts,
   wins, podiums, top tens, DNFs — no points, no prize money). It never
   includes a hidden trait. It returns 404 for a rider that does not exist.
2. `/riders/:riderId` in the SPA draws that profile: a radar, a five-line
   history chart, identity, freshness, a race-history list and a career
   strip. It has explicit empty states, and a "no longer in the game" state
   on a 404.
3. A rider's name links to the page from the Roster panel ("Full profile"),
   from race result rows and from free-agent cards.
4. Race-history rows and the race results endpoint name the team the rider
   **raced for**, not the team they are on now.

## Design decisions (settled — implement these, do not substitute)

**D1. One endpoint, one payload: `GET /api/riders/<int:rider_id>/`.** It is
not three endpoints (profile, history, results). The page draws nothing until
it has everything, and three requests would triple the loading and error
states for no gain. It sits next to the existing `GET /api/riders/`, which is
the caller's roster.

**D2. Readable by any authenticated user, whatever their team.** Follow
`RaceDetailView`'s pattern, not `RiderListView`'s. There is no `team_for()`
gate and no 403 for a team-less caller. The spec decided that every rider's
page is identical for every viewer. **Do not** add a "this is your rider"
branch to the payload or the screen.

**D3. The identity fields are exactly `RiderSerializer`'s, inherited.**
`RiderProfileSerializer(RiderSerializer)` adds keys and never redeclares an
inherited one. This is load-bearing. `RiderSerializer` is where the
"no hidden traits" and "display scale" rules are already enforced and
tested. Inheriting keeps the Roster and the rider page from drifting apart,
which the spec forbids: *"a rider must never look different on this page than
they look on the Roster"*. `release_cost` is inherited and serializes as
`null` because no team context is passed. That is the same documented
behaviour `FreeAgentSerializer` relies on. The page does not show it.

**D4. The team a rider raced for comes from `RaceSquadRider`, never from
`Rider.team`.** Take one query over
`RaceSquadRider.objects.filter(rider=rider).select_related("squad__team")`
and build a map from `race_id` to team. **Do not** use `result.rider.team`,
because for a released or re-signed rider that is the wrong team for every
past race. `RaceResultsView` currently does exactly that, and W2 fixes it
there too, so the two screens agree about the same race.

**D5. No points and no prize money anywhere on this page.** Both are team
awards (see *Context you need*), not individual ones, and the spec cuts them
explicitly. **Do not** add a `points` key to a race row or the career totals,
and do not join to `competitions.RacePoints` or `economy.LedgerEntry` at all
— this plan has no reason to import `competitions/` from `api/` for this
feature.

**D6. The career totals are computed in Python from the same list the page
shows.** Do not use separate aggregate queries. This follows the
`squad_value` precedent (`api/README.md`): two numbers derived from one list
cannot disagree.
- `starts` is the number of result rows.
- `wins`, `podiums` and `top_tens` count *finished* rows at position 1, ≤3
  and ≤10.
- `dnfs` counts rows with `finish_time is None`.

A DNF never counts as a podium, even though it carries a position.

**D7. Attribute history ships snapshots in time order and marks where
recording began. The chart's right-hand end is the rider's current value.**
- The payload lists snapshots in time order. The baseline (`week=None`)
  comes first, then the others by `(week.season.number, week.number)`.
  Order in Python or with `order_by("week__season__number", "week__number")`
  plus nulls first. **Do not** order by `created_at`: that is wall-clock time
  (`core.TimeStampedModel`) and the backfill wrote baselines long after the
  riders existed.
- The baseline has no game time, so the chart labels it **"Start"** and
  places it at the left edge. That is the spec's "the point at which
  recording began".
- The payload also carries `current_week` (`{season, week}` or `null`,
  explained below). The SPA extends every line flat from the last snapshot
  to `current_week`, using the **rider's current attributes** as the final
  value, not the last snapshot. This is load-bearing: the radar and the
  history chart then end on the same numbers by construction, and a missed
  or late snapshot cannot make the two charts disagree.

`current_week` comes from `schedule.services.current_position(now())`:
- `in_season` gives `{season: n, week: w}`.
- `off_season` gives `{season: n, week: SEASON_WEEKS}`. The season just
  ended, so it is shown as its last week.
- `no_season` gives `null`, and the chart draws the baseline across the full
  width.

**D8. The history chart is a step chart on a season-week axis.** A
displayed value only changes at a snapshot, so a sloped line between two
snapshots would invent intermediate values. Draw horizontal-then-vertical
steps.
- The x position of a weekly snapshot is `(season - 1) * SEASON_WEEKS + week`.
- The domain runs from one unit before the first weekly snapshot, where
  "Start" sits, to `current_week`.
- The y axis is fixed at 0-10 with gridlines on whole numbers. Never
  autoscale it: an autoscaled axis turns a one-point move into a cliff.
- Five lines, one colour each, from a new `attributeColor` map in
  `theme.ts`. A legend names them in the same order as the radar axes.

**D9. The radar is hand-written SVG with whole-number rings.**
- Five axes at 72° intervals starting straight up, in the order climb,
  sprint, flat, resistance, positioning (`ENGINE_ATTRIBUTES` order).
- Ten concentric rings, one per whole step. Rings 5 and 10 are drawn
  stronger.
- A single filled polygon, with each vertex's integer value printed beside
  it.
- The input values are already integers from the API. The component must
  **not** interpolate, smooth or animate between values. The spec's
  honesty rule is "points only on whole numbers".
- No chart dependency. Adding one is a new runtime dependency, which this
  plan does not authorise.

**D10. A 404 is a "no longer in the game" state. Any other failure is an
error state.** `getRiderProfile` throws a `RiderNotFound` error class on a
404 status. The hook exposes `notFound` separately from `error`. **Do not**
fold them together. The spec requires a deleted rider (#104) to read as an
explained absence, not a broken page. A 500 or a network failure should
still say "Couldn't load this rider."

**D11. Race rows are newest first, by `race.starts_at` descending, then
`race.id` descending.** The id is a tiebreak, because `starts_at` is
nullable. Only `FINISHED` races have results rows, so no status filter is
needed; add one anyway (`race__status=Race.Status.FINISHED`) so a future
change to when results are written cannot leak a half-run race. Each row
ships `finish_time` **and** `winner_time`, the fastest finishing time in
that race, so the SPA can show the same cell as the results screen: total
time for the winner, `+gap` for everyone else, `DNF` for non-finishers. Use
the existing `formatRaceTime` / `formatGap` in `src/raceTime.ts`. Do not
reimplement them.

**D12. The rider page has no actions.** No Release and no Sign. Those stay
on the Roster panel and the Transfers screen, which already own the
cost-and-balance context those buttons need. The spec kept the Roster panel
for exactly this reason.

## Data model

No changes. No migrations. Everything is read from existing models:
- `riders.Rider`
- `riders.RiderAttributeSnapshot`
- `racing.RaceResult`, `racing.RaceSquadRider` (with `squad__team`)
- `schedule.Week` / `Season`, via `current_position`

## The payload

`GET /api/riders/<rider_id>/` → 200:

```jsonc
{
  // --- inherited from RiderSerializer (D3), unchanged ---
  "id": 12, "name": "…", "speciality": "Climber", "nationality": "Spain",
  "age": 24, "height_cm": 176, "weight_kg": 61,
  "climb": 8, "sprint": 3, "flat": 5, "resistance": 6, "positioning": 5,
  "freshness": 7, "weekly_salary": 4200, "market_value": 310000,
  "release_cost": null,
  // --- added by RiderProfileSerializer ---
  "team": {"id": 3, "name": "…", "code": "ABC"},        // null for a free agent
  "current_week": {"season": 1, "week": 7},              // null when no_season (D7)
  "attribute_history": [
    {"season": null, "week": null, "climb": 7, "sprint": 3, "flat": 5, "resistance": 6, "positioning": 5},
    {"season": 1, "week": 4, "climb": 8, "sprint": 3, "flat": 5, "resistance": 6, "positioning": 5}
  ],
  "races": [
    {
      "race": {"id": 41, "name": "…", "starts_at": "2027-03-15T10:00:00Z"},
      "team": {"id": 3, "name": "…", "code": "ABC"},     // team raced for (D4); null never expected, but allow it
      "position": 2,
      "finish_time": 3642.0,                             // null = DNF
      "winner_time": 3600.0,                             // null only if nobody finished
      "finished": true
    }
  ],
  "career": {"starts": 9, "wins": 1, "podiums": 3, "top_tens": 7, "dnfs": 1}
}
```

404 when no `Rider` has that id. 403 for an anonymous caller (project
default).

## `api/rider_profile.py` (new)

A module of plain functions that build the dict above for the serializer.
It lives in `api/` because it joins `riders/`, `racing/` and `schedule/`,
which only `api/` and `world/` may all import (`AGENTS.md`, *Dependency
direction*). Keeping it out of `views.py` makes it unit-testable without
HTTP.

```python
def rider_profile(rider: Rider, *, at: datetime) -> dict: ...
def attribute_history(rider: Rider) -> list[dict]: ...
def race_history(rider: Rider) -> list[dict]: ...
def career_totals(races: list[dict]) -> dict: ...
def current_week_payload(at: datetime) -> dict | None: ...
```

`rider_profile` returns the rider **instance's** attributes untouched, since
the serializer maps them, plus the four added keys. It takes `at`, not
`now()`, so tests control the clock. The view passes `world.services.now()`.

`race_history` has a fixed number of queries, whatever the career length.
The query shape below is where the natural first attempt goes wrong: a
per-row `.rider.team` lookup, which reads the rider's **current** team
instead of the team they raced for (D4).

```python
def race_history(rider):
    results = list(
        RaceResult.objects
        .filter(rider=rider, race__status=Race.Status.FINISHED)
        .select_related("race")
        .order_by(F("race__starts_at").desc(nulls_last=True), "-race_id")
    )
    race_ids = [r.race_id for r in results]

    team_by_race = {
        m.squad.race_id: m.squad.team
        for m in RaceSquadRider.objects
            .filter(rider=rider, squad__race_id__in=race_ids)
            .select_related("squad__team")
    }
    winner_time = dict(
        RaceResult.objects
        .filter(race_id__in=race_ids, finish_time__isnull=False)
        .values("race_id").annotate(t=Min("finish_time"))
        .values_list("race_id", "t")
    )

    rows = []
    for r in results:
        team = team_by_race.get(r.race_id)
        rows.append({...})
    return rows
```

`team_by_race.get` may legitimately miss a row only for data written
outside `simulate_race`, such as the admin or old fixtures. Ship `team:
null` in that case rather than raising.

`attribute_history`: one query,
`rider.attribute_snapshots.select_related("week__season")`. Sort it in
Python with the key `(0, 0, 0)` for the baseline and
`(1, season.number, week.number)` for the rest. The model's `ordering` is
`created_at`, which is wrong for this purpose (D7). Emit `season`/`week`
as `None` for the baseline.

## `api/serializers.py`

- `RiderProfileTeamSerializer`: `id`, `name`, `code`. Reuse
  `RaceResultTeamSerializer` if you prefer, since it has the same three
  fields. **Do** reuse it and do not duplicate.
- `AttributeSnapshotSerializer`: `season` and `week` (`IntegerField(allow_null=True)`)
  plus the five attributes as `IntegerField`. These are **already** display
  values. **Do not** pass them through `to_display_scale` a second time:
  that would floor 8 to 0.
- `CurrentWeekSerializer`: `season`, `week`.
- `RiderRaceSerializer`: `race` (a nested `id`/`name`/`starts_at`), `team`
  (`allow_null=True`), `position`, `finish_time` (`allow_null`),
  `winner_time` (`allow_null`), `finished`. No `points` field (D5).
- `CareerSerializer`: `starts`, `wins`, `podiums`, `top_tens`, `dnfs`. No
  `points` field (D5).
- `RiderProfileSerializer(RiderSerializer)`: adds `team`
  (`allow_null=True`), `current_week` (`allow_null=True`),
  `attribute_history` (`many=True`), `races` (`many=True`) and `career`.
  Because `RiderSerializer.to_representation` reads attributes off the
  instance with `getattr`, feed it the `Rider` instance. Populate the added
  keys with `SerializerMethodField`s that read from
  `self.context["profile"]`, the dict from `rider_profile`, **or** pass an
  object that carries both. Either works. Pick the first: it keeps
  `RiderSerializer`'s instance handling untouched.

## `api/views.py` and `api/urls.py`

```python
class RiderProfileView(APIView):
    def get(self, request, rider_id: int):
        rider = get_object_or_404(Rider.objects.select_related("team"), pk=rider_id)
        profile = rider_profile(rider, at=now())
        return Response(RiderProfileSerializer(rider, context={"profile": profile}).data)
```

Route: `path("riders/<int:rider_id>/", RiderProfileView.as_view(), name="rider-profile")`,
placed directly after `riders/`.

**`RaceResultsView` (W2):** replace the `r.rider.team` lookup with the
squad-derived team. Take one extra query,
`RaceSquadRider.objects.filter(squad__race=race).select_related("squad__team")`,
map `rider_id` to team, and use that map for the `team` key of each result
row. The `select_related("rider__team")` becomes `select_related("rider")`.
Nothing else in the view changes: `results[].team` becomes the team raced
for, and the existing `points` list (each *team's* award from `RacePoints`,
unrelated to this cut) is untouched.

## Frontend

### `src/api.ts`

- Types `RiderProfile extends Rider` with `team`, `current_week`,
  `attribute_history`, `races` and `career`, plus `AttributeSnapshot`,
  `RiderRace` and `Career`, mirroring the payload above field for field.
- `export class RiderNotFound extends Error {}`.
- `getRiderProfile(id)`: `fetch('/api/riders/${id}/')`. On a 404, throw
  `new RiderNotFound()`. On any other non-OK status, throw a plain `Error`,
  as the other getters do.

### `src/useRiderProfile.ts` (new)

`useRiderProfile(riderId: number): { profile, loading, notFound, error }`.
It fetches once on mount and whenever `riderId` changes, with the same
`cancelled`-flag shape as `useRaceDetail.ts`, and does not poll. Set
`notFound` when the caught error is an `instanceof RiderNotFound` (D10).
Reset all three flags when `riderId` changes, so moving from one rider's
page to another's does not show the previous rider mid-load.

### `src/theme.ts`

Add `attributeColor: Record<'climb'|'sprint'|'flat'|'resistance'|'positioning', string>`.
Pick five distinguishable hues that work against the white `surface`. Do
not reuse `positive`/`negative`: those mean good and bad elsewhere, and an
attribute has no such meaning.

### `src/components/AttributeRadar.tsx` (new)

- `export function radarVertices(values: number[], radius: number): Array<[number, number]>`
  is pure. Axis *i* sits at angle `-90° + i*72°` and value `v` at
  `radius * v / 10`. Export it for tests.
- `export function AttributeRadar({ rider }: { rider: Pick<Rider, AttrKey> })`
  renders an SVG with a `viewBox` and fixed width 100%, so it scales on a
  phone. It draws the ten rings, five axis lines, axis labels (Climb,
  Sprint, Flat, Resistance, Positioning), the polygon and each vertex's
  printed value (D9).

### `src/components/AttributeHistoryChart.tsx` (new)

- `export function historySeries(history: AttributeSnapshot[], current: Pick<Rider, AttrKey>, currentWeek: CurrentWeek | null): { xMax: number; points: Array<{ x: number; label: string; values: Record<AttrKey, number> }> }`
  is pure. Export it for tests.
  - Weekly snapshots map to `x = (season-1)*12 + week`. Take 12 from a
    shared `SEASON_WEEKS = 12` constant in the file and note in a comment
    that it mirrors `schedule.models.SEASON_WEEKS`.
  - The baseline maps to `x = firstWeeklyX - 1`, or to `currentX - 1` when
    there are no weekly snapshots, or to 0 when there is no `currentWeek`
    either.
  - It appends a final point at `currentX` carrying the **current**
    attribute values (D7).
  - Labels are `"Start"` and `"S{n} W{w}"`.
- `export function AttributeHistoryChart(...)` renders an SVG step chart:
  five `<path>`s built horizontal-then-vertical, a y axis fixed 0-10 with
  whole-number gridlines, a legend in radar-axis order, and x-axis labels at
  the first and last points only, to avoid crowding. When `history.length === 1`
  and there are no weekly points, also render the caption
  "Recording began at the start of this rider's history; no change yet."
  (spec *In scope* 3).

### `src/screens/RiderProfile.tsx` (new)

This is the route component for `/riders/:riderId`. It reads `riderId` with
`useParams`, as `Race.tsx` does, and calls `useRiderProfile`.

- `loading` renders `null`, the house rule (`frontend/README.md`, *Where the
  data comes from*).
- `notFound` renders a `PageBody` with a `Card`: "This rider is no longer
  part of the game." (D10).
- `error` renders a `Card`: "Couldn't load this rider."
- Otherwise it renders, top to bottom:
  1. `PageHeading`, with the speciality in capitals as the eyebrow, the name
     as the title, and a subtitle of `{Team name | "Free agent"} · {age} yrs ·
     {nationality}`.
  2. A row of `StatTile`s: height, weight, weekly salary (`formatMoney` +
     `/wk`), market value (`formatMoney`), freshness (`n / 10`).
  3. A two-column grid that collapses to one column under ~720px: the
     `AttributeRadar` card and the `AttributeHistoryChart` card.
  4. A career strip of five `StatTile`s: Races, Wins, Podiums, Top 10, DNF.
     These are plain numbers with **no `$`**, per `AGENTS.md`, *Displaying
     game money*. No points tile (D5).
  5. A "Race history" `Card` with one row per race: date, race name
     (`Link` to `/race/:id`), the team code raced for, the position (or `—`
     when not finished), and the time cell (D11). No points column (D5).
     With no races, show one muted line: "No races yet."

There are no action buttons (D12).

### Links: `src/navigation.ts`, `App.tsx`, and three screens

- `navigation.ts`: `export function riderPath(id: number): string`, which
  returns `` `/riders/${id}` ``. Every link below uses it, and nothing
  builds the path by hand. Extend `titleForPath` to return `'Rider'` for a
  path starting `/riders/`. Today every non-nav path falls back to
  `'Dashboard'` in the mobile top bar.
- `App.tsx`: `<Route path="/riders/:riderId" element={<RiderProfile />} />`,
  next to the `/race/:raceId` route, with the same comment style.
- `Roster.tsx` `RiderPanel`: add a `Link` "Full profile →" under the name
  line, in `color.accentInk`. The panel otherwise stays exactly as it is.
- `Race.tsx` `RiderResultsTable`: wrap `entry.rider.name` in a `Link` to
  `riderPath(entry.rider.id)`.
- `Transfers.tsx` `FreeAgentCard`: wrap `agent.name` in a `Link`. Keep the
  ellipsis styles on the link, not on a parent that the link overflows.
- **Not** the squad-selection candidate rows (spec *Out of scope*).

## Work items

### W1 — `api/rider_profile.py`, `api/serializers.py`, `api/views.py`, `api/urls.py`: the rider profile endpoint — done

Build D1–D7 and D11 as specified above. Tests go in `api/tests.py`, in a new
`# --- rider profile ---` block with fixtures for two teams, a season with
weeks and a finished race whose squads and results are written directly:

- `test_rider_profile_requires_authentication`: anonymous → 403.
- `test_rider_profile_readable_by_any_manager_and_by_teamless_user`: a
  rival's rider is 200, and so is a user with no team.
- `test_rider_profile_unknown_rider_is_404`.
- `test_rider_profile_has_no_hidden_traits`: assert the **exact** top-level
  key set. Do not assert only the absence of known hidden names, because a
  new hidden trait would pass that.
- `test_rider_profile_identity_matches_roster_payload`: for the caller's own
  rider, every `RiderSerializer` key (except `release_cost`) is equal between
  `/api/riders/` and `/api/riders/<id>/`.
- `test_rider_profile_attribute_history_orders_baseline_first_then_by_week`:
  create snapshots out of `created_at` order and assert the payload order.
- `test_rider_profile_attribute_history_values_are_not_rescaled`: a snapshot
  of 8 ships as 8.
- `test_rider_profile_race_team_is_team_raced_for_not_current_team`: the
  rider races for A, is then moved to B (`rider.team = b; save()`), and the
  row still says A.
- `test_rider_profile_dnf_row_and_career_counts`: a DNF at position 3 counts
  as a start and a DNF, and does not count as a podium.
- `test_rider_profile_has_no_points_field`: neither a race row nor `career`
  carries a `points` key.
- `test_rider_profile_winner_time_and_order_newest_first`.
- `test_rider_profile_current_week_in_off_and_no_season`.
- `test_rider_profile_query_count_is_constant`: with
  `django_assert_max_num_queries`, a rider with one race and a rider with
  five races stay under the same bound (fix the bound at whatever W1
  produces, e.g. 10). **This test is the guard against the N+1.**

### W2 — `api/views.py`: race results name the team raced for — done

Change `RaceResultsView` as described under *`api/views.py`*. Test in
`api/tests.py`:
- `test_race_results_team_is_team_raced_for_after_release`: after the race,
  set the rider teamless. The results row still shows the original team,
  where today it shows `null`.

Existing race-results tests must stay green unchanged.

### W3 — `frontend/src/api.ts`, `src/useRiderProfile.ts`: types, fetcher, hook — done

Test `src/useRiderProfile.test.ts` with `renderHook` and a mocked
`getRiderProfile`:
- A 404 (`RiderNotFound`) sets `notFound: true, error: false`.
- A generic error sets `error: true, notFound: false`.
- Changing `riderId` resets `profile` to `null` while the next fetch is in
  flight.

### W4 — `src/theme.ts`, `src/components/AttributeRadar.tsx`: the radar — done

Test `src/components/AttributeRadar.test.tsx`:
- `radarVertices([10,10,10,10,10], 100)`: the first vertex is `[0,-100]`
  (straight up), and all five sit at distance 100.
- `radarVertices([0,…], r)`: every vertex is at the origin.
- Rendering prints each of the five integer values and all five axis
  labels.

### W5 — `src/components/AttributeHistoryChart.tsx`: the history chart — done

Test `src/components/AttributeHistoryChart.test.tsx`, which is mostly
`historySeries`:
- Baseline only, with `currentWeek` S1 W5: two points (`Start` at x=4, the
  current values at x=5).
- Baseline plus snapshots at S1 W3 and S2 W1: x values 2, 3, 13, then
  current.
- The final point carries the **current** values even when they differ from
  the last snapshot (D7).
- `currentWeek: null` gives a baseline at 0.
- The render shows the "no change yet" caption for baseline-only history.

### W6 — `src/screens/RiderProfile.tsx`, `src/App.tsx`, `src/navigation.ts`: the page and route — done

Test `src/screens/RiderProfile.test.tsx`, mocking `useRiderProfile`:
- The full profile renders the name, team, `$` salary and value, the five
  career numbers and a race row with a `+gap`.
- A free agent's subtitle says "Free agent".
- A DNF row shows `—` and `DNF`.
- An empty `races` list shows "No races yet."
- `notFound` shows "no longer part of the game".
- `error` shows "Couldn't load this rider."
- No `button` is rendered (D12).
- No points figure appears anywhere on the page (D5).

In `src/navigation.test.ts`, test that `riderPath(7)` returns `'/riders/7'`
and that `titleForPath('/riders/7')` returns `'Rider'`.

### W7 — `Roster.tsx`, `Race.tsx`, `Transfers.tsx`: the links — done

Extend the existing tests:
- `Roster.test.tsx`: the open panel has a "Full profile" link to
  `/riders/<id>`.
- `Race.test.tsx`: each rider name in the results table is a link to
  `/riders/<id>`.
- `Transfers.test.tsx`: a free agent's name is a link to `/riders/<id>`.

### W8 — Documentation — done

See below.

## Execution order

1. **W1**, then commit. The payload is the contract everything else reads.
   Proving it first, with the query-count and hidden-trait tests, is the
   cheapest place to catch the two serious mistakes.
2. **W2**, then commit. It uses the same squad-to-team idea while it is
   fresh, and it is independent of the frontend.
3. **W3**, then commit. Types and the hook are needed by W6.
4. **W4** and **W5**, a commit each. They are pure components with pure
   helpers and are independently testable.
5. **W6**, then commit. It composes W3–W5.
6. **W7**, then commit. The links are added last, so none points at a route
   that does not exist yet.
7. **W8**, then commit. Then move spec and plan to `specs/archive/` with
   `Status: implemented` (`AGENTS.md`, *Closing a ticket*).

Run `.venv/bin/python -m pytest` and `npm --prefix frontend test` at every
commit, and `npm --prefix frontend run build` after W6, because `tsc -b`
catches type drift the tests do not.

## Documentation update (required, not optional)

- **`api/README.md`**, *What exists*: add a `GET /api/riders/<rider_id>/`
  entry. It should cover:
  - readable by any authenticated user;
  - 404 on a missing rider;
  - the identity keys are inherited from `RiderSerializer`;
  - the team raced for comes from squads;
  - that race points and prize money are deliberately absent — both are team
    awards, not individual ones (`competitions/README.md`);
  - attribute history ordering, and that values are already display-scale;
  - `current_week`.

  Amend the `GET /api/racing/races/<race_id>/results/` entry: `team` is now
  the team raced for (W2), not the rider's current team.
- **`frontend/README.md`**:
  - Add a `/riders/:riderId` row to *What exists*.
  - Extend the parameterised-route paragraph.
  - Record that the radar and the history chart are hand-written SVG with
    no chart dependency, and explain the step chart and the "right-hand end
    is the current value" rule (D7, D8).
  - Record `riderPath` as the one way to build the link.
  - Record `attributeColor` under *Conventions*.
- **`riders/README.md`**, *Attribute history*: replace "**Nothing serializes
  this.**…" with a pointer to `GET /api/riders/<id>/`. Keep the
  display-scale rule and restate that the API must not re-map the values.
- **`racing/README.md`**, *Squads*: one sentence noting that squads are now
  also the record of which team a rider raced for, read by the rider
  profile and race results. Say so because `Rider.team` is only the current
  team.
- **`AGENTS.md`**: update the `frontend/` row's screen count and list (add
  the rider page).

## Verification

Beyond the unit tests, in this worktree's own database and port
(`python config/worktree.py`):

```bash
.venv/bin/python scripts/dev_db.py
.venv/bin/python manage.py migrate
.venv/bin/python manage.py seed_user
.venv/bin/python manage.py seed_teams --claim-for test@mail.com
.venv/bin/python manage.py seed_trainers
.venv/bin/python manage.py load_season seasons/season-1.example.json
# under GAME_CLOCK_CLASS=world.clocks.MockClock:
.venv/bin/python manage.py mock_clock set <season start>
.venv/bin/python manage.py tick        # advance a few weeks so races run
npm --prefix frontend run build && .venv/bin/python manage.py runserver <port>
```

Then check each of these:

1. **Hidden traits.** `curl` the endpoint as the demo user and compare the
   key set against `RiderSerializer`'s plus the five added keys. No
   `potential`, `peak_age`, `decline_rate`, `injury_proneness`,
   `training_affinity`, `recovery_rate` or `growth_debt` at any depth.
2. **Team raced for (the likeliest silent failure).** Release a rider who
   has raced, from the Roster. Open an old race they rode in. The results
   row still shows the old team code. Open the rider's page: the race row
   still shows the old team, and the subtitle says "Free agent". Before W2,
   the results row would lose its team code, so this check can fail.
3. **No points anywhere.** Neither a race row nor the career strip on the
   rider page shows a points figure, even for a rider who scored heavily —
   the race's own screen and the League table are still where points live.
4. **Radar/graph agreement.** On a rider whose attributes moved during the
   ticks (see the Training screen's last-week list), the radar's value for
   that attribute equals the right-hand end of that attribute's line, and
   both equal the Roster panel's bar value.
5. **Gone rider.** Delete a rider in `manage.py shell` and load
   `/riders/<id>`. The page says "no longer part of the game", not a blank
   page or a redirect to `/`.
6. **Phone width.** At 375px, the radar and the chart stack in one column,
   nothing scrolls horizontally, and the race rows fit.

## Risks

| Risk | Mitigation |
|---|---|
| Taking the team from `Rider.team`, the natural spelling, which silently mislabels every past race of a moved rider | D4. `test_rider_profile_race_team_is_team_raced_for_not_current_team`. Verification step 2. |
| Adding a per-rider points figure (race row or career total), which double-counts a team award as an individual one and cannot be reconciled against the standings | D5. `test_rider_profile_has_no_points_field`. Verification step 3. |
| An N+1 over race rows (per-row team or winner-time lookups) that grows with career length | `race_history` has a fixed query shape. `test_rider_profile_query_count_is_constant`. |
| A new hidden trait added to `Rider` later leaks through a hand-listed serializer | D3 inherits `RiderSerializer`. The exact-key-set test fails on any addition. |
| Snapshot values passed through `to_display_scale` again, which turns 8 into 0 | Called out in the serializer section. `test_rider_profile_attribute_history_values_are_not_rescaled`. |
| Ordering history by `created_at`, which the backfill made meaningless | D7. The ordering test creates rows out of `created_at` order. |
| The radar and the graph disagree because the last snapshot is stale | D7: the chart's final point is the current attributes. W5 test. Verification step 4. |
| A 404 rendered as a generic error, or as a redirect to `/` | D10. A separate `notFound` flag. W3 and W6 tests. Verification step 5. |
| An autoscaled y axis exaggerating one-point moves | D8: the y domain is fixed 0-10. |
| Reintroducing cut items (prize money, sparkline, season summary, a Release button on the page) | The spec's *Out of scope* is binding. D12. The W6 test asserts no buttons. |

## Open questions

None blocking.
