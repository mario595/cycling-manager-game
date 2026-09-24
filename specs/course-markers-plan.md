# Course markers — Implementation Plan

**Spec:** `specs/course-markers.md` · **Issue:** #70 · **Status:** proposed
**Apps touched:** `race_engine/`, `racing/`, `schedule/`, `api/`, `frontend/`

## Context you need

A race today is a `racing.models.Race` row whose `course` is a JSON list of
`{length, gradient}` segments (meters, percent). `schedule/`'s `load_season`
command creates races from a hand-edited season file
(`seasons/season-1.example.json`); `world/`'s tick calls
`racing.services.simulate_race`, which converts the rows to engine dataclasses
through `racing/adapters.py`, runs `race_engine.models.run_race`, and writes a
`RaceResult` per rider plus a brotli log file.

The engine (`race_engine/models.py`) is a per-second tick loop. Each tick,
`RaceState._decide_actions` decides whether a rider starts a *surge* (a
20-tick burst above cruise) by a first-match rule chain: finish sprint (last
1000 m, everyone), climb attack (last 25%, steep, `climb >= 75`), bridge to
a break (support riders, last 25%). **Nothing happens mid-race before the
last 25%** — which is why a marker placed there would otherwise be won by
whoever happens to be pulling the pack. Read `race_engine/README.md`,
*Tactics: race phases & surge decisions*, before W2.

The race screen (`frontend/src/screens/Race.tsx`) draws the course with
`frontend/src/components/CourseProfile.tsx`, which wraps `race_player`'s
`CourseChart`. `CourseChart` already takes an `overlay` render prop that
draws extra SVG using the chart's own scale — markers use it; `race_player/`
is not modified.

Repo rules this work is bound by (all in `AGENTS.md`):

- **Only `racing/adapters.py` imports `race_engine`.** `race_engine/` never
  imports Django.
- **`schedule/` never imports `racing/`** in library code. `load_season`'s
  `handle()` may, and already injects a `create_race` callable into
  `schedule.loaders.create_races` — see `schedule/README.md`, *What
  `schedule/` may import*.
- **Engine changes are validated with `race_engine/audit.py`** against the
  six bundled courses (`race_engine/README.md`, *Regression audit*).
- Tests are pytest (`.venv/bin/python -m pytest`) and vitest (`frontend/`).

## Goal

1. A season file's race may declare `markers`: `{kind, name, distance}`,
   `kind` ∈ `sprint`/`mountain`, `distance` in meters from the start.
2. Markers are stored as rows, one per marker per race, and fed to the engine.
3. The engine makes specialists contest a marker (a sprinter kicks for a
   sprint marker, a climber surges for a summit) at any point in the race,
   and records every rider's crossing of every marker, strictly ordered.
4. `simulate_race` stores every crossing, in order, per marker.
5. The race screen shows the markers on the course profile before the race,
   and the first three riders across each marker after it.
6. A race with no markers simulates **exactly** as it does today.

## Design decisions (settled — implement these, do not substitute)

**D1. Markers are rows (`RaceMarker`), not JSON on `Race`.** Crossings need
something to point at, and #17 will add a weight/category column to the
marker — a migration on a model, not a reshaped JSON blob. **Do not** put
markers inside `Race.course`: that field is a bare segment list read by
`course_training_attribute`, the API, the frontend and the engine adapter,
and changing its shape breaks all of them for no gain.

**D2. Crossings are rows (`MarkerCrossing`), not log events.** The issue
suggested an "event record" in the log. Rejected: the log is the race
player's input and nothing else reads it (`racing/README.md`); #16/#17/#18
need to *query* crossings, which means database rows, the same reason
`RaceResult` is a table and not a log line. **The log format does not change
in this ticket** — no header key, no version bump. Showing markers in the
player is out of scope (spec) and will add its own header data.

**D3. The engine records a crossing time per rider, not an ordered list.**
`RiderState.marker_times: dict[int, float]` — marker index → interpolated
race second of the crossing. This rides out of the engine on the
`RiderState`s `run_race` already returns, so **`run_race`'s signature and
return value do not change** (eight call sites, including tests, unpack its
3-tuple). The index is the marker's position in `Course.markers`.

**D4. Crossing time is interpolated inside the tick.** Load-bearing: several
riders routinely cross a marker in the same one-second tick, and recording
the tick number alone would order them by the engine's rider list (rider pk
in the Django path) — a manufactured result. For a rider who moved from
`prev` to `new` this tick at `speed` m/s, crossing `d` where
`prev < d <= new`, the time is `current_time + (d - prev) / speed`. The
remaining exact ties (same `prev`, same `speed`) are broken by the stable sort
in `simulate_race`, which is deterministic and practically never hit.

**D5. A marker exactly at the finish line takes its order from the
results.** Spec, In scope 5: it must never contradict the finish order.
`RaceResult` orders finishers by the integer `finish_time` and breaks
same-second ties by the engine's rider order, so an interpolated marker time
*would* disagree with it in a bunch sprint. `simulate_race` therefore builds
a finish-line marker's crossings from the same `ordered` list it writes
`RaceResult` from (finishers only, `crossed_at = finish_time`). **Do not**
"fix" this by changing how finishes are ordered — that changes existing race
results and the audit baseline, and is not this ticket.

**D6. Contesting is a new rule 2 in `_decide_actions`, between the finish
sprint and the climb attack.** Rule text:

- A rider considers the **nearest marker ahead of them that they have not
  already decided on**, excluding markers at the finish line (rule 1 already
  owns the last 1000 m).
- **Sprint marker:** within `MARKER_SPRINT_WINDOW` (300 m) and
  `sprint >= MARKER_MIN_SPRINT` (75). The effort is a `sprinting` surge — its
  boost sized by the `sprint` attribute exactly like the finish kick — but of
  `SURGE_DURATION` (20 ticks), not the 40-tick finish kick.
- **Mountain marker:** within `MARKER_CLIMB_WINDOW` (150 m) and
  `climb >= MARKER_MIN_CLIMB` (75). A normal surge (`SURGE_SPEED_BOOST`).
- Gated by `energy >= MARKER_MIN_ENERGY` (60), deliberately higher than the
  30 an attack needs: only a rider with plenty in reserve spends it on a
  marker, which is what keeps the finale intact.
- **Not phase-gated and not terrain-gated.** That is the point of the rule —
  it is the one effort allowed in the early race. A mountain marker on flat
  ground is contested like any other (spec: placement is the author's call).
- **Role-blind.** Leaders contest too, like the finish sprint and the climb
  attack (spec, *Decisions taken*; manager control is #38).
- **Decided once per marker per rider.** Entering the window adds the marker
  to `RiderState.contested` whether or not the energy gate passes — a rider
  who rolls through does not re-try every tick as energy trickles back.

The windows are sized so the 20-tick effort ends at or just past the marker
(≈17 m/s × 20 ≈ 340 m for a sprint kick; ≈7 m/s × 20 ≈ 140 m climbing).
The four constants live in `formulas.py` beside the other surge constants
and are **starting values**, calibrated in W4.

**D7. No markers ⇒ no change, byte for byte.** The contest rule and the
crossing detection are both guarded by `if self.course.markers:` and neither
draws from any RNG. The audit of the six bundled courses must produce
identical output before and after this work — that is the proof the spec's
"the same kind of rider still wins" holds for every existing race, and it is
checked twice (after W2 and in *Verification*).

**D8. Marker validation lives in three places, deliberately.** The engine
(`Course.__post_init__`, so `create_initial_state`, `run_race` and the audit
all get it), the season loader (the error an admin actually reads), and
`RaceMarker.clean()` (the admin path, mirroring `Race.clean()`). This is the
same duplication `schedule/README.md`, *Why the course is validated twice*,
defends: `schedule/` cannot import the engine or `racing/`. **Do not** "fix"
it with an import. Rules everywhere: `kind` ∈ {sprint, mountain}; `name`
non-empty, ≤ 100 characters; `0 < distance <= course length`. Two markers may
share a distance; names may repeat.

**D9. One ordering of markers, threaded through.** Marker index `i` in the
engine must mean the same `RaceMarker` in `simulate_race`. `simulate_race`
fetches `list(race.markers.order_by("distance", "pk"))` **once** and passes
that same list to `to_engine_course` and to the crossing writer. **Do not**
let `to_engine_course` run its own query — two queries are two orderings the
day someone changes one of them.

**D10. Races with markers are created by `racing.services.create_race`.**
`load_season` injects it in place of `Race.objects.create`; it creates the
`Race` and its `RaceMarker` rows in one transaction, one `create()` per
marker so `save()` → `clean()` runs. `schedule/` still imports nothing from
`racing/`.

**D11. The API returns the first three crossings per marker.**
`MARKER_PLACES_SHOWN = 3` in `api/views.py`. The full order stays in the
database for #16/#17; a 64-rider field over ten markers is 640 rows nobody
reads on this screen.

## Data model

`racing/models.py`, migration **`racing/migrations/0007_racemarker_markercrossing.py`** (new).

### `RaceMarker(models.Model)` (new)

Plain `models.Model`, not `TimeStampedModel` — written as a set with its
race and never amended, the same reasoning `RaceSquadRider` records.

| Field | Type | Null/blank | Default | Notes |
|---|---|---|---|---|
| `race` | `ForeignKey(Race, on_delete=CASCADE, related_name="markers")` | no | — | Deleting a race deletes its markers. |
| `kind` | `CharField(max_length=10, choices=Kind.choices)` | no | — | `class Kind(models.TextChoices)`: `SPRINT = "sprint", "Sprint"`, `MOUNTAIN = "mountain", "Mountain"`, nested in the model. |
| `name` | `CharField(max_length=100)` | no | — | Non-empty enforced in `clean()`. |
| `distance` | `FloatField()` | no | — | Meters from the start, same unit as `Race.course` lengths. |

`Meta.ordering = ["distance", "pk"]`. No unique constraint (D8). `clean()`
checks `0 < distance <= sum(s["length"] for s in race.course)` and a
non-blank name; `save()` calls `self.clean()` first, as `Race.save()` does.

### `MarkerCrossing(models.Model)` (new)

| Field | Type | Null/blank | Default | Notes |
|---|---|---|---|---|
| `marker` | `ForeignKey(RaceMarker, on_delete=CASCADE, related_name="crossings")` | no | — | |
| `rider` | `ForeignKey("riders.Rider", on_delete=CASCADE, related_name="marker_crossings")` | no | — | String reference, as `RaceResult.rider`. |
| `position` | `PositiveSmallIntegerField()` | no | — | 1 = first across. Contiguous from 1. |
| `crossed_at` | `FloatField()` | no | — | Race seconds, interpolated (D4); `finish_time` for a finish-line marker (D5). |

`Meta.ordering = ["marker", "position"]`. Constraints:
`UniqueConstraint(["marker", "rider"], name="unique_crossing_per_rider_per_marker")`,
`UniqueConstraint(["marker", "position"], name="unique_position_per_marker")`.

A rider appears only for markers they actually reached. A rider cut by the
time limit keeps the crossings they made before it.

## race_engine/models.py

```python
class MarkerKind(str, Enum):
    SPRINT = "sprint"
    MOUNTAIN = "mountain"

@dataclass(frozen=True)
class Marker:
    kind: MarkerKind
    distance: float  # meters from the start
    name: str

@dataclass
class Course:
    segments: list[Segment]
    markers: list[Marker] = field(default_factory=list)
    def __post_init__(self) -> None: ...  # raises RaceSetupError (D8)
```

`RiderState` gains:

```python
marker_times: dict[int, float] = field(default_factory=dict)  # marker index -> race second
contested: set[int] = field(default_factory=set)              # marker indices already decided on
```

Neither is written to the log.

**Crossing detection** goes in `tick()`'s Phase 2 apply loop, right after the
finish clamp (so a finish-line marker sees the clamped position). `positions`
is the Phase 1 snapshot, i.e. this rider's pre-move position:

```python
prev = positions[i]
rs.position += speed
if rs.position >= self.profile.total_distance:
    ...  # existing finish handling, unchanged
if markers:  # markers = self.course.markers, read once above the loop
    for m_idx, marker in enumerate(markers):
        if m_idx not in rs.marker_times and prev < marker.distance <= rs.position:
            frac = (marker.distance - prev) / speed if speed > 0 else 0.0
            rs.marker_times[m_idx] = self.current_time + frac
```

**The contest rule** (D6). Add the helper, then insert the branch as rule 2:

```python
def _marker_to_contest(self, rs: RiderState, pos: float) -> tuple[int, Marker] | None:
    """Nearest undecided, non-finish marker within its kind's window that this
    rider is specialist enough to contest, or None."""

# in _decide_actions, per rider:
contest = self._marker_to_contest(rs, pos) if markers else None
if pos >= profile.total_distance - SPRINT_DISTANCE:
    ...                                   # rule 1, unchanged
elif contest is not None:                 # rule 2 — new
    m_idx, marker = contest
    rs.contested.add(m_idx)               # decided once, whatever the energy says
    if rs.energy >= MARKER_MIN_ENERGY:
        surge = True
        sprinting = marker.kind is MarkerKind.SPRINT
        # duration stays SURGE_DURATION
elif (...):                               # climb attack, unchanged
```

Note the attribute gate lives **inside** `_marker_to_contest`: a rider who is
not a specialist gets `None` and falls through to the climb-attack and bridge
rules exactly as today. Only a specialist in the window takes the rule-2
branch.

`validate_team_leaders` and `run_race` are unchanged.

## race_engine/formulas.py

Beside the surge constants:

```python
MARKER_SPRINT_WINDOW = 300.0  # meters before a sprint marker a sprinter kicks
MARKER_CLIMB_WINDOW = 150.0   # meters before a mountain marker a climber surges
MARKER_MIN_SPRINT = 75.0      # sprint attribute needed to contest a sprint marker
MARKER_MIN_CLIMB = 75.0       # climb attribute needed to contest a mountain marker
MARKER_MIN_ENERGY = 60.0      # reserve needed to spend on a marker (vs 30 for an attack)
```

## race_engine/config.py

`_parse_markers(raw: dict, course: Course) -> list[Marker]` reads the
optional `race.markers` list (a sibling of `race.course`, not inside it).
Each entry: `kind` (string, one of the two), `name` (non-empty string),
`distance` (number). Raises `ConfigError` naming `race.markers[i]`. Build the
final `Course(segments, markers)` so `__post_init__` range-checks it, and
turn its `RaceSetupError` into `ConfigError`. `load_config`'s returned
`course` carries the markers; `build_race` and `__main__` need no change.

## race_engine/audit.py and configs

- Two new configs (**new** files):
  `race_engine/configs/sprinters_classic_markers.json` — `sprinters_classic`'s
  course and roster plus two sprint markers in the flat first 90 km and one
  mountain marker at the top of its 2.5% rise (km 94);
  `race_engine/configs/mountain_stage_markers.json` — `mountain_stage`'s
  course and roster plus a mountain marker at the top of every climb before
  the last and one sprint marker on its flattest early stretch.
- `EXPECTED_ARCHETYPE` gains both, with the same expectation as their
  unmarked twins (`"sp"` and `"gc"`).
- `RunResult` gains `marker_winners: list[str]` — the archetype of the rider
  with the lowest `marker_times[i]` for each marker, in index order — and the
  report prints them per run. This is what shows specialists are actually
  winning markers rather than whoever is on the front.

## racing/adapters.py

`to_engine_course(race: Race, markers: list[RaceMarker]) -> Course` — the
second argument is **required** (D9). Maps each row to
`Marker(kind=MarkerKind(m.kind), distance=m.distance, name=m.name)` in the
given order.

## racing/services.py

- `create_race(*, markers: Iterable[dict] = (), **fields) -> Race` (new) —
  D10. `markers` entries are `{"kind", "name", "distance"}` dicts, as the
  loader produces them.
- `simulate_race` — fetch the markers once (D9), pass them to
  `to_engine_course`, and inside the existing results transaction, after
  `RaceResult` rows, write the crossings:

```python
course_length = sum(s["length"] for s in race.course)
crossings = []
for idx, marker in enumerate(markers):
    if marker.distance >= course_length:              # D5: finish line
        crossers = [(s, float(s.finish_time)) for s in ordered if s.finish_time is not None]
    else:                                             # D4: interpolated time, stable
        crossers = sorted(
            ((s, s.marker_times[idx]) for s in states if idx in s.marker_times),
            key=lambda pair: pair[1],
        )
    crossings += [
        MarkerCrossing(marker=marker, rider=by_pk[s.rider.id], position=p, crossed_at=t)
        for p, (s, t) in enumerate(crossers, start=1)
    ]
MarkerCrossing.objects.bulk_create(crossings)
```

Same transaction as the results, so a race never has results without its
crossings or the other way round.

## racing/admin.py

`RaceMarkerInline(admin.TabularInline)` on `RaceAdmin`, `extra = 0`.
Register `MarkerCrossing` read-mostly: `list_display = ("marker", "position", "rider", "crossed_at")`,
`list_filter = ("marker__race",)`.

## schedule/loaders.py

- `_KNOWN_RACE_KEYS` gains `"markers"`.
- `RaceDeclaration` gains `markers: list[dict[str, Any]] = field(default_factory=list)`
  as its **last** field, so existing constructions keep working.
- `_parse_markers(raw, path, course_length, warnings) -> list[dict]` — absent
  or `None` → `[]`; otherwise a list of objects, D8's rules, errors naming
  `races[i].markers[j]`, unknown keys inside a marker warned about and
  ignored (the file's existing forward-compatibility rule). Returns
  `{"kind", "name", "distance": float}` dicts.
- `create_races` passes `markers=d.markers` to the injected `create_race`.

## schedule/management/commands/load_season.py

Inside `handle()`, import `racing.services.create_race` alongside the
existing `racing.models.Race` (still needed for `--replace`'s delete) and
inject it instead of `Race.objects.create`. The per-race summary line appends
the marker count when non-zero: `— Opening Sprint (110.0 km, 2 markers)`.

## seasons/season-1.example.json

Add markers so the feature is visible after seeding:

- *Opening Sprint* — sprint markers at 40000 and 80000.
- *Mountain Road* — mountain marker at 40000 (top of the 4% climb), sprint at 70000.
- *Summit Finish* — mountain markers at 65000 and at 100000 (the finish:
  exercises D5).

## api/views.py and api/serializers.py

- `RaceDetailView` payload gains `markers`: `[{id, kind, name, distance}]`
  from `race.markers.all()` (model ordering). Serializer
  `RaceMarkerSerializer` (new).
- `RaceResultsView` payload gains `markers`: per marker
  `{id, kind, name, distance, crossings: [{position, rider: {id, name}, team}]}`,
  first `MARKER_PLACES_SHOWN` crossings only. One prefetch:
  `race.markers.prefetch_related(Prefetch("crossings", queryset=MarkerCrossing.objects.filter(position__lte=MARKER_PLACES_SHOWN).select_related("rider")))`.
  `team` comes from the `team_by_rider` map the view already builds — the
  team the rider *raced for*, not their current team (same reasoning as
  `test_race_results_team_is_team_raced_for_after_release`). Serializer
  `RaceMarkerResultSerializer` (new), reusing `RaceResultRiderSerializer` and
  `RaceResultTeamSerializer`.
- A race with no markers returns `markers: []` from both.

## frontend/

- `src/api.ts` — `RaceMarker { id; kind: 'sprint' | 'mountain'; name; distance }`;
  `RaceDetail.markers: RaceMarker[]`;
  `RaceMarkerResult extends RaceMarker { crossings: Array<{ position; rider; team }> }`;
  `RaceResults.markers: RaceMarkerResult[]`.
- `src/components/CourseProfile.tsx` — optional `markers?: RaceMarker[]`.
  Passes `overlay` to `CourseChart`: per marker a dashed vertical line at
  `scale.x(distance)` from the baseline to the top margin, and a short label
  at the top (kind symbol + name). Below the SVG, a compact list —
  "Sprint · Verbier · km 42.0" — because labels at shared or near distances
  collide on the chart and the list is always legible. Nothing extra renders
  when `markers` is empty or absent. **Do not modify `race_player/`**: the
  `overlay` prop exists for exactly this.
- `src/screens/Race.tsx` — pass `race.markers` to `CourseProfile` in both
  the upcoming and finished branches. In the finished branch, after
  `TeamPointsTable`, a `MarkerResultsCard` (`Card` + `CardHeader
  title="Sprints and summits"`), one block per marker: kind, name, km, then
  the first three riders with team code. Hidden when `results.markers` is
  empty. Use the existing `primitives.tsx` and `theme.ts` tokens.

## Work items

### W1 — `race_engine/models.py`: markers on the course, crossings recorded
`MarkerKind`, `Marker`, `Course.markers` + `__post_init__` validation,
`RiderState.marker_times`, crossing detection in `tick()` (D4).
**Tests**, new `race_engine/test_markers.py`:
`test_course_rejects_marker_beyond_finish`, `test_course_rejects_marker_at_or_before_start`,
`test_course_accepts_marker_on_finish_line`,
`test_crossing_time_is_interpolated_within_the_tick` (two riders placed 5 m
and 10 m short of a marker, the *farther-back* one first in `rider_states`,
seeded; one tick; assert the nearer one has the smaller time and both times
fall inside `[t, t+1)`), `test_rider_who_never_reaches_marker_has_no_crossing`,
`test_finish_line_marker_is_crossed`.

### W2 — `race_engine/models.py` + `formulas.py`: specialists contest markers
Constants, `RiderState.contested`, `_marker_to_contest`, rule 2 (D6).
**Tests** in `race_engine/test_markers.py`:
`test_sprinter_kicks_for_sprint_marker_in_the_early_race` (remaining > 25%;
`surging` and `sprinting` true within the window),
`test_non_sprinter_rolls_through_sprint_marker`,
`test_climber_surges_for_mountain_marker_without_sprinting`,
`test_leader_contests_too`,
`test_low_energy_specialist_rolls_through_and_does_not_retry`,
`test_marker_is_contested_once`,
`test_finish_line_marker_is_left_to_the_finish_sprint`.
**Load-bearing check before committing:** the audit identity run in
*Verification* step 1 must be identical — this item is the one that could
change existing races.

### W3 — `race_engine/config.py`: `race.markers` in config files
**Tests** in `race_engine/test_config.py`: markers parsed onto the course;
bad kind / empty name / distance out of range / non-list each raise
`ConfigError` naming the path; absent `markers` gives `[]`.

### W4 — `race_engine/audit.py` + two configs: marker courses audited, constants calibrated
Add the configs, `EXPECTED_ARCHETYPE` entries and `marker_winners`. Run
*Verification* step 2. **Calibrate** until both hold on the default seeds:
(a) each marker config's expected-archetype win rate is no worse than its
unmarked twin's; (b) sprint markers are won by an `sp` rider and mountain
markers by a `gc`/`pu` rider in a clear majority of runs. Tune only the five
`MARKER_*` constants; record the final values and the audit numbers in the
commit message. No test file — the audit is the test, and step 1's identity
run must still pass after tuning.

### W5 — `racing/models.py`, migration 0007, `racing/admin.py`: `RaceMarker`, `MarkerCrossing`
**Tests** in `racing/tests.py`: `test_marker_beyond_course_is_rejected`,
`test_marker_with_blank_name_is_rejected`, `test_markers_order_by_distance`,
`test_crossing_position_is_unique_per_marker`.

### W6 — `racing/adapters.py` + `racing/services.py`: markers in, crossings out
`to_engine_course(race, markers)`, `create_race`, crossing rows in
`simulate_race` (D5, D9). Update `test_course_json_converts_to_engine_course`
for the new argument.
**Tests** in `racing/tests.py`:
`test_create_race_creates_its_markers`,
`test_simulate_race_records_every_crossing_in_order` (real engine, a
mid-course sprint marker: positions contiguous from 1, `crossed_at`
non-decreasing, one row per starter who reached it),
`test_finish_line_marker_matches_the_result_order` (monkeypatch
`run_race_via_adapter` to return states whose `marker_times` disagree with
the finish order and whose `finish_time`s tie — assert crossings follow
`RaceResult` positions; this is the test that fails if D5 is skipped),
`test_race_without_markers_records_no_crossings`.

### W7 — `schedule/`: markers in the season file
Loader, command, `season-1.example.json`.
**Tests**: `schedule/tests/test_loaders.py` — markers parsed; each invalid
case raises `SeasonFileError` naming `races[i].markers[j]`; unknown marker
key warned; `create_races` passes `markers` to the stub. Update the test at
line ~170 that injects `Race.objects.create` to inject
`racing.services.create_race`. `schedule/tests/test_load_season.py` —
`test_load_season_creates_race_markers`.

### W8 — `api/`: markers on race detail and results
**Tests** in `api/tests.py`: `test_race_detail_includes_markers`,
`test_race_detail_markers_empty_for_plain_course`,
`test_race_results_include_first_three_per_marker`,
`test_race_results_marker_team_is_team_raced_for`.

### W9 — `frontend/`: markers on the profile, crossings on the results
**Tests**: `CourseProfile.test.tsx` — `draws a line and a list entry per marker`,
`renders nothing extra without markers`; `Race.test.tsx` —
`upcoming race lists its markers`, `finished race shows the first three over each marker`,
`finished race without markers has no marker card`.

### W10 — Documentation (see below)

## Execution order

W1 → W2 → W3 → W4 → W5 → W6 → W7 → W8 → W9 → W10, one commit each.

Engine first (W1–W4) because it is pure Python, fast to test, and the only
part that can change existing race outcomes — settle that before anything
depends on it. **Stop after W2 and run the identity audit**; do not continue
on a mismatch. W4 calibrates before any other layer is built on the
constants. W5 before W6 because the adapter needs the model; W6 before W7
because `load_season` injects W6's `create_race`. API and frontend last:
they only read what W6 writes.

## Documentation update (required, not optional)

- **`race_engine/README.md`** — *Data model*: `Marker`, `MarkerKind`,
  `Course.markers`, `RiderState.marker_times`/`contested`. *Race
  configuration*: `race.markers` in the schema and field list. *Tactics*:
  the decision chain becomes four rules, with rule 2 (contest a marker) and
  why it is the one effort exempt from the phase gate; *Race phases* table
  gets a footnote. *Simulation tick*: crossing detection in step 6 and the
  interpolation. *Bundled configs*: the two marker configs. *Regression
  audit*: `marker_winners`. *Realism status*: the W4 numbers. *JSONL output
  format*: say markers and crossings are deliberately **not** in the log.
- **`racing/README.md`** — *What lives here*: `RaceMarker`,
  `MarkerCrossing`. New section *Markers and crossings*: D1, D2, D5, D9, and
  that `create_race` is how `load_season` creates races.
- **`schedule/README.md`** — *The `races` list*: `markers` row in the key
  table and in the example. *Why the course is validated twice*: markers are
  validated the same way. *What `schedule/` may import*: the command now
  also imports `racing.services.create_race`.
- **`api/README.md`** — the new `markers` fields on race detail and results,
  and the three-places cut.
- **`frontend/README.md`** — the `/race/:raceId` row: markers on the profile
  and the marker results card.
- **`AGENTS.md`** — the `schedule -> core` paragraph names
  `racing.services.create_race` alongside `racing.models.Race`; the seeding
  section notes the example season now declares markers.
- On close: spec and plan `Status: implemented`, both moved to
  `specs/archive/`.

## Verification

1. **No-marker races are unchanged (the likeliest regression).** On
   `master` and on the branch:
   ```bash
   .venv/bin/python -m race_engine.audit --configs sprinters_classic,san_remo,lombardia,classics_hilly,summit_finish,mountain_stage --json /tmp/audit-<branch>.json
   diff /tmp/audit-master.json /tmp/audit-course-markers.json
   ```
   The diff must be empty. A non-empty diff means the contest rule or the
   crossing loop runs, or consumes randomness, on a course with no markers.
2. **Marker races still pick the right winner, and specialists win markers.**
   ```bash
   .venv/bin/python -m race_engine.audit --configs sprinters_classic,sprinters_classic_markers,mountain_stage,mountain_stage_markers
   ```
   Compare win rates twin to twin; read `marker_winners`. If the pulling
   domestique (`do`) wins sprint markers, the contest rule is not firing.
3. **End to end.** In the worktree:
   ```bash
   .venv/bin/python scripts/dev_db.py && .venv/bin/python manage.py migrate
   .venv/bin/python manage.py seed_user
   .venv/bin/python manage.py seed_teams --claim-for test@mail.com
   .venv/bin/python manage.py load_season seasons/season-1.example.json
   GAME_CLOCK_CLASS=world.clocks.MockClock .venv/bin/python manage.py mock_clock set 2027-03-07T15:00:00Z
   GAME_CLOCK_CLASS=world.clocks.MockClock .venv/bin/python manage.py tick
   ```
   `load_season` prints "2 markers" for *Opening Sprint*. Open *Summit
   Finish*'s race page: two markers on the profile and in the list. Open
   *Opening Sprint* after the tick: the marker card lists three riders per
   sprint, and they are not simply the first riders by pk.
4. **Full suites:** `.venv/bin/python -m pytest` and `npm test` in `frontend/`.

## Risks

| Risk | Mitigation |
|---|---|
| Crossings recorded by tick number, so a bunch crossing is ordered by rider pk. | D4 interpolation; `test_crossing_time_is_interpolated_within_the_tick` places riders so that list order and physical order disagree. |
| Finish-line marker contradicts `RaceResult` in a same-second sprint. | D5; `test_finish_line_marker_matches_the_result_order` forces tied finish times. |
| Engine marker index and `RaceMarker` row drift apart (two queries, two orders). | D9: one list, passed to both; `to_engine_course` has no default for it. |
| Existing races change — the rule fires or draws RNG without markers. | D7 guard; Verification step 1 is an exact diff, run after W2 and again at the end. |
| A contesting sprinter goes more than 60 m clear and the whole bunch switches to chase tempo, burning everyone's energy early. | Expected and bounded (20-tick effort); W4's twin comparison catches a finale that changes. Tune `MARKER_MIN_ENERGY` up or the windows down, not the pack-tempo code. |
| Implementer phase-gates the rule "for consistency" with the attack rule. | D6 says why not: an early effort is the whole point of the rule. `test_sprinter_kicks_for_sprint_marker_in_the_early_race` fails if it is gated. |
| `schedule/` gains an import of `racing/` to validate markers. | D8, D10; the loader duplicates the checks. |
| Marker labels overlap on the chart. | The list under the chart is the legible record; the chart labels are secondary. |

## Open questions

None.
