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

## Simulation tick (`RaceState.tick`)

The tick runs in phases so all riders see a consistent snapshot.

1. **Snapshot**: record each non-finished rider's current `position`.
2. **Natural cruise**: for each rider compute their uncontested base speed on the
   current segment's gradient, throttled by stamina (see `compute_base_speed` and
   `apply_stamina_cruise_modifier`), plus per-rider speed jitter. Finalized
   riders and riders past the line are skipped (speed 0).
3. **Decide surges**: for each rider that could surge, apply the reflex rules
   (see Surge reflexes) using the snapshot positions.
4. **Resolve drafting**: group riders whose led rider is within `DRAFT_DISTANCE`
   adopt that leader's pace, propagated wheel-to-wheel down the group. A rider
   currently surging always rides their own pace. No drafting above
   `DRAFT_UPHILL_LIMIT` gradient.
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
if drafting: drain *= 0.85                            # conserve in the wheels
if gradient > 0: drain *= 1 + gradient × 0.20         # climbs cost more
if gradient < 0: drain −= 0.006                       # descents recover a little
```
Stamina is clamped to `[0, 100]`.

## Energy

`compute_energy_drain` returns a positive cost (drain) when the rider is working
above their own cruise, or a negative value (recovery) when under their own pace:
```
overshoot = max(0, effective_speed − own_speed)       # excess over natural pace
intensity = overshoot × 0.10
if drafting: intensity ×= 0.60                        # conserve in the wheels
if intensity > 0: return intensity                     # drained
return −0.008                                          # recovered while cruising/descending
```
`apply_energy_burst_modifier` throttles burst speed when energy is low: unchanged
while `energy >= 40`, else `speed × (0.5 + 0.5 × (energy / 40))`. This caps
surges without throttling steady cruising (which stamina governs). Energy is
clamped to `[0, 100]`.

## Drafting

- `DRAFT_DISTANCE = 3.0` m — a rider drafts when another is ahead within this
  range.
- `DRAFT_UPHILL_LIMIT = 5.0` % — no drafting on steeper climbs.
- **Finished riders provide no shelter** — they are excluded when finding a
  drafting leader (this prevents a frozen finish-line bunch from sheltering
  riders).
- A drafting rider adopts the group's pace: the front rider's speed propagated
  down the wheel chain.
- **Pulling**: a rider pulls only when (a) not drafting themselves and (b) at
  least one rider is within `DRAFT_DISTANCE` behind them. Only the group front
  rider pulls.

`_drafting_leader(idx, …)` returns the nearest rider ahead within
`DRAFT_DISTANCE` and on a draft-allowed gradient, or `None`.

## Surge reflexes

A surge is a discrete ~20s energy-burst effort (`SURGE_DURATION = 20` ticks),
granting a `SURGE_SPEED_BOOST = 0.25` fraction above the rider's natural cruise
while burning `SURGE_ENERGY_COST = 0.05` extra energy per tick. A surging rider
breaks from drafting and rides their own pace.

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
| `drafting` | sheltered behind a leader this tick |
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