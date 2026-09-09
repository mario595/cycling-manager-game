# Plan — Finding 1: make a flat classic finish in a bunch sprint

Target: `ENGINE_FINDINGS.md` Finding 1 (rouleur bias on `sprinters_classic`),
the last wrong course. Companion to `FLAT_PACK_PLAN.md`, which fixed the pack's
*flat-section* behaviour; this one fixes what the race does **from the first
ramp to the line**.

## 1. Corrected diagnosis

`ENGINE_FINDINGS.md` records the cause as "the rouleurs press off the front in
the finale and nobody organises a chase". Instrumenting seed 1 tick by tick,
that is not what happens. **No rouleur ever attacks** — `sprint 55-60` is below
`SPRINT_MIN_SPRINT`, and there is no STEEP terrain, so neither the sprint nor
the attack reflex can fire for them. The race is lost in two separate places,
neither of them a missing chase.

### 1a. The sprinters are dropped at km 90, on a 2.5 % drag

`Sprinter 1`'s gap first exceeds 100 m at **tick 8357, position 90,218 m** —
the first metres of the 4 km / 2.5 % ramp. By tick 9000 both sprinters are
**2.7 km** down. They are shelled before any tactic fires.

The cause is `compute_base_speed`. At `gradient == 0` it maps the `flat`
attribute; the instant `gradient > 0` it switches to a **pure `climb` map**.
There is a cliff at zero:

| rider | 0.0 % | 0.1 % | 2.5 % |
|---|---|---|---|
| `sp1` (flat 82, climb 26) | 14.55 m/s | **6.90 m/s** | 6.21 m/s |
| `gc1` (flat 40, climb 94) | 11.15 m/s | 13.37 m/s | 12.76 m/s |

A false flat turns a sprinter into a 22 km/h rider and a GC climber into a
46 km/h rider — a **106 % spread on a 2.5 % drag**, where real life gives about
10 %. The pack tempo on that ramp is 9.3 m/s; the sprinter's draft-credited
cruise is 6.99 m/s. The drop is arithmetic, not tactics, and **no tactical fix
can let a sprinter win this course while it stands**.

### 1b. At km 110 the entire bunch chase-surges at once

Every rider except the two dropped sprinters starts surging within 6 ticks of
each other, at **tick 10113-10119, position ~110.5 km** — precisely where
`remaining_fraction` crosses `CHASE_DISTANCE_MAX` (0.15).

Rule 3 reads: *no wheel within 3 m ahead, and someone is 3-30 m up the road*.
In a bunch that is strung out over 30 m, **every rider satisfies that every
tick**. There is no break; they are chasing each other's wheels. The gate was
never "a break is clear", it was "I am not glued to a wheel".

The result is that the last 19.5 km become an unmanaged drag race in which
surging riders leave the pack and ride their own pace. `Rouleur 2` spends 297
ticks surging, `Rouleur 1` 114. The strongest flat engine wins a flat drag
race — which is the observed "rouleur bias", arrived at by accident.

### 1c. Baseline to beat (seed 1, HEAD `81b4267`)

```
1. Rouleur 1     11684s   2. Rouleur 2   11686s   3. Puncheur 1  11745s
...
10. Sprinter 1   11866s  (+182s)        11. Sprinter 2  11867s  (+183s)
```
- winner avg **40.1 km/h**; 1st-to-last spread **183 s**
- riders within 5 s of the winner: **2**
- sprinters detached from km 90.2 onward; whole-bunch surge from km 110.5

## 2. What we change

Three root causes, in dependency order. Each phase is independently revertable
and independently measured by the audit harness (§3).

### Phase 1 — Replace the three speed maps with one resistance model

This is `FLAT_PACK_PLAN.md` Step 6, done properly rather than by narrowing
`FLAT_MIN_SPEED`. It removes the cliff at gradient 0, and it fixes the second
half of the same problem: the attribute spreads are wrong at **every** gradient
(32 % on the flat where reality is 8-12 %; 106 % on a shallow drag; 105 % on a
climb where reality is ~40 %).

Replace `compute_base_speed`'s three lerps + `GRADIENT_PENALTY` +
`DESCENT_BOOST` with a single power balance. A rider's steady speed `v` on
gradient `s` is the root of

```
K_aero * v**3  +  (K_roll + K_grav * s) * v  =  1
```

with the three coefficients derived per rider from two calibration anchors:

```
v_flat   = lerp(FLAT_MIN_SPEED,  FLAT_MAX_SPEED,  t_flat)    # solo speed at s = 0
v_climb8 = lerp(CLIMB_MIN_SPEED, CLIMB_MAX_SPEED, t_climb)   # solo speed at s = 8 %

K_aero = AERO_SHARE       / v_flat**3          # aero is 85 % of flat resistance
K_roll = (1 - AERO_SHARE) / v_flat             # rolling is the other 15 %
K_grav = (1 - K_roll*v_climb8 - K_aero*v_climb8**3) / (0.08 * v_climb8)
```

Solve by bisection (monotone in `v` for `K_roll + K_grav*s > 0`), memoised on
`(rider_id, gradient)` — gradients are per-segment constants, so this is a few
dozen solves per race, not one per tick.

Descents (`s < 0`) use the same equation and are then clamped by a handling cap
`lerp(DOWNHILL_MIN_SPEED, DOWNHILL_MAX_SPEED, t_(sprint+flat)/2)` — on a real
descent the limit is cornering and braking, not power, and this keeps the
existing "descending blends sprint and flat" idea.

**Why this is the honest version.** `climb` and `flat` stop being two disjoint
speed tables and become what they physically are: power-to-weight and
power-to-drag. The blend between them is not a tuning curve, it is the ratio of
the gravity term to the aero term, which falls out of the equation. A 1 % false
flat is mostly aero, so `flat` decides it; a 10 % wall is nearly all gravity, so
`climb` decides it; everything in between interpolates itself.

**Proposed constants** (calibrated against real pro speeds, prototype-verified):

```
FLAT_MIN_SPEED  = 12.0   FLAT_MAX_SPEED  = 14.2    # 43.2 - 51.1 km/h solo
CLIMB_MIN_SPEED =  3.5   CLIMB_MAX_SPEED =  6.1    # 12.6 - 22.0 km/h at 8 %
DOWNHILL_MIN_SPEED = 17.0  DOWNHILL_MAX_SPEED = 21.0   # 61 - 76 km/h cap
AERO_SHARE = 0.85        CLIMB_REF_GRADIENT = 0.08
```

Resulting roster speeds (km/h) and, in the last row, the fast/slow ratio — the
number that must look like real racing:

| gradient | `gc1` | `pu1` | `ru1` | `sp1` | spread |
|---|---|---|---|---|---|
| 0 % | 46.3 | 47.9 | 49.5 | 49.7 | **1.07** |
| 1 % | 42.4 | 43.2 | 43.9 | 42.7 | 1.03 |
| 2.5 % | 36.8 | 36.5 | 36.0 | 33.2 | **1.11** |
| 5 % | 28.6 | 27.2 | 25.6 | 22.1 | **1.30** |
| 8 % | 21.4 | 19.7 | 18.0 | 15.0 | **1.43** |
| 12 % | 15.5 | 14.0 | 12.6 | 10.3 | **1.50** |
| -5 % | 65.6 | 70.9 | 71.2 | 74.1 | 1.13 |

The 1 % row is the crossover, where the climber's aero limit and the sprinter's
weight penalty cancel and the field converges — physically correct, and it is
what makes a false flat a place where nobody gets dropped.

Real cycling: ~10 % spread on the flat, ~30 % on a 5 % climb, ~45 % on a steep
one. The model reproduces that shape from two anchors.

Estimated winner averages after the change (pure course-time estimate, all six
configs): **43.0 / 42.2 / 35.5 / 32.0 / 35.4 / 32.4 km/h** — all inside the
real-world band, and climbing courses correctly slower than they are today
(a top climber currently rides an 8 % climb at **41 km/h**).

### Phase 2 — Rotation-averaged shelter in the drop test

Today `depth_of[m]` is the rider's **instantaneous** rank in the pack, so
whoever happens to be 30 cm ahead is charged as fully exposed (depth 0, no
draft credit) and can be shed by a single jitter tick. Real bunches rotate;
nobody is on the front for a whole race.

For the **drop test and the fatigue reference only**, use an effective depth

```
eff_depth = max(depth, ROTATION_SHARE * (pack_size - 1))    # ROTATION_SHARE = 0.5
```

The `drafting` / `pulling` display flags keep using instantaneous position, so
the visualizer is unchanged.

This is a smaller and more principled version of `FLAT_PACK_PLAN.md` Step 4
(hysteresis + elastic): it removes the coin-flip drop at the source instead of
adding a grace timer on top of it. It is inert above `DRAFT_UPHILL_LIMIT`
(5 %), where packs do not form at all, so the climbs stay as selective as they
are now.

### Phase 3 — Make the chase reflex mean "a break is clear"

Two changes, one deletion.

**3a. Define "clear" once.** `break_ahead` already exists for pack tempo:
someone more than `BREAK_CLEAR_DISTANCE` (60 m) ahead of the pack's front
rider. Rule 3 uses that same test instead of its own 3-30 m window. No break,
no chase — which alone deletes the km-110 free-for-all.

**3b. Only the front of the group bridges.** Add `depth <= BRIDGE_MAX_DEPTH`
(2) to the chase gate. Riders bridge from the front of the bunch, not from 8
wheels back. This is what stops one trigger from firing eleven surges.

Rewritten rule 3: surge to bridge when a rider is genuinely clear, the gap is
`<= BRIDGE_GAP_MAX` (150 m — about three surges' worth of closing speed), the
rider is in the front `BRIDGE_MAX_DEPTH` of their pack, `remaining_fraction <
ATTACK_PHASE_THRESHOLD` (0.25, widened from 0.15 so a move can be answered when
it goes, not only in the last 15 %), energy is above `CHASE_MIN_ENERGY`, and
the existing `_can_chase` terrain check passes.

**3c. A chasing bunch is faster than a lone rider — on the flat only.** Add

```
PACK_TEMPO_CHASE = 1.08   # applied when break_ahead and gradient <= DRAFT_UPHILL_LIMIT
```

as a fourth tempo band above `PACK_TEMPO_HARD`. A rotating group shares the
wind, so its road speed exceeds any solo rider's; that is why flat breaks get
caught. Above 5 % there is no wind to share, the tempo falls back to
`PACK_TEMPO_HARD`, and a climber who goes clear on a real climb still stays
away — which is exactly why the five climber-leaning courses must not move.

Phase 3c depends on Phase 2: a chase above 1.0x the pace-setter reference would
shed the pack one rider at a time from the front without rotation-averaged
shelter.

### Phase 4 — The finish kick is decided by `sprint`

Today the kick is `own_speed * 1.25` with `sprint` used only as a yes/no gate
at 70, so `sp1` (sprint 97) and `pu2` (sprint 82) get an identical boost and the
bunch sprint is won by whoever has the better `flat`. Replace with

```
boost = lerp(SPRINT_BOOST_MIN, SPRINT_BOOST_MAX, t_sprint)   # 0.05 - 0.35
```

and **delete `SPRINT_MIN_SPRINT`**: everyone kicks in the last kilometre, a
climber's kick is simply worth 5 %. One fewer magic threshold, and the sprint
finally resolves on the sprint attribute.

### Explicitly not in this plan

- Finding 2 (unbounded decay of dropped riders / autobus). The audit reports it
  so it cannot get quietly worse, but it is not fixed here.
- Deriving `draft_hold_multiplier` from the same resistance model. It is the
  obvious next simplification — the `drag` fade is hand-made where the physics
  would produce it — but changing shelter and speed in the same step makes a
  regression impossible to attribute.
- Team tactics, breakaway formation, echelons.

## 3. How we test that it improved

### 3a. `race_engine/audit.py` — the regression harness

The current audit is a person re-running six configs by hand and reading the
finish order. Replace it with a script, because "did it improve" has to be a
number before it is an opinion.

```
python -m race_engine.audit [--configs a,b] [--seeds 1,7,42,123,2024]
                            [--jobs 4] [--json out.json] [--baseline base.json]
```

Runs every (config, seed) pair with `log_path=None`, in a process pool, and
records per run:

| metric | why |
|---|---|
| winner id + archetype | the primary correctness question |
| winner time, avg km/h | realism band check |
| gap 1st-to-2nd, 1st-to-last | did it finish as a bunch or a procession |
| riders within 5 s / 30 s / 60 s of the winner | group size at the line |
| riders finishing with stamina 0 | Finding 2 watchdog |
| last finisher / winner time ratio | Finding 2 watchdog |
| first tick any rider is >100 m off the front, and where | where the race broke |
| ticks spent surging, per rider | catches a recurrence of the km-110 bug |

Expected winners live in a table **inside the audit script**, not in the
configs — they are test data, and `DOMAIN.md` says configs carry no engine
knowledge. With `--baseline` it prints a before/after delta column so a phase's
effect is visible in one run.

### 3b. The assertions that define "fixed"

Run over 5 seeds (1, 7, 42, 123, 2024). Finding 1 is closed when:

1. **`sprinters_classic` is won by a sprinter in >= 4 of 5 seeds.** *(now: 0/5)*
2. **`sprinters_classic` finishes as a bunch: >= 6 riders within 5 s of the
   winner.** *(now: 2)* This is the real test — a sprinter squeaking home from a
   shattered field would be the right name for the wrong reason.
3. **No rider more than 60 s down on `sprinters_classic`.** *(now: 183 s)*
4. **No rider is >100 m off the front before km 100 on `sprinters_classic`.**
   *(now: km 90.2)* The ramp must stop shelling sprinters.
5. **No rider surges while `break_ahead` is false.** *(now: 8 riders do, from
   km 110.5)* Asserted directly in a unit test, not just via the audit.
6. **No regression:** `lombardia`, `classics_hilly`, `summit_finish`,
   `mountain_stage` keep their expected archetype in >= 4 of 5 seeds.
7. **`san_remo` reaches >= 3 of 5** for puncheur/sprinter-climber (today it is a
   coin flip; Phase 1 widens the spread on its 4.1 % climbs, so this should
   improve, but it is a stretch goal, not a gate).
8. **Every winner averages 32-46 km/h**, and no course's winner time moves by
   more than 25 % without that being an intended, documented consequence.

### 3c. Unit tests (`test_speeds.py`, new)

The audit answers "did the race come out right"; these answer "is the model
right", and they fail fast:

- **Continuity:** `|v(0%) - v(0.05%)| < 0.05 m/s` for all six archetypes. This
  is the bug of §1a, asserted directly.
- **Monotonicity:** speed strictly decreases in gradient over -8..+15 %;
  increases in `climb` at 8 %; increases in `flat` at 0 %.
- **Calibration table:** every archetype's speed at 0 / 2.5 / 5 / 8 / 12 / -5 %
  falls inside a stated real-world band. This doubles as executable
  documentation of what the constants mean, and is the file to edit when
  someone wants to re-tune.
- **Spread bands:** fastest/slowest ratio is 1.05-1.12 at 0 %, 1.25-1.40 at 5 %,
  1.35-1.55 at 8 %.
- **Reflex tests:** on a synthetic `RaceState`, (a) a compact bunch with no
  break produces zero surges; (b) one rider 100 m clear produces surges only
  from riders at depth <= 2; (c) a rider 400 m clear produces none (out of
  bridging range).

### 3d. Order of work

Phase 0 is the harness, run against **unmodified HEAD**, saved as
`audit_baseline.json`. Nothing else starts until the baseline exists — the
whole point is to compare against a recorded number rather than a memory.

Then Phase 1 -> re-audit, Phase 2 -> re-audit, Phase 3 -> re-audit, Phase 4 ->
re-audit. Expected signature of each phase:

| after | expected movement |
|---|---|
| 1 | sprinters survive the km-90 ramp (assertion 4 passes); all climbing-course times rise; assertion 8 re-baselined; winner names may still be wrong |
| 2 | drop events become rare and reversible; 1st-to-last spread narrows on flat courses |
| 3 | assertions 1-3 and 5 pass; `sprinters_classic` becomes a bunch sprint |
| 4 | the sprint is won by `sp1` rather than by the best `flat` in the group |

If a phase moves a course it should not have touched, that is the phase to
revisit — which is the reason for auditing four times instead of once.

## 4. Risks

- **Phase 1 re-times every course.** Climbing courses get materially slower
  (a top climber goes from 41 km/h to 22 km/h on an 8 % climb). That is the
  correction, but `ENGINE_FINDINGS.md`'s "realistic time" verdicts must be
  recomputed against it, not carried over.
- **Phase 3c could reel in legitimate climber escapes.** `lombardia` finishes
  downhill, and a descent is drafting terrain, so a chasing bunch will close on
  a solo leader there. If `lombardia` flips, the knob is gating
  `PACK_TEMPO_CHASE` to `gradient >= -2 %` — but check first whether the catch
  is actually unrealistic; a lone rider being caught on a long descent is not.
- **Phase 2 could over-glue the bunch.** It is inert above 5 %, so the decisive
  climbs on four of six courses are untouched, but `san_remo` (max 4.1 %) sits
  entirely inside the drafting band and is the course to watch.
- **Audit runtime.** `mountain_stage` currently runs 78 k ticks because of
  Finding 2. With `--jobs 4` the full 30-run sweep is a couple of minutes; add a
  `--tick-cap` (default ~3x the winner's time, riders past it recorded as
  "did not finish within cap") so a Finding 2 regression slows the audit down by
  a bounded amount instead of an unbounded one.

## 5. Documentation and commit procedure

Per `race_engine/DOMAIN.md`:

- Rewrite **"Terrain speed"** entirely (Phase 1), and update **"Surge
  mechanics"**, **"Decision chain"**, **"Group tempo"**, **"Draft hold
  multiplier"** and the constants list.
- Add `FINDING1_PLAN.md` to the doc links in `DOMAIN.md`'s "Known
  discrepancies" section.
- Refresh `ENGINE_FINDINGS.md`'s per-course table from the final audit output,
  correct Finding 1's stated cause (§1 above supersedes it), and mark it closed
  or restate what remains.
- Add the audit harness to `DOMAIN.md` as the way engine changes are validated.
- Show the diff and get explicit approval before committing.
