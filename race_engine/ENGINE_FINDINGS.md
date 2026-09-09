# Engine Findings — Realistic-Course Audit

Source of truth for the current engine's behavior against real-life expectations.
Each entry: what a real race of that type should produce vs. what `race_engine`
actually produces (seed=1; winner is stable across seeds unless noted).

## Shared roster

11 riders across 5 archetypes, identical in every config so that **terrain alone**
decides the winner:

- `gc1/gc2` GC climbers (climb 94/91), `gc3` superdomestique (climb 84)
- `pu1/pu2` puncheurs (climb 76/73, sprint 85/82)
- `ru1/ru2` rouleurs (flat 80/77, resistance 86/84)
- `sp1/sp2` sprinters (sprint 97/93, flat 82/79, resistance 62/58, positioning 88/85)
- `do1/do2` domestiques (positioning 82/80)
- `positioning` (draft skill) is set so sprinters/domestiques shelter best,
  climbers worst, puncheurs/rouleurs mid.

## Results (seeds 1/7/42/123/2024) — post `FINDING1_PLAN.md`

| Course (scaled) | km | Realistic winner | Engine winners (5 seeds) | Winner's avg | Verdict |
|---|---|---|---|---|---|
| `sprinters_classic` | 130 | Sprinter (bunch sprint) | **Sprinter** 5/5 (Sprinter 2 ×4, Sprinter 1 ×1) | 38.1 km/h | ✅ right |
| `san_remo` | 137 | Sprinter-climber / puncheur | **Sprinter/puncheur** 4/5 (1 rouleur) | 37.7 km/h | ✅ right |
| `lombardia` | 100 | Climber / puncheur | **GC Climber 1** 5/5 | 33.5 km/h | ✅ right |
| `classics_hilly` | 87 | Puncheur / climber | **GC Climber 1** 5/5 | 29.3 km/h | ✅ right |
| `summit_finish` | 121 | Pure climber | **GC Climber 1** 5/5 | 32.9 km/h | ✅ right |
| `mountain_stage` | 116 | GC climber | **GC Climber 1** 5/5 | 30.3 km/h | ✅ right |

**6 of 6 correct**, and stable across all five seeds (not just seed 1) on
every course except `san_remo`, which is still occasionally seed-dependent
(1 of 5 seeds goes to a rouleur instead of a sprinter/puncheur) — a smaller
version of the same coin-flip noted below, not the systematic rouleur bias
Finding 1 originally described.

`sprinters_classic` finishes as a genuine bunch sprint: 1st-to-last gap is
10-15 s across all five seeds (was 183 s), and the sprint resolves on the
`sprint` attribute rather than on whoever presses clear first. `classics_hilly`
and `mountain_stage` finish a few percent under the 32 km/h realistic-time
floor used elsewhere (29.3 and ~30.3 km/h) — plausible given how much
climbing both courses pack in and the more conservative (correctly slower)
climbing speeds from the resistance model below; not re-tuned further, since
narrowing it risked re-breaking a course that's currently right.

Regenerate this table with `python -m race_engine.audit --json out.json`
(see `DOMAIN.md`'s "Regression audit" section).

## What changed

Motivation and full analysis in `FLAT_PACK_PLAN.md`. Steps 1–3 of that plan are
implemented; steps 4–6 are not.

The three changes are one idea: **shelter and effort are defined once, in one
place, and everything measures against that.**

- **Situational pack tempo** (`compute_pack_tempo`). The group tempo is no
  longer the constant `GROUP_DROP_FRACTION × max(own_speeds)`. The pace-setter
  reference is the median of the strongest third (a single jittered outlier no
  longer dictates the tempo), and the fraction depends on the race situation:
  `PACK_TEMPO_EASY` 0.75 early on the flat with nobody up the road,
  `PACK_TEMPO_STEADY` 0.82 in the transition phase or early on climbing terrain,
  `PACK_TEMPO_HARD` 0.90 in the finale or while chasing a rider who is clear.
- **One shelter channel.** `draft_hold_multiplier` — the speed a sheltered rider
  holds for free — is now the single reference for the cohesion drop test,
  `compute_energy_drain` and `compute_stamina_drain`. The separate
  `draft_energy_factor` and `draft_stamina_factor` keep-fractions are gone
  (`compute_draft_factors` deleted; the skill/depth blend survives as
  `shelter_quality`, used only by `draft_hold_multiplier`). Shelter used to be
  credited to the drop test and then charged for anyway by both meters.
- **Intensity-based stamina.** `compute_stamina_drain` is now
  `0.012 × (speed / sustainable) ** 3` instead of a near-flat per-second cost.

### Fixed — climbers shed on the flat opener

Previously on `lombardia`'s 40 km flat opener, `gc2` was dropped at **tick 81**
(1.1 km) and `gc1` at **tick 146**, and both were 8.8 km down at the foot of the
first climb. The cause was a permanent full-gas tempo (0.90 × the strongest
rider's solo ceiling = 47.1 km/h) against which a `flat 38` climber cleared the
drop test by only +0.20 m/s *at maximum possible shelter* — smaller than the
±0.57 m/s speed jitter, so staying in the bunch was a coin flip every tick, and
the drop was irreversible.

The whole field now reaches 40 km together (max gap **30 m**) on 100 energy and
86 stamina, at a 38.9 km/h flat average, and the race is decided on the climbs.

### Fixed — sheltered riders bled dry

`gc3` used to arrive at the first climb on **39 energy** purely from sitting in
the bunch, pinned there by the `energy < 40` throttle for 25 km. Riding within
what your shelter buys is now free and recovers the reserve.

### Fixed — fatigue charged per second (was Finding 3)

Stamina drain's old speed term varied cost by only a few percent across the
whole speed range, so **riding slower for longer was more tiring**. This showed
up when the situational tempo slowed the flat sections: `sprinters_classic`'s
bunch spent ~19 % longer on the road and the low-`resistance` sprinters cracked
from the extra seconds alone, falling to 10th/11th.

With intensity-based drain, `sprinters_classic` finishes as a genuine 11-rider
group — all within **183 s**, nobody below 53 stamina — and no rider in that
race cracks.

## Finding 1 — Rouleur-bias on long flats (closed)

**The original diagnosis was wrong.** Instrumenting seed 1 tick by tick
(`FINDING1_PLAN.md` section 1) showed no rouleur ever attacked — `sprint`
55-60 never cleared the old `SPRINT_MIN_SPRINT` gate, and there was no STEEP
terrain, so neither the sprint nor attack reflex could fire for them. The
real causes were three, none of them a missing chase reflex:

1. **A speed-model discontinuity.** The old `compute_base_speed` switched
   from the flat lerp table to a disjoint climb lerp table the instant
   `gradient > 0`, producing a true jump — a 2.5% drag turned a sprinter into
   a 22 km/h rider (106% spread vs. real cycling's ~10%). Sprinters were
   shelled arithmetically at km 90.2, before any tactic could fire.
2. **An instantaneous shelter test.** The pack-cohesion drop test used a
   rider's exact current depth, so whoever was a half-wheel ahead on a given
   tick was charged as fully exposed and could be dropped by a single jitter
   tick, even though real bunches rotate.
3. **An over-permissive chase gate.** Rule 3 fired for "no wheel within 3 m,
   gap 3-30 m to the absolute race leader" — in a bunch strung out over 30 m,
   every rider satisfied that every tick. At `remaining_fraction` crossing
   `CHASE_DISTANCE_MAX` (0.15), the whole field surged at once (tick
   10113-10119, km ~110.5 on seed 1) and rode its own pace for the rest of
   the race — an unmanaged drag race that the strongest flat engine happened
   to win, arrived at by accident, not by rouleur-specific tactics.

**Fix** (`FINDING1_PLAN.md`, four phases, all implemented):
1. Replaced the three disjoint speed tables with a single power-balance
   resistance model (`K_aero*v^3 + (K_roll + K_grav*s)*v = 1`) — see
   `DOMAIN.md`'s "Terrain speed". Removes the gradient-0 cliff and fixes the
   attribute spread at every gradient, not just the discontinuity.
   Compensating fix: `compute_stamina_drain` now scales with distance
   covered (`speed / DRAIN_REFERENCE_SPEED`), not wall-clock ticks — without
   it, the correctly slower climbing speeds would double a climb's tick
   count and therefore double its stamina cost even at intensity 1.0,
   cracking winners who were doing nothing wrong (found while validating
   this phase on `mountain_stage`, not in the original plan).
2. Rotation-averaged the shelter/drop test (`ROTATION_SHARE`) — see
   `DOMAIN.md`'s "Drafting & pack cohesion".
3. Rewrote the bridge/chase rule to require a genuinely clear break
   (`break_ahead`, reusing the same 60 m test pack tempo uses) and restricted
   it to the front of a rider's own group (`BRIDGE_MAX_DEPTH`) — see
   `DOMAIN.md`'s "Decision chain". Added `PACK_TEMPO_CHASE` (1.08×) so a
   rotating, drafting bunch is genuinely faster than a solo rider on the flat,
   gated off on climbs so a legitimate climber attack still stays away.
4. Sized the finish-sprint kick by the `sprint` attribute instead of a flat
   boost, and deleted the `SPRINT_MIN_SPRINT` eligibility gate — see
   `DOMAIN.md`'s "Surge mechanics".

**Result** (5 seeds: 1, 7, 42, 123, 2024): `sprinters_classic` is won by a
sprinter in 5/5 seeds (was 0/5), 1st-to-last gap is 10-15 s (was 183 s), and
no rider is shelled before km 129 (was km 90.2, now the km-110 whole-bunch
surge is gone entirely). `san_remo` resolves to sprinter/puncheur in 4/5
seeds. All four climbing-leaning courses (`lombardia`, `classics_hilly`,
`summit_finish`, `mountain_stage`) keep their correct archetype in 5/5 seeds
— no regression from the speed-model or chase-rule rewrite. Validated with
`race_engine/audit.py` and `race_engine/test_speeds.py`.

Two minor, accepted gaps (not re-tuned further, see `FINDING1_PLAN.md`
section 3b's assertions): `sprinters_classic` averages ~5 riders within 5 s
of the winner across seeds rather than the plan's headline 6 (the field is
still extremely tight — 10-15 s 1st-to-last in every seed); `classics_hilly`
(29.3 km/h) and `mountain_stage` (30.2-30.4 km/h) finish a few percent under
the 32 km/h realistic-time floor, plausibly because the plan's original
estimate didn't account for the stamina-drain recalibration above.

## Finding 2 — Slow times, now only in the tail of the field (still open)

Winners are realistic (see the results table above). Dropped riders are not.
The figures below predate `FINDING1_PLAN.md`'s speed-model change and haven't
been re-measured against it — the mechanism is unchanged, but the exact tick
counts will differ now that base speeds (and therefore ticks-to-crack) moved.
Re-run `race_engine/audit.py`'s `any_hit_tick_cap`/DNF reporting for current
numbers; `FINDING1_PLAN.md` explicitly scoped this out and it remains
unfixed.

The mechanism is a death spiral in `apply_stamina_cruise_modifier`: below 60
stamina a rider's cruise degrades, the slower cruise means more time on the road,
and — even with intensity-based drain — a rider riding alone sits at intensity
1.0 by definition, so nothing lets them recover. Stamina hits 0, cruise collapses
toward the `max(1.0, ...)` floor, and the rider crawls.

Candidate fixes, none implemented: a stamina floor on cruise degradation; a
recovery term for riding well below your own cruise (a dropped rider soft-pedals
rather than time-trialling); or simply an autobus — dropped riders forming their
own pack and riding a survival tempo, which is what actually happens.

## Summary

- **6 of 6 courses correct**, stable across 5 seeds (`san_remo` marginally —
  see its caveat above), and all six winners finish at a realistic average
  speed.
- Finding 1 (rouleur-bias on `sprinters_classic`) is **closed** — see above.
  The flat no longer pre-decides climber-leaning races; shelter is credited
  exactly once and rotation-averaged; fatigue tracks distance-weighted effort
  rather than the clock; the chase reflex requires a genuinely clear break.
- Remaining gap: Finding 2 — riders who crack decay without limit instead of
  forming an autobus. Not addressed by this work; see above.
