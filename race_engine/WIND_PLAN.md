# Wind — Implementation Plan (Tier A: attrition)

**Audience:** an implementing agent who has not read the wind brainstorm. This
document is self-contained: it states what to build and why, and it makes the
design decisions so you do not have to re-litigate them.

**Status:** proposed, not implemented. Awaiting approval.

**Scope:** Tier A (wind as an aero tax that decides who cracks). Tier B
(echelons — wind that splits the race) is designed for but deliberately **not**
built here; see "Tier B: echelons (deferred)".

---

## Goal

Make wind a real, occasionally decisive force in a race without making it a
constant one. Three requirements, taken directly from the brief:

1. **Wind is usually not present, and usually not decisive.** Most race days
   should feel exactly like today's races.
2. **Wind blows from different angles and affects riders differently by angle.**
   A headwind is not a crosswind is not a tailwind.
3. **Wind changes realistically.** Both angle and intensity drift. Real wind
   does not go 0 → 30 km/h → 0 in a heartbeat.

---

## Design decisions (settled — implement these, do not substitute)

### 1. Wind is modelled RELATIVE TO THE RIDERS. There is no compass.

The engine does **not** model course bearing, segment bearing, or absolute wind
direction. It models a single **relative angle**: where the wind comes from as
seen by a rider travelling forward.

```
  0°   = pure headwind (straight in the face)
  90°  = pure crosswind from the rider's RIGHT
  180° = pure tailwind
  270° = pure crosswind from the rider's LEFT
```

**Why this is right, not just simpler.** The physics only ever needs the angle
*between* the wind and the direction of travel. Absolute bearings are two
unknowns that exist solely to be subtracted into that one number. Adding
per-segment bearings would mean touching the config schema and all six bundled
configs to compute a quantity we would immediately collapse back to one value.

**The consequence to accept:** a course turning left and the weather shifting
are indistinguishable to the model. Both appear as "the relative angle
changed". This is fine — it is also indistinguishable *to a rider*, which is
whose experience we are simulating. The angle-drift model below deliberately
produces both kinds of change (slow meander = weather; occasional sharp swing =
the road turned) out of one variable.

### 2. All riders experience the same wind at the same tick.

No per-rider or per-position wind field. The whole race sees one
`(speed, angle)` pair each tick. Differentiation between riders comes from
their `positioning` (shelter) and where they sit in the pack — machinery that
already exists — not from giving them different wind.

This is what keeps Tier A cheap: **wind adds no new pass over the field.** It is
two floats on `RaceState`, updated once per tick.

### 3. Wind enters the physics through the AERO TERM ONLY.

`compute_base_speed` already solves a power balance:

```
K_aero * v³ + (K_roll + K_grav*s) * v = 1
```

Wind multiplies `K_aero`. Nothing else changes. **This one hook gives correct
terrain behaviour for free** — verified against the real solver:

| Aero multiplier | Flat speed change | 8% climb speed change |
|---|---|---|
| 1.5 (headwind) | **−12.0%** | **−1.8%** |
| 2.2 (gale)     | **−22.1%** | **−4.1%** |

Wind stops mattering on a climb automatically, because at 17 km/h the gravity
term dominates the aero term. There is **no special-casing for climbs**, no
`if gradient > x` — the same equation that made `flat`/`climb` blend correctly
makes wind fade correctly. Do not add a gradient check; you would be
double-counting something the solver already does.

### 4. The effect is ASYMMETRIC: headwind hurts more than tailwind helps.

Naive aero scaling is wrong on the tailwind side. Scaling `K_aero` by the pure
apparent-wind ratio produces **+59% speed (75 km/h)** for a 25 km/h tailwind,
because as drag vanishes the power balance lets speed run away.

Two corrections, both physically motivated:

- **`TAILWIND_EFFICIENCY = 0.55`** — only 55% of a tailwind's along-course
  component counts. A rider with a big tailwind spins out their gearing and
  still pays rolling resistance; they do not convert the whole tailwind into
  speed. Applied *only* to the tailwind component.
- **`AERO_MULT_MIN = 0.55`, `AERO_MULT_MAX = 2.20`** — hard clamps so a freak
  roll cannot produce a 90 km/h bunch or a race that never finishes.
  `AERO_MULT_MAX` binds around a 25–30 km/h headwind.

Verified output of the tuned model (mid-attribute rider, flat, solo):

| Wind | Head (0°) | Head-cross (45°) | Cross (90°) | Tail-cross (135°) | Tail (180°) |
|---|---|---|---|---|---|
| 8 km/h  | −9.4%  | −7.0%  | −0.2% | +4.3%  | +6.3%  |
| 15 km/h | −16.0% | −12.2% | −0.6% | +8.2%  | +12.8% |
| 25 km/h | −22.1% | −18.7% | −1.7% | +14.0% | +20.6% |

A 15 km/h headwind costs 16% and gives back 13% as a tailwind. That asymmetry
is the thing every cyclist knows to be true, and it falls out of one constant.

### 5. Crosswind is near-neutral on SPEED, and that is correct.

Note the ~0% column at 90° above. A pure crosswind barely changes how fast the
bunch rolls. Its real effect is on **shelter** — you must ride echeloned across
the road to hide from it, and the road is only so wide. That is the echelon
mechanism, and it is **Tier B**. In Tier A the crosswind term exists (it feeds
`K_CROSS` into apparent wind, worth a percent or two) but does not restructure
packs.

Do not try to fake echelons in Tier A by, say, dropping riders at random in a
crosswind. A crosswind that quietly does nothing dramatic is the honest Tier A
behaviour, and it leaves Tier B a clean slate.

### 6. Most race days are calm. Weather is rolled once per race.

A race draws a **weather band** at construction from the seeded RNG:

| Band | Probability | Mean wind (km/h) |
|---|---|---|
| `calm`     | 45% | 0–6   |
| `light`    | 30% | 6–14  |
| `moderate` | 18% | 14–24 |
| `strong`   | 7%  | 24–38 |

75% of races are calm or light, where wind is a texture, not a story. 7% are
genuinely windy days that riders will remember. Verified over 1000 rolls: 46.2%
/ 30.0% / 17.2% / 6.6%.

The band sets the *mean*; the drift model below wanders around it, so even a
`strong` day has lulls and a `light` day has gusts.

### 7. Wind drifts. It never jumps.

Both intensity and angle evolve by exponential relaxation toward a slowly
re-rolled target (an Ornstein–Uhlenbeck-style walk), never by direct assignment.

- **Intensity:** target re-rolled with probability `0.002`/tick (~ every 8 min),
  current value moves 0.4% of the way to it each tick.
- **Angle:** continuous slow meander (`gauss(0, 0.15)`/tick on the target) plus
  a rare **sharp swing** (probability `0.0008`/tick, ±60–140°) representing the
  road turning. Current angle moves 1% of the way to target per tick, along the
  shorter arc (`((target - current + 180) % 360) - 180`).

Verified over two 2-hour races: **max per-tick intensity change 0.15 km/h.**
Requirement 3 is met by construction — there is no code path that assigns
intensity or angle directly after initialisation.

---

## Data model changes

### `WindState` (new, `models.py`)

```python
@dataclass
class WindState:
    speed: float          # km/h, current
    angle: float          # degrees, 0=head, 90=from right, 180=tail
    target_speed: float   # internal: drift target
    target_angle: float   # internal: drift target (unwrapped, may exceed 360)
    band_mean: float      # internal: the race's weather band mean
    band: str             # "calm" | "light" | "moderate" | "strong"
```

Only `speed`, `angle` and `band` are read outside the drift function.
`angle` is always normalised to `[0, 360)` on read; `target_angle` is left
unwrapped so the shorter-arc math stays simple.

### `RaceState`

Add `wind: WindState | None = None`. **`None` means "no wind modelled"** and
every wind code path must no-op — this is what keeps existing tests, the
`test_speeds.py` calibration table, and hand-built `RaceState` objects passing
unchanged. `create_initial_state` gains a `wind: bool = True` parameter.

Follow the precedent set by team tactics: **defaults must reproduce today's
behaviour exactly** where wind is off, so the diff stays reviewable.

### Config schema (`config.py`)

Optional `"wind"` block on `race`:

```json
"race": {
  "name": "...",
  "wind": {"band": "strong"},
  "course": [...],
  "riders": [...]
}
```

- **Absent** (the case for all six bundled configs) → band rolled from the
  seeded RNG per decision 6. This is the normal path.
- `band` — optional, one of `calm`/`light`/`moderate`/`strong`. Forces the
  band, for testing and for authoring a deliberately windy race. Any other
  value is a `ConfigError`.
- `enabled` — optional bool, default `true`. `false` disables wind entirely
  (`RaceState.wind = None`), for A/B comparison against pre-wind baselines.

Deliberately **not** configurable: the drift rates, the caps, `K_CROSS`,
`TAILWIND_EFFICIENCY`. Engine constants stay in `formulas.py`, matching the
existing rule that draft distance and surge thresholds are not exported.

---

## Formulas (`formulas.py`)

### New constants

```python
WIND_V_REF = 13.1              # m/s reference speed for apparent-wind calc
WIND_K_CROSS = 0.45            # how much a crosswind component adds to apparent wind
WIND_TAILWIND_EFFICIENCY = 0.55
WIND_AERO_MULT_MIN = 0.55
WIND_AERO_MULT_MAX = 2.20
WIND_BANDS = {...}             # per decision 6
WIND_SPEED_RETARGET_PROB = 0.002
WIND_SPEED_RELAX = 0.004
WIND_ANGLE_TURN_PROB = 0.0008
WIND_ANGLE_TURN_RANGE = (60.0, 140.0)
WIND_ANGLE_MEANDER_SIGMA = 0.15
WIND_ANGLE_RELAX = 0.01
```

### `wind_aero_multiplier(wind_speed_kmh, angle_deg) -> float`

```python
w = wind_speed_kmh / 3.6
along = w * cos(radians(angle))          # + = headwind component
if along < 0:                            # tailwind
    along *= WIND_TAILWIND_EFFICIENCY
cross = abs(w * sin(radians(angle)))
apparent = sqrt((WIND_V_REF + along)**2 + (WIND_K_CROSS * cross)**2)
mult = (apparent / WIND_V_REF) ** 2
return clamp(mult, WIND_AERO_MULT_MIN, WIND_AERO_MULT_MAX)
```

Uses a fixed `WIND_V_REF` rather than the rider's actual speed. This is a
deliberate simplification: using live speed would make the multiplier
speed-dependent and therefore re-entrant with the solver (speed depends on
drag depends on speed), forcing an inner fixed-point iteration for a
second-order effect. It would also break the memoisation below.

### `compute_base_speed(attributes, gradient, aero_mult=1.0)`

Add a third parameter, defaulting to `1.0` so every existing call site is
unchanged. Multiply `k_aero` by it before solving.

**Memoisation must be handled carefully.** The existing
`_POWER_BALANCE_CACHE` is keyed `(flat, climb, gradient)`. Wind changes
continuously, so a naive addition of `aero_mult` to the key would make the
cache grow unboundedly and never hit — turning a few dozen solves per race
into hundreds of thousands.

**Fix: quantise the multiplier for the cache key**, e.g.
`round(aero_mult, 2)`. A 1% error in drag is far below the model's noise floor
(per-tick jitter is already ±0.3 m/s) and it bounds the cache at ~165 distinct
multipliers × gradients × archetypes. **Do not skip this** — it is the one
place where wind could plausibly wreck engine performance, and the audit's
`--tick-cap` would not catch it (the race still finishes, just slowly).

### `advance_wind(wind: WindState, rng: random.Random) -> None`

Mutates in place per decision 7. Takes an explicit `rng` rather than using the
`random` module.

**Wind MUST use its own `random.Random` instance — not the global module RNG.**

`add_speed_jitter` calls `random.uniform` on the global stream, seeded once by
`run_race`. If wind drew from that same stream it would consume numbers jitter
would otherwise have received, shifting every subsequent value. Races would
stay perfectly deterministic (same seed + same code → byte-identical, always),
but **every existing seeded race would produce a different result** — including
a `calm` race where wind does nothing physically.

That is not a correctness problem; it is a *diagnostic* problem. It would make
the audit baseline useless exactly when it is needed, because you could not
distinguish "wind changed this race" from "the RNG got shuffled".

The fix is one line — give wind a decorrelated substream derived from the same
seed:

```python
wind_rng = random.Random(seed * 7919 + 1)   # or any fixed decorrelation
```

Verified: with a separate generator the jitter stream is **bit-identical** to
the pre-wind engine, while wind itself remains fully reproducible from the
seed. This buys three things:

- The existing `audit_baseline.json` stays valid — no re-baselining needed.
- A `calm`-band race reproduces today's result **exactly**, so any audit delta
  is genuinely attributable to wind.
- A wind-disabled run is bit-identical to the current engine, making the
  "land it inert first" commit verifiable by comparing finish times rather
  than merely asserting `aero_mult == 1.0`.

The band roll (decision 6) happens once at construction and must draw from this
same `wind_rng`, not the global stream, for the same reason.

---

## Simulation changes (`models.py`)

Exactly two touch points in `tick()`:

**1. Advance wind — at the very top of the tick,** before any rider is
evaluated, so all riders see one consistent wind for the tick (matching the
existing snapshot discipline):

```python
if self.wind is not None:
    advance_wind(self.wind, rng)
    aero_mult = wind_aero_multiplier(self.wind.speed, self.wind.angle)
else:
    aero_mult = 1.0
```

**2. Pass it to the cruise calculation** in Phase 1:

```python
cruise = apply_stamina_cruise_modifier(
    compute_base_speed(rs.rider.attributes, segment.gradient, aero_mult),
    rs.stamina,
)
```

**That is the entire engine integration.** Everything else follows for free,
and it is worth understanding *why*, because it is the strongest argument for
this design:

- **Stamina** — `compute_stamina_drain` charges `speed / sustainable_speed`.
  In a headwind both fall together, so intensity is roughly unchanged, but
  `drain *= speed / DRAIN_REFERENCE_SPEED` means a slower headwind hour drains
  *less per second* while taking *more seconds* — net: wind makes a race
  longer and harder in the way distance does. Correct, and free.
- **Pack tempo** — `compute_pack_tempo` is a fraction of `pace_setter_speed`,
  which is computed from wind-affected cruises. The bunch slows in a headwind
  automatically.
- **Drafting** — `draft_hold_multiplier` is a multiplier on the rider's own
  (wind-affected) cruise, so shelter is worth proportionally the same.
  *Physically this understates shelter in a headwind* — drafting is worth more
  when there is more wind to hide from. Noted as a Tier B refinement; in Tier A
  the effect is directionally harmless and keeps shelter credited exactly once,
  preserving the single-channel invariant the DOMAIN doc is emphatic about.
- **Surges / breakaways** — a solo attacker into a headwind is hurt more than
  the sheltered bunch chasing them, because the bunch's `PACK_TEMPO_CHASE` of
  1.08 is applied to an already wind-reduced pace while the attacker eats the
  full aero penalty alone. **Headwind breaks get caught; tailwind breaks stay
  away.** This is real racing, and it emerges without a single line of tactics
  code.

Do **not** add wind terms to `compute_stamina_drain`, `compute_energy_drain`,
or `draft_hold_multiplier`. The engine's core invariant — shelter and effort
are credited in exactly one place — is what previous refactors were built to
establish. Wind respects it by entering upstream of all three.

---

## Log format (`race_logger.py`)

Add a top-level `wind` object to each tick, alongside `time` and
`course_length`:

```json
{
  "time": 42,
  "course_length": 38000.0,
  "wind": {"speed": 17.3, "angle": 214.6, "band": "moderate"},
  "segments": [...],
  "riders": [...]
}
```

- `speed` — km/h, rounded to 1 dp (this is display data; 2 dp is noise).
- `angle` — degrees `[0, 360)`, rounded to 1 dp. **0 = headwind, 90 = from the
  rider's right, 180 = tailwind, 270 = from the left.**
- `band` — the race's weather band, constant across all ticks. Lets the player
  label the day without scanning the whole file.
- **Omit the whole `wind` key when wind is disabled.** Consumers must treat it
  as optional (see the player plan).

Update `DOMAIN.md`'s "JSONL output format" section and its field-reference
table in the same commit.

---

## Tier B: echelons (deferred — design notes only)

Recorded so the Tier A data model does not foreclose it. **Do not implement.**

The mechanism: in a crosswind, shelter is found *diagonally*, so the sheltered
positions form an echelon whose width is limited by the road. Once an echelon
is full, the next rider has nowhere to hide and must start a new one — the
`gutter`. This is what shatters a bunch.

The Tier A design supports this cleanly:
- `WIND_K_CROSS` already isolates the crosswind component.
- Echelon capacity would be a function of crosswind strength: strong cross →
  fewer sheltered slots per echelon.
- It would attach to the existing `eff_depth_of` block in `tick`, capping how
  many riders can be credited with shelter, rather than adding a new pass.
- Team tactics would gain real meaning: a team that masses at the front before
  an exposed section makes the front echelon.

The reason it is deferred: it is the only part of wind that requires changing
**pack structure**, which is the most delicate code in the engine and the part
the rotation-averaging/gap-decay work was built to stabilise. It deserves its
own plan and its own audit baseline.

---

## Work items

Ordered. Each is independently testable.

### E1 — `formulas.py`: constants + `wind_aero_multiplier`
Pure function, no dependencies. Unit-test the table in decision 4 directly.

### E2 — `formulas.py`: `compute_base_speed` gains `aero_mult=1.0`
Including the **quantised cache key**. Existing tests must pass untouched —
that is the proof the default is inert.

### E3 — `models.py`: `WindState` + `advance_wind` + band rolling
**Wind gets its own `random.Random` substream** — see the determinism note
above; this is the load-bearing detail of this work item, not an aside.
Test: run 7200 ticks, assert max per-tick delta is small and that angle stays
in range. Test band distribution over many seeds. Assert the global RNG stream
is untouched by wind.

### E4 — `models.py`: wire into `RaceState` / `tick`
The two touch points above, plus `wind=None` no-op paths.

### E5 — `config.py`: optional `wind` block + validation
`ConfigError` on an unknown band. Existing configs load unchanged.

### E6 — `race_logger.py`: emit `wind`
Omitted entirely when wind is off.

### E7 — Audit: verify inertness, then assess wind's effect
No re-baselining needed (E3's separate RNG substream preserves the existing
baseline). First prove wind-off is bit-identical, then measure what wind
actually does. See Verification.

### E8 — `DOMAIN.md`: document all of the above
Per the commit procedure: engine changes **must** be reflected there. New
"Wind" section; update JSONL format, config schema, tick phases, and
`compute_base_speed`'s description.

---

## Verification

1. **Unit tests** per work item above.
2. **Wind-off regression — must be BIT-IDENTICAL.** With `enabled: false`,
   finish times must match the pre-wind engine exactly. Because wind uses its
   own RNG substream (E3), this is a real, checkable assertion rather than a
   proxy one: run the audit before and after with wind disabled and diff the
   JSON. Any difference at all is a bug.
3. **Calm-band regression — also bit-identical.** A `calm` race with wind
   *enabled* but drawing ~0 km/h should still reproduce today's results very
   closely, since `wind_aero_multiplier` → ~1.0. This is the check that the
   aero hook is inert when it should be.
4. **Audit deltas are attributable.** Run
   `python -m race_engine.audit --baseline audit_baseline.json`. The existing
   baseline stays valid (E3), so any movement is caused by wind, not RNG
   shuffling. Check:
   - `EXPECTED_ARCHETYPE` must still hold per course. If a windy seed flips a
     flat race away from a sprinter, that is arguably correct — but confirm it
     is wind, not a bug.
   - Winner average km/h should move roughly as the band predicts; calm runs
     should barely move.
   - **Watch for riders finishing at stamina 0** rising sharply. That would
     mean wind is over-taxing, and `AERO_MULT_MAX` is the dial.
4. **Force each band** (via the config block) on `sprinters_classic` and
   `mountain_stage` and sanity-check: strong wind should visibly change the flat
   race and barely touch the mountain one. This is the single best end-to-end
   check that decision 3 is working.

---

## Risks

| Risk | Mitigation |
|---|---|
| **Cache blowup** from an unquantised `aero_mult` key silently making races 1000× slower | Quantise to 2 dp (E2). Explicitly assert cache size stays bounded in a test. |
| Wind over-taxes stamina and every race becomes a survival slog | `AERO_MULT_MAX` is the single dial; audit's stamina-0 count is the detector. |
| Tailwind speeds run away (the bug found and fixed during design) | `TAILWIND_EFFICIENCY` + `AERO_MULT_MIN`, with the verified table in decision 4 as a regression test. |
| Baseline churn makes it hard to tell wind's effect from a bug | Wind uses its **own RNG substream** (E3), so the existing baseline stays valid and every audit delta is attributable to wind. Additionally land wind **disabled by default** in one commit, verify bit-identical output, then enable in a second. |
| Wind accidentally drawn from the global RNG (easy to do — `random.uniform` is right there) | The wind-off regression (Verification 2) catches it immediately: any finish-time difference means the global stream was touched. |
| Crosswind feels like it "does nothing" | It is *supposed* to in Tier A (decision 5). The player's wind compass makes it visible even when it is not decisive, which is most of the point. |
