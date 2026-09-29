# Mountain points — Implementation Plan

**Spec:** `specs/mountain-points.md` · **Issue:** #17 · **Status:** proposed
**Apps touched:** `racing/`, `schedule/`, `competitions/`, `world/`, `api/`, `frontend/`, `seasons/` (example data)

## Context you need

**#16 (sprint points) is merged** — PR #119, on master as of this plan's W0
pass. Every name and shape below (`RaceMarker.Weight`, migration `0008`,
`MarkerPoints`, `score_sprints`, `_marker_payload`, `MARKER_PLACES_SHOWN`,
the `sprint_by_team` split in `RaceResultsView`) was checked directly
against the merged code, not against #16's plan, and matches what is written
here exactly. W0 below is the record of that check.

**Markers (#70, `specs/archive/course-markers.md`, `racing/README.md`,
*Markers and crossings*).** `racing.RaceMarker` has a `kind` (sprint or
mountain), a `name` and a `distance`. `simulate_race` writes one
`racing.MarkerCrossing` per rider per marker, with `position` numbered
contiguously from 1. A marker placed exactly on the finish line takes its
order from the results, finishers only. The engine already contests mountain
markers: strong climbers push for the summit. **That behaviour does not
change here**, and the engine never sees a category.

**What #16 adds, and this ticket reuses:**
- `RaceMarker.weight`: a `TextChoices` field with the values `minor`,
  `standard` and `major`. It is non-null and defaults to `standard`, and it
  is **inert on mountain markers**. The season loader rejects a `weight` key
  on a mountain marker (#16 D5); that rule stays.
- `competitions.MarkerPoints`: one row per (marker, team), holding the
  scoring rider, their crossing position and the frozen points. #16 named it
  `MarkerPoints` rather than `SprintPoints` precisely so this ticket could
  write mountain rows into the same table. The kind is read from
  `marker.kind`.
- `competitions.services.score_sprints(race)`: cut to the top 5 crossings
  **first**, then keep each team's best rider (#16 D3). It is called from
  `world/services.py::_execute` inside its own `try`.
- `competitions/scoring.py`: `SPRINT_PLACES = 5`, `SPRINT_POINTS_BY_WEIGHT`
  and `sprint_points_for(weight, position)`.
- `points_by_team(week)` and `standings(season)` add the `MarkerPoints`
  totals, **filtered to `marker__kind="sprint"`**, so that this ticket's
  rows don't leak in early. This ticket removes that filter on purpose.
- API: a `_marker_payload(m)` helper that returns `weight` and `points`
  (null on mountain markers); `MARKER_PLACES_SHOWN = 5`; each crossing
  carries `points`; each team entry carries `finish_points` and
  `sprint_points`.
- SPA: `CourseProfile.tsx` shows each sprint's weight and what the winner
  gets; in `Race.tsx`, `MarkerResultsCard` shows `+N` beside riders who
  scored, and `TeamPointsTable` shows a finish/sprints line.

**Rules this work is bound by (AGENTS.md):**
- `competitions -> racing, teams, schedule, core` is allowed. `racing` never
  imports `competitions`.
- `schedule/` library code (`loaders.py`) imports nothing from `racing/`, so
  constants that must match `racing` values are duplicated there and pinned
  by a drift test in `racing/tests.py`. #16 does the same for weights.
- `race_engine/` is untouched, and the adapter is untouched.

## Goal

- A mountain marker carries a category: **HC, Cat 1, Cat 2 or Cat 3**. It is
  written in the season file and defaults to **Cat 2**.
- When a race finishes, the top 5 crossings at each mountain marker score
  from a per-category table, and each team is credited only from its
  best-placed rider among them. The rows are frozen, and a summit finish
  gets no special treatment.
- Mountain points add to the season standings total and to `points_by_team`
  (and therefore to fanbase and sponsorship). Countback is unchanged, and
  sprint and mountain points remain separately addressable everywhere.
- The course preview shows each climb's category and what the winner gets.
  The results screen shows points beside the riders who scored at mountain
  markers, and each team's race total is broken into finish, sprints and
  mountains.

## Design decisions (settled — implement these, do not substitute)

**D1 — A separate `RaceMarker.category` field, not more values on
`weight`.** Add a new `TextChoices` field, `category`, with the values `hc`,
`cat1`, `cat2` and `cat3`. It is non-null, defaults to `cat2`, and is
**inert on sprint markers**. This is exactly the mirror of how #16 made
`weight` inert on mountain markers. Why a separate field:
- `AddField` with `default="cat2"` gives every existing mountain row the
  spec's default in one step, with **no data migration**.
- The season file keeps the two vocabularies under two different keys
  (`weight` for sprints, `category` for climbs). An author cannot mix them
  up without the loader noticing.

*Rejected:* adding `hc`/`cat1`/… to `weight`'s choices. Existing mountain
rows hold `standard` (#16's default), so that would need a data migration.
It would also need a default that depends on the kind, which a column
default can't express, and a check constraint on kind and weight. That
constraint would break every test fixture and every `create_race` call that
builds a mountain marker without saying anything about weight.

**D2 — Stored values `hc`, `cat1`, `cat2`, `cat3`; displayed labels "HC",
"Cat 1", "Cat 2", "Cat 3".** The labels are the `TextChoices` labels. The
spec calls them "HC, 1st, 2nd or 3rd". "Cat 1" is the conventional way to
print that on a course profile, and the spec leaves representation to the
plan. The SPA keeps its own value→label map, the same way it capitalises
`weight`. The API sends the stored value, not the label.

**D3 — The loader key is `category`; it is allowed on mountain markers only
and defaults to `cat2`.** A `category` key on a sprint marker raises a
`SeasonFileError`. This is the mirror of #16 D5, for the same reason: data
authored now would have to be reinterpreted later. After parsing, sprint
markers get `"category": "cat2"`, matching the column default, just as #16
gives mountain markers `"weight": "standard"`.

**D4 — Explicit per-category integer tables, with the top 5 scoring, at
parity with sprints.** Add to `competitions/scoring.py`:

```python
#: How many crossing positions at a mountain marker score. Its own constant,
#: not SPRINT_PLACES: the spec defers making depth grow with category, and
#: that change must not move sprints.
MOUNTAIN_PLACES = 5

#: Mountain points by marker category, then crossing position (1-indexed).
#: Positions beyond MOUNTAIN_PLACES score nothing. Frozen per marker at award
#: time — see specs/mountain-points.md. Keys match RaceMarker.Category.
MOUNTAIN_POINTS_BY_CATEGORY: dict[str, dict[int, int]] = {
    "cat3": {1: 4,  2: 3, 3: 2, 4: 1, 5: 1},
    "cat2": {1: 6,  2: 4, 3: 3, 4: 2, 5: 1},
    "cat1": {1: 8,  2: 6, 3: 4, 4: 2, 5: 1},
    "hc":   {1: 10, 2: 7, 3: 5, 4: 3, 5: 2},
}
```

Three of the four rows equal #16's sprint rows: Cat 3 = minor, Cat 2 =
standard, HC = major. This is **deliberate parity**, so that neither
specialist is structurally favoured before the retune the spec defers.
A test pins "an HC win pays the same as a major sprint win". Changing that
belongs to the retune ticket, not to anyone tidying up here. The spec's
ceiling (the heaviest category's win stays a fraction of a race win) is
enforced the same way #16 does it: an HC win is at most half of
`POINTS_BY_POSITION[1]`.

**D5 — Load-bearing: one private scorer shared by both kinds, with an
idempotency guard *filtered by kind*.** #16's `score_sprints` returns early
if **any** `MarkerPoints` row exists for the race. Once mountain rows exist,
that guard is wrong. Whichever of `score_sprints` and `score_mountains` runs
second would see the other's rows, return them, and score nothing — and no
error would be raised. Refactor `score_sprints`' body into
`_score_markers(race, kind, places, points_for)`. The guard there filters on
`marker__kind=kind`. `score_sprints` and the new `score_mountains` become
three-line wrappers. Do **not** write `score_mountains` as a copy with its
own unfiltered guard. See *competitions/services.py* for the code.

*Rejected:* merging both kinds into one public `score_markers(race)` called
once from `world/`. It is tidier, but it renames #16's function, rewrites
#16's tests and its `world/` wiring, and puts a sprint failure and a
mountain failure in the same `try`. Two wrappers keep #16's surface
unchanged.

**D6 — `score_mountains` is called from `_execute` in its own `try`,
straight after `score_sprints`.** It uses the same isolation as #16 D7: a
failure is recorded on `tick.error` as `race {id} mountain points:` and
never changes `race.status`. Because of D5 the call order doesn't matter,
but put mountains after sprints so the tick reads in the same order as the
results screen.

**D7 — Every aggregate now counts both kinds, and keeps them separately
addressable.**
- `points_by_team(week)`: **remove** #16's `marker__kind="sprint"` filter.
  Every `MarkerPoints` row is now a league point. #16's test
  `test_points_by_team_ignores_mountain_marker_points` asserts the opposite
  and is **deleted**, replaced by `test_points_by_team_adds_mountain_points`.
  That test existed only to guard the gap before this ticket landed.
- `standings(season)`: aggregate `MarkerPoints` grouped by
  `("team_id", "marker__kind")`. Add both kinds into `points`, record
  `entry["sprint_points"]` and a new `entry["mountain_points"]` (0 when
  there are none), and create entries for teams that scored only on
  climbs. As in #16, the API does not expose these two fields.
- **Countback is unchanged.** Being first over a summit is not a 1st place
  for tie-breaking, for the same reason a sprint win isn't (#16 D9).

**D8 — The results payload splits team points by kind; it never sums
`MarkerPoints` blindly into `sprint_points`.** If #16 built `sprint_by_team`
from every `MarkerPoints` row of the race without filtering on kind, mountain
points would silently land in `sprint_points`. Build `{(team_id, kind): sum}`
once, then read `sprint_points` and `mountain_points` from it.
`points = finish_points + sprint_points + mountain_points`.

**D9 — A summit finish is not a special case, and there is no code for it.**
A mountain marker at the course length is scored by the same function from
the same crossing rows. #70 already guarantees that those rows come from
the finishing order, finishers only. A test proves this (W4), so nobody
"adds" a doubling later believing it was forgotten.

**D10 — No backfill, and the engine is untouched.** Mountain markers in races
finished before this ships stay unscored (the spec's frozen-at-scoring rule,
#16 D10). `category` is not passed through `racing/adapters.py`: it changes
what a crossing is worth, not how a climb is ridden.

**D11 — A crossing that crossed and then abandoned still scores; a teamless
rider is skipped; team attribution uses `rider.team_id` at scoring time.**
All three come free with `_score_markers` and are exactly #16's rules (D8,
D12). They are restated here because W4 tests them for the mountain kind.

## Data model

### `racing/models.py` — `RaceMarker.category` (new field)

```python
class Category(models.TextChoices):
    HC = "hc", "HC"
    CAT1 = "cat1", "Cat 1"
    CAT2 = "cat2", "Cat 2"
    CAT3 = "cat3", "Cat 3"

category = models.CharField(
    max_length=4, choices=Category.choices, default=Category.CAT2,
    help_text="A mountain marker's climb category. Inert on sprint markers.",
)
```

Not null, not blank, no index, no constraint. Also update `weight`'s
`help_text` to drop "(#17 decides theirs)", replacing it with "Inert on
mountain markers.".

Migration **new: `racing/migrations/0009_racemarker_category.py`** (an
`AddField`; existing rows get `cat2`). It depends on #16's
`0008_racemarker_weight`. Confirm the number in W0: if master has gained
another racing migration in the meantime, take the next free number.

`competitions.MarkerPoints` **does not change.** Only its docstring's first
line changes, from "one sprint marker" to "one sprint or mountain marker".

## `racing/services.py`, `racing/admin.py`

- `create_race`: pass
  `category=marker.get("category", RaceMarker.Category.CAT2)` through to
  `RaceMarker.objects.create`, and update the docstring's dict shape to
  `{"kind", "name", "distance", "weight"?, "category"?}`.
- The admin `RaceMarkerInline` picks the field up automatically.

## `schedule/loaders.py`

- `_KNOWN_MARKER_KEYS` gains `"category"`.
- Add a new module constant, `MARKER_CATEGORIES = ("hc", "cat1", "cat2", "cat3")`,
  next to #16's `MARKER_WEIGHTS`. It is duplicated deliberately (the loader
  may not import `racing/`).
- In `_parse_markers`, after #16's weight block:
  - if `category` is present and `kind == "sprint"`, raise
    `SeasonFileError(f"{at}.category is only allowed on mountain markers")`;
  - if `category` is absent or `None`, use `"cat2"`;
  - if it is not in `MARKER_CATEGORIES`, raise
    `SeasonFileError(f"{at}.category must be one of hc, cat1, cat2, cat3, got {category!r}")`;
  - add `"category": category` to the appended dict.

## `competitions/scoring.py`

Add `MOUNTAIN_PLACES` and `MOUNTAIN_POINTS_BY_CATEGORY` (D4), plus:

```python
def mountain_points_for(category: str, position: int) -> int:
    """What a crossing position at a climb of this category is worth. Zero
    outside the table."""
    return MOUNTAIN_POINTS_BY_CATEGORY.get(category, {}).get(position, 0)
```

## `competitions/services.py`

This is the hard part. Replace `score_sprints` with the following, and
adjust the imports (`MOUNTAIN_PLACES`, `mountain_points_for`, `Callable`):

```python
def _score_markers(
    race: Race,
    kind: str,
    places: int,
    points_for: Callable[[RaceMarker, int], int],
) -> list[MarkerPoints]:
    """Award one kind of marker points for one finished race: per marker of
    `kind`, each team's best-placed rider among the top `places` crossings.
    Idempotent per kind: a kind already scored for this race returns its
    existing rows.

    Raises ValueError if the race is not FINISHED.
    """
    if race.status != Race.Status.FINISHED:
        raise ValueError(f"{race} is not finished; nothing to score")

    # Filter the guard by kind (D5). Unfiltered, whichever of sprints and
    # mountains ran second would find the other's rows and score nothing.
    existing = list(MarkerPoints.objects.filter(marker__race=race, marker__kind=kind))
    if existing:
        return existing

    to_create = []
    for marker in race.markers.filter(kind=kind):
        # Cut to the top `places` FIRST, then keep each team's best — #16 D3.
        crossings = (
            MarkerCrossing.objects
            .filter(marker=marker, position__lte=places)
            .order_by("position")
            .values_list("rider_id", "rider__team_id", "position")
        )
        best: dict[int, tuple[int, int]] = {}
        for rider_id, team_id, position in crossings:
            if team_id is None or team_id in best:
                continue
            best[team_id] = (rider_id, position)
        to_create += [
            MarkerPoints(marker=marker, team_id=team_id, rider_id=rider_id,
                         position=position, points=points_for(marker, position))
            for team_id, (rider_id, position) in best.items()
        ]
    return MarkerPoints.objects.bulk_create(to_create, ignore_conflicts=True)


def score_sprints(race: Race) -> list[MarkerPoints]:
    """Sprint points for one finished race. See _score_markers."""
    return _score_markers(race, RaceMarker.Kind.SPRINT, SPRINT_PLACES,
                          lambda m, p: sprint_points_for(m.weight, p))


def score_mountains(race: Race) -> list[MarkerPoints]:
    """Mountain points for one finished race. See _score_markers."""
    return _score_markers(race, RaceMarker.Kind.MOUNTAIN, MOUNTAIN_PLACES,
                          lambda m, p: mountain_points_for(m.category, p))
```

Keep #16's long comment explaining why the cut comes before the per-team
de-duplication. Move it into `_score_markers` rather than dropping it.

`points_by_team(week)`: remove the `marker__kind=RaceMarker.Kind.SPRINT`
filter from #16's `MarkerPoints` aggregate (D7). Nothing else changes.

`standings(season)`: change #16's sprint aggregate to

```python
marker_totals = (
    MarkerPoints.objects
    .filter(marker__race__week__season=season)
    .values("team_id", "marker__kind")
    .annotate(total=Sum("points"))
)
```

For each row, add `total` into the team's `points`, and into
`entry["sprint_points"]` or `entry["mountain_points"]` according to the
kind. Initialise both to 0 on **every** entry, including the ones created
for teams missing from `by_team`, which #16 fetches with
`Team.objects.in_bulk`. `_countback_key` is unchanged.

## `world/services.py`

Import `score_mountains` next to `score_sprints`. In `_execute`, straight
after #16's sprint `try` and before the prize `try`:

```python
try:
    score_mountains(race)
except Exception:
    tick.error += f"race {race_id} mountain points:\n{traceback.format_exc()}\n"
```

It comes after the `continue` for failed races, and it never touches
`race.status`.

## `api/views.py`, `api/serializers.py`

- `_marker_payload(m)` (from #16): add `category`, set to `m.category` for
  mountain markers and `None` for sprint markers. For a mountain marker,
  fill `points` with that category's table in position order
  (`[10, 7, 5, 3, 2]` for HC), where #16 currently returns `None`.
  `RaceMarkerSerializer` gains `category = CharField(allow_null=True)`.
- `RaceResultsView`:
  - Crossing `points`: #16 builds `scored_crossing` from **all** of the
    race's `MarkerPoints`, so mountain crossings pick up their points with
    no change. Check this in W0. If #16 filtered it to sprints, remove the
    filter.
  - Team split (D8): build
    `marker_by_team_kind = {(team_id, kind): total}` from
    `MarkerPoints.objects.filter(marker__race=race).values("team_id", "marker__kind").annotate(total=Sum("points"))`.
    Each points entry gains `mountain_points`. `sprint_points` reads from
    the same dict. `points` is the sum of all three. In the no-finish group,
    order by `sprint_points + mountain_points` descending, then by name.
  - `RaceResultPointsEntrySerializer` gains
    `mountain_points = IntegerField()`.
- `StandingsView`: no change.

## `frontend/`

- `src/api.ts`: `RaceMarker` gains
  `category: 'hc' | 'cat1' | 'cat2' | 'cat3' | null`, and the comment on
  `points` changes to say it is set for both kinds. `RaceResultPointsEntry`
  gains `mountain_points: number`.
- `src/components/CourseProfile.tsx`: add
  `const CATEGORY_LABEL = { hc: 'HC', cat1: 'Cat 1', cat2: 'Cat 2', cat3: 'Cat 3' }`,
  exported, because `Race.tsx` reuses it. Mountain markers in the list
  render as
  `Mountain · <name> · km <x> · <Cat label> · <points[0]> pts to the winner`,
  the same pattern #16 uses for sprints.
- `src/screens/Race.tsx`:
  - `MarkerResultsCard`: for a mountain marker, show the category label
    after the name. The `+N` beside scorers is already driven by
    `crossing.points` and needs no change.
  - `TeamPointsTable`: show the muted line when
    `sprint_points + mountain_points > 0`. It reads `finish <n>`, then
    `· sprints <n>` only if greater than 0, then `· mountains <n>` only if
    greater than 0. The bold total is unchanged.
- `League.tsx` and `Dashboard.tsx` don't change.

## `seasons/season-1.example.json`

- Race 11, "Summit Finish": set `First Climb` to `"category": "cat1"` and
  `Final Top` to `"category": "hc"`. `Final Top` sits at 100,000 m, which is
  the course length, so this is the summit finish.
- Race 2, "Mountain Road": leave `Hilltop` without a category, to show the
  default (Cat 2). This race also has a sprint, so it demonstrates the
  three-way split.

## Work items

### W0 — Rebase onto master; confirmed done ✅
`git rebase origin/master` on `mountain-points` was clean (the branch held
only the spec and this plan). Every name and shape this plan assumes was then
checked directly against the merged `sprint-points` code (PR #119) and
matches exactly:
- `RaceMarker.Weight`, `racing/migrations/0008_racemarker_weight.py` ✅
- `competitions.scoring.SPRINT_PLACES`, `SPRINT_POINTS_BY_WEIGHT`,
  `sprint_points_for` ✅
- `competitions.services.score_sprints` — guard is
  `MarkerPoints.objects.filter(marker__race=race)`, **unfiltered by kind**,
  confirming D5's refactor is necessary, not precautionary ✅
- `points_by_team` and `standings` both filter their `MarkerPoints`
  aggregate to `marker__kind=RaceMarker.Kind.SPRINT` — D7's removal of that
  filter (`points_by_team`) and its per-kind split (`standings`) apply
  exactly as written ✅
- `api.views._marker_payload`, `MARKER_PLACES_SHOWN = SPRINT_PLACES` (i.e.
  5) ✅
- `RaceResultsView`: `scored_crossing` (crossing → points) is built from
  **all** of the race's `MarkerPoints`, unfiltered — mountain crossings will
  carry their points with no change once mountain rows exist, matching D8.
  `sprint_by_team` is already filtered to `marker__kind=SPRINT` — add a
  parallel `mountain_by_team` dict the same way, per D8, rather than
  building one unfiltered dict and splitting it.
- `RaceResultPointsEntrySerializer` has `finish_points`, `sprint_points`,
  `points`, `prize` — add `mountain_points` alongside `sprint_points`.
- `RaceMarkerSerializer` has `weight` and `points`, both nullable — add
  `category`, nullable the same way.

No code difference from what this plan assumed anywhere. No commit for this
step.

### W1 — `racing/`: `RaceMarker.category`, migration 0009, `create_race` ✅
Tests in `racing/tests.py`:
- `test_marker_category_defaults_to_cat2`
- `test_create_race_stores_marker_category`
- `test_create_race_without_category_gives_cat2`

### W2 — `schedule/loaders.py`: parse `category` ✅
Tests in `schedule/tests/test_loaders.py`:
- `test_mountain_marker_category_is_parsed`
- `test_missing_category_defaults_to_cat2`
- `test_rejects_unknown_category`
- `test_rejects_category_on_sprint_marker`

Also add `test_loader_categories_match_race_marker_categories` to
`racing/tests.py`, next to #16's weights drift test, and
`test_load_season_stores_marker_category` to
`schedule/tests/test_load_season.py`.

### W3 — `competitions/scoring.py`: the mountain tables ✅
Tests in `competitions/tests/test_scoring.py`:
- `test_every_category_has_exactly_five_scoring_places`
- `test_mountain_points_decline_down_the_order`
- `test_harder_categories_never_pay_less` (per position:
  cat3 ≤ cat2 ≤ cat1 ≤ hc)
- `test_hc_win_is_at_most_half_a_race_win`
- `test_hc_win_equals_major_sprint_win` (the parity pin from D4)
- `test_mountain_position_outside_table_scores_zero`
- `test_mountain_table_keys_match_marker_categories`

### W4 — `competitions/services.py`: `_score_markers`, `score_mountains` ✅
Refactor as shown. **#16's `test_sprints.py` must pass unchanged**; that
alone proves the refactor preserved sprint behaviour.

New file, **`competitions/tests/test_mountains.py`** (`make_marker` in
`conftest.py` gains a `category` keyword, defaulting to `cat2`):
- `test_top_five_at_a_climb_score_by_category`
- `test_team_scores_only_its_best_rider_at_a_climb`
- `test_sixth_place_does_not_move_up_when_a_team_doubles_on_a_climb`
- `test_sprint_markers_score_nothing_as_mountains`
- `test_summit_finish_scores_like_any_climb` (a mountain marker at course
  length, crossings as #70 writes them: normal points, nothing doubled; D9)
- `test_rider_who_crossed_a_climb_then_abandoned_keeps_points`
- `test_score_mountains_is_idempotent`
- `test_score_mountains_rejects_unfinished_race`
- `test_mountain_points_frozen_when_table_changes`

Add to `competitions/tests/test_sprints.py`, since these are the **D5
load-bearing** tests:
- `test_sprints_still_score_after_mountains_scored`: a race with one
  sprint marker and one mountain marker. Call `score_mountains`, then
  `score_sprints`. Both kinds have rows.
- `test_mountains_still_score_after_sprints_scored`: the same, in the
  other order.

### W5 — `competitions/services.py`: `points_by_team` and `standings` count mountains ✅
In `competitions/tests/test_services.py`: **delete**
`test_points_by_team_ignores_mountain_marker_points` (D7) and add
- `test_points_by_team_adds_mountain_points`
- `test_points_by_team_adds_sprint_and_mountain_points_together`

In `test_standings.py`:
- `test_standings_include_mountain_points_in_total`
- `test_standings_keep_sprint_and_mountain_points_separate` (both entry
  fields hold the right totals)
- `test_team_with_only_mountain_points_appears_in_standings`
- `test_mountain_points_do_not_count_in_countback`

### W6 — `world/services.py`: call `score_mountains` ✅
In `world/tests/test_tick.py`:
- `test_tick_scores_mountain_points_for_a_finished_race`
- `test_mountain_scoring_failure_does_not_fail_the_race`: monkeypatch
  `world.services.score_mountains` to raise. The race stays `FINISHED`,
  sprint points and prizes still land, and `tick.error` names mountain
  points.

### W7 — `api/`: category and mountain points on race detail and results ✅
In `api/tests.py`:
- `test_race_detail_mountain_marker_has_category_and_points`
- `test_race_detail_sprint_marker_has_null_category`
- `test_race_results_mountain_crossing_shows_points_for_scoring_rider_only`
- `test_race_results_team_points_split_finish_sprint_and_mountain`
  (`points == finish_points + sprint_points + mountain_points`, and the
  mountain total is not counted in `sprint_points`, per D8)
- `test_race_results_team_with_only_mountain_points_listed_with_them`
- `test_standings_total_includes_mountain_points`

Update #16's test
`test_race_detail_mountain_marker_has_null_weight_and_points`: `points` is
no longer null for a mountain marker. Rename it to
`test_race_detail_mountain_marker_has_null_weight`.

### W8 — `frontend/`: types, course profile, results cards ✅
- `CourseProfile.test.tsx`: `shows category and winner points for a mountain marker`.
  Update #16's `mountain marker shows no weight`, which should still hold
  for weight, so it may need no change at all; confirm this.
- `Race.test.tsx`:
  `marker results show category for a mountain marker`,
  `team points line includes mountains when scored`,
  `team points line omits sprints when only mountains scored`.

Run `npm test`, `npm run lint` and `npm run build` in `frontend/`.

### W9 — `seasons/season-1.example.json`: categories and a summit finish
Add
`test_example_season_declares_categorised_climbs_and_a_summit_finish` to
`schedule/tests/test_loaders.py`. It asserts that an `hc` marker exists,
that a `cat1` marker exists, and that a mountain marker sits at its race's
course length. Put it next to #16's example-season test.

### W10 — Docs, then archive the spec and plan (see *Documentation update*).

## Execution order

1. **W0.** Nothing starts until #16 is on master and the names are
   confirmed.
2. **W1 → W2.** Category exists and can be written in the season file.
   Commit each. The suite stays green because the default covers every
   existing path.
3. **W3 → W4.** The tables, then the refactor. At W4, run #16's
   `test_sprints.py` **before** writing any mountain test: if it is still
   green, the refactor is behaviour-preserving. Do not move on until both
   D5 order tests pass.
4. **W5.** The totals now include mountains. Nothing calls
   `score_mountains` yet, so live behaviour is unchanged until W6.
5. **W6.** Wire the tick. From here on, real races produce mountain points,
   and fanbase and sponsorship move with them.
6. **W7 → W8.** The API, then the SPA.
7. **W9**, then the **Verification** run, then **W10**.

Make one commit per work item.

## Documentation update (required, not optional)

- **`competitions/README.md`**:
  - Rename #16's *Sprint points* section to *Marker points (sprint and
    mountain)*. Cover the shared `_score_markers`, the per-kind
    idempotency guard (D5) and why it exists, the two tables and their
    deliberate parity (D4), and `MOUNTAIN_PLACES` being separate from
    `SPRINT_PLACES`.
  - In *Standings are computed, not stored*, say that totals include
    mountain points, that `sprint_points` and `mountain_points` stay
    separate on each entry, and that countback is unchanged.
  - Add to the `points_by_team` paragraph that mountain points count too.
  - In Future work, remove "mountain points (#17)" and keep the retune
    note, which now covers all three sources and category-scaled depth.
- **`racing/README.md`**, *Markers and crossings*: describe
  `RaceMarker.category` — its choices and default, that it is inert on
  sprint markers, and that the engine never sees it.
- **`schedule/README.md`**: document the `category` key on season-file
  markers (mountain only, default `cat2`) and `MARKER_CATEGORIES` with its
  drift test.
- **`world/README.md`**, *How a tick works*: `score_mountains` runs after
  `score_sprints`, in its own `try`.
- **`api/README.md`**: `category` on markers, `points` now set for
  mountain markers, and `mountain_points` on results entries.
- **`frontend/README.md`**: the race screen row mentions climb categories
  and mountain points.
- **`economy/README.md`**: extend #16's line so it says `points_by_team`
  includes sprint **and mountain** points.
- **`AGENTS.md`**, the `competitions/` row: "Race points, sprint and
  mountain points, prize money and season standings…".
- **Spec and plan**: set `Status: implemented` and move both to
  `specs/archive/`.

## Verification

From the worktree root, using the main checkout's interpreter:

```bash
PY=/home/mario/dev/cycling-manager/.venv/bin/python
$PY scripts/dev_db.py && $PY manage.py migrate
$PY manage.py seed_user && $PY manage.py seed_teams --claim-for test@mail.com
$PY manage.py seed_trainers && $PY manage.py load_season seasons/season-1.example.json
$PY -m pytest
```

Then move the mock clock past "Mountain Road" (race 2) and, later, past
"Summit Finish" (race 11). Read each race's `starts_at` in
`manage.py shell` (`Race.objects.get(name="Mountain Road").starts_at`),
then run
`GAME_CLOCK_CLASS=world.clocks.MockClock $PY manage.py mock_clock set <just after it>`
followed by `... manage.py tick`. Tick again if the race is still
`SCHEDULED`.

Check, in order:

1. **Both kinds scored in the same race.** For Mountain Road,
   `MarkerPoints.objects.filter(marker__race__name="Mountain Road")` should
   have rows for **both** `Hilltop` (mountain) and `Valley Sprint`
   (sprint). **This catches the D5 mistake.** An unfiltered guard leaves
   only one kind's rows, with nothing on `tick.error`, so an empty kind here
   is the failure, not a quiet race. `Hilltop`'s winner has 6 points (Cat 2
   by default).
2. **Summit finish.** For Summit Finish, `Final Top`'s winner has 10 points
   (HC) and `First Climb`'s has 8 (Cat 1). `Final Top`'s top-5 crossings
   are the race's top finishers, in finishing order.
3. **API.** On `/api/racing/races/<Mountain Road id>/results/`, every team
   satisfies
   `points == finish_points + sprint_points + mountain_points`. A team that
   scored only on Hilltop has `sprint_points == 0` (**D8**).
   `/api/racing/races/<id>/` shows `category: "cat2"` on Hilltop and
   `category: null` on Valley Sprint.
4. **League.** `/api/competitions/standings/` totals equal the sum of
   finish, sprint and mountain points across each team's races.
5. **Screen.** Start the dev server with `preview_start`, log in as the demo
   account and open Summit Finish. The course profile should list
   *HC · 10 pts to the winner* and *Cat 1 · 8 pts to the winner*. The
   results card should show `+N` beside mountain scorers, and a scoring
   team should show a `finish … · mountains …` line. Take a screenshot as
   proof.

## Risks

| Risk | Mitigation |
|---|---|
| `score_mountains` is written as a copy of `score_sprints` with its unfiltered guard, so whichever kind is scored second silently scores nothing (the most likely mistake) | D5 is marked load-bearing and the reference code is given; the two order tests in W4; Verification step 1 checks for both kinds in one race |
| Mountain points leak into `sprint_points` on the results payload | D8; `test_race_results_team_points_split_finish_sprint_and_mountain`; Verification step 3 |
| #16 merges in a different shape from its plan and this plan's names don't match | W0 reconciles them before any code; the rule is that the code wins |
| An existing sprint behaviour changes during the refactor | #16's `test_sprints.py` must pass unchanged at W4 before any new test is written |
| Someone "restores" #16's mountain-exclusion test, believing it is a regression | D7 says it is deleted on purpose, and why; the README records that mountains now count |
| A later tidy-up adds category values to `weight` "to have one field" | D1 records the rejected alternative and its cost |
| A later tidy-up breaks sprint/mountain parity without realising it was intended | `test_hc_win_equals_major_sprint_win` fails and points to D4; changing it belongs to the retune ticket |
| Fanbase and sponsorship shift on climb-heavy weeks | Accepted in the spec, as for sprints. Sponsorship compares against the team's own season average, so it self-normalises |
| The loader's category list and the model's choices drift apart | `test_loader_categories_match_race_marker_categories`, `test_mountain_table_keys_match_marker_categories` |

## Open questions

None. The only prerequisite is #16 merging, which W0 covers.
