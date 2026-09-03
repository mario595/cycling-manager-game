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
- `sp1/sp2` sprinters (sprint 97/93, flat 82/79, resistance 62/58)
- `do1/do2` domestiques

## Results (seed=1, winner archetype)

| Course (scaled) | km | Realistic winner | Engine winner | Verdict |
|---|---|---|---|---|
| `sprinters_classic` | 130 | Sprinter (bunch sprint) | **Rouleur 1** (12/12 seeds) | ❌ wrong |
| `san_remo` | 137 | Sprinter-climber / puncheur | **Rouleur 1** (12/12) | ❌ wrong |
| `lombardia` | 100 | Climber / puncheur | **Rouleur 1** (10/12) | ❌ wrong |
| `classics_hilly` | 87 | Puncheur / climber | **GC Climber 1** | ~ right |
| `summit_finish` | 121 | Pure climber | **GC Climber 1** | ✅ right |
| `mountain_stage` | 116 | GC climber | **GC Climber 1** | ✅ right |

## Finding 1 — Rouleur-bias / no effort management (root cause)

The **fastest flat rider loses** on the flat course. On `sprinters_classic`,
Sprinter 1 (flat 82) rides away from the field for the first ~7000s (gap +1491m,
never drafting) but drains stamina at max rate the whole way. With low
`resistance` (62) their stamina falls below the 60 "cracking" zone at ~t=6100s,
their cruise speed collapses to ~1-3 m/s, and the rouleur passes them at t~7000s
to win by **~35 minutes**.

Mechanism: **every rider always rides at maximal natural pace**. There is no
effort-management layer — no "ride at the bunch's moderate tempo," no conserving
in the wheels for a bunch finish. A real flat stage is ridden at a controlled
pace with the sprinter protected in the draft; the engine models it as an
all-out effort, so low-`resistance` riders systematically blow up over distance.

Resolution: introduce a **pacing / group-tempo concept** so the peloton rolls at
a sustainable effort rather than flat out, letting sprinters preserve stamina
for the finish. This is a model change, not a constant tweak.

## Finding 2 — San Remo mis-modeled

The flat-open/rolling profile of San Remo has no mechanism to let the Cipressa
+ Poggio reduce the field back into a sprinter-puncheur finale. Because riders
ride flat-out from the start, the rouleur simply endures better over the long
flat first half and the sprinters arrive spent — the classic "MSR is won by the
sprinter who survives the climbs" outcome never materializes. Same root cause as
Finding 1.

## Finding 3 — Lombardia mis-modeled

The late climbs (9km @7%, then 3km @6% to the finish) should favor climbers/
puncheurs, but the rouleur wins 10/12. The climber attacks and gains, but the
stamina model is so punishing that the climber is also heavily fatigued by the
flat/rolling opener, letting the high-resistance rouleur hold on and take the
downhill run-in. The descents (modeled as a crude sprint+flat blend, no skill/
freshness effect) hand the rouleur back the time.

## Finding 4 — Climber courses mostly right

`classics_hilly`, `summit_finish`, and `mountain_stage` all correctly favor the
GC climbers — the climb attribute does separate on sustained/steep gradients,
and `DRAFT_UPHILL_LIMIT=5%` stops drafting shelter on the climbs. These are
usable as-is.

## Finding 5 — Unrealisticly slow total times

`mountain_stage`: 116 km in ~25,000s ≈ **6.9 h** (~16.7 km/h avg). `summit_finish`:
121 km in ~10,350s ≈ 2.9 h. Long/steep stages crawl because riders bottom out
below the stamina cracking zone and coast at a few m/s in the finale. Real
mountain stages average 32-38 km/h. Downstream of Finding 1 (no effort pacing),
the endurance/stamina constants make low-stamina riding unreasonably slow.

## Summary

- **3 of 6 courses are wrong**, all sharing one root cause: **no effort-management /
  bunch-pacing model**, so every race is all-out and low-`resistance` rouleurs
  beat sprinters/puncheurs over distance.
- Climber-vs-flat separation works; the gap is effort management + endurance
  pacing (Findings 1-3) and overly punishing stamina at low values (Finding 5).