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

## Results (seed=1) — post single-channel shelter model

| Course (scaled) | km | Realistic winner | Engine winner | Winner's avg | Verdict |
|---|---|---|---|---|---|
| `sprinters_classic` | 130 | Sprinter (bunch sprint) | **Rouleur 1** (rouleur solos away) | 40.1 km/h | ❌ wrong |
| `san_remo` | 137 | Sprinter-climber / puncheur | **Puncheur 1** | 40.0 km/h | ⚠️ right, but seed-dependent |
| `lombardia` | 100 | Climber / puncheur | **GC Climber 1** | 40.4 km/h | ✅ right |
| `classics_hilly` | 87 | Puncheur / climber | **GC Climber 1** | 37.5 km/h | ✅ right |
| `summit_finish` | 121 | Pure climber | **GC Climber 1** | 40.3 km/h | ✅ right |
| `mountain_stage` | 116 | GC climber | **GC Climber 1** | 32.3 km/h | ✅ right |

**5 of 6 correct at seed 1**, up from 4. `san_remo` flipped to the realistic
winner without being targeted: with a rolling early tempo and intensity-based
fatigue, the puncheur arrives at the Poggio-style finale fresh enough to use his
kick, instead of the rouleur having ground everyone down on the flat.

**Caveat on `san_remo`:** the result is now a near-tie, not a clean win. Seeds 1
and 7 give Puncheur 1 (by 6 s and 23 s); seed 42 gives Rouleur 1 (by 3 s over
Puncheur 2). The top four finish within ~11 s of each other. So the course has
moved from *reliably wrong* to *a coin flip decided by jitter* — real progress,
but it is Finding 1's missing chase/follow reflex that would make the finale
resolve on merit rather than on the random seed. `lombardia` is stable across
seeds 1/7/42 (GC Climber 1 every time).

Every winner now averages **32–40 km/h**, inside the real-world band (Finding 2
was 5.9 h for `mountain_stage`; it is now 3.6 h).

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

## Finding 1 — Rouleur-bias on long flats (residual, `sprinters_classic`)

The last wrong course. Cause is unchanged and is **tactics, not physics**: the
rouleurs press off the front in the finale and nobody organises a chase. The
reflex set has no flat-attack/press decision and no follow-the-move response,
so a rider going clear is simply unanswered.

The physics around the move are now right — the bunch arrives intact and the
sprinters reach the line with 62–64 stamina and 84 energy, i.e. perfectly able
to contest a sprint they are never given. They lose 182 s to a move nobody
chased. The fix needed is specifically a chase/follow reflex (the `CHASE_*`
rules are gated to the final 15 % of the race and gaps ≤ 30 m, far too narrow to
respond to a real attack), not better pack physics.

Probes that did **not** flip it (ruled out): raising sprinter `resistance` to the
rouleur's; lowering the rouleur's `positioning`; lowering the pack tempo.

## Finding 2 — Slow times, now only in the tail of the field

Winners are now realistic (32–40 km/h). Dropped riders are not: `mountain_stage`
sheds its sprinters to 78,091 s (21.7 h) and `lombardia` to 32,023 s.

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

- **5 of 6 courses right at seed 1** (`san_remo` marginally — see its caveat),
  and all six winners now finish in a realistic time.
- The flat no longer pre-decides climber-leaning races; shelter is credited
  exactly once; fatigue tracks effort rather than the clock.
- Remaining gaps: (1) `sprinters_classic` over-rewards the rouleur for lack of
  attacking/following tactics, and (2) riders who crack decay without limit
  instead of forming an autobus.
