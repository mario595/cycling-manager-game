# Sprint points — Implementation Plan

**Spec:** `specs/sprint-points.md` · **Issue:** #16 · **Status:** proposed
**Apps touched:** `racing/`, `schedule/`, `competitions/`, `world/`, `api/`, `frontend/`, `seasons/` (example data)

## Context you need

**Markers already exist (#70, `specs/archive/course-markers.md`).** A race's
course can declare named points: `racing.RaceMarker` (`kind` sprint/mountain,
`name`, `distance`), one row per marker. When `racing.services.simulate_race`
runs, it writes one `racing.MarkerCrossing` per rider per marker, `position`
contiguous from 1. A marker placed on the finish line takes its order from the
results, finishers only (racing README, *Markers and crossings*, D5). Markers
are authored in the season file (`seasons/season-1.example.json`), parsed by
`schedule/loaders.py::_parse_markers`, and created through
`racing.services.create_race`. #70 deliberately left out **weight**; this
ticket adds it.

**Race points today (`competitions/`, read its README).**
- `competitions.scoring.POINTS_BY_POSITION` pays 20 down to 1 for 1st–10th.
- `competitions.services.score_race(race)` writes one `RacePoints` row per
  team, from the team's **single best finisher**. It is called from
  `world/services.py::_execute` right after `simulate_race`.
- `standings(season)` sums `RacePoints` and breaks ties by countback (most 1sts,
  then 2nds…).
- `points_by_team(week)` sums a week's `RacePoints` per team. `world.tick()`
  hands that dict to `economy.apply_weekly_fanbase` and `economy.pay_sponsorship`,
  **so whatever that function returns moves fanbase and sponsorship too.**

**Presentation.** Four places show the data:
- `api/views.py::RaceDetailView` serves the course preview (markers included).
- `RaceResultsView` serves the results screen. It shows the first
  `MARKER_PLACES_SHOWN = 3` crossings per marker and a per-team points list.
- `StandingsView` serves the league table.
- The SPA renders them in `frontend/src/screens/Race.tsx` (`MarkerResultsCard`,
  `TeamPointsTable`), `frontend/src/components/CourseProfile.tsx` (the marker
  list under the chart), and `League.tsx`/`Dashboard.tsx` (the total).

**Rules this work is bound by (AGENTS.md):**
- `competitions -> racing, teams, schedule, core` is allowed; `racing` must
  never import `competitions`.
- `schedule/` library code (`loaders.py`) imports nothing from `racing/`.
- `race_engine/` is untouched: weight does not change how a marker is
  contested (spec, *Player experience*), so it is **not** passed through
  `racing/adapters.py`.

## Goal

- A sprint marker carries a named weight (`minor` / `standard` / `major`),
  authored in the season file and defaulting to `standard`.
- When a race finishes, the top 5 crossing positions at each sprint marker
  score by a per-weight table. Each team is credited only from its best-placed
  rider in that top 5. The rows are frozen.
- Those points add to the season standings total and to `points_by_team`
  (hence fanbase and sponsorship). Countback is unchanged.
- The course preview shows each sprint's weight and what winning it pays. The
  results screen shows the top 5 at each marker with the points each scored,
  and each team's race total split into finish points and sprint points.

## Design decisions (settled — implement these, do not substitute)

**D1 — A new model `competitions.MarkerPoints`, not a column on `RacePoints`.**
`RacePoints` is "one team's finish award for one race". Its `position` is
non-null and drives countback. A team that won a sprint but finished 30th has
no finish position, so bolting sprint points onto that row would force a
nullable `position` and teach countback to skip it. A separate table keeps
both meanings clean. It is named `MarkerPoints`, not `SprintPoints`, because
#17 (mountain points) will write the identical shape for mountain markers; the
kind is read from `marker.kind`, so the two tallies stay separable, as the spec
requires.

**D2 — One row per (marker, team), recording the scoring rider.** This mirrors
`RacePoints`' best-finisher rule (spec, In scope 3). The rider is stored so
the results screen can put the points beside the right name without
recomputing anything. A recomputation would silently disagree with the frozen
row the day the table is retuned.

**D3 — Load-bearing: take the top 5 crossing positions first, then keep each
team's best.** Filter `MarkerCrossing.position <= 5` **before** de-duplicating
by team. Do **not** walk down the crossing order until five distinct teams
have scored. If a team takes 1st and 2nd, the 2nd-place points are simply
lost and 6th place still scores nothing. That is the spec's "a lead-out rider
doesn't add a second helping", the same way the finish works today: a team
with riders 1st and 2nd scores 20, and 11th does not move up.

**D4 — Weight is a `TextChoices` on `RaceMarker`: `minor`, `standard`,
`major`; non-null, default `standard`.** The default means migrated rows and
unweighted season-file markers all become `standard`, which is what the spec
says an unweighted marker is. It is not nullable: a null weight would need a
"what is null worth" rule in every reader.

**D5 — Mountain markers must not author a weight.** The loader rejects a
`weight` key on a `mountain` marker with a `SeasonFileError`. #17 owns what a
mountain marker's weight means, and may want HC/1st/2nd… rather than these
three. Accepting the key now would let authors write data #17 then has to
reinterpret. Mountain rows in the database still get the column default; that
value is inert, because no reader scores or displays it (see D9). #17 is free
to migrate it.

**D6 — Explicit per-weight integer tables, not a multiplier.** A multiplier on
one base table produces fractions (a 0.5× "minor" of a 3-point place), and
points are whole numbers everywhere (`PositiveSmallIntegerField`). The tables,
in `competitions/scoring.py`:

```python
#: Sprint points by marker weight, then crossing position (1-indexed).
#: Positions beyond 5 score nothing. Frozen per marker at award time.
SPRINT_POINTS_BY_WEIGHT: dict[str, dict[int, int]] = {
    "minor":    {1: 4,  2: 3, 3: 2, 4: 1, 5: 1},
    "standard": {1: 6,  2: 4, 3: 3, 4: 2, 5: 1},
    "major":    {1: 10, 2: 7, 3: 5, 4: 3, 5: 2},
}
```

The spec's ceiling ("even the heaviest sprint tier stays a fraction of first
place at the finish") is enforced by a test: the `major` win is at most
half of `POINTS_BY_POSITION[1]`. The numbers are a starting point; the spec
defers a full retune until #17 exists. Keys are the `RaceMarker.Weight` values;
a test pins the two together.

**D7 — `score_sprints(race)` is its own function, called from `world/`, in its
own `try`.** It is not folded into `score_race`: `score_race` returns early if
the race already has `RacePoints` rows, and that idempotency guard must not
cover a second table. In `world/services.py::_execute` the call goes in a
**separate** `try` after the existing one, the same way prize payout is
isolated. A bug in sprint scoring must not rewrite a race that ran and was
finish-scored into `FAILED`. Record the traceback on `tick.error` as
`race {id} sprint points:`.

**D8 — Team attribution uses `rider.team_id` at scoring time,** exactly as
`score_race` does. Scoring runs in the same `_execute` call as the
simulation, so this is the team the rider raced for. A rider with no team is
skipped, as `score_race` skips them.

**D9 — Sprint points flow into `points_by_team` and `standings`; countback
does not change.** Both functions add `MarkerPoints` totals (for **sprint**
markers only — filter `marker__kind="sprint"` so #17's rows do not leak in
early). `standings` must now include a team that has sprint points but no
`RacePoints` row. Countback still counts finish positions only. A sprint 1st
is not a "1st place" for tie-breaking, because the spec keeps the league table
a single total and the brain dump keeps sprinting a different skill from
finishing.

**D10 — No backfill.** Races finished before this ships keep what they were
awarded (spec, *Rules*: frozen at scoring). There is no data migration and no
management command. `score_sprints` is only ever called from `_execute`.

**D11 — The results screen shows 5 crossings per marker, not 3.**
`MARKER_PLACES_SHOWN` becomes `5`, matching the scoring depth. Without this,
4th and 5th score points no player can see.

**D12 — A crossing that crossed then abandoned still scores.** The crossing
row exists (the rider reached the marker), and the spec only denies points to
a rider who "never reaches a marker". Do not join to `RaceResult.finish_time`.
A finish-line marker already contains finishers only (D5 of #70).

**D13 — Deleting a rider must not delete frozen points:**
`MarkerPoints.rider` is `on_delete=SET_NULL, null=True`. Raced riders are no
longer deleted (#104), so this is belt-and-braces. The team's points are the
record; the rider is attribution.

## Data model

### `racing/models.py` — `RaceMarker.weight` (new field)

```python
class Weight(models.TextChoices):
    MINOR = "minor", "Minor"
    STANDARD = "standard", "Standard"
    MAJOR = "major", "Major"

weight = models.CharField(
    max_length=10, choices=Weight.choices, default=Weight.STANDARD,
    help_text="How much a sprint marker is worth. Inert on mountain markers (#17 decides theirs).",
)
```

Not null, not blank, no index. Migration **`racing/migrations/0008_racemarker_weight.py`**
(`AddField`; existing rows get `standard`).

### `competitions/models.py` — `MarkerPoints` (new model)

| Field | Type | Null/blank | Default | Notes |
|---|---|---|---|---|
| `marker` | `ForeignKey("racing.RaceMarker", on_delete=CASCADE, related_name="points")` | no | — | string FK, as `RacePoints.race` |
| `team` | `ForeignKey("teams.Team", on_delete=CASCADE, related_name="marker_points")` | no | — | |
| `rider` | `ForeignKey("riders.Rider", on_delete=SET_NULL, null=True, blank=True, related_name="marker_points")` | yes | null | D13 |
| `position` | `PositiveSmallIntegerField` | no | — | the rider's crossing position, 1–5 |
| `points` | `PositiveSmallIntegerField` | no | — | frozen at award time |

Inherits `TimeStampedModel` (like `RacePoints`, it is an award record).
`Meta`:
- `ordering = ["marker", "position"]`
- `UniqueConstraint(fields=["marker", "team"], name="one_points_row_per_team_per_marker")`
- `Index(fields=["team", "marker"], name="markerpoints_team_marker_idx")`

Migration **`competitions/migrations/0002_markerpoints.py`**, which depends on
`racing/0008`. Register it in `competitions/admin.py` (`list_display = ("marker",
"team", "rider", "position", "points")`).

## `racing/models.py`, `racing/services.py`, `racing/admin.py`

- `RaceMarker.Weight` and `weight` as above.
- `create_race`: pass `weight=marker.get("weight", RaceMarker.Weight.STANDARD)`
  through to `RaceMarker.objects.create`. Update its docstring's dict shape to
  `{"kind", "name", "distance", "weight"?}`.
- `RaceMarkerInline` picks the field up automatically. Nothing else in
  `racing/` changes; the adapter and crossing writer are untouched.

## `schedule/loaders.py`

- `_KNOWN_MARKER_KEYS` gains `"weight"`.
- New module constant `MARKER_WEIGHTS = ("minor", "standard", "major")`,
  duplicated deliberately because `loaders.py` may not import `racing/`. A
  drift test lives in `racing/tests.py` (which may import `schedule`).
- In `_parse_markers`, after `distance`:
  - `weight` absent or `None` → `"standard"`.
  - `kind == "mountain"` and a `weight` key present → `SeasonFileError(f"{at}.weight is only allowed on sprint markers")`.
  - otherwise not in `MARKER_WEIGHTS` → `SeasonFileError(f"{at}.weight must be one of minor, standard, major, got {weight!r}")`.
  - append `"weight": weight` to the dict (mountain gets `"standard"`, matching the column default).

## `competitions/scoring.py`

Add `SPRINT_POINTS_BY_WEIGHT` (D6) and:

```python
SPRINT_PLACES = 5

def sprint_points_for(weight: str, position: int) -> int:
    """What a crossing position at a sprint of this weight is worth. Zero outside the table."""
```

## `competitions/services.py`

The hard part. Write it like this:

```python
def score_sprints(race: Race) -> list[MarkerPoints]:
    """Award sprint points for one finished race: per sprint marker, each
    team's best-placed rider among the top SPRINT_PLACES crossings.
    Idempotent: a race already scored returns its existing rows.

    Raises ValueError if the race is not FINISHED.
    """
    if race.status != Race.Status.FINISHED:
        raise ValueError(f"{race} is not finished; nothing to score")

    existing = list(MarkerPoints.objects.filter(marker__race=race))
    if existing:
        return existing

    to_create = []
    for marker in race.markers.filter(kind=RaceMarker.Kind.SPRINT):
        crossings = (
            MarkerCrossing.objects
            .filter(marker=marker, position__lte=SPRINT_PLACES)   # D3: cut first...
            .order_by("position")
            .values_list("rider_id", "rider__team_id", "position")
        )
        best: dict[int, tuple[int, int]] = {}
        for rider_id, team_id, position in crossings:
            if team_id is None or team_id in best:                # ...then best per team
                continue
            best[team_id] = (rider_id, position)
        to_create += [
            MarkerPoints(marker=marker, team_id=team_id, rider_id=rider_id,
                         position=position,
                         points=sprint_points_for(marker.weight, position))
            for team_id, (rider_id, position) in best.items()
        ]
    return MarkerPoints.objects.bulk_create(to_create, ignore_conflicts=True)
```

`points_by_team(week)`: after the existing `RacePoints` aggregation, add

```python
sprint = (
    MarkerPoints.objects
    .filter(marker__race__week=week, marker__kind=RaceMarker.Kind.SPRINT)
    .values("team_id").annotate(total=Sum("points"))
)
```

and merge by adding each total into the dict (`result[t] = result.get(t, 0) + total`).

`standings(season)`: build `by_team` from `RacePoints` exactly as now. Then
aggregate `MarkerPoints` for the season (`marker__race__week__season=season`,
sprint only), add each total into the team's `points`, and create the entry
for any team not yet in `by_team`. Fetch those teams with
`Team.objects.in_bulk(missing_ids)` and give them `positions: {}`. Also record
`entry["sprint_points"]` (0 when none) for tests and future use. The API does
**not** expose it (spec: single total). `_countback_key` is unchanged.

## `world/services.py`

Import `score_sprints` next to `score_race`. In `_execute`, between the
existing simulate/score `try` and the prize `try`:

```python
try:
    score_sprints(race)
except Exception:
    tick.error += f"race {race_id} sprint points:\n{traceback.format_exc()}\n"
```

It must come after the `continue` for failed races, and must not touch
`race.status`.

## `api/views.py`, `api/serializers.py`

- A shared helper `_marker_payload(m) -> dict` returns `id, kind, name,
  distance`, plus:
  - `weight`: `m.weight` for sprint markers, `None` for mountain.
  - `points`: for sprint markers, the list of that weight's table values in
    position order (`[10, 7, 5, 3, 2]`); `None` for mountain.

  Use it in both `RaceDetailView` and `RaceResultsView`.
  `RaceMarkerSerializer` gains `weight = CharField(allow_null=True)` and
  `points = ListField(child=IntegerField(), allow_null=True)`.
- `MARKER_PLACES_SHOWN = 5` (D11). Update the comment's reference.
- `RaceResultsView`:
  - Load `MarkerPoints.objects.filter(marker__race=race)` once. From it build
    `scored_crossing = {(marker_id, rider_id): points}` and
    `sprint_by_team = {team_id: sum}`.
  - Each crossing payload gains `points`: `scored_crossing.get((m.pk, c.rider_id))`.
    That is `None` for mountain markers and for a rider whose teammate crossed
    ahead. `RaceMarkerCrossingSerializer` gains
    `points = IntegerField(allow_null=True)`.
  - Each points entry gains `finish_points` (the `RacePoints.points` value, or
    0) and `sprint_points` (`sprint_by_team.get(team_id, 0)`). `points` becomes
    their sum. The ordering rule is unchanged: teams with a finish position
    first, by position, then the other starters. That second group is now
    ordered by `sprint_points` descending, then name.
    `RaceResultPointsEntrySerializer` gains both fields.
- `StandingsView`: no code change; `standings()` now includes sprint points.

## `frontend/`

- `src/api.ts`:
  - `RaceMarker` gains `weight: 'minor' | 'standard' | 'major' | null` and
    `points: number[] | null`.
  - `RaceMarkerCrossing` gains `points: number | null`.
  - `RaceResultPointsEntry` gains `finish_points: number` and
    `sprint_points: number`.
- `src/components/CourseProfile.tsx`: in the marker list under the chart,
  sprint markers render `Sprint · <name> · km <x> · <Weight> · <points[0]> pts
  to the winner`, with the weight capitalised. Mountain markers render as today.
- `src/screens/Race.tsx`:
  - `MarkerResultsCard`: for a sprint marker, add the weight label after the
    name. For each crossing with non-null `points`, add a right-aligned mono
    `+<points>`. A null shows nothing.
  - `TeamPointsTable`: when `sprint_points > 0`, show a muted line under the
    team name: `finish <finish_points> · sprints <sprint_points>`. The bold
    total is unchanged.
- Nothing changes in `League.tsx` or `Dashboard.tsx`; they read the total.

## `seasons/season-1.example.json`

So the feature is visible after seeding:
- Week 1 "Opening Sprint": `First Sprint` → `"weight": "minor"`,
  `Second Sprint` → `"weight": "major"`.
- Week 3 "Long Haul": add
  `{ "kind": "sprint", "name": "Finish Sprint", "distance": 210000, "weight": "standard" }`.
  This demonstrates a finish-line sprint (spec, In scope 7).
- Leave week 2's `Valley Sprint` unweighted, which shows the default.

## Work items

### W1 — `racing/`: `RaceMarker.weight` + migration 0008 + `create_race` ✅
Add the `Weight` choices, the field and the migration, and pass `weight`
through `create_race`.
Tests in `racing/tests.py`:
- `test_marker_weight_defaults_to_standard`
- `test_create_race_stores_marker_weight`
- `test_create_race_without_weight_gives_standard`

### W2 — `schedule/loaders.py`: parse `weight` ✅
Implement as above.
Tests in `schedule/tests/test_loaders.py`:
- `test_sprint_marker_weight_is_parsed`
- `test_missing_weight_defaults_to_standard`
- `test_rejects_unknown_weight`
- `test_rejects_weight_on_mountain_marker`

In `racing/tests.py`, `test_loader_weights_match_race_marker_weights` asserts
`set(schedule.loaders.MARKER_WEIGHTS) == set(RaceMarker.Weight.values)`.
In `schedule/tests/test_load_season.py`,
`test_load_season_stores_marker_weight` covers the file-to-row path.

### W3 — `competitions/scoring.py`: the sprint tables ✅
Tests in `competitions/tests/test_scoring.py`:
- `test_every_weight_has_exactly_five_scoring_places`
- `test_sprint_points_decline_down_the_order` (non-increasing)
- `test_heavier_weights_never_pay_less` (per position: minor ≤ standard ≤ major)
- `test_major_sprint_win_is_at_most_half_a_race_win`
- `test_sprint_position_outside_table_scores_zero`
- `test_sprint_table_keys_match_marker_weights` (against `RaceMarker.Weight.values`)

### W4 — `competitions/`: `MarkerPoints` model, migration 0002, admin, `score_sprints`
New file `competitions/tests/test_sprints.py`. Add a `make_crossing` fixture to
`competitions/tests/conftest.py`.
- `test_top_five_at_a_sprint_score_by_weight`
- `test_team_scores_only_its_best_rider_at_a_marker`: riders 1st and 2nd on
  one team → one row, 1st's points.
- `test_sixth_place_does_not_move_up_when_a_team_doubles` (**D3, load-bearing**)
- `test_mountain_markers_score_nothing`
- `test_rider_who_crossed_then_abandoned_keeps_points` (D12)
- `test_teamless_rider_is_skipped`
- `test_score_sprints_is_idempotent`
- `test_score_sprints_rejects_unfinished_race`
- `test_race_without_sprint_markers_scores_nothing`
- `test_points_frozen_when_table_changes` (monkeypatch the table after scoring; the row is unchanged)

### W5 — `competitions/services.py`: `points_by_team` and `standings` include sprint points
Tests in `competitions/tests/test_services.py` and `test_standings.py`:
- `test_points_by_team_adds_sprint_points`
- `test_points_by_team_ignores_mountain_marker_points` (a hand-made
  `MarkerPoints` row on a mountain marker is excluded)
- `test_standings_include_sprint_points_in_total`
- `test_team_with_only_sprint_points_appears_in_standings`
- `test_sprint_points_do_not_count_in_countback`: two teams level on total,
  one via a finish 1st and one via sprints; the finish 1st ranks higher.

### W6 — `world/services.py`: call `score_sprints` in `_execute`
Tests in `world/tests/test_tick.py`:
- `test_tick_scores_sprint_points_for_a_finished_race` (a race with a sprint
  marker runs through `tick()` and gets `MarkerPoints` rows)
- `test_sprint_scoring_failure_does_not_fail_the_race`: monkeypatch
  `world.services.score_sprints` to raise; the race stays `FINISHED`,
  `RacePoints` exist, prizes are paid, and `tick.error` names sprint points.

### W7 — `api/`: weight and points on race detail and results
Tests in `api/tests.py`:
- `test_race_detail_sprint_marker_has_weight_and_points`
- `test_race_detail_mountain_marker_has_null_weight_and_points`
- Rename `test_race_results_include_first_three_per_marker` →
  `test_race_results_include_first_five_per_marker`.
- `test_race_results_crossing_shows_points_for_scoring_rider_only`
  (a teammate behind gets `null`)
- `test_race_results_team_points_split_finish_and_sprint`
- `test_race_results_team_with_only_sprint_points_listed_with_them`
- `test_standings_total_includes_sprint_points`

### W8 — `frontend/`: types, course profile, results cards
Tests:
- `CourseProfile.test.tsx`: `shows weight and winner points for a sprint marker`;
  `mountain marker shows no weight`.
- `Race.test.tsx`: `marker results show points beside scoring riders`;
  `team points show finish/sprint split when sprints scored`;
  `no split line when a team scored no sprint points`.

Run `npm test`, `npm run lint` and `npm run build` in `frontend/`.

### W9 — `seasons/season-1.example.json`: weights and a finish sprint
No test loads the example season today. Add
`test_example_season_declares_weighted_and_finish_line_sprints` to
`schedule/tests/test_loaders.py`. It parses `seasons/season-1.example.json`
with the loader's parse function and asserts three things: a `major` marker
exists, a `minor` marker exists, and a sprint marker sits at its race's
course length.

### W10 — Docs, then archive spec and plan (see *Documentation update*).

## Execution order

1. **W1 → W2.** The data first: weight exists and can be authored. Commit
   each; the suite stays green because the default covers every existing path.
2. **W3 → W4.** Tables, then the scoring function against real crossing rows.
   W4 is where D3 lives; do not move on until
   `test_sixth_place_does_not_move_up_when_a_team_doubles` passes.
3. **W5.** The totals now include sprints. Nothing calls `score_sprints` yet,
   so no existing behaviour changes until W6.
4. **W6.** Wire the tick. From here a real race produces sprint points, and
   fanbase and sponsorship move with them.
5. **W7 → W8.** API, then SPA. W8 depends on W7's payload.
6. **W9**, then the **Verification** run, then **W10**.

One commit per work item.

## Documentation update (required, not optional)

- **`competitions/README.md`**:
  - New section *Sprint points*: `MarkerPoints`, the per-weight tables, and
    the top-5-then-best-per-team rule (D3) with the reason.
  - *Standings are computed, not stored*: totals include sprint points;
    countback counts finish positions only (D9).
  - The `points_by_team` paragraph: it now includes sprint points, so fanbase
    and sponsorship move with them.
  - *What this app owns*: add `MarkerPoints`.
  - Future work: mountain points (#17) reuse `MarkerPoints`; the retune after
    #17.
- **`racing/README.md`**, *Markers and crossings*: `RaceMarker.weight` — its
  choices and default, that it is inert on mountain markers, and that the
  engine never sees it.
- **`schedule/README.md`**: the `weight` key on season-file markers (sprint
  only, default `standard`) and the duplicated `MARKER_WEIGHTS` constant with
  its drift test.
- **`world/README.md`**, *How a tick works*: `score_sprints` after
  `score_race`, isolated in its own `try`.
- **`api/README.md`**: the new race-detail and race-results fields;
  `MARKER_PLACES_SHOWN` is 5.
- **`frontend/README.md`**: the race screen row mentions sprint weight and
  sprint points.
- **`economy/README.md`**: one line where `points_by_team` is described — it
  now includes sprint points.
- **`AGENTS.md`**, `competitions/` row: "Race points, sprint points, prize
  money and season standings…".
- **Spec and plan**: set `Status: implemented` and move both to
  `specs/archive/`.

## Verification

Unit tests prove the pieces. The end-to-end run proves the tick wires them
together and that the screens show them. From the worktree root, with the
main checkout's interpreter:

```bash
PY=/home/mario/dev/cycling-manager/.venv/bin/python
$PY scripts/dev_db.py && $PY manage.py migrate
$PY manage.py seed_user && $PY manage.py seed_teams --claim-for test@mail.com
$PY manage.py seed_trainers && $PY manage.py load_season seasons/season-1.example.json
GAME_CLOCK_CLASS=world.clocks.MockClock $PY manage.py mock_clock set 2027-03-07T15:00:00Z
GAME_CLOCK_CLASS=world.clocks.MockClock $PY manage.py tick
$PY -m pytest
```

Then check, in order:

1. **The rows.** In `manage.py shell`, `MarkerPoints.objects.filter(marker__race__name="Opening Sprint")`
   gives at most 5 rows per marker and at most one per team per marker.
   The `major` marker's winner has 10 points and the `minor` marker's has 4.
   Cross-check against `MarkerCrossing` positions ≤ 5 for the same marker:
   every team that appears there has exactly one row, from its lowest
   position. **This catches the D3 mistake**: walking down the order would
   show a `position` of 6 or more.
2. **The API.** `/api/racing/races/<id>/results/` returns 5 crossings per
   marker, `points` on the scoring crossings, and on each team
   `points == finish_points + sprint_points`.
3. **The league.** `/api/competitions/standings/` totals equal the sum of
   `finish_points + sprint_points` across that team's races. A team with
   sprint points but no top-10 finish is present.
4. **The screen.** Start the dev server (`preview_start`), log in as the demo
   account and open the Opening Sprint race. The course profile shows
   *Minor* / *Major* with winner points, the results card shows `+N` beside
   scorers, and a team that scored sprints shows the finish/sprints line.
   Take a screenshot as proof.
5. **Fanbase moved.** Tick into week 2. The demo team's `FanbaseEntry`
   (kind weekly, week 2) `points` equals its week-1 finish plus sprint total.

## Risks

| Risk | Mitigation |
|---|---|
| Implementer de-duplicates by team *before* cutting to 5, so the 6th rider scores when a team doubles (the most likely mistake) | D3 is marked load-bearing, the reference code is given in full, and `test_sixth_place_does_not_move_up_when_a_team_doubles` plus Verification step 1 both catch it |
| `standings` silently drops a team that only scored sprints | `test_team_with_only_sprint_points_appears_in_standings`; Verification step 3 |
| Sprint scoring crashes and flips a finished race to `FAILED` | D7: its own `try`; `test_sprint_scoring_failure_does_not_fail_the_race` |
| #17's mountain rows later leak into sprint totals | Every aggregate filters `marker__kind="sprint"`; `test_points_by_team_ignores_mountain_marker_points` |
| Fanbase and sponsorship shift because weekly points are now higher on sprint-heavy weeks | Accepted in the spec (sprint points feed the league total, which feeds both). Sponsorship compares against the team's own season average, so it self-normalises. Noted in `economy/README.md` |
| The 4th/5th scorers are invisible on screen | D11 raises `MARKER_PLACES_SHOWN` to 5; the renamed API test pins it |
| The loader's weight list and the model's choices drift apart | `test_loader_weights_match_race_marker_weights` and `test_sprint_table_keys_match_marker_weights` |
| Someone "fixes" the lack of backfill with a data migration | D10 says no backfill, and why |

## Open questions

None.
