# Unmanaged teams: simple heuristic AI — Implementation Plan

**Spec:** `specs/unmanaged-team-heuristic-ai.md` · **Issue:** #45 · **Status:** proposed
**Apps touched:** `world/` (most of it), `racing/`, `teams/` (docs and tests only), `staff/` (docs only), `economy/` (docs only)

## Context you need

An **unmanaged team** is a `teams.Team` with `manager IS NULL`. Today it:

- gets a squad from `racing.services.auto_pick_squad`, called by `ensure_squads` at the top of `simulate_race`. That pick is course-blind: total of the five engine attributes × `freshness_multiplier`, then pk;
- has no `staff.Trainer`, so `world.services._apply_training_week` gives it no focus and no training;
- never signs a `SponsorContract`. `ensure_offer_round` already generates its three offers at every season open (`tick()`, the `opened` loop), but nothing signs one;
- already trades through `world/ai_market.py` (#30). That file is the house style for this work: pure decision helpers plus orchestrators that return `(count, error_string)` and are called from `tick()` inside a guard, so a failure is recorded on `TickRun.error` and never kills the tick.

Rules that bind this plan (`AGENTS.md`):

- `staff/` may not import `economy/`, and `economy/` may not import `staff/`. `world/` is where they meet. `hire_trainer` therefore takes an injected `charge` callback, and `economy.charge_trainer_fee` already exists for it.
- `racing/` may not import `world/`, `staff/` or `economy/`. The squad pick is decided from a `Team`, a `Race.course`, and `riders/`.
- `world/` may import everything. Nothing imports `world/`.
- A tick reads time only through its `at` argument; never call `timezone.now()`.

Read before starting: `world/README.md` (*How a tick works*, *The AI market*), `racing/README.md` (*Squads*, *Terrain is classified here*), `staff/README.md` (*The one-slot rule*, *Weekly training*), `economy/README.md` (*Sponsorship*), `teams/README.md` (*Releasing a team*).

## Goal

When this is done:

1. An unmanaged team's squad for every race is picked with the course in mind. A human team that does not pick keeps the naive default, unchanged.
2. Every tick that crosses a week gives each unmanaged team without a trainer a chance to hire the cheapest pool trainer it can afford, paying the normal fee.
3. Every unmanaged team with a trainer has its training focus set each week, on a rotation weighted by the specialities on its roster.
4. Every unmanaged team signs the **steady** sponsor offer of the current season, at season open and, for a team that has none, at any later week boundary.
5. Claiming keeps the AI-hired trainer. Releasing keeps trainer, focus and sponsor.
6. Everything above is deterministic for a given database state, never reads hidden rider attributes, and is idempotent when a tick re-runs.
7. The seeded-season measurement in *Verification* is recorded in `world/README.md`.

## Design decisions (settled — implement these, do not substitute)

1. **The AI lives in one new module, `world/ai_management.py`, beside `world/ai_market.py`.** It follows the same shape: pure helpers, then orchestrators returning `(count, error)`. Do not extend `ai_market.py`; that file is about the auction market only. Do not put hiring or signing in `staff/` or `economy/`: those apps may not import each other, and `world/` is the only place both are visible.

2. **The course-aware squad pick lives in `racing/services.py`, not `world/`.** `ensure_squads` runs inside `simulate_race`, which `racing/` owns, and the engine adapter must not be reached from `world/`. The new function is `course_pick_squad(team, course)`. `ensure_squads` calls it instead of `auto_pick_squad` when `team.manager_id is None`. Do not add a `course` argument to `auto_pick_squad`: that function is the human fallback, which the spec says must stay unchanged, and a shared signature invites someone to "simplify" the two together.

3. **"Suited to the course" reuses `course_training_attribute(course)`.** It already answers "which one attribute does this course reward" (climb, sprint, resistance, flat), is pure, and is the vocabulary the rest of the game already uses for race↔attribute. Do not invent a second course classifier. The score is `(COURSE_ATTRIBUTE_WEIGHT × the rider's value in that attribute + the sum of all five) × freshness_multiplier`, with `COURSE_ATTRIBUTE_WEIGHT = 3`. The leader is the highest scorer. The weight 3 makes the course attribute worth a bit over half of the score, so a specialist beats an all-rounder on their terrain without a one-dimensional rider ever beating a clearly stronger one. This is a light heuristic by design: do not tune it against race results.

4. **A stage race picks its squad for stage 1 only.** `ensure_squads` already delegates stages 2+ to `_carry_squads`. Do not touch that path. The squad is chosen against stage 1's course.

5. **Hiring takes the cheapest pool trainer, one team at a time, in team-pk order.** "Adequate" in the spec means any pool trainer: generation guarantees every trainer a speciality of 70–95, so none is useless. "Cheapest" is `staff.pricing.hire_fee`, tie-broken by trainer pk. Teams are processed in pk order and each takes the cheapest *remaining* trainer, so the outcome is deterministic and a pool smaller than the number of teams simply leaves later teams unstaffed until the next top-up. Do not rank by fit to the roster. That would make AI teams compete for the same good trainers humans want.

6. **Affordability rule.** A team hires only if, after paying the fee, its balance still covers `AI_STAFF_RESERVE_WEEKS` (12, one season) of outgoings: `payroll_for(team) + trainer weekly salary`. At today's numbers that is roughly an $18,000 fee against a ~$200,000 reserve, so a seeded team can hire at once, and a team near insolvency cannot. Use `economy.services.balance_for` and `payroll_for`. Do not reuse `AI_CUSHION_FRACTION` from the market: that is a spending fraction, this is a runway check, and conflating them would couple two unrelated tunings.

7. **Hiring is retried at every week boundary, not only at season open.** The spec leaves the cadence to the plan. Weekly retry costs one pool query per tick that crosses a week, and it means a team that could not afford a trainer, or found the pool empty, picks one up when it can. It also covers a team released by an inactive manager, which may have no trainer. Hiring runs **after** the per-week loop, so the new trainer's first salary is charged on the next tick's loop. The existing code builds `salary_by_team` once before that loop and relies on no hire happening mid-tick; this keeps that true.

8. **Training focus is set per crossed week, inside the loop, before `_apply_training_week(week)`.** The focus for week `n` is `attrs[(week.number + team.pk) % len(attrs)]`, where `attrs` is the list of each rostered rider's *dominant attribute*, sorted by rider pk. Dominant attribute = the key of the largest weight in `riders.generation.SPECIALITY_PROFILES[speciality]` (ties resolved in `ENGINE_ATTRIBUTES` order). The list contains one entry per rider, so a climber-heavy team trains `climb` most weeks, and the modulus walks through the list so every present speciality gets turns. Do not hardcode a speciality→attribute table: the profiles already say it. Do not use a random choice: it makes tests and re-runs non-deterministic.

9. **Sponsor: always the `steady` offer.** `economy.sponsors.PROFILES` already has a `steady` key. The AI selects `SponsorOffer.objects.filter(team=..., season=..., profile="steady")` and calls `economy.services.sign_offer`. Signing happens in two places, both calling the same function:
   - right after `ensure_offer_round` in `tick()`'s `opened` loop, so the first week of the season already pays it;
   - in the AI step after the week loop, for any unmanaged team that has no active contract this season. `ensure_offer_round` is called first (it no-ops when offers or a contract exist), because a team released mid-season has had its offers cleared by an earlier claim.
   Do not sign on the team's behalf during the claim path: `claim_team` voids sponsorship and must keep doing so (spec item 8).

10. **Claim and release need no new production code.** `claim_team` does not touch `staff`, so the AI-hired trainer stays, and `release_team` touches nothing but the manager link. These behaviours are *tests*, because the spec promises them and nothing currently proves them. Do not add an explicit "keep trainer" step: absence of code is the implementation, and the test is what protects it from a future "reset staff on claim" change.

11. **Errors are recorded, never fatal.** Each orchestrator catches per-team exceptions, appends a traceback to the returned error string, and carries on. The whole AI-management step in `tick()` is also wrapped, like the market, because losing a tick over an AI trainer hire is a bad trade. The pre-loop sponsor signing is wrapped the same way.

12. **Counters.** Two new `TickRun` columns, `ai_trainers_hired` and `ai_sponsors_signed`. Training focus changes are not counted: they are idempotent writes with no new row.

## Data model

No new models. One migration:

**`world/migrations/0020_tickrun_ai_management.py`** (check the highest existing number first; the latest at time of writing is `0019_tickrun_youth_intake_riders`):

| Model | Field | Type | Null/blank | Default |
|---|---|---|---|---|
| `TickRun` | `ai_trainers_hired` | `PositiveIntegerField` | no | `0` |
| `TickRun` | `ai_sponsors_signed` | `PositiveIntegerField` | no | `0` |

Give each a `help_text` in the style of `ai_bids_placed`. Generate with `makemigrations world`; do not hand-write it.

## racing/services.py

Add, next to `auto_pick_squad`:

```python
#: How much more the course's own attribute counts than a rider's general
#: strength when an unmanaged team picks a squad. See the plan, Design decision 3.
COURSE_ATTRIBUTE_WEIGHT = 3


def course_pick_squad(team: Team, course: list[dict]) -> tuple[list[int], int]:
    """Four rider ids and the leader's id, chosen for this course.

    Used for unmanaged teams only (ensure_squads). Humans who do not pick
    keep auto_pick_squad, which stays course-blind. Same shape, same
    SquadError for a roster under SQUAD_SIZE, same pk tiebreak.
    """
```

Body: `attribute = course_training_attribute(course)`; `score(r) = (COURSE_ATTRIBUTE_WEIGHT * getattr(r, attribute) + sum(getattr(r, n) for n in ENGINE_ATTRIBUTES)) * freshness_multiplier(r.freshness)`; sort by `(-score, r.pk)`; take `SQUAD_SIZE`; the first is the leader. Mirror `auto_pick_squad`'s `SquadError` message for a short roster.

Change `ensure_squads`, only the pick line:

```python
if team.manager_id is None:
    rider_ids, leader_id = course_pick_squad(team, race.course)
else:
    rider_ids, leader_id = auto_pick_squad(team)
```

Keep `is_auto_picked=True` for both: the flag means "the manager did not choose", which is true for the AI too. Update the `auto_pick_squad` docstring so it no longer says "and #45" for a smarter fallback.

## world/ai_management.py (new)

```python
"""How unmanaged teams run their staff and sponsorship.

Pure helpers first (a roster in, a decision out), then orchestrators the tick
calls. Same shape as ai_market.py and for the same reason: world/ is the only
place staff/ and economy/ can meet.
"""

AI_STAFF_RESERVE_WEEKS = 12        # a season of outgoings must survive the hire
AI_SPONSOR_PROFILE = "steady"
```

**Pure helpers** (query-free; tested with unsaved `Rider`/`Trainer` instances):

- `dominant_attribute(speciality: str) -> str` — the largest weight in `SPECIALITY_PROFILES[speciality]`, ties in `ENGINE_ATTRIBUTES` order.
- `focus_for_week(riders: list[Rider], week_number: int, team_pk: int) -> str | None` — `None` for an empty roster, otherwise the rotation in Design decision 8. Sort `riders` by pk inside the function so the caller cannot get the order wrong.
- `cheapest_trainer(pool: list[Trainer]) -> Trainer | None` — min by `(hire_fee, pk)`.
- `can_afford_trainer(balance: int, payroll: int, trainer: Trainer) -> bool` — `balance - hire_fee >= AI_STAFF_RESERVE_WEEKS * (payroll + weekly_salary)`.

**Orchestrators** (all `Team.objects.filter(manager__isnull=True).order_by("pk")`):

- `hire_ai_trainers(at) -> tuple[int, str]`. Load the pool once as a list. For each unmanaged team with no trainer (`staff.services.trainer_for`): pick `cheapest_trainer(pool)`; if none, stop; if `can_afford_trainer`, call `hire_trainer(team, trainer.pk, charge=...)` where `charge` calls `economy.services.charge_trainer_fee(team, amount=-hire_fee(trainer), at=at, description=f"Hired {trainer.name}")`. On success remove that trainer from the in-memory pool. Catch `TrainerNotAvailable` (a human took them since the pool was read) and `SlotOccupied` silently; skip. Anything else: record and continue. **Do not** pre-check the balance and then charge outside `hire_trainer`: the charge must run inside the callback so a failure rolls both back.
- `set_ai_focuses(week) -> int`. For each unmanaged team that has a trainer, compute `focus_for_week` from its `riders.all()` and call `staff.services.set_focus` only if it differs from `focus_for(team)`. Returns how many changed. Skips teams with no trainer or no riders.
- `sign_ai_sponsors(season, at) -> tuple[int, str]`. For each unmanaged team with no `active_contract(team, season)`: `ensure_offer_round(team, season, at=at)`, then find the team's `steady` offer for that season and `sign_offer(team, offer.pk, at=at)`. Catch `AlreadySponsored` and `OfferNotAvailable` silently; anything else record and continue.

## world/services.py

Import the three orchestrators. Edit `tick()` in four places:

1. **`opened` loop**, after `ensure_offer_round(team, transition.season, at=at)` for all teams, add one guarded call: `sign_ai_sponsors(transition.season, at)`, accumulating `ai_sponsors_signed` and any error into a new `ai_management_error` string.
2. **Per-week loop**, as the first line after `week = transition.week`: `set_ai_focuses(week)`. It must come *before* `_apply_training_week(week)`.
3. **After the per-week loop and before `_reclaim_unfinished`**, or equivalently inside the existing AI `try` block after the market calls (either is fine; the block must stay guarded): `if weeks:` call `hire_ai_trainers(at)`, then `sign_ai_sponsors(current_position(at).season, at)` when the position has a season. Add their counts and errors to the same strings.
4. **`TickRun.objects.create(...)`**: pass `ai_trainers_hired`, `ai_sponsors_signed`, and add the new error string to `error=`.

`current_position` is `schedule.services.current_position`; the module already imports from `schedule.services`.

## Work items

### W1 — `world/models.py` + migration: two TickRun counters — done
Add the fields; `makemigrations world`. Test: `world/tests/test_models.py` — a `TickRun` created with no arguments has both counters at 0.

### W2 — `racing/services.py`: `course_pick_squad` — done
Add the function and constant. Tests, in `racing/tests.py`:
- a mountain course picks the four best climbers over four stronger-overall non-climbers when the climb gap is large enough;
- a flat course does not;
- a tired climber ranks behind an equal rested one;
- fewer than four riders raises `SquadError`;
- a 100 km course with no climb ranks sprinters first, a 210 km flat ranks resistance first (uses `course_training_attribute`'s own thresholds).

### W3 — `racing/services.py`: `ensure_squads` uses it for unmanaged teams — done
Change the one pick line. Tests: with one managed and one unmanaged team on identical rosters and a mountain course, the unmanaged squad is the climber squad and the managed one is `auto_pick_squad`'s; a stage 2 still carries stage 1's squad (existing behaviour, assert it did not change).
**Load-bearing:** the branch must test `team.manager_id`, not call `team_for`/a user lookup. `Team.manager` is already on the instance `ensure_squads` iterates.

### W4 — `world/ai_management.py`: pure helpers — done
`dominant_attribute`, `focus_for_week`, `cheapest_trainer`, `can_afford_trainer`, constants. Tests in a new `world/tests/test_ai_management.py` using unsaved instances: dominant attribute per speciality equals the expected five; a roster of 3 climbers and 1 sprinter yields `climb` on three of four consecutive weeks and `sprint` on one; same inputs give the same answer; `focus_for_week([], …)` is `None`; `cheapest_trainer` breaks fee ties by pk and returns `None` for an empty pool; `can_afford_trainer` is false exactly at the boundary minus one.

### W5 — `world/ai_management.py`: `hire_ai_trainers` — done
Tests (DB): an unmanaged team with money hires the cheapest trainer and a `trainer_fee` ledger row of that fee appears; a managed team never hires; a team that cannot afford one hires nothing and is retried (give it money, run again, it hires); two teams and one trainer — only the lower pk hires; running twice does not hire a second trainer or charge twice; a trainer taken by a human between pool read and hire is skipped without an error string.

### W6 — `world/ai_management.py`: `set_ai_focuses` and `sign_ai_sponsors` — done
Tests: focus is applied to unmanaged-with-trainer only, and calling it twice for the same week changes nothing the second time; a team with no trainer is left alone; `sign_ai_sponsors` signs the `steady` offer, a second call signs nothing; a team that already has a contract keeps it; a released team with a voided/absent round gets a fresh round and a steady contract; managed teams are never touched.

### W7 — `world/services.py`: wire into `tick()` and count — done
Tests, in `world/tests/test_tick.py`: a tick that opens a season leaves every unmanaged team with an active steady contract and pays it for week 1; a tick that crosses a week hires for a funded unmanaged team and `TickRun.ai_trainers_hired` equals the count; the trainer's salary is **not** charged on the tick that hired and **is** charged on the next; the focus set for a week is in `TrainingWeekReport.attribute` for that week; a failure injected into `hire_ai_trainers` (monkeypatch to raise) lands on `TickRun.error` and the tick still writes wages. **Load-bearing:** `set_ai_focuses` runs before `_apply_training_week`; the report-attribute assertion is what catches the wrong order.

### W8 — claim and release behaviour — done
Tests only, no production change. In `teams/tests/`: claiming an unmanaged team that has an AI-hired trainer leaves the trainer on it and voids its sponsor; releasing a managed team with a trainer, focus and sponsor leaves all three. In `world/tests/test_tick.py`: after a release, the next week boundary sets the focus by the AI rule.

### W9 — docs and measurement
See *Documentation update*. Run the *Verification* measurement on the finished branch and record its numbers.

## Execution order

W1 → W2 → W3 → W4 → W5 → W6 → W7 → W8 → W9.

W2/W3 first because they are self-contained in `racing/` and visibly change a race. W4 (pure) before W5/W6 (DB) so the decisions are pinned before the orchestrators use them. W7 only after all three orchestrators work alone, because it is the integration point and the one most likely to reveal an ordering bug. Commit after each item. Run the full suite after W3, W7 and W8.

## Documentation update (required, not optional)

- `world/README.md`: add *The AI management (#45)* beside *The AI market (#30)*: the three orchestrators, where each runs in the tick, the constants, the affordability rule and why the hire is after the loop. Update *How a tick works* (steps 0 and the AI step) and the `TickRun` counters. **Replace the *Balances, measured* paragraph** with the numbers from *Verification*: the "$330,000 / three seasons" figure is stale.
- `racing/README.md`, *Squads*: describe `course_pick_squad`, who gets it, and that humans keep the naive pick. Remove "#45 covers a smarter fallback later".
- `staff/README.md`: replace the *AI/unmanaged teams hiring a trainer* future-work bullet with a pointer to `world/README.md`.
- `economy/README.md`, *Sponsorship*: one line that unmanaged teams sign the steady offer, and where.
- `teams/README.md`, *Releasing a team* and *claim*: the claim keeps the trainer; release keeps trainer, focus and sponsor.
- `AGENTS.md` (the `world/` row) and `specs/roadmap.md`: mark #45 as built.
- Set `Status: implemented` in the spec and this plan and move both to `specs/archive/`, per `AGENTS.md`, at the end.

## Verification

Unit tests prove each decision; they cannot show the economy behaves. Do both.

**The measurement** (this proves spec item 9). In the ticket's worktree, with `GAME_CLOCK_CLASS=world.clocks.MockClock`:

```bash
/home/mario/dev/cycling-manager/.venv/bin/python scripts/dev_db.py
/home/mario/dev/cycling-manager/.venv/bin/python manage.py migrate
manage.py seed_user && manage.py seed_teams --claim-for test@mail.com
manage.py seed_trainers && manage.py load_season seasons/season-1.example.json
manage.py mock_clock set 2027-03-01T00:00
# then: for each of ~86 days:  mock_clock advance --by 1d  &&  tick
```

Run **two** seasons (load a season 2 file if needed) and compute, for the unmanaged teams, the net weekly flow by ledger kind. The spec's threshold is "no more than about half of today's roughly $65,500 a season". Use the second season, which excludes the one-off hire fee, as the steady-state figure, and report the first as well.

**Likeliest failure, and the check that catches it.** *The threshold may be missed by a small margin.* From the pre-feature measurement the steady sponsor is about +$4,200 a week and the cheapest trainer about −$1,500 a week, so the steady-state loss lands near $33,000 a season, almost exactly half, and the first season adds the $18,000 fee. If the measured steady-state loss is over about $33,000, **do not tune constants to hit it** — report it back (see *Open questions*). A trainer also makes riders better, which raises prize money, so the real number may be better than the projection.

**Second failure:** a double hire or double charge on a re-run. The W5/W7 idempotency tests catch it; confirm in the dev database with `LedgerEntry.objects.filter(kind="trainer_fee")` — exactly one row per hired team.

**What counts as evidence:** the per-kind breakdown printed before and after, not a passing test. A test asserting "balance went up" could pass while the loss is still twice the target.

## Risks

| Risk | Mitigation |
|---|---|
| The trainer's cost eats the sponsor's gain and item 9 is missed by a hair. | Measure steady state, not season 1; report rather than tune; see *Open questions*. |
| `set_ai_focuses` placed after `_apply_training_week`, so every week trains on last week's focus. | W7's report-attribute assertion. |
| A hire inside the week loop changes `salary_by_team` mid-tick. | Hire only after the loop (Design decision 7). |
| AI teams take the cheap trainers humans want, empty the pool and leave a new player unable to hire. | The pool is topped up by 8 each season; the AI takes only unmanaged teams' share and never the best. Check pool size after the two-season run; if humans are locked out, report. |
| A released team's human focus is overridden at once. | Intended: AI continues the training. The test in W8 pins it. |
| Confusing `ai_market`'s `AI_CUSHION_FRACTION` with the staff reserve. | Separate constants and Design decision 6. |
| `Team.objects.filter(manager__isnull=True)` includes a team whose manager was just released this tick and still has a human squad row. | `ensure_squads` only writes missing squads; no interaction. |

## Open questions

1. **Will item 9 be met?** Projection says steady state is about $33,000 against a $32,750 target, i.e. on the line. If the measurement lands over, the product owner decides between accepting it, skipping the trainer when the projected loss is too high, or a cheaper trainer rule. This is a product decision; the plan does not pre-empt it.
