# Race Engine — Specification & Agent Guide

## Role of this document

This file is the authoritative spec for the race engine. It describes the data
model, the physics/formulas, and the per-tick simulation logic in enough detail
that a coding agent could reproduce the engine exactly. Changes to the engine
**must** be reflected here (see "Commit procedure" below).

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
cracking), plus a first layer of team tactics (Tier A: leader protection,
teammate shelter, not chasing your own break, leaders not bridging — see
"Team and role" in Data model and the A1–A4 biases described in Drafting &
pack cohesion and Tactics below). It is **not** a full team-tactics model —
finer roles and cross-team cooperation remain a future concern (Tier B/C,
see Future work).

## Core concepts — the two meters

The engine separates two forms of effort:

- **Stamina (0–100)** — aerobic, long-duration endurance. Depletes continuously
  with cumulative rolling workload (faster pace, steeper climbs, leading the
  group all burn more; drafting and descents conserve/recover). It degrades a
  rider's sustainable cruising pace smoothly as it falls (**progressive
  cracking**). Stamina is the meter that decides who cracks in the finale.

- **Energy (0–100)** — anaerobic, short-term burst reserve. It drains **only**
  when a rider works above the pace they can sustain *in the position they are
  riding* — their solo cruise when exposed or alone, a higher, draft-credited
  speed when sheltered in a pack (an *overshoot*, e.g. actively surging, or
  hanging on to a group pace their shelter cannot buy). Sitting in the wheels at
  the bunch's tempo is free and recovers the reserve. Steady riding on a climb
  costs stamina, not energy. Energy is the meter that gates surges
  (attacks/sprint/chase). It is capped at 100.

## Data model

### Attributes (`Rider`) — all ints in `[1, 100]`, validated on construction
- `climb` — speed on uphill terrain and the ability to attack climbs.
- `sprint` — top-end finishing power (finish kick) and descending speed blend.
- `flat` — speed on flat terrain.
- `resistance` — fatigue tolerance; slows stamina drain.
- `positioning` — draft/shelter skill; raises the pace a rider can hold for
  free while sheltering in the wheels, which in turn lowers what both fatigue
  meters charge them.

### Team and role (`Rider`)

Riders belong to a team and hold one of two roles, feeding the team-tactics
biases below (see "Team tactics"):
- `team_id` — which team the rider rides for. Defaults to the rider's own
  `id` (a team of one) when not given, so hand-built `Rider` objects and
  code paths that predate teams keep working unchanged.
- `role` — `"leader"` or `"support"`. Defaults to `"leader"`, so a
  default-constructed field of soloists behaves exactly as it did before
  teams existed: every rider is their own one-person team's leader.

There is no engine-side notion of "who deserves to lead" — the engine reads
`role`, it does not derive it. Choosing a course-appropriate leader is a
config/player decision (see "Bundled configs" below); a deliberately wrong
choice is expressible and will lose.

### Position / course
- `Segment` = `length` (meters) + `gradient` (percent, `+` = uphill).
- `Course` = ordered list of `Segment`; `total_distance` = sum of lengths.
- A rider's `position` is meters from the start; each tick adds their speed
  (m/s) to it. When `position >= total_distance` the rider **finishes** and is
  frozen at the line.

### Per-rider runtime state (`RiderState`)
- `speed` (m/s), `position` (m), `energy` (0–100), `stamina` (0–100).
- `pulling` (bool) — setting the pace at the front of a multi-member pack
  this tick. There is no separate "drafting" flag — shelter degree varies
  continuously across a pack (see Gap-decayed depth) and doesn't compress
  into a meaningful boolean, so every non-pulling pack member is simply
  assumed to be benefiting, unevenly.
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
        "team": "t1",
        "role": "leader",
        "attributes": {"climb": 92, "sprint": 40, "flat": 45, "resistance": 72, "positioning": 60}
      }
    ]
  }
}
```
- `course` — non-empty list of `{"length": m, "gradient": %}`, positive lengths.
- `riders` — non-empty list; each has a unique `id`, a display `name`, and
  `attributes` (all five ints in `[1, 100]`, validated as in `RiderAttributes`).
- `team` — optional; which team the rider rides for. Defaults to the
  rider's own `id` (a team of one) when absent.
- `role` — optional; `"leader"` or `"support"` when present (any other value
  is a `ConfigError`). Defaults to `"leader"` when absent.
- **Exactly one leader per team** — `load_config` raises `ConfigError` if any
  team has zero or more than one rider with `role: "leader"`. Silent
  acceptance would produce races that are confusing to debug: a team with no
  leader has nobody to protect, and one with two has no well-defined "the"
  leader for the role-scaled tactics below.
- `name` — optional display name for the race (informational).
- Starting `energy`/`stamina` are always 100 (engine-internal, not configurable).
  Engine constants (draft distance, surge thresholds, etc.) are not exported to
  config; they remain fixed in `formulas.py`.

### CLI
`python -m race_engine <config.json> [--seed N]` runs a race from a config
file, writing the JSONL log to `race_player/public/<name>.jsonl` (overwriting
if it exists). `--seed N` makes the run reproducible. Progress (percentage,
tick, wall-clock time) is printed to stderr. `race_engine.config.load_config`
returns `{"riders", "course", "name"}` after validation (`ConfigError` on
malformed input).

### Bundled configs (`configs/`)
The `configs/` directory holds reusable race definitions modeled on real
single-day races. They use a **shared 16-rider roster of 4 teams of 4**
(built from the same five archetypes — GC climbers, puncheurs, rouleurs,
sprinters, domestiques — so per-archetype attribute tuning is unchanged)
embedded in each file. Courses are **scaled down** (roughly 90–140 km
instead of the 250–300 km of real Monuments) for fast iteration; the profile
character (climb ratios, late steep sections) is preserved.

Rider ids keep their archetype prefix (`gc`/`pu`/`ru`/`sp`/`do`) regardless of
team — team membership lives only in the `team` field — so `audit.py`'s
`_archetype()` needs no changes and terrain alone still determines the
winning archetype (see "Realism status" below).

**Team roster and identities** (same 16 riders across all 6 configs):

| Team | Identity | Composition |
|------|----------|-------------|
| `t1` | Climbing / GC | `gc1`, `gc2`, `ru1`, `do1` |
| `t2` | Sprint | `sp1`, `pu1`, `do2`, `do3` |
| `t3` | Classics / puncheur | `pu2`, `pu3`, `ru2`, `gc3` (Superdom) |
| `t4` | Mixed / opportunist | `gc4`, `sp2`, `ru3`, `do4` |

**Per-config leaders** — each config declares its own leader per team, chosen
for the course's terrain (a team without a suitable rider for the terrain
simply has a leader who cannot win, which is the intended, expressible
outcome of a bad leader choice):

| Config | `t1` leader | `t2` leader | `t3` leader | `t4` leader |
|--------|------|------|------|------|
| `sprinters_classic` | `ru1` | `sp1` | `pu2` | `sp2` |
| `san_remo` | `ru1` | `sp1` | `pu2` | `sp2` |
| `lombardia` | `gc1` | `pu1` | `pu2` | `gc4` |
| `classics_hilly` | `gc1` | `pu1` | `pu2` | `gc4` |
| `summit_finish` | `gc1` | `pu1` | `gc3` | `gc4` |
| `mountain_stage` | `gc1` | `pu1` | `gc3` | `gc4` |

- `sprinters_classic.json` — flat bunch-sprint style race.
- `san_remo.json` — flat-first + Cipressa/Poggio-style late climbs.
- `lombardia.json` — rolling opener, big climbs late, downhill finish.
- `classics_hilly.json` — long shallow climbs + short steep finale.
- `summit_finish.json` — flat/downhill approach to a summit climb.
- `mountain_stage.json` — sustained climbs with descents between.

`_roster.json` is a reference copy of the shared roster (not loaded by the
engine; the roster is embedded in each config).

### Regression audit (`race_engine/audit.py`)

The way engine changes are validated: runs every bundled config across a
fixed seed set (`1, 7, 42, 123, 2024` by default) and reports, per run, the
winner and archetype, winner time/avg km/h, 1st-2nd and 1st-last gaps, riders
within 5s/30s/60s of the winner, riders finishing at stamina 0, the first
tick+position any rider falls more than 100 m off the front, and per-rider
surge-tick counts. Expected winning archetype per course lives in
`EXPECTED_ARCHETYPE`, a dict literal inside the script — test data, not
engine knowledge, so configs stay free of it.

```
python -m race_engine.audit [--configs a,b] [--seeds 1,7,42] [--jobs 4]
                            [--json out.json] [--baseline base.json]
                            [--tick-cap 3.0]
```

`--json` saves per-run results; `--baseline` loads a prior `--json` output
and prints a before/after delta per course, so a change's effect is visible
in one run. `--tick-cap` (default `3.0`, a multiplier on the winner's finish
tick) stops a run once it's clearly not going to finish in reasonable time —
a bounded guard against Finding 2's unbounded-decay watchdog turning one bad
run into an unbounded one. Before changing engine formulas or reflexes, run
the audit against the unmodified code and save the baseline; after each
change, re-run with `--baseline` and check the delta only moved what the
change was meant to move.

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

### Realism status

Verified with `race_engine/audit.py` (5 seeds) against the real-world
expected winner per course, on the current 16-rider/4-team roster with Tier A
tactics (A1–A4) active:

| Course (scaled) | Realistic winner | Engine winner |
|---|---|---|
| `sprinters_classic` | Sprinter (bunch sprint) | Sprinter, 5/5 seeds |
| `san_remo` | Sprinter-climber / puncheur | Sprinter/puncheur, 5/5 seeds |
| `lombardia` | Climber / puncheur | GC Climber, 5/5 seeds |
| `classics_hilly` | Puncheur / climber | GC Climber, 5/5 seeds |
| `summit_finish` | Pure climber | GC Climber, 5/5 seeds |
| `mountain_stage` | GC climber | GC Climber, 5/5 seeds |

**Known limitation — dropped riders decay without limit — no longer observed
in practice at 16 riders.** A rider who cracks and falls off the back of
every pack has no way back to equilibrium in principle: isolated, their
`sustainable` reference is their own cruise, so `compute_stamina_drain`'s
intensity is pinned at ~1.0 regardless of how slow they go, and
`apply_stamina_cruise_modifier`'s progressive-cracking curve compounds —
stamina keeps falling, cruise keeps degrading, with nothing to break the
loop. The underlying mechanism is unchanged, but going from 11 to 16 riders
gave every straggler more company to fall back on (rotation-averaged
shelter, see below, is credited relative to pack size), so nobody isolates
completely — the regression audit's baseline went from 55 DNFs/20
tick-cap-hit runs (of 30) at 11 riders to **zero** at 16. Not fixed at the
mechanism level; candidate approaches (a recovery term for riding below
one's own cruise, a stamina floor, an "autobus", a time-cut/broom-wagon DNF
rule) remain in Future work below in case a future roster or course change
brings the tail back.

Update this section (and re-run the audit) when engine behavior changes.

## Simulation tick (`RaceState.tick`)

The tick runs in phases so all riders see a consistent snapshot.

1. **Snapshot**: record each non-finished rider's current `position`.
2. **Natural cruise**: for each rider compute their uncontested base speed on the
   current segment's gradient, throttled by stamina (see `compute_base_speed` and
   `apply_stamina_cruise_modifier`), plus per-rider speed jitter. Finalized
   riders and riders past the line are skipped (speed 0).
3. **Decide actions**: for each rider that could surge, apply the tactics rules
   (see Tactics: race phases & surge decisions) using the snapshot positions and
   the pre-computed course profile (terrain look-ahead).
4. **Resolve pack cohesion**: riders within `PACK_COHESION_DISTANCE` of each
   other on a draft-allowed gradient cohere into a pack that rolls at a shared
   tempo chosen for the race situation (`compute_pack_tempo`, see Group tempo).
   A rider
   whose **drafting-credited** cruise falls below that pace is DROPPED (not
   sheltered) — shelter lets a weaker rider hold a higher pace than their solo
   cruise (see Draft hold multiplier). A rider currently surging always rides
   their own pace. No cohesion above `DRAFT_UPHILL_LIMIT` gradient. Each
   coherent rider's pack **depth** (wheels back) is recorded to scale draft
   savings, gap-decayed by physical distance to the wheel ahead (see
   Gap-decayed depth). The `pulling` flag is set only for the pack's front
   rider (depth 0) in a multi-member pack.
5. **Compute deltas** (per rider): final effective speed, energy drain, stamina
   drain, the `pulling` flag — using the shared snapshot, not the mutated
   state.
6. **Apply deltas**: write speed/flags, move each rider by their speed
   (1 tick = 1 s), subtract drains (m meters clamped to `[0, 100]`), mark
   finishers, advance `current_time`.

## Terrain speed (`compute_base_speed`)

A rider's speed on a gradient is the solution to a single power-balance
equation rather than three disjoint lookup tables. For gradient `s` (as a
fraction, e.g. `0.08` for 8%) and per-rider coefficients `K_aero`, `K_roll`,
`K_grav`:

```
K_aero * v**3 + (K_roll + K_grav * s) * v = 1
```

solved for `v` by bisection (`_solve_power_balance`; monotone increasing in
`v` whenever `K_roll + K_grav*s > 0`, true for every gradient these courses
use). `climb` and `flat` stop being two disjoint speed tables and become what
they physically are: power-to-weight and power-to-drag. The blend between
them is not a tuning curve — it falls out of the equation as the ratio of the
gravity term to the aero term. A 1% false flat is mostly aero, so `flat`
decides it; a 10% wall is nearly all gravity, so `climb` decides it;
everything in between interpolates itself. This also removes the old model's
cliff at gradient 0 (a rider's speed no longer jumps discontinuously the
instant a flat road tips into the first tenth of a percent of gradient).

**Per-rider coefficients** (`_rider_resistance_coeffs`), derived from two
calibration anchors via `_lerp(min, max, t)` where `t = (attr − 1) / 99`:

```
v_flat   = lerp(FLAT_MIN_SPEED,  FLAT_MAX_SPEED,  t_flat)     # solo speed at s=0
v_climb8 = lerp(CLIMB_MIN_SPEED, CLIMB_MAX_SPEED, t_climb)    # solo speed at s=CLIMB_REF_GRADIENT

K_aero = AERO_SHARE       / v_flat**3          # aero is 85% of flat resistance
K_roll = (1 - AERO_SHARE) / v_flat             # rolling is the other 15%
K_grav = (1 - K_roll*v_climb8 - K_aero*v_climb8**3) / (CLIMB_REF_GRADIENT * v_climb8)
```

Constants: `FLAT_MIN_SPEED = 12.0`, `FLAT_MAX_SPEED = 14.2` (43.2-51.1 km/h);
`CLIMB_MIN_SPEED = 3.5`, `CLIMB_MAX_SPEED = 6.1` (12.6-22.0 km/h at
`CLIMB_REF_GRADIENT = 0.08`); `AERO_SHARE = 0.85`.

**Downhill** (`gradient < 0`) uses the same equation, then applies a handling
cap — on a real descent the limit is cornering and braking, not power:
`min(v, lerp(DOWNHILL_MIN_SPEED, DOWNHILL_MAX_SPEED, t))` where
`t = ((sprint + flat) / 2 − 1) / 99` (`DOWNHILL_MIN_SPEED = 17.0`,
`DOWNHILL_MAX_SPEED = 21.0`, i.e. 61-76 km/h) — keeping the "descending blends
sprint and flat" idea as a cap rather than the primary formula.

Coefficients and solved speeds are memoised per `(flat, climb, gradient)` —
gradients are per-segment constants, so this is a few dozen solves per race,
not one per tick. Real-world spread this model reproduces: ~7-12% between
fastest/slowest archetype on the flat, ~25-40% on a 5% climb, ~35-55% on 8%
(see `test_speeds.py`'s calibration table for the full band-by-gradient
breakdown per archetype).

Per-tick jitter: `speed += uniform(−0.3, 0.3)`, floored at 1 m/s
(`add_speed_jitter`). This breaks perfect ties so groups form a realistic echelon.

## Stamina

### Cruise modifier (`apply_stamina_cruise_modifier`)
Sustainable base speed is unchanged while `stamina >= 60`. Below 60 it degrades
progressively (`progressive cracking`):
`base_speed × (max(0, stamina / 60) ^ 0.7)`.

### Drain (`compute_stamina_drain`)
Charged on **relative intensity**, not on wall-clock time. Per tick:
```
sustainable = own_speed × draft_hold_multiplier(positioning, eff_depth, gradient)
intensity   = speed / max(1, sustainable)             # 1.0 = riding at your limit
drain = 0.012 × intensity ** 3                        # aerobic cost of the effort
drain *= 1 − (resistance / 100) × 0.6                 # fatigue tolerance
drain *= speed / 13.4                                 # DRAIN_REFERENCE_SPEED — distance, not ticks
if gradient > 0: drain *= 1 + gradient × 0.20         # climbs cost more
if gradient < 0: drain −= 0.006                       # descents recover a little
```
Stamina is clamped to `[0, 100]`.

`sustainable` is the **same draft-credited reference** used by the pack-cohesion
drop test and by `compute_energy_drain`, so shelter is credited exactly once, in
one place, to all three. There is deliberately no separate
`draft_stamina_factor`.

The cubic exponent is what makes soft-pedalling in the wheels genuinely restful:
an easy bunch tempo runs at intensity ~0.6–0.8 and so costs 20–50 % of riding at
your limit, while hanging on above your means costs steeply more. The previous
formula's speed term (`(speed − 10) × 0.010`) varied drain by only a few percent
across the whole speed range, which charged fatigue per second regardless of
effort — so slowing the bunch down made a race *more* tiring, not less.

The `speed / DRAIN_REFERENCE_SPEED` term makes drain scale with **distance
covered**, not wall-clock ticks. Fatigue is fundamentally a cost of work done,
not of time elapsed at a given relative effort. Without it, the resistance
model's correctly slower climbing speeds (see Terrain speed above — climbing
at 8% roughly halved from the old model's ~41 km/h to ~20 km/h) would double a
climb's tick count and therefore double its cumulative stamina cost even at
intensity 1.0 (a rider riding exactly their own sustainable pace, no
overshoot at all) — cracking riders who are doing nothing wrong.
`DRAIN_REFERENCE_SPEED = 13.4` m/s is the old model's mid-flat speed; the new
model's mid-flat speed (13.1 m/s) still matches closely, so flat-terrain
drain is essentially unchanged and only climbs (where speed drops sharply)
scale down.

## Energy

`compute_energy_drain` returns a positive cost (drain) when the rider is working
above the pace their current shelter lets them sustain, or a negative value
(recovery) when riding within it:
```
sustainable = own_speed × draft_hold_multiplier(positioning, depth, gradient)
overshoot   = max(0, effective_speed − sustainable)   # excess over what shelter buys
intensity   = overshoot × 0.10
if intensity > 0: return intensity                     # drained
return −0.008                                          # recovered while within your means
```
`sustainable` is the **same reference the pack-cohesion drop test uses**, so a
rider the engine says can hold the tempo is not simultaneously charged for
holding it. There is deliberately no separate `draft_energy_factor`: shelter is
credited to the anaerobic reserve exactly once, through this reference speed.
`apply_energy_burst_modifier` throttles burst speed when energy is low: unchanged
while `energy >= 40`, else `speed × (0.5 + 0.5 × (energy / 40))`. This caps
surges without throttling steady cruising (which stamina governs). Energy is
clamped to `[0, 100]`.

## Drafting & pack cohesion

Riders cluster into **packs** and share a sustainable tempo rather than each
riding at maximum. Shelter within a pack is set by the rider's position (depth)
and their `positioning` skill, so a skilled deep rider conserves more than an
exposed or socially-sheltered one.

Shelter reaches the rest of the engine through **exactly one channel**: the
speed a sheltered rider can hold for free (`draft_hold_multiplier`). The drop
test, the energy model and the stamina model all measure effort against that
same speed. Crediting shelter a second time — as separate stamina/energy
keep-fractions once did — meant a rider the engine said could hold the tempo was
simultaneously charged for holding it.

- `PACK_COHESION_DISTANCE = 60.0` m — riders within this of each other on a
  draft-allowed gradient cohere into a single pack (connected-component BFS).
  This governs pace-sharing / dropping, not any physical proximity label.
- `DRAFT_UPHILL_LIMIT = 5.0` % — no cohesion/drafting on steeper climbs.
- **No standalone "drafting" flag.** There used to be one, set from a rider's
  nearest wheel within `DRAFT_DISTANCE` in any direction — independent of
  real pack membership, so a rider deep in a coherent pack with no
  *particularly* close neighbour showed neither `drafting` nor `pulling`,
  while a rider outside a real pack could show `drafting` from a passing
  near-miss. Real shelter is continuous (see Gap-decayed depth below) — most
  pack members get *some* benefit, to varying degrees — and that doesn't
  compress into a meaningful boolean. Only `pulling` (see Pack depth below)
  is exposed: the pack's front rider is assumed to be doing the work, and
  every other coherent member is assumed to be benefiting.
- **Group tempo** (`compute_pack_tempo`) — a pack rolls at
  `pace_setter_speed(member_speeds) × pack_tempo_fraction(...)`.
  `pace_setter_speed` is the **median of the strongest third** of the pack's
  cruises, not `max()`: one jittered outlier should not dictate the tempo for
  the whole bunch. The fraction is **situational**, because a real bunch only
  rides near its ceiling when it has a reason to:

  | Situation | Fraction |
  |---|---|
  | Everyone still willing to chase (`chase_willingness = 1.0`) on draftable terrain (`gradient <= DRAFT_UPHILL_LIMIT`) | `PACK_TEMPO_CHASE` = 1.08 |
  | Someone clear up the road (> `BREAK_CLEAR_DISTANCE` = 60 m ahead of the pack's front rider) on steeper terrain, or finale (`remaining < TRANSITION_PHASE_THRESHOLD`) | `PACK_TEMPO_HARD` = 0.90 |
  | Transition phase (`remaining < EARLY_PHASE_THRESHOLD`), or early on climbing terrain | `PACK_TEMPO_STEADY` = 0.82 |
  | Early **and** flat **and** nobody up the road | `PACK_TEMPO_EASY` = 0.75 |

  `PACK_TEMPO_CHASE` (> 1.0×) reflects that a rotating, drafting bunch shares
  the wind and so is genuinely faster than any solo rider on the flat — this
  is why real flat breaks get caught. Above `DRAFT_UPHILL_LIMIT` there is no
  wind to share (power-to-weight dominates, not drag), so the chase falls
  back to `PACK_TEMPO_HARD` and a climber who attacks on a real climb stays
  away. This band depends on rotation-averaged shelter (below): chasing above
  1.0× the pace-setter reference would shed the pack one rider at a time from
  the front without it.

  **Teammate-aware chase willingness (Tier A3)** — `break_ahead` used to be a
  single pack-wide bool ("is anyone clear up the road"). It is now
  `chase_willingness`, the **fraction of the pack** that sees a break worth
  chasing: each member checks whether any rider clear ahead (the same
  `BREAK_CLEAR_DISTANCE` test) is on a *different* team than themself —
  chasing down your own teammate's break helps nobody, so a member whose own
  team is the one up the road doesn't count as willing. `pack_tempo_fraction`
  interpolates linearly between the no-break tempo (`chase_willingness = 0`)
  and the full chase tempo (`chase_willingness = 1`) rather than snapping
  between two fixed values, so one team with a rider away genuinely blunts
  the chase without unilaterally calling it off for every other team still
  racing normally. The bridge rule's `_nearest_clear_leader` (see Tactics
  below) applies the same team filter: bridging to your own teammate isn't
  chasing a break, it's just riding up to them.

  A rider is DROPPED (rides alone, not sheltered) only if their
  **drafting-credited** cruise is below that tempo — see `draft_hold_multiplier`
  below. A sheltered rider can hold a higher pace than their solo cruise; an
  exposed rider (depth 0) gets no credit and is dropped if their own cruise can't
  hold the tempo.
- **Finished riders provide no shelter** — excluded when finding pack neighbours,
  so a frozen finish-line bunch cannot shelter riders.
- **Pack depth** — within a coherent pack, the rider with the front position is
  the puller (depth 0, exposed); each wheel behind gains a deeper shelter
  (depth 1, 2, …). Shelter quality scales with depth up to
  `DRAFT_DEPTH_SATURATION (10)`. This ordinal depth (rank within the pack) is
  then adjusted by gap-decay and rotation-averaging below before it reaches
  `draft_hold_multiplier` — the raw rank alone is not what the fatigue
  formulas or the drop test actually use.
- **Gap-decayed depth** — real drafting benefit falls off sharply with
  physical distance to the wheel ahead; ordinal rank alone doesn't capture
  that a rider two wheels back on paper but far off the wheel ahead isn't
  meaningfully sheltered. For each pack-coherent rider at depth `d >= 1`, a
  `gap_factor` scales that depth before it reaches `draft_hold_multiplier`:
  ```
  gap = distance to the wheel immediately ahead in the pack's chain
  gap_factor = clamp(1 - max(0, gap - DRAFT_DISTANCE) / (PACK_COHESION_DISTANCE - DRAFT_DISTANCE), 0, 1)
  ```
  `gap_factor` is 1.0 (full ordinal credit) for any gap `<= DRAFT_DISTANCE`
  (3 m — the closest a rider can sit to the wheel ahead), and decays
  linearly to 0 as the gap approaches `PACK_COHESION_DISTANCE` (60 m,
  the edge of the pack itself). `depth 0` (the pack front) is unaffected —
  `draft_hold_multiplier` already special-cases `depth < 1` to no credit
  regardless.
- **Rotation-averaged depth for the drop test and fatigue reference**
  (`ROTATION_SHARE_LEADER = 0.65`, `ROTATION_SHARE_SUPPORT = 0.35`) — real
  bunches rotate, so nobody rides a whole race at their instantaneous depth.
  Using raw instantaneous depth charged whoever happened to be a half-wheel
  ahead a given tick as fully exposed (depth 0, no draft credit), which
  could shed them on a single jitter tick. The pack-cohesion drop test and
  the `sustainable` reference fed to the energy/stamina drain formulas use
  ```
  eff_depth = max(depth * gap_factor, rotation_share * (pack_size - 1) * gap_factor) + teammate_bonus
  ```
  instead of raw depth — every rider is credited with at least "sometimes
  near the front, sometimes not" shelter. Scaling the rotation floor by the
  *same* `gap_factor` (rather than leaving it unconditional) keeps the two
  corrections consistent: the floor still protects a rider from one noisy
  tick's ordinal position, but it no longer overrides a genuinely large,
  sustained physical gap — this combination is what keeps gap-decay from
  reintroducing the coin-flip drops rotation-averaging was built to remove.
  Inert above `DRAFT_UPHILL_LIMIT`, where `draft_hold_multiplier`'s `drag`
  term already fades to 0.

  **Role-scaled rotation floor (Tier A2)** — `rotation_share` is no longer a
  single pack-wide constant. A `role == "leader"` rider uses
  `ROTATION_SHARE_LEADER` (0.65) and a `role == "support"` rider uses
  `ROTATION_SHARE_SUPPORT` (0.35), so supports are credited with less "often
  near the front" shelter (they really do take more than their share of
  front-line time for the team) and leaders with more (teammates hand them
  more shelter than their instantaneous position alone would credit). This
  biases the *rotation average* the fatigue formulas see; a leader
  physically at the front this tick still pulls (depth 0, `pulling=True`) —
  the geometry is untouched, only the fatigue reference. A solo rider (team
  of one, `role` defaults to `"leader"`) always gets the generous end, same
  as every rider did before teams existed.

  **Teammate shelter priority (Tier A1)** — `teammate_bonus` adds
  `TEAMMATE_SHELTER_BONUS` (1.0), scaled by the same `gap_factor`, to a
  rider's `eff_depth` whenever the wheel immediately ahead of them in the
  pack's chain belongs to a rider on their own team. Real teams hand each
  other wheels deliberately; strangers in a pack merely happen to be near
  each other. Additive (not multiplicative) so it matters most for a rider
  already close enough to be credited at all, and does nothing for one too
  far off the wheel to shelter regardless of who is up there.

  A1 and A2 both favor the leader and are known to stack (see Risks in
  `TEAM_TACTICS_PLAN.md`); the audit's leader-vs-support finish-order/stamina
  check (below) is what catches an over-tuned combination.

### Shelter quality (`shelter_quality`)
The 0–1 blend of draft skill and pack depth that `draft_hold_multiplier` is
built from. `depth` here is the gap-decayed, rotation-averaged effective
depth from above, not raw ordinal rank:
```
skill = (positioning − 1) / 99                       # 0..1
depth_factor = min(depth, 10) / 10                   # 0..1
quality = clamp(0.6 × skill + 0.4 × depth_factor, 0, 1)
```

### Draft hold multiplier (`draft_hold_multiplier`)
The drop test uses a rider's **drafting-credited** cruise rather than their raw
solo cruise, so a weaker rider sheltering in a strong group can hold the tempo.
It is also the reference speed **both** fatigue meters measure effort against
(`compute_energy_drain`'s overshoot and `compute_stamina_drain`'s intensity).
```
quality = shelter_quality(positioning, depth)
drag = 1 − min(1, max(0, gradient) / DRAFT_UPHILL_LIMIT)   # fades on climbs
multiplier = DRAFT_HOLD_MIN + (DRAFT_HOLD_MAX − DRAFT_HOLD_MIN) × quality × drag
```
`DRAFT_HOLD_MIN = 1.0`, `DRAFT_HOLD_MAX = 1.30`. A rider at depth 0 (pulling/solo)
uses 1.0 (no save). The credit fades to 1.0 as gradient rises to
`DRAFT_UPHILL_LIMIT`, because drafting is hugely effective on flats (a sheltered
climber holds the bunch's flat pace despite a low `flat` attribute) but nearly
useless on a sustained climb — so weak climbers are protected on flats but not on
climbs, and climber-leaning courses still split correctly.

### Pulling
`pulling=True` for exactly the pack's front rider (`depth == 0`) in any
coherent pack with more than one member — the rider actually setting the
tempo the rest of the pack is riding at. This replaced a standalone pairwise
test ("not drafting, and someone within `DRAFT_DISTANCE` directly behind"),
which needed a close trailing wheel to fire and so often missed the true
pace-setter (e.g. if the next rider back happened to be 10+ m adrift that
tick) while occasionally flagging a mid-pack rider as pulling just because
someone was momentarily close behind *them*. A solo rider, or one outside any
multi-member pack, never pulls.

## Tactics: race phases & surge decisions

The engine's rule-set is a set of *reflexes* layered over emergent group
behavior (drafting, pace-sharing, fatigue cracking), with one reflex
(rule 3, Bridge to a break, below) gated by team role — see Tier A4 and A3.
It is **not** a full team-tactics model; finer roles and cross-team
cooperation remain a future concern (see Future work). Reflexes are terrain-
and phase-aware: riders evaluate their situation (remaining distance, terrain
ahead, their own energy budget) before choosing to surge, so they only make
efforts they can plausibly sustain — mimicking how a real pro manages a race.

### Course profile (terrain look-ahead)

Pre-computed once at race start and attached to `RaceState` as `profile`
(`CourseProfile`). It classifies each course segment by its (whole-segment
average) gradient:

- **FLAT** — `< TERRAIN_MODERATE_THRESHOLD (3.0)` %
- **MODERATE** — `3.0` % to `< TERRAIN_STEEP_THRESHOLD (7.0)` %
- **STEEP** — `>= 7.0` %

Each `SegmentProfile` records its `length`, `gradient`, cumulative
`start_distance`, and `terrain` bucket. The profile exposes terrain-at-position,
remaining distance (and fraction), and the steepest gradient within a look-ahead
window. Riders have full route knowledge (realistic for pro cyclists).

### Race phases

Defined by remaining distance as a fraction of the total course length:

| Phase | Remaining | Rider behavior |
|---|---|---|
| **Early** | `> 25%` | No attacking. Ride in pack, conserve energy. |
| **Transition** | `10–25%` | Positioning; attack only in the finale-approach. |
| **Finale** | `< 10%` | Attacks and the contest for the finish. |

Constants: `EARLY_PHASE_THRESHOLD (0.25)`, `TRANSITION_PHASE_THRESHOLD (0.10)`.

### Energy budgeting

Riders only launch an effort they can plausibly finish:
- A normal surge/attack needs `energy >= SURGE_MIN_ENERGY (30.0)`.
- A finish sprint costs more and needs `energy >= SPRINT_MIN_ENERGY (35.0)`.
- A bridge/chase needs `energy >= CHASE_MIN_ENERGY (25.0)`.

### Surge mechanics

A surge is a discrete ~20s energy-burst effort (`SURGE_DURATION = 20` ticks),
burning `SURGE_ENERGY_COST = 0.05` extra energy per tick. A surging rider
breaks from drafting and rides their own pace. An attack or bridge/chase gets
a flat `SURGE_SPEED_BOOST = 0.25` fraction above the rider's natural cruise.
A finish sprint is a **longer kick** (`SPRINT_DURATION = 40` ticks) — the
sprinter sustains the burst further to the line — and its boost is **sized by
`sprint`** rather than flat:
`boost = lerp(SPRINT_BOOST_MIN, SPRINT_BOOST_MAX, t_sprint)` where
`t_sprint = (sprint − 1) / 99` (`SPRINT_BOOST_MIN = 0.05`,
`SPRINT_BOOST_MAX = 0.35`). `RiderState.sprinting` marks which kind of surge
is active so `tick()` applies the right boost; it clears when the surge ends
and is engine-internal (not written to the JSONL log).

### Refusal conditions
A rider does **not** start a surge if they are finished, already surging
(`surge_ticks > 0`), cooling down (`surge_cooldown > 0`), whose energy is below
the effort's minimum (see Energy budgeting), or who fails the relevant
terrain/phase/strength gate below.

### Decision chain (`_decide_actions` — first matching rule wins, in this order)
1. **Finish sprint** — within `SPRINT_DISTANCE (1000 m)` of the finish.
   **Everyone kicks**; `sprint` sizes the boost (see Surge mechanics above),
   it no longer gates eligibility. A weak sprinter's kick is simply worth
   less — the sprint finally resolves on the `sprint` attribute rather than
   being a yes/no gate that left every qualifying rider's kick identical.
2. **Attack a climb** — remaining `< ATTACK_PHASE_THRESHOLD (25%)`, current
   terrain bucket `STEEP` (gradient `>= 7.0` %), and `climb >= ATTACK_MIN_CLIMB (75)`.
   A strong climber tries to break away only in the late race on a genuinely
   steep section.
3. **Bridge to a break** — team leaders don't consider this rule at all
   (**Tier A4**: a leader sits in and saves themself for the finale instead
   of spending energy on a speculative early move — that's what support
   riders are for). For a `role == "support"` rider: only those at the front
   of their own group (`depth <= BRIDGE_MAX_DEPTH (2)`, computed by
   `_group_front_and_depth` over the rider's own
   `PACK_COHESION_DISTANCE`-chained neighbours, not the absolute race
   leader) consider it, and only when someone is **genuinely clear** —
   `_nearest_clear_leader` finds a rider more than `BREAK_CLEAR_DISTANCE`
   (60 m) ahead of the group's front, the same test pack tempo's
   `chase_willingness` uses, **excluding the chaser's own teammates** (Tier
   A3: bridging to your own teammate isn't chasing a break, it's just riding
   up to them, so it isn't evaluated — or energy-gated — as a chase). Gap to
   that leader must be `<= BRIDGE_GAP_MAX (150 m)`, `remaining_fraction <
   ATTACK_PHASE_THRESHOLD (0.25)`, and `_can_chase` must pass (on steep
   terrain, don't chase a leader who is markedly a stronger climber —
   `CHASE_MIN_CLIMB_ADVANTAGE = -10` points).

   Rules 1 (finish sprint) and 2 (climb attack) stay role-blind — a team
   leader must still be able to attack a climb or contest the sprint, that
   is their whole purpose; only the speculative bridge move is gated by role.

   This replaced a much looser rule ("no wheel within `DRAFT_DISTANCE`
   ahead, and a 3-30 m gap to the absolute race leader") that every rider in
   a strung-out bunch satisfied every tick — the gate wasn't "a break is
   clear", it was "I am not glued to a wheel", so a normally-spaced peloton
   read as eleven simultaneous breakaways the moment `remaining_fraction`
   crossed its old threshold.

### Cooldown
On starting a surge a rider sets `surge_ticks = SURGE_DURATION` (or
`SPRINT_DURATION` for a finish sprint) and `surge_cooldown = SURGE_COOLDOWN
(60 ticks)`. `surge_ticks` and `surge_cooldown` both decrement per tick,
preventing runaway/back-to-back surges (a rider can make a fresh effort only
after the cooldown elapses).

> Effect on terrain balance: gating attacks by phase and steepness makes
> climber-leaning courses play out realistically — the pack stays together
> through the early and middle race, and the decisive moves come on the late
> steep climbs. Long flat courses used to be unaffected by the attack gate
> (no STEEP terrain) and were decided by an unmanaged drag race once the old
> chase rule's loose gap window fired for the whole bunch at once (a
> "rouleur bias" — the strongest flat engine won a drag race nobody
> organized, not because rouleurs were tactically favored). The bridge
> rewrite above, together with the resistance-model speed fix
> (Terrain speed) and rotation-averaged shelter (Drafting & pack cohesion),
> closed it: `sprinters_classic` now resolves as a genuine bunch sprint.

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
      "team": "t1",
      "role": "leader",
      "pos": 15234.56,
      "speed": 13.42,
      "energy": 62.1,
      "stamina": 88.9,
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
| `team` | team id (`Rider.team_id`; a team of one uses its own `id`) |
| `role` | `"leader"` or `"support"` |
| `pos` | meters from start, rounded to 2 dp |
| `speed` | effective speed this tick, m/s, rounded to 2 dp |
| `energy` | anaerobic reserve 0–100, rounded to 2 dp |
| `stamina` | aerobic endurance 0–100, rounded to 2 dp |
| `pulling` | setting the pace at the front of a multi-member pack this tick |
| `surging` | in a surge effort this tick |
| `finished` | crossed the line |
| `finish_time` | finish tick, or `null` |

Bytes are exact (no line wrapping). Consumers may aggregate frames by `time`.
Note there is currently **no** per-tick event/commentary stream; a visualizer
derives narrative purely from these snapshots.

## Future work / possible improvements

Backlog items — not planned, not scheduled, just recorded so a future
decision to implement (or not) is informed rather than a re-discovery. Size
is a rough shirt-size estimate (small/medium/large), not a scoped plan.

### Broom wagon (time-cut DNF)

**Problem it solves:** the "Known limitation" above (dropped riders decay
without limit) currently manifests as absurd finish times in the tail of the
field — a cracked rider can take hours longer than the winner instead of
abandoning, which is what would actually happen. A broom wagon rule doesn't
fix the underlying death-spiral (see below), it just stops the engine from
reporting a nonsense result: once a rider falls more than some threshold gap
behind the leader (real racing uses a time cut, e.g. a % of the winner's
time, or an absolute distance/time gap), they're marked DNF instead of
crawling to an eventual, meaningless finish.

**Size: small.** A single check in `RaceState.tick()` (or the results
step) — no new mechanic, just a threshold and a `finished`-like DNF state on
`RiderState`. The audit harness already has a `--tick-cap` escape hatch
(`race_engine/audit.py`) that approximates this for regression-testing
purposes; a real broom wagon would need a home in the engine itself, plus a
decision on where DNF riders show up in `get_results()` and the JSONL output
(a new `dnf: bool` field, most likely).

**Caveat:** a broom wagon alone treats the symptom, not the cause. It should
probably ship together with (or after) the autobus below — otherwise a
courageous but genuinely mid-pack rider who has a bad patch gets the same
DNF treatment as one who's catastrophically cracked, since nothing lets a
dropped rider recover before the cutoff.

### Autobus (dropped riders group up)

**Problem it solves:** the same death-spiral, addressed at the mechanism
rather than papered over. Real dropped riders don't time-trial alone to
exhaustion — they find each other and ride a shared, survivable tempo
(literally called the "autobus" or "grupetto" in pro cycling). The engine's
existing pack-cohesion machinery (`PACK_COHESION_DISTANCE` BFS, shared
tempo, gap-decayed shelter) already does almost everything needed; the gap
is that a rider whose credited cruise can't hold the *main* pack's tempo is
simply dropped, with no fallback second-tier grouping among similarly-paced
stragglers.

**Size: medium.** Plausible shape: once one or more riders are dropped from
the main pack, run the same cohesion/tempo logic over just the dropped
riders as a second, slower peloton (its own `pace_setter_speed`, its own
`chase_willingness`, at a survival-oriented tempo fraction below
`PACK_TEMPO_EASY`) rather than leaving them all fully isolated. Needs care around: riders
dropped at different times/positions re-cohering into the bus without a
teleport, whether a strong rider can bridge back to the main pack from the
bus, and whether the bus itself can further shed its weakest riders (to the
broom wagon, if that's implemented) rather than being a floor everyone
sinks to. Should be audited the same way as the Finding-1 work (baseline
before, `race_engine/audit.py` after, watch for regressions on the six
bundled configs) since it touches the same pack-cohesion code path every
other course result depends on.

### Shelter-quality retune (small, deferred)

`shelter_quality`'s skill/depth blend (`0.6 × skill + 0.4 × depth_factor`)
and `DRAFT_DEPTH_SATURATION` (10) were flagged as worth retuning in an
earlier investigation — reweighting toward depth and lowering the
saturation point (3-4 wheels back should already be ~full shelter, not 10)
— but never implemented, and the resistance-model speed rewrite changed
enough of the surrounding math that the specific old numbers aren't
trustworthy without re-deriving them against the current model. **Size:
small**, but needs fresh calibration work, not a drop-in constant change.

### Team tactics Tier B (finer roles, negotiated cooperation)

**Problem it solves:** Tier A (implemented; see "Team and role" in Data
model and the A1–A4 biases threaded through Drafting & pack cohesion and
Tactics above) gives every team exactly one protected leader and undifferentiated
support riders. Real team tactics have finer structure: a designated
lead-out man who times a sprint train rather than just "a support rider,"
a road captain who reads the race and directs teammates mid-race, and
riders from *different* teams cooperating in a break (an alliance of
convenience against the chasing bunch) — none of which Tier A's two-role
model expresses.

**Size: medium-large.** Unlike Tier A (biases layered onto computations that
already run every tick, no new subsystem), finer roles likely need their
own state — a lead-out sequencing mechanic tied to `SPRINT_DISTANCE`/phase,
a road-captain decision override on teammates' surges, or a shared
"break coalition" concept that the chase-willingness fraction (Tier A3)
doesn't currently have any notion of (right now the model only reasons
about *your own* team, never a temporary alliance with a rival's rider up
the road). Explicitly out of scope until Tier A's tuning is validated
against actual gameplay (see `TEAM_TACTICS_PLAN.md`, which also scopes
Tier C — dynamic leader reassignment, negotiated break cooperation, rival
marking — as out of scope entirely, not just deferred).

## Submission / commit procedure

The engine, its module layout, and this spec are under active development.

- **Keep this file current**: after any change to the engine's data model,
  formulas, constants, tick logic, or output format, update `DOMAIN.md`
  to match before committing.
- **Review ask**: before committing, re-read `DOMAIN.md`; if the pending changes
  alter anything described here, apply the needed edits to it, then ask
  the user to review the diff and explicitly approve before committing. Do not
  commit until the user confirms.
- **Scope of commits**: commit only intentional work (exclude stray/unrelated
  edits such as local test-course tweaks unless the user includes them).