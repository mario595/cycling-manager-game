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

## Results (seed=1, winner archetype) — post pack-cohesion + positioning/depth model

| Course (scaled) | km | Realistic winner | Engine winner | Verdict |
|---|---|---|---|---|
| `sprinters_classic` | 130 | Sprinter (bunch sprint) | **Rouleur 1** (rouleur solos away) | ❌ wrong |
| `san_remo` | 137 | Sprinter-climber / puncheur | **Rouleur 1** (same mechanism) | ❌ wrong |
| `lombardia` | 100 | Climber / puncheur | **GC Climber** (Superdom) | ✅ right |
| `classics_hilly` | 87 | Puncheur / climber | **GC Climber 1** | ✅ right |
| `summit_finish` | 121 | Pure climber | **GC Climber 2** | ✅ right |
| `mountain_stage` | 116 | GC climber | **Superdom** | ✅ right |

## What changed (pack cohesion, sprint kick)

- **Pack cohesion**: riders within `PACK_COHESION_DISTANCE` (60 m) on draft-allowed
  terrain cohere into a pack rolling at `GROUP_DROP_FRACTION ×` the best cruise;
  slower riders are dropped rather than dragging the pack. This fixed the original
  absurdity of every rider maxing out solo and blowing apart.
- **Positioning + pack depth**: a rider's stamina/energy draft saving is scaled by
  `positioning` and how deep they sit in the pack (`compute_draft_factors`), so a
  skilled deep drafter conserves more.
- **Lengthened finish kick**: the finish sprint now lasts `SPRINT_DURATION = 40`
  ticks instead of a normal 20-tick surge.

Net effect: all four climber-leaning courses are now correct, and Lombardia's
late climbs correctly reward the climber. The two long flat courses remain wrong.

## Finding 1 — Rouleur-bias on long flats (residual, causes sprinters_classic + san_remo)

Even with pack cohesion and positioning/depth sheltering, the **rouleur still
wins** both long flat courses. Root cause is now *not* "riding flat-out with no
pacing" (that is fixed): the sprinter now survives stamina-wise (equal to the
rouleur, still drafting while the rouleur has broken away). Instead:

- The **rouleur breaks out of the pack mid-race and solos off the front** (lead
  grows to several km), while the **sprinter keeps sheltering in a slower shell
  and never chases**.
- The engine's reflex set has **no mechanism for a strong-flat rider to press the
  pace/attack, and no follow-the-move response** for the sprinter to bridge or
  position for the bunch sprint.

Probes that did **not** flip it (ruled out):
- Raising sprinter `resistance` to equal the rouleur (78) — sprinter survives but
  never leaves the pack/attacks; rouleur still solos to the win.
- Lowering the rouleur's `positioning` — still wins.
- Lowering the pack tempo (`GROUP_DROP_FRACTION` 0.88/0.85) — a rouleur still wins.

This is a **tactics** gap (deliberately out of scope for the reflex set): deciding
when to attack/breakaway/follow/stay-in-the-bunch is the next evolution of the
engine's rule-set. Until then, long flat courses over-reward the rouleur.

## Finding 2 — Unrealistically slow total times (residual)

`mountain_stage`: 116 km in ~21,300s ≈ **5.9 h**; `summit_finish`: 121 km in
~10,250s ≈ 2.8 h. Long/steep stages crawl because riders bottom out below the
stamina cracking zone and coast slowly in the finale. Real mountain stages average
32-38 km/h. Downstream of the endurance/stamina constants making low-stamina
riding unreasonably slow.

## Summary

- **4 of 6 courses are right**, and the pack-cohesion + positioning model fixed
  the original no-pacing failure and Lombardia's climber reward.
- Remaining gaps: (1) long flat courses over-reward the rouleur for lack of
  attacking/following tactics (Finding 1), and (2) mountain stages run slower than
  reality (Finding 2).