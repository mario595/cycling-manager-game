# Plan — Realistic pack behaviour on the flat

Analysis of `race_player/public/lombardia.jsonl` (100 km, 40 km flat opener,
11-rider archetype roster) and the plan to fix the climbers being shed on the
flat.

## 1. What the log actually shows

| Rider | flat | positioning | Dropped at tick | Distance into the 40 km flat |
|---|---|---|---|---|
| `gc2` GC Climber 2 | 38 | 50 | **81** | ~1.1 km |
| `gc1` GC Climber 1 | 40 | 52 | **146** | ~1.9 km |
| `gc3` Superdom | 45 | 56 | 901 | ~11.8 km |

Both GC climbers are off the back before kilometre 2 of a 40 km flat run-in on
which, narratively, *nobody is racing*. By tick 600 they are 1.4 km down; by the
foot of the first climb (tick ~3000) they are **8.8 km** behind. The race is
decided before the first gradient.

Two further symptoms in the same log:

- **`gc3` survives but is bled dry.** His energy falls 100 → 35 over the flat
  and then pins at ~39.5 for the rest of the opener. He reaches the first climb
  with essentially no anaerobic reserve, purely from *sitting in the bunch*.
- **Stamina is irrelevant on the flat.** Every rider is still at 78–86 stamina
  after 40 km. Nothing about the flat section is governed by the endurance
  meter — it is governed entirely by the drop test and the energy meter.
- **Downstream nonsense.** Both sprinters, once shed on the climbs, finish at
  tick ~36,100 (10 hours). `gc2`, dropped at kilometre 1, finishes 2nd.

## 2. Root cause

### 2.1 The drop test is on a knife-edge, and shelter is capped too low

The pack tempo is `pace = max(own_speeds) × GROUP_DROP_FRACTION`. With this
roster that is `14.545 × 0.90 = 13.09 m/s (47.1 km/h)` — 90 % of the *single
fastest rider's absolute solo maximum*, every tick, from the gun.

A rider stays in only if `own_cruise × draft_hold_multiplier(...) ≥ pace`:

| id | solo cruise | max hold (depth 10) | margin vs tempo | min depth needed |
|---|---|---|---|---|
| `gc1` | 11.15 | 13.52 | **+0.43** | 7th wheel |
| `gc2` | 10.99 | 13.29 | **+0.20** | 9th wheel |
| `gc3` | 11.56 | 14.10 | +1.01 | 3rd wheel |
| `ru1` | 14.38 | 17.71 | +4.61 | 0 |
| `sp1` | 14.55 | 18.59 | +5.50 | 0 |

So in an **11-rider** field, `gc1` must sit 7th wheel or deeper and `gc2` 9th or
deeper — *at maximum possible shelter* — merely to survive. And `add_speed_jitter`
applies ±0.3 m/s to both the rider's own cruise and the pace-setter's, a ±0.57 m/s
swing on a margin of +0.20. **Staying in the bunch is a coin flip on every tick.**

Contributing constants:

- `DRAFT_HOLD_MAX = 1.30`, but the `quality` blend (`0.6 × skill + 0.4 × depth`)
  means a mid-`positioning` rider never gets more than ~1.21×. Real drafting in
  a bunch is a 30–40 % power saving, which at `P ∝ v³` and equal power is roughly
  a 1.12–1.19× speed gain **for the same power** — but that is the wrong frame.
  The real point is that a sheltered rider holds the bunch's speed at ~60 % of
  the power the man on the front is producing, so the binding constraint is the
  *pace the front chooses*, not the follower's solo ceiling.
- `DRAFT_DEPTH_SATURATION = 10` in an 11-rider field means only the very last
  rider gets full depth credit. Shelter quality is accidentally coupled to field
  size. In reality 3–5 wheels back is already fully sheltered.

### 2.2 The bunch always rides at 90 % of the strongest rider's ceiling

`GROUP_DROP_FRACTION` is a constant. The engine has no concept of *nobody is
pushing*. On a flat opening 40 km with no break up the road and no team with a
reason to chase, a real peloton rolls at 40–43 km/h — comfortably inside
everyone's aerobic range — and the field stays together for hours. The engine
instead runs a permanent full-gas tempo set by whoever happens to be strongest.

### 2.3 Being in the wheels costs energy

`compute_energy_drain` charges `overshoot = effective_speed − own_solo_cruise`.
For `gc3` that is `13.1 − 11.56 = 1.54 m/s` → ~0.077 energy/tick after the draft
factor → ~4.6/min. That is why he arrives at the climbs empty.

This is **internally inconsistent**: `draft_hold_multiplier` says "sheltered, you
can sustain 1.2× your solo cruise", while `compute_energy_drain` says "anything
above 1.0× your solo cruise burns matches". The drop test and the cost model
disagree about what shelter means. The reference speed for "free" riding must be
the same in both.

The `energy < 40` throttle (`apply_energy_burst_modifier`) then forms a feedback
loop that pins `gc3` at ~39.5 energy for 25 km — the anaerobic meter is acting
as the steady-state flat speed governor, which is not what it is for.

### 2.4 The drop is a cliff with no elastic

Once a rider is outside `PACK_COHESION_DISTANCE` (60 m) there is no way back:

- no reintegration or slipstream-of-the-convoy effect,
- the chase reflex is gated to the final 15 % of the race (`CHASE_DISTANCE_MAX`)
  **and** to gaps ≤ 30 m (`CHASE_GAP_MAX`), so it can never fire here,
- a dropped rider immediately reverts to solo cruise (11 m/s vs the pack's 13.1),
  so a 2 m slip compounds monotonically into kilometres.

Real bunches are elastic: riders drift back, sit in the cars, and come back on.
A single unlucky tick should not end a rider's race.

### 2.5 Pack depth is emergent noise, not a decision

`depth` is just the rider's index in the position ordering of the 60 m blob,
which is driven by jitter. A real climber *deliberately* sits in the wheels on
a flat opener and a real sprinter's team *deliberately* rides the front. The
engine has no positioning intent, so a climber randomly floats to 3rd wheel and
gets shed.

## 3. The plan

Ordered so that each step is independently testable and the early steps do most
of the work.

### Step 1 — Situational pack tempo (biggest single win)

Replace the constant `GROUP_DROP_FRACTION` with a tempo the pack *chooses*
based on race situation. Add `compute_pack_tempo(pack, profile, position)` in
`formulas.py`:

```
tempo_fraction =
    EASY_TEMPO_FRACTION      (~0.72)  when remaining_frac > EARLY_PHASE_THRESHOLD
                                       and terrain is FLAT and no rider is clear
                                       up the road
    TEMPO_FRACTION           (~0.82)  in the transition phase
    GROUP_DROP_FRACTION      (0.90)   in the finale, or while chasing a break
pace = median_of_top_third(own_speeds) × tempo_fraction
```

Two changes here, both deliberate:

- **Phase-aware fraction** — the bunch only rides at 90 % of its ceiling when
  there is a reason to.
- **Pace set by a robust statistic, not `max()`** — using `max()` lets one
  jittered outlier dictate the tempo for everyone. Use the median of the
  strongest third (or simply the 2nd-fastest cruise) so the tempo is stable
  tick-to-tick.

At an easy tempo of `14.545 × 0.72 = 10.5 m/s (37.7 km/h)` every rider in the
roster holds on with their *solo* cruise, before any draft credit — which is the
realistic outcome for a Monument's opening hour.

### Step 2 — Make the energy reference the sheltered cruise

In `compute_energy_drain`, take the rider's draft-credited sustainable speed as
the free-riding reference instead of their solo cruise:

```python
sustainable = own_speed * draft_hold_multiplier(positioning, depth, gradient)
overshoot   = max(0.0, effective_speed - sustainable)
```

Then drop the `draft_energy_factor` multiplication on the overshoot (the shelter
is now accounted for once, in the reference speed, instead of twice and
inconsistently). Sitting in the bunch at a tempo you can shelter at becomes
free — and recovers energy — which is what happens in reality. A rider only
burns matches when the pack pace exceeds what their shelter can buy them,
which is exactly the "hanging on by the fingernails" case.

This alone stops `gc3` arriving at the climbs on 39 energy.

### Step 3 — Fix the shelter model's scaling

- `DRAFT_DEPTH_SATURATION`: 10 → **4**. Three or four wheels back is already
  full shelter; this decouples shelter from field size.
- Reweight `quality` toward depth: `0.35 × skill + 0.65 × depth_factor`.
  Being in the bunch should matter more than the skill stat; `positioning`
  should be the tiebreaker, not the dominant term.
- `DRAFT_HOLD_MAX`: 1.30 → **1.45** on the flat. With Step 1 this is rarely the
  binding constraint any more, but it should be generous enough that a
  specialist climber can sit in a hard-but-not-full-gas bunch.
- Keep the `drag` fade to `DRAFT_UPHILL_LIMIT` unchanged — this is the part
  that correctly refuses to protect weak climbers on the climbs, and it is why
  the climber-leaning courses currently give right answers. **Do not touch it.**

### Step 4 — Hysteresis and elastic on the drop

Being dropped should be a process, not a per-tick coin flip.

- **Hysteresis**: require the drop condition to hold for `DROP_GRACE_TICKS`
  (~10 s) consecutively before a rider is actually shed; a single bad tick just
  costs a couple of metres. Track `off_pace_ticks` on `RiderState`.
- **Asymmetric thresholds**: drop at `pace`, but allow re-attachment at
  `pace × 1.02` (a dropped rider who can hold slightly more than the tempo gets
  back on). Implement by letting a rider within `PACK_COHESION_DISTANCE ×
  REATTACH_FACTOR` (~2.0, i.e. 120 m) rejoin the pack when their credited cruise
  clears the higher bar.
- **Convoy slipstream**: a rider within, say, 150 m of a pack keeps a partial
  draft credit (~50 %) while chasing back. This is the mechanism that makes real
  gaps close.

### Step 5 — Positioning intent (small, high-value)

Rather than depth falling out of jitter, give riders a target depth in
`_decide_actions`:

- A rider whose credited cruise is close to the tempo (i.e. under pressure)
  *seeks shelter*: target the back third of the pack.
- Sprinters/domestiques with high `positioning` in the finale seek the front.
- Implement as a small per-tick bias to `own_speed` inside the pack (±2 %) so
  riders drift toward their target depth over ~30 s rather than teleporting.

This is the cheap approximation of tactics; a full team-tactics model is out of
scope here.

### Step 6 — Re-tune the flat/uphill speed maps (optional, after 1–5)

`FLAT_MIN_SPEED = 8.0` means a `flat 38` climber solos at 39.6 km/h and a
`flat 82` sprinter at 52.4 km/h — a 32 % spread in *solo* flat speed between
pros, which is far too wide (real spread on the flat between a Grand Tour
climber and a rouleur is maybe 8–12 % at threshold). Narrowing to
`FLAT_MIN_SPEED = 10.5` would make the flat far less decisive on its own and
reduce how much work Steps 1–4 have to do. This also feeds
`ENGINE_FINDINGS.md` Finding 2 (unrealistically slow total times).

Treat as a separate change with its own re-audit of all six configs.

## 4. Validation

Add to `test_simulation.py`, run on `lombardia.json` with a fixed seed:

1. **No rider is dropped in the first 20 km of a flat opener.** Assert
   `max_gap(t) < PACK_COHESION_DISTANCE` for all `t` while the leader is on
   segment 0.
2. **Field is intact at the foot of the first climb.** Assert all 11 riders are
   within 60 m at the tick the leader reaches 40,000 m.
3. **Energy is preserved through the flat.** Assert every rider has
   `energy > 85` at that same tick.
4. **The climbs still split the race.** Assert the field is *not* intact at the
   summit of the 7 % climb — the fix must not turn the engine into a permanent
   bunch. `gc1`/`gc2`/`gc3` in the front group, `sp1`/`sp2` shed.
5. **Regression across all six configs**: re-run the `ENGINE_FINDINGS.md` table.
   The four currently-correct courses must stay correct. Steps 1 and 4 may also
   improve `sprinters_classic`/`san_remo` by keeping the sprinters in contact
   with the rouleur, but that is a bonus, not the goal.

Sanity check on realism: 100 km in ~9,050 s is 39.8 km/h average, which is
plausible; the first 40 km currently runs at 47 km/h, which is not. Expect the
flat split to slow to ~40–42 km/h and total time to rise slightly.

## 5. Sequencing

Steps 1 + 2 are ~40 lines together and should be done as one change — they are
the two halves of the same inconsistency (what does shelter buy you?) and
fixing only one leaves the other visible. Re-run and re-audit before touching
Steps 3–5. Step 6 is a separate project.

Per `race_engine/DOMAIN.md`: update the spec's "Drafting & pack cohesion",
"Energy" and constants sections alongside the code, and refresh
`ENGINE_FINDINGS.md` with the new per-course table before asking for review.
