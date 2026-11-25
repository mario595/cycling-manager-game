# Replacement riders for unmanaged teams — Implementation Plan

**Spec:** `specs/archive/ai-roster-replacements.md` · **Issue:** #157 · **Status:** implemented
**Apps touched:** `world/`

## Context

`world/ai_market.py`'s `list_ai_riders` skips a team whose roster minus one would fall below `AI_MIN_ROSTER` (10). Seeded teams start at `ROSTER_SIZE` (12, `teams/services.py`). `tick()` retires due riders at each season close (`riders.services.retire_due_riders`), then ages (`advance_ages`) and reprices (`reprice_all`). Nothing adds a rider to an unmanaged team.

## Design decisions

1. **Lives in `world/ai_management.py`.** It is AI behaviour for unmanaged teams, beside hiring and sponsorship. `world/` may import `riders/` and `teams/`; nothing new crosses a boundary.
2. **Runs once per tick that crossed a close, after the close loop.** After ageing, so a replacement is generated at the age it races at and is not aged on arrival; after repricing, because `generate_rider` already prices it with `weekly_salary_for`.
3. **Pure helper plus orchestrator**, like the rest of the AI: `thinnest_speciality(roster)` and `replacements_for(roster, rng)` take lists and return unsaved riders; `replenish_ai_rosters(rng)` does the queries and writes.
4. **No ledger entry.** Matches seeded rosters; the economy pays through wages.
5. **Baseline snapshot** via `riders.services.record_initial_snapshots`, the same as seeding and youth intake, so the attribute history has a starting point.
6. **Per-team guard plus call-site guard**, like the AI market: one team's failure lands on `TickRun.error` and the others still fill.
7. **`TickRun.ai_riders_added`** counter (migration `world/0024`), for diagnosis alongside the other AI counters.

## Work items

1. `world/ai_management.py`: `AI_REPLACEMENT_AGE_RANGE = (19, 23)`, `thinnest_speciality`, `replacements_for`, `replenish_ai_rosters`. Tests in `world/tests/test_ai_management.py`: the thinnest speciality and its tie-break, a short roster filled to 12 with ages in range and the gap filled first, nothing for a full or oversized roster, managed and oversized teams untouched, no ledger rows, a snapshot per new rider, idempotent on a second run, one failing team not stopping the others.
2. `world/models.py` + migration: `TickRun.ai_riders_added`. `world/services.py`: call after the close loop, guarded. Tests in `world/tests/test_services.py`: a close replaces three retirees and counts them, a managed team is not topped up, no top-up mid-season.
3. `world/README.md` and `AGENTS.md`: the tick order and *Replacement riders*.
