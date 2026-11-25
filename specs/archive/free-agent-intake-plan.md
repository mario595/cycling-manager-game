# Free-agent intake — Implementation Plan

**Spec:** `specs/archive/free-agent-intake.md` · **Issue:** #157 · **Status:** implemented
**Apps touched:** `riders/`, `world/`

## Context

The pool is `transfers.services.free_agents()`: active riders with no team and no development squad. `world.services._expire_free_agents(week)` prunes it in the tick's week loop. `world/ai_market.py`'s `list_ai_riders` skips a team whose roster minus one would fall below `AI_MIN_ROSTER` (10). Nothing put a rider on an unmanaged team.

## Design decisions

1. **The intake lives in `riders/free_agent_intake.py`**, beside youth intake: `riders/` decides what a batch looks like, `world/` decides when. It takes a datetime, never a `Week`, since `riders/` may not import `schedule/`.
2. **Called in the week loop after expiry**, so a batch is not weighed against the pool it is joining. The `WeekTransition` is the exactly-once guarantee.
3. **AI signing lives in `world/ai_market.py`**, beside buying, and reuses `_buyers()` and `headroom()`, so a signing fee and pending auction wins draw on the same budget. A pure `pick_free_agent(roster, candidates, budget)` plus the orchestrator `sign_ai_free_agents(week, at)`.
4. **Signing goes through `transfers.services.sign_free_agent`** with a `charge_transfer_fee` callback, the same path `api/` uses, so the roster cap, locking and ledger behave the same.
5. **Signing runs before listing** in the AI market step, so a team a signing takes back above `AI_MIN_ROSTER` can list in the same pass.
6. **A rider is eligible for the AI only if `unattached_since` is before the crossed week's start** (or null), so humans get a week's head start.
7. **Counters** `TickRun.free_agents_generated` and `ai_free_agents_signed` (migration `world/0024`).
8. **`world/tests/test_expiry.py` switches the intake off** with an autouse fixture: those tests build an exact pool to place a known rider in its bottom quintile.

## Work items

1. `riders/free_agent_intake.py` and `riders/tests/test_free_agent_intake.py`: the cadence, a batch of six teamless riders dated to the week with ages in range, in the pool, with snapshots.
2. `world/ai_market.py`: `pick_free_agent` and `sign_ai_free_agents`. Tests in `world/tests/test_ai_market.py`: thinnest speciality first, strongest next, ageing and unaffordable riders skipped, full rosters sign nobody, the fee is charged, one signing per team per pass, the thinnest team first, this week's arrivals left alone, managed, full and broke teams sign nobody.
3. `world/services.py`, `world/models.py` and the migration: wire both in and count them. Tests in `world/tests/test_services.py`: an intake week adds and counts six, and a short unmanaged team signs one a week after the intake.
4. READMEs (`riders/`, `transfers/`, `world/`), `AGENTS.md` and `beta_agents/PLAYERS_GUIDE.md`.
