# Race Engine — Specification & Agent Guide

## Role of this document

This file is the authoritative spec for the race engine. It describes the data
model, the physics/formulas, and the per-tick simulation logic in enough detail
that a coding agent could reproduce the engine exactly. Changes to the engine
**must** be reflected here (see "Commit procedure" below).

A textual viewer/player is included for visualizing races, but it is **not** part
of the engine and is deliberately out of scope for this document.

## Overview

The engine simulates a bicycle race as a set of riders moving along a fixed
course of straight segments. Time advances in integer **ticks**; **one tick = one
second**. Each rider has a position along the course and two meters — **energy**
(anaerobic burst reserve) and **stamina** (aerobic endurance) — plus attributes
that determine their natural pace. The engine resolves every rider's per-tick
state from these values each second and produces a JSONL log every tick for
consumption (e.g. by visualizers).

The current rule-set is a set of *reflexes* (finish sprint, climb attack, gap
chase) layered over emergent group behavior (drafting, pace-sharing, fatigue
cracking). It is **not** a full team-tactics model; tactics are a future concern.

## Core concepts — the two meters

The engine separates two forms of effort:

- **Stamina (0–100)** — aerobic, long-duration endurance. Depletes continuously
  with cumulative rolling workload (faster pace, steeper climbs, leading the
  group all burn more; drafting and descents conserve/recover). It degrades a
  rider's sustainable cruising pace smoothly as it falls (**progressive
  cracking**). Stamina is the meter that decides who cracks in the finale.

- **Energy (0–100)** — anaerobic, short-term burst reserve. It drains **only**
  when a rider works above their own natural sustainable pace (an *overshoot*,
  e.g. being dragged along in the group faster than they could ride alone, or
  actively surging), and recovers while cruising or descending. Stationary
  riding on a climb costs stamina, not energy. Energy is the meter that gates
  surges (attacks/sprint/chase). It is capped at 100.

## Data model

### Attributes (`Rider`) — all ints in `[1, 100]`, validated on construction
- `climb` — speed on uphill terrain and the ability to attack climbs.
- `sprint` — top-end finishing power (finish kick) and descending speed blend.
- `flat` — speed on flat terrain.
- `resistance` — fatigue tolerance; slows stamina drain.
- `positioning` — draft/shelter skill; deepens the energy/stamina saving a
  rider gets while sheltering in the wheels.

### Position / course
- `Segment` = `length` (meters) + `gradient` (percent, `+` = uphill).
- `Course` = ordered list of `Segment`; `total_distance` = sum of lengths.
- A rider's `position` is meters from the start; each tick adds their speed
  (m/s) to it. When `position >= total_distance` the rider **finishes** and is
  frozen at the line.

### Per-rider runtime state (`RiderState`)
- `speed` (m/s), `position` (m), `energy` (0–100), `stamina` (0–100).
- `drafting` (bool) — sheltered behind another rider this tick.
- `pulling` (bool) — on the front of a group, being drafted.
- `surging` (bool), `surge_ticks` (int), `surge_cooldown` (int) — surge bookkeeping
  (see Surge reflexes).
- `finished` (bool), `finish_time` (seconds or None).

## Race configuration (input)

A race can be built in code (constructing `Course`/`Rider` objects) or loaded
from a **config JSON file** via `race_engine.config.build_race`. The file
declares the riders and the course; the engine derives everything else. This
makes it easy to keep multiple reusable race configurations side by side.

### Schema
```json
{
  "race": {
    "name": "Hilly Classic",
    "course": [
      {"length": 7000.0, "gradient": 0.0},
      {"length": 1000.0, "gradient": 5.0}
    ],
    "riders": [
      {
        "id": "c1",
        "name": "Climber 1",
        "attributes": {"climb": 92, "sprint": 40, "flat": 45, "resistance": 72, "positioning": 60}
      }
    ]
  }
}
```
- `course` — non-empty list of `{"length": m, "gradient": %}`, positive lengths.
- `riders` — non-empty list; each has a unique `id`, a display `name`, and
  `attributes` (all five ints in `[1, 100]`, validated as in `RiderAttributes`).
- `name` — optional display name for the race (informational).
- Starting `energy`/`stamina` are always 100 (engine-internal, not configurable).
  Engine constants (draft distance, surge thresholds, etc.) are not exported to
  config; they remain fixed in `formulas.py`.

### CLI
`python -m race_engine <config.json> [log.jsonl] [--seed N]` runs a race from a
config and writes the JSONL log (default `race.jsonl`), printing the results
table. `--seed N` makes the run reproducible. `race_engine.config.load_config`
returns `{"riders", "course", "name"}` after validation (`ConfigError` on
malformed input).

### Bundled configs (`configs/`)
The `configs/` directory holds reusable race definitions modeled on real
single-day races. They use a **shared 11-rider archetype roster** (GC climbers,
puncheurs, rouleurs, sprinters, domestiques) embedded in each file, so terrain
alone determines the winner. Courses are **scaled down** (roughly 90–140 km
instead of the 250–300 km of real Monuments) for fast iteration; the profile
character (climb ratios, late steep sections) is preserved.

- `sprinters_classic.json` — flat bunch-sprint style race.
- `san_remo.json` — flat-first + Cipressa/Poggio-style late climbs.
- `lombardia.json` — rolling opener, big climbs late, downhill finish.
- `classics_hilly.json` — long shallow climbs + short steep finale.
- `summit_finish.json` — flat/downhill approach to a summit climb.
- `mountain_stage.json` — sustained climbs with descents between.

`_roster.json` is a reference copy of the shared roster (not loaded by the
engine; the roster is embedded in each config).

### Rider archetypes

Each archetype occupies a distinct niche defined by attribute trade-offs.
Typical attribute ranges are shown; exact values vary per rider.

**GC Climber** — the mountain specialist. Excels on long, steep climbs where
`climb` dominates speed. Weak on flats and has a negligible sprint. Wins by
attacking on climbs and riding away from the group under sustained aerobic
effort. High `resistance` keeps them fresher late in the race.

| climb | sprint | flat | resistance | positioning |
|---|---|---|---|---|
| 88–94 | 28–30 | 38–40 | 78–80 | 50–52 |

**Superdom** — the mountain domestique. Strong climber who can follow attacks
on steep terrain but lacks the top-end to contest the summit finish. Highest
`resistance` of any archetype, so they burn slowly and can set a grinding pace
for teammates. Terrible sprint and weak on flats.

| climb | sprint | flat | resistance | positioning |
|---|---|---|---|---|
| 84 | 25 | 45 | 84 | 56 |

**Puncheur** — the short-climb puncher. Combines solid climbing (`climb`
73–76) with a strong finishing kick (`sprint` 82–85). Thrives on hilly
courses with repeated short ascents where a burst of speed at the crest
matters more than sustained climbing. Moderate endurance; not a pure sprinter
or pure climber.

| climb | sprint | flat | resistance | positioning |
|---|---|---|---|---|
| 73–76 | 82–85 | 58–60 | 66–68 | 70–72 |

**Rouleur** — the flat-road engine. Dominates on flat and rolling terrain
(`flat` 77–80) with the highest `resistance` (84–86) in the roster — barely
tires over long distances. Moderate sprint and weak climbing; struggles on
steep gradients but is devastating on flats where sustained power wins.
Tends to press clear of the pack on flat courses.

| climb | sprint | flat | resistance | positioning |
|---|---|---|---|---|
| 57–60 | 55–60 | 77–80 | 84–86 | 58–62 |

**Sprinter** — the bunch finish specialist. Highest `sprint` (93–97) and
excellent `positioning` (85–88) to stay sheltered in the wheels until the
final kick. Very weak climbing (`climb` 26–30) — gets dropped on any
meaningful ascent. Low `resistance` means they fatigue faster, but their
energy reserve is preserved by draft skill. Wins flat bunch sprints
decisively; useless in the mountains.

| climb | sprint | flat | resistance | positioning |
|---|---|---|---|---|
| 26–30 | 93–97 | 79–82 | 58–62 | 85–88 |

**Domestique** — the team worker. Well-rounded with no standout strength but
no fatal weakness. High `positioning` (80–82) lets them shelter efficiently,
and solid `resistance` (74–76) means they stay in the group longer than
their speed alone would suggest. Provides draft for teammates and covers
moderate terrain. Cannot win from a breakaway but rarely gets dropped.

| climb | sprint | flat | resistance | positioning |
|---|---|---|---|---|
| 52–55 | 45–48 | 68–70 | 74–76 | 80–82 |

### Known discrepancies (`ENGINE_FINDINGS.md`)
`ENGINE_FINDINGS.md` documents, per course, the real-world expected winner vs.
what the engine actually produces (seeded runs) and the mechanism behind each
discrepancy. Climber-leaning courses match reality; long flat courses
(`sprinters_classic`, `san_remo`) still have a **rouleur bias**: the rouleur
presses away from the pack and solos to the win while the sprinter keeps
sheltering — the reflex set lacks a flat-attack/press and a follow-the-move
response (a tactics concern, see the doc). Update this file when the engine's
behavior changes.

## Simulation tick (`RaceState.tick`)

The tick runs in phases so all riders see a consistent snapshot.

1. **Snapshot**: record each non-finished rider's current `position`.
2. **Natural cruise**: for each rider compute their uncontested base speed on the
   current segment's gradient, throttled by stamina (see `compute_base_speed` and
   `apply_stamina_cruise_modifier`), plus per-rider speed jitter. Finalized
   riders and riders past the line are skipped (speed 0).
3. **Decide surges**: for each rider that could surge, apply the reflex rules
   (see Surge reflexes) using the snapshot positions.
4. **Resolve pack cohesion**: riders within `PACK_COHESION_DISTANCE` of each
   other on a draft-allowed gradient cohere into a pack that rolls at a shared
   sustainable tempo (`GROUP_DROP_FRACTION ×` the pack's best cruise). A rider
   whose own cruise falls below that pace is DROPPED (not sheltered). A rider
   currently surging always rides their own pace. No cohesion above
   `DRAFT_UPHILL_LIMIT` gradient. Each coherent rider's pack **depth** (wheels
   back) is recorded to scale draft savings. The `drafting` flag is set only
   for riders who have a wheel within `DRAFT_DISTANCE` (3 m) directly ahead
   — pack membership alone does not imply `drafting`.
5. **Compute deltas** (per rider): final effective speed, energy drain, stamina
   drain, drafting/pulling flags — using the shared snapshot, not the mutated
   state.
6. **Apply deltas**: write speed/flags, move each rider by their speed
   (1 tick = 1 s), subtract drains (m meters clamped to `[0, 100]`), mark
   finishers, advance `current_time`.

## Terrain speed (`compute_base_speed`)

Attributes map to speeds via linear interpolation `_lerp(min, max, t)` where
`t = (attr − 1) / 99`.

- **Flat** (`gradient == 0`): `flat` → `[8.0, 16.0]` m/s.
- **Uphill** (`gradient > 0`): `climb` → `[4.0, 14.0]` m/s, minus
  `gradient × 0.25` (speed loss per % climb), floored at 1 m/s.
- **Downhill** (`gradient < 0`): blend `(sprint + flat) / 2` → `[12.0, 25.0]`
  m/s, plus `|gradient| × 0.30`, capped at 25 m/s.

Per-tick jitter: `speed += uniform(−0.3, 0.3)`, floored at 1 m/s
(`add_speed_jitter`). This breaks perfect ties so groups form a realistic echelon.

## Stamina

### Cruise modifier (`apply_stamina_cruise_modifier`)
Sustainable base speed is unchanged while `stamina >= 60`. Below 60 it degrades
progressively (`progressive cracking`):
`base_speed × (max(0, stamina / 60) ^ 0.7)`.

### Drain (`compute_stamina_drain`)
Per tick:
```
drain = 0.012 × (1 + (speed − 10.0) × 0.010)          # rolling workload
drain *= 1 − (resistance / 100) × 0.6                 # fatigue tolerance
drain *= draft_stamina_factor                         # shelter conservation (below)
if gradient > 0: drain *= 1 + gradient × 0.20         # climbs cost more
if gradient < 0: drain −= 0.006                       # descents recover a little
```
Stamina is clamped to `[0, 100]`. `draft_stamina_factor` ∈ `[0.70, 1.0]` is the
fraction of drain kept while sheltered — lower = better shelter (see Drafting).

## Energy

`compute_energy_drain` returns a positive cost (drain) when the rider is working
above their own cruise, or a negative value (recovery) when under their own pace:
```
overshoot = max(0, effective_speed − own_speed)       # excess over natural pace
intensity = overshoot × 0.10
intensity *= draft_energy_factor                      # shelter conservation (below)
if intensity > 0: return intensity                     # drained
return −0.008                                          # recovered while cruising/descending
```
`draft_energy_factor` ∈ `[0.40, 1.0]` is the fraction of burst cost kept while
sheltered (see Drafting).
`apply_energy_burst_modifier` throttles burst speed when energy is low: unchanged
while `energy >= 40`, else `speed × (0.5 + 0.5 × (energy / 40))`. This caps
surges without throttling steady cruising (which stamina governs). Energy is
clamped to `[0, 100]`.

## Drafting & pack cohesion

Riders cluster into **packs** and share a sustainable tempo rather than each
riding at maximum. Shelter within a pack is set by the rider's position (depth)
and their `positioning` skill, so a skilled deep rider conserves more than an
exposed or socially-sheltered one.

- `PACK_COHESION_DISTANCE = 60.0` m — riders within this of each other on a
  draft-allowed gradient cohere into a single pack (connected-component BFS).
  This governs pace-sharing / dropping, not the physical drafting label.
- `DRAFT_UPHILL_LIMIT = 5.0` % — no cohesion/drafting on steeper climbs.
- **Drafting flag** — `drafting=True` only when a rider has a wheel within
  `DRAFT_DISTANCE (3.0 m)` directly ahead. Pack membership (cohesion) does
  NOT set the flag; only physical proximity to a wheel does.
- **Group tempo** — a pack rolls at `GROUP_DROP_FRACTION (0.90) ×` the pack's best
  cruise. A rider whose own cruise is below that tempo is DROPPED (rides alone,
  not sheltered).
- **Finished riders provide no shelter** — excluded when finding pack neighbours,
  so a frozen finish-line bunch cannot shelter riders.
- **Pack depth** — within a coherent pack, the rider with the front position is
  the puller (depth 0, exposed); each wheel behind gains a deeper shelter
  (depth 1, 2, …). Draft savings scale with depth up to
  `DRAFT_DEPTH_SATURATION (10)`.

### Draft factors (`compute_draft_factors`)
A rider's hold-on-to-cost fractions are derived from `positioning` (skill) and
pack `depth`:
```
skill = (positioning − 1) / 99                       # 0..1
depth_factor = min(depth, 10) / 10                   # 0..1
quality = 0.6 × skill + 0.4 × depth_factor           # 0..1
stamina_factor = 0.85 − (0.85 − 0.70) × quality      # 1.0 if not sheltering
energy_factor  = 0.60 − (0.60 − 0.40) × quality      # 1.0 if not sheltering
```
A rider at depth 0 (pulling or solo) uses factor 1.0 (no save).

### Pulling
A rider pulls only when (a) not drafting themselves and (b) at least one rider
is within `DRAFT_DISTANCE (3.0 m)` behind them. Only the group front rider pulls.

## Surge reflexes

A surge is a discrete ~20s energy-burst effort (`SURGE_DURATION = 20` ticks),
granting a `SURGE_SPEED_BOOST = 0.25` fraction above the rider's natural cruise
while burning `SURGE_ENERGY_COST = 0.05` extra energy per tick. A surging rider
breaks from drafting and rides their own pace. A finish sprint is a **longer
kick** (`SPRINT_DURATION = 40` ticks) — the sprinter sustains the burst further
to the line.

### Refusal conditions
A rider does **not** start a surge if they are finished, already surging
(`surge_ticks > 0`), cooling down (`surge_cooldown > 0`), or have
`energy < SURGE_MIN_ENERGY (30.0)`.

### Triggers (first matching rule wins, in this order)
1. **Finish sprint** — within `SPRINT_DISTANCE (1000 m)` of the finish and
   `sprint >= 70`. A strong sprinter kicks for the line.
2. **Attack a climb** — current gradient `>= 6.0` % and `climb >= 75`. A strong
   climber tries to break away on a steep section.
3. **Chase a leader** — not drafting and a clear break ahead: the gap to the
   front rider is `> DRAFT_DISTANCE` and `<= CHASE_GAP_THRESHOLD (8.0 m)`.

### Cooldown
On starting a surge a rider sets `surge_ticks = SURGE_DURATION` and
`surge_cooldown = SURGE_COOLDOWN (60 ticks)`. `surge_ticks` and
`surge_cooldown` both decrement per tick, preventing runaway/back-to-back
surges (a rider can make a fresh effort only after the cooldown elapses).

## Determinism & order

- Each tick snapshots all positions, computes all deltas from that snapshot, then
  applies them together, so ordering is consistent.
- Per-tick jitter uses `random`; the race is therefore non-deterministic across
  runs unless a seed is applied externally.
- Results are ordered by `finish_time` ascending (`get_results`).

## JSONL output format

`run_race` writes a JSONL file (one JSON object per line) with no terminal
journal/effects data. Each line is a full snapshot of one tick at `"time"` t.
The first line is t=0 (the neutral start) and subsequent lines are t=1, 2, …
so a consumer can step frame-by-frame. `course_length` is constant across all
lines. Riders array order is fixed and matches `state.rider_states` order.

```json
{
  "time": 42,
  "course_length": 38000.0,
  "segments": [
    {"length": 15000.0, "gradient": 0.0},
    {"length": 1000.0, "gradient": 5.0}
  ],
  "riders": [
    {
      "id": "c1",
      "name": "Climber 1",
      "pos": 15234.56,
      "speed": 13.42,
      "energy": 62.1,
      "stamina": 88.9,
      "drafting": false,
      "pulling": true,
      "surging": false,
      "finished": false,
      "finish_time": null
    }
  ]
}
```

Field reference (rider entries):

| Field | Meaning |
|---|---|
| `id` | stable rider identifier |
| `name` | display name |
| `pos` | meters from start, rounded to 2 dp |
| `speed` | effective speed this tick, m/s, rounded to 2 dp |
| `energy` | anaerobic reserve 0–100, rounded to 2 dp |
| `stamina` | aerobic endurance 0–100, rounded to 2 dp |
| `drafting` | has a wheel within DRAFT_DISTANCE (3 m) directly ahead |
| `pulling` | working on the front of the group this tick |
| `surging` | in a surge effort this tick |
| `finished` | crossed the line |
| `finish_time` | finish tick, or `null` |

Bytes are exact (no line wrapping). Consumers may aggregate frames by `time`.
Note there is currently **no** per-tick event/commentary stream; a visualizer
derives narrative purely from these snapshots.

## Submission / commit procedure

The engine, its module layout, and this spec are under active development.

- **Keep AGENTS.md current**: after any change to the engine's data model,
  formulas, constants, tick logic, or output format, update this document
  to match before committing.
- **Review ask**: before committing, re-read AGENTS.md; if the pending changes
  alter anything described here, apply the needed edits to AGENTS.md, then ask
  the user to review the diff and explicitly approve before committing. Do not
  commit until the user confirms.
- **Scope of commits**: commit only intentional work (exclude stray/unrelated
  edits such as local test-course tweaks unless the user includes them).