# World — the game clock and the tick

## Why this exists

Nothing in the game has a sense of *when* it is without a clock — no season,
no calendar, no wage day, no training week, and no race that starts on its
own. For the player, the clock is what turns a simulator into a world: a
race arrives because the date arrived, is shown as racing now while it is
being worked out, and has a result once it's known. If the player is away
for a while, the races that were scheduled in the meantime have results
waiting when they come back — nothing they did caused any of it; time
passed, and the world responded.

## What this app owns

The single source of truth for what time it is in the game, and the machinery
that finds and processes due work: `world/clocks.py` (`Clock`, `RealClock`,
`MockClock` and staging's `AcceleratedClock`), `GameClock`, `TickRun`, and the `tick` and `mock_clock`
management commands. No calendar. It also owns **the AI market**
(`world/ai_market.py`): what an unmanaged team bids on and what it lists
when nobody is managing it — see *The AI market (#30)* below — and **the AI
management** (`world/ai_management.py`): the trainer it hires, the focus it
trains on and the sponsor it signs — see *The AI management (#45)*.

The tick also records season and week boundaries as they're crossed, via
`schedule.services.process_transitions()` and
`process_week_transitions()` — see `schedule/README.md` for what a
transition is and why it's a row rather than an action — and, off the back
of those, advances every rider's age at a season close and applies each
week's growth plus the team's weekly training
([#58](https://github.com/mario595/cycling-manager/issues/58),
[#36](https://github.com/mario595/cycling-manager/issues/36); see
`riders/README.md`, *The age curve* and *Weekly training*).

## The clock discipline rule

Game code reads `world.services.now()`, never `timezone.now()` or
`datetime.now()`, when deciding whether something scheduled is due.
`now()` reads whichever `Clock` is configured
(`settings.GAME_CLOCK_CLASS`) — real, live time in production, a
developer-controlled mock clock in dev and test.

The one sanctioned exception is `TickRun.finished_at`, set with
`django.utils.timezone.now()` inside `world/services.py`. That field records
when a check actually ran on the host — real time, regardless of which clock
the game itself is running on — and is not a stand-in for "is X due?"
anywhere.

The second is `GameClock.anchored_at`, written with real time by every
`MockClock` / `AcceleratedClock` write (`world/clocks.py`). It is the real
moment the stored game time was true, which is what lets the accelerated
clock count game time forward (*The accelerated clock (#129)*). It answers
"when was the clock last moved", never "is X due".

There is no automated enforcement of this rule yet. It is a project
convention, not a constraint the code checks — worth revisiting once there
is enough timed behaviour elsewhere in the game for the rule to be worth
policing; today there is almost none.

## Which clock runs where

`settings.GAME_CLOCK_CLASS` names the active `Clock`, resolved once and
cached by `world.services.get_clock()`.

| Setting file | Clock | Notes |
|---|---|---|
| `config/settings/base.py` | `world.clocks.RealClock` | The default. No state, no database — `now()` returns `timezone.now()` directly. |
| `config/settings/dev.py` | `world.clocks.RealClock` | Same as prod by default, so a normal dev session just shows the actual time with no manual resyncing. **Read from the `GAME_CLOCK_CLASS` environment variable** — set it to `world.clocks.MockClock` for a session where you deliberately want to fast-forward a season, e.g. `GAME_CLOCK_CLASS=world.clocks.MockClock manage.py runserver`. |
| `config/settings/staging.py` | `world.clocks.AcceleratedClock`, `GAME_CLOCK_SPEED = 24` | **The staging world (#129).** Inherits `prod.py` and changes only the clock and `ALLOW_WORLD_RESET`. Set in the module, never read from the environment, for the same reason as `prod.py`. See *The accelerated clock (#129)*. |
| `config/settings/prod.py` | *(inherits `RealClock` from `base.py`)* | **Deliberately not read from the environment**, unlike `dev.py`. Every other production setting in `prod.py` is env-driven, but the clock is the one exception: a non-real clock must never be a live-game possibility — not disabled, not gated behind a permission, simply not a code path production runs. An environment variable is a code path in `dev.py`, by design; it is not one in `prod.py`, also by design. |

`manage.py mock_clock` refuses to run — raising `CommandError` — unless the
active clock is `MockClock` (which includes its `AcceleratedClock` subclass). This is the runtime enforcement that a mistaken
invocation cannot move time in an environment running `RealClock`.

**Tests always run against `MockClock`**, regardless of what `GAME_CLOCK_CLASS`
a developer's shell happens to have set — `world/tests/conftest.py`'s
`_use_mock_clock` fixture forces it for every test under `world/tests/`, and
`api/tests.py`'s clock test does the same locally. This is what makes the
suite deterministic: against `RealClock`, two separate `now()` reads
a millisecond apart would almost never compare equal.

## How a tick works

`manage.py tick` — the only entry point cron, or a developer, ever calls —
reads `now()` once, then finds and processes whatever is due, in six steps:

0. **Transitions** — `schedule.services.process_transitions(at)` records any
   season boundary crossed at or before `now()` that hasn't been recorded
   yet (see `schedule/README.md`, *Exactly-once*). This runs **before**
   claiming races: a race in week 1 of a season that has just opened should
   be processed in a world that has already recorded the opening.
   Immediately after, `tick()` calls `staff.services.top_up_pool()` once
   per transition `process_transitions` actually wrote — the season-boundary
   hook's first consumer. Idempotency comes from that return value, not
   from anything tracked in `staff/`: a `SeasonTransition` row is written at
   most once ever, so a tick that runs twice, or catches up several weeks
   late, cannot top up the trainer pool twice for the same boundary. See
   `staff/README.md`. For every `OPENED` transition, `tick()` also calls
   `economy.services.ensure_offer_round(team, season, at=now)` for every
   team — a fresh round of three sponsor offers each season (#22; see
   `economy/README.md`, *Sponsorship*). `ensure_offer_round` is itself
   idempotent per `(team, season)`, so a tick that runs twice, or catches up
   late, cannot double the round the same way it cannot double-fill the
   trainer pool. Straight after the round, `world.ai_management.
   sign_ai_sponsors(season, at)` signs every unmanaged team's **steady**
   offer, so week 1 already pays it (#45; see *The AI management (#45)*).
1. **Retiring, ageing, repricing, training and wages** — for every `CLOSED`
   transition `process_transitions` returned, the season close runs in this
   order, and the order is load-bearing:
   `riders.services.retire_due_riders(at=final_week.starts_at)` →
   `transfers.services.cancel_open_auctions(retired_ids, at=at)` →
   `riders.services.advance_ages()` → `riders.services.reprice_all()` →
   `economy.services.write_salary_reviews(transition.season, changes)`.

   **Retiring first** ([#42](https://github.com/mario595/cycling-manager/issues/42))
   is what guarantees a full season's warning: the reverse order would age a
   rider into their retirement window and retire them in the same breath, and
   no season would ever have flagged them. It also keeps retirees out of the
   salary review for free (`reprice_all` iterates `active()`), freezes their
   age at the one the player last saw, and — in the same
   `transaction.atomic()` — cancels any auction of theirs so managers cannot
   keep bidding on a rider who is already gone. See `riders/README.md`,
   *Retiring by age*, and `transfers/README.md`, *Auctions*. The count lands
   on `TickRun.riders_retired`, which is **distinct from**
   `TickRun.agents_retired` below: that one is free-agent expiry by neglect,
   this one is age.

   The retirement stamp is the closing season's **final week's `starts_at`**,
   not `season.ends_at`: the profile's `retired` label resolves the stamp
   through `current_position()`, whose ranges are half-open, so `ends_at`
   would resolve to the *next* season's week 1 when seasons abut. A season
   always has twelve weeks, so the final week always exists.

   **Then** every rider's age advances by one
   (`riders.services.advance_ages()`). **Immediately after ageing, and only
   for a `CLOSED` transition**, every rider's salary is repriced:
   `riders.services.reprice_all()` recomputes each `weekly_salary` from the
   pricing formula, and `economy.services.write_salary_reviews(transition.
   season, changes)` writes one `SalaryReviewReport` per managed team
   (#26; see `economy/README.md`, *Salary review*). Repricing must run
   **after** ageing — next season's wage has to reflect the rider a manager
   will actually have, age included, not the rider they had — and it is
   exactly-once by the same rule retiring and ageing are: one `CLOSED`
   transition ever, so no pass can run twice for one season. Then
   `schedule.services.process_week_transitions(at)` records any week
   boundary opened at or before `now()` that hasn't been recorded yet (see
   `schedule/README.md`, *Week transitions*), and each recorded transition
   is applied **one week at a time**. First,
   `world.ai_management.set_ai_focuses(week)` sets every staffed unmanaged
   team's training focus for that week (#45) — **before** training, or every
   week would train on the previous week's choice. Then
   `world.services._apply_training_week(week)` moves every rider along
   their age curve via `riders.services.apply_weekly_growth(weeks=1,
   extra_deltas=...)`, adding that week's training deltas — the trainer's
   focused skill and last week's racing — through the one `growth_debt`
   ledger, writes a per-team `staff.TrainingWeekReport` of the
   display-scale changes it made, records a `riders.RiderAttributeSnapshot`
   for each rider named in that same return value
   (`riders.services.record_week_snapshots`, reusing the records
   `apply_weekly_growth` already returns rather than re-reading the table —
   see [#95](https://github.com/mario595/cycling-manager/issues/95) and
   `riders/README.md`, *Attribute history*), and then settles freshness:
   `riders.services.apply_weekly_recovery(exclude_ids=started)` — where
   `started = racing.services.riders_who_started(raced_week)` — restores
   one week's recovery to every rider who did **not start** a race in the
   week being settled ([#59](https://github.com/mario595/cycling-manager/issues/59);
   see `riders/README.md`, *Freshness*). `started` is a superset of `raced`
   (the training reader, `riders_who_raced`, above): a rider cut by the race
   engine's time limit (the broom wagon) started but didn't finish, so they
   are excluded from recovery the same as a finisher, while still earning no
   training credit — see `racing/README.md`, *The weekly-training readers*.
   Recovery follows the same per-week
   shape as training — one pass per `CLOSED` transition, never collapsed for
   a late tick — because whether a rider raced differs week to week.
   [#58](https://github.com/mario595/cycling-manager/issues/58)'s single
   `apply_weekly_growth(weeks=len(weeks))` call is gone, deliberately:
   training cannot collapse to a count, because each week has its own focus
   and its own races — a tick that runs three weeks late must apply three
   *different* training weeks ([#36](https://github.com/mario595/cycling-manager/issues/36),
   the plan's Design decision 3; see `staff/README.md`, *Weekly training*).
   The same per-transition loop charges every team its wages for the week
   just closed — `economy.services.charge_weekly_wages(week)`, one combined
   `wages` entry per team per week, dated to `week.starts_at`
   (`economy/README.md`). The entry count is summed onto the tick's
   `TickRun.wage_entries` counter (the column added by
   `world/migrations/0006`), so each `TickRun` row records how many wage
   entries its parse wrote; idempotency is the `(team, week)` constraint,
   the same defence `charge_weekly_wages` and `WeekTransition` lean on.
   Directly after wages the same loop charges each **staffed** team its
   trainer's weekly salary —
   `economy.services.charge_trainer_salaries(week, salary_by_team=...)`,
   where `salary_by_team` is built here from
   `staff.pricing.weekly_salary` (this is the one place `staff/` meets
   `economy/`; neither may import the other). One `trainer_salary` row per
   staffed team per week, dated to `week.starts_at`, counted on
   `TickRun.trainer_salary_entries`. An unstaffed team gets no row at all,
   unlike wages' `amount = 0` entry — see `economy/README.md`, *Trainer
   salaries run off the same loop*.
   Directly after trainer salaries, the same loop charges every team with an
   open **development squad** its weekly cost —
   `economy.services.charge_development_squad_costs(week,
   cost_by_team=...)`, where `cost_by_team` maps team pk to
   `(weekly_cost, level_name)` and is built here from
   `riders.development_squad.LEVELS` (#32). One `development_squad` row per
   team with a squad per week, dated to `week.starts_at`, counted on
   `TickRun.development_squad_entries`. A team with no squad gets no row, on
   the same reasoning as the unstaffed team above. The map is built **once**
   before the loop, like `salary_by_team`: no player action happens mid-tick,
   so a squad's level cannot change between the weeks one tick crosses.
   **Unmanaged teams are included deliberately** — a squad on a team nobody is
   managing still costs the team money, exactly as its riders still draw
   wages, and filtering on management would make a squad free to hand to an AI
   team. See `economy/README.md`, *Development squad costs*, and
   `riders/README.md`, *Development squad*.
   Directly after the development squad cost, still inside the per-week
   loop: `youth_graduated += _graduate_squad_riders(week)` and
   `youth_graduates_released += _release_expired_graduates(week)`, then
   `if is_intake_week(week.number): youth_intake_riders / 
   youth_intake_turned_away += run_intake(at=week.starts_at)` (#33, #34) —
   every open squad's next youth batch, managed or not, dated to
   `week.starts_at` rather than `now()` so a late tick's batch is still found
   by `run_intake`'s own idempotency check and still reads as arriving in the
   week it belongs to. `run_intake` returns an `IntakeResult(created,
   turned_away)`, and the two counts land on `TickRun.youth_intake_riders` and
   `TickRun.youth_intake_turned_away`.
   **That order — graduate, release, then intake — is load-bearing** (#34). A
   rider finishing their spell and a batch arriving at the same boundary must
   not collide on the last place: graduation *after* training means a spell
   rider gets exactly `SPELL_WEEKS` weeks of squad development, and the
   window's release before intake means a graduate whose two weeks are up
   frees its place in the same pass the next batch asks for one. Running
   intake first would turn away arrivals that a place was about to open under
   them. `world.services.tick` is the only place this order exists.
   `_graduate_squad_riders` returns 0 before `SPELL_WEEKS` weeks have
   declared-opened, so nobody graduates early; `_release_expired_graduates`
   skips a **listed** graduate, because their auction decides the outcome and
   `resolve_auction` either sells them (clearing the squad link) or releases
   them with `unattached_since` stamped. See `riders/README.md`, *Youth
   intake* and *Youth triage*, for what a batch looks like, what graduation
   and the decision window mean, and why intake runs here rather than earlier
   in the loop (after growth, training and charges, so a rider's baseline
   snapshot and first week of growth never land at the same instant).
   `TickRun` grew three counters for this — `youth_intake_turned_away`,
   `youth_graduated` and `youth_graduates_released` — beside #33's
   `youth_intake_riders`. They are diagnostic only: nothing branches on them,
   which is the point, since a manager's complaint about a squad is exactly a
   disagreement about these numbers.
   The same loop then settles the week's economy side (#21, #22):
   `economy.services.apply_weekly_fanbase(week, points_by_team=...)`
   adjusts every team's fanbase, `economy.services.pay_merchandise(week)`
   pays each team its merchandise income, and
   `economy.services.pay_sponsorship(week, points_by_team=...)` pays each
   team with an active contract its sponsorship — **in that order**:
   merchandise is paid on the *now-updated* fanbase, and sponsorship's
   season-to-date average (`economy/README.md`, *Sponsorship*) reads
   settled `FanbaseEntry` rows, so it wants fanbase already current for the
   week being paid too. All three read the week that just *completed*,
   exactly as training reads it (see *Training's race half reads the week
   that just completed* below). `points_by_team` comes from
   `competitions.services.points_by_team(week)`, computed once and reused
   for both fanbase and sponsorship: this is where `competitions/` meets
   `economy/`, because neither may import the other (`economy/README.md`,
   *Why `economy/` does not query `RacePoints`*).
   Each write is once per `(team, week)`, backed by the relevant `economy/`
   constraint, and the rows each pass writes land on the
   `TickRun.fanbase_entries` / `TickRun.merchandise_entries` /
   `TickRun.sponsorship_entries` counters. A team with no active contract
   gets no sponsorship row for the week at all — not a zero-amount one.
   After the week's money has moved, and before inactivity,
   `world.services._settle_solvency(week, ...)` assesses every managed team
   (#27; `economy/README.md`, *Insolvency*). It writes a `SolvencyCheck` for
   each team that is negative or has an open case, withdraws the live bids of a
   team whose case just **opened** (via `transfers.services.withdraw_bids` — the
   embargo stops new ones, so only the opening payday has any), and releases a
   team on its fourth unmet payday with `ManagerialSpell.Reason.INSOLVENCY`,
   dated to `week.starts_at`. It runs before `_release_inactive` so a team due
   for both is lost to the more specific cause, and a team already released
   here is simply skipped by the next week's assessment. Counts land on
   `TickRun.solvency_checks` and `TickRun.teams_lost_to_insolvency`;
   `teams_released` stays inactivity only, so the two causes are
   distinguishable. A raise is caught onto `TickRun.error` like every other
   per-item guard in this loop.
   Last in the same per-week loop, after the economy calls:
   `world.services._release_inactive(week)` releases the team of every
   manager who has gone `INACTIVITY_WEEKS` (ten) in-season game-weeks
   without logging in, via `teams.services.release_team(team,
   reason=ManagerialSpell.Reason.INACTIVITY, at=week.starts_at)`
   ([#63](https://github.com/mario595/cycling-manager/issues/63); see
   `teams/README.md`, *Releasing a team*). "Ten weeks" is counted by
   `schedule.services.weeks_opened_between`, which counts `schedule.Week`
   rows
   whose `starts_at` falls in `[user.last_seen_at, week.starts_at)` —
   querying rather than a stored counter, so a gap between seasons
   contributes no weeks for free (weeks only exist inside a declared
   season). `last_seen_at` is a **game**-time field on `accounts.User`,
   stamped at login, and on API-token requests at most once a game hour
   (#130, `api/README.md`, *Authentication*), so a token-only agent is not
   exempt as a never-logged-in account is, by `api.services.touch_last_seen`
   — deliberately not
   `django.contrib.auth`'s `last_login`, which is real time and would
   compare incorrectly against game time under `MockClock` (see
   `accounts/README.md`, *Last seen is game time*). A manager who has
   never logged in (`last_seen_at` is null) is exempt. The release is
   dated to `week.starts_at`, not the tick's own `at`, for the same reason
   every other per-week write in this loop is: a tick that catches up
   several weeks late must record each release at the boundary that
   actually crossed the threshold. A release that raises is caught and
   recorded on `TickRun.error` without stopping the week's remaining work —
   the same per-item guard *Execute* below uses for a broken race — and the
count of teams released lands on `TickRun.teams_released`.
    After `_release_inactive`, `world.services._expire_free_agents(week)`
    prunes the active free-agent pool. The pool comes from
    `transfers.services.free_agents()`, so retired riders are excluded. It
    selects riders whose `unattached_since` has crossed
    `transfers.services.EXPIRY_WEEKS` (eight) in-season weeks
    (weeks_opened_between's same Week-row count) and whose value at that
    moment falls in the pool's bottom quintile
    (`EXPIRY_VALUE_PERCENTILE`, 0.20). A selected rider with at least one
     `RaceResult` is retired with `retired_at = week.starts_at` and counted
     on `TickRun.agents_retired` — a *different* counter from the
     `TickRun.riders_retired` of the age-driven close above, since the two
     retire riders for unrelated reasons; a selected rider who never raced
     is deleted
     and counted on `TickRun.agents_expired`. Value is never stored, so the
     cutoff is computed fresh each pass, and a pool too small for a real
     bottom quintile expires nobody. A rider with null `unattached_since`
     (pre-migration free agents) is exempt, never treated as long-lost.
     Ageing runs before growth, so a rider who turned 33 at this same
     boundary is evaluated against the new age immediately. None of this
     touches a race row, so it runs outside the claim transaction below, the
     same as race simulation does and for the same reason: a full-table
     update must not extend the lock window race claiming holds.

   **After the per-week loop**, on a tick that crossed at least one week,
   `world.ai_management.hire_ai_trainers(at)` gives each unstaffed unmanaged
   team a chance to hire, and `sign_ai_sponsors` signs for any unmanaged team
   still without a contract in the current season (one released mid-season).
   Hiring is after the loop because the trainer-salary map is built once,
   before it, on the promise that nobody hires mid-tick; the new trainer's
   first salary is charged at the next boundary. Counts land on
   `TickRun.ai_trainers_hired` / `ai_sponsors_signed`
   (`world/migrations/0021`). See *The AI management (#45)*.

2. **Claim** — inside one transaction, holding a row lock on the due race
   rows themselves (not a clock row — there is no longer one to lock in
   production): every `scheduled` race whose `starts_at` is at or before
   `now()` is flipped to `running`, up to `catch_up_max_races` at a time.
3. **Auctions** (#28) — `world.services._resolve_expired_auctions(at)`
   resolves every auction `transfers.services.due_auctions(at)` returns.
   **This is the one step in the whole tick that is not keyed to a week
   boundary.** Every other per-week economic step above runs inside
   `for transition in weeks:` and is skipped entirely on a tick that
   crosses no week; auction resolution runs unconditionally, once per
   tick, every time, because an auction's deadline is wall-clock real time
   by design (`transfers/README.md`, *Auctions* — it decouples the market
   from the race calendar and stays fair across timezones). A hard week
   with zero transitions must still resolve a due auction. It supplies
   `resolve_auction`'s two callbacks, since `transfers/` may not import
   `economy/`: `charge_transfer_fee` (negative) debits the winner,
   `pay_transfer_income` (positive) credits the seller — the same injected
   shape `sign_free_agent`'s `charge` uses. Placed after race claiming and
   before `TickRun` is created, so a won auction's roster change cannot
   interfere with a squad already locked in for this tick's races.
   `TickRun.auctions_sold` / `auctions_unsold` count the outcomes.
4. **The AI market** (#30) — `world.ai_market.place_ai_bids(at)`, and on a
   tick that crossed at least one week `world.ai_market.list_ai_riders(
   last_crossed_week, at)` before it. Both run **after** step 3, so the AI
   never sees an auction this same tick is about to close, and listing runs
   before bidding. Bidding runs on every tick because auction deadlines are
   wall-clock; listing is week-keyed and uses the **last** week crossed, so a
   tick catching up three weeks lists once, not three times. Counts land on
   `TickRun.ai_bids_placed` / `ai_listings_created`
   (`world/migrations/0015`). See *The AI market (#30)*.
5. **Execute** — outside any transaction: simulate each claimed race,
   record its result, then score it (`competitions.services.score_race`),
   then score its marker points (`competitions.services.score_sprints`, then
   `score_mountains`), then pay its prize money
   (`economy.services.pay_race_prizes`). If the
   race belongs to a stage race (`race.stage_race_id`),
   `world.services._settle_stage_race` runs next, on **every** race in the
   loop that has one — including a race that failed simulation — and
   checks `stage_race.is_complete()` itself before doing anything: it is a
   no-op until the stage race's last stage has actually run, and a
   catch-up tick that simulates several stages of one tour in this same
   loop only sees it complete on the last one. Once complete, it scores
   and pays the general classification exactly once
   (`competitions.services.score_general_classification`/
   `gc_prizes_by_team`, `economy.services.pay_gc_prizes`) — see
   `racing/README.md`, *Stage races*, and `competitions/README.md`,
   *Stage races*.

   **Running on the failure path too is deliberate.** A race that raises
   during simulation still gets `FAILED`, not `FINISHED`, and the normal
   marker-scoring/prize-payout steps are skipped for it — but
   `_settle_stage_race` is called unconditionally after that step, not
   inside it, because `is_complete()` only needs every stage `FINISHED`
   **or** `FAILED`, with at least one actually `FINISHED`: a tour whose
   last stage failed to run should still settle the GC over whatever
   stages did complete, rather than leave it stuck forever.

   **Stage order inside one tick is load-bearing.** Stages of one tour sit
   on consecutive calendar days, `_claim` orders the rows it locks by
   `starts_at`, and `_execute` processes them in that same order — so a
   later stage's carried squad (`racing.services.ensure_squads` →
   `_carry_squads`) always reads an earlier stage's already-committed
   `RaceResult` rows within the same tick. Do not parallelise this loop.

**Training's race half reads the week that just completed, not the one being
entered.** A `WeekTransition` is written when a week *opens*, and the steps
above apply growth and training before claiming the races due now — so a
week's own races have not run yet at the moment its training is settled.
`_apply_training_week` therefore asks `_completed_week(week)` (the same
season's week `number - 1`) for `racing.services.riders_who_raced`, meaning
entering week N rewards week N-1's racing. Week 1 has no preceding week and
trains nothing from racing; a rider on a team with no trainer still gains
the race effect, just no report. This offsets the tick's internal ordering,
not the season's — a manager planning against the calendar sees a raced
week credited at the boundary into the next week.

**Scoring happens here, not inside `racing.services.simulate_race`.**
`racing/` may not import `competitions/` — that would invert the
dependency graph (`AGENTS.md`) — so the tick, which already imports both
to orchestrate them, is where a finished race's points are awarded. A race
that simulates but fails to score is treated as a broken race: the
existing per-race `try`/`except` in `_execute` marks it `FAILED` and
records the traceback, without stopping the rest of the tick.

**Marker points are scored in their own try block, between finish scoring
and the prize payout, and a marker-scoring failure does not fail the race
either.** `score_sprints(race)` writes `competitions.MarkerPoints` for
each sprint marker's top crossings, and `score_mountains(race)` does the same
for the mountain markers — see `competitions/README.md`, *Marker points*. The
order is sprints then mountains only so the tick reads the way the results
screen does; neither scorer's guard sees the other's rows. Each has its own
`try`/`except`: same reasoning as the prize block below, a race that
simulated and finish-scored is a real result, so a marker-scoring bug must
not retroactively mark it `FAILED`. The failure is recorded on `tick.error`
(`"race {id} sprint points: ..."` / `"race {id} mountain points: ..."`) and
the tick carries on to pay prizes regardless.

**Prize money is paid in a third, separate try block, and a payout
failure does not fail the race.** After scoring, the tick computes
`competitions.services.prizes_by_team(race)` and hands it to
`economy.services.pay_race_prizes`. It is deliberately *not* inside the
simulate-and-score block: a race that simulated and scored successfully is
a real result, and a ledger write failing afterwards — a transient database
error, say — must not mark it `FAILED` and destroy it. The failure is
recorded on `tick.error` and the tick carries on. `TickRun.prize_entries`
counts the rows written.

The `continue` at the end of the first `except` matters: without it, a race
that just failed to simulate would fall through and be paid a prize it
never earned. Scoring and paying both hang off the same "the race actually
ran" branch.

`now()` is read once at the top of `tick()` and threaded through every step
as `at`, rather than re-read at each one — against `RealClock` those would
otherwise be three slightly different instants.

Simulation is deliberately outside the claim transaction. A race takes real,
measurable time (~8 seconds); holding a database lock for that long, times
however many races a backlog holds, is how a tick ends up starving every
other reader and getting killed mid-transaction by the host.

## Exactly-once

The row lock (`SELECT ... FOR UPDATE` on exactly the due race rows) is what
makes a tick safe to run concurrently or interrupted: a second `tick`
arriving while one is in progress blocks on the lock, then re-runs its own
filter after the first commits — the rows just claimed are now `running` and
no longer match, so the second tick claims nothing.

Because claiming and executing are separate, a killed tick can strand a race
`running` with no results. The next call to `tick()` re-claims any such
race — found by `status=RUNNING` with no `RaceResult` rows — and executes it
before looking for anything newly due. A race only ever finishes once,
because `finished` is written together with its results in one transaction,
and a second simulation would need to find the race `scheduled`, which it
will not.

## The catch-up cap

`GameClock.catch_up_max_races` (default `50`) bounds how many due races one
tick will claim — reclaimed and newly-claimed races together count against
the same cap. Beyond it, `TickRun.capped` is set and the rest is picked up by
the next tick. This is configuration, not a fixed rule — it exists so an
exceptional backlog can be recovered from by raising it temporarily.

Unlike the previous design, there is no "clock catching up" — the game's
time is always the true current time. What can lag is *processing*: races
that fell due while nothing was checking are still worked out, in order, the
next time a tick runs.

## The AI market (#30)

`world/ai_market.py` is what an unmanaged team does in the auction market
when no manager is telling it what to do. It lives here and not in
`transfers/` because it needs a balance (`economy/`) and a manager
(`teams/`), and `transfers/` may import neither. It is two pure decision
helpers plus two orchestrators, and it writes nothing the auction market
does not already own: it calls `place_bid` and `list_for_auction` like any
other client of `transfers/`.

**Buying** (`place_ai_bids`) — an unmanaged team bids on a human listing
when all of these hold:

- Nobody has bid on it yet. The AI **only ever bids the reserve** on an
  auction with no live bid, never `current_price + min_increment`. With no
  bids, the asking price *is* the reserve, and an AI bid above the reserve
  would put it into a bidding war it is not equipped to win — worse, it
  would reopen the buy-from-AI, sell-to-AI flip the spec closes, where a
  managed team sells a rider, an AI team buys it at a premium, then the
  managed team buys it straight back off the AI. `place_bid` re-checks the
  minimum under its lock, so a reserve bid that lost a race with a human
  comes back as `BidTooLow` and is skipped silently — a normal outcome, not
  an error.
- The seller is **managed**. The AI never bids on another unmanaged team's
  listing: AI-to-AI trading is out of scope, and it guarantees the AI can
  never hit `SelfBid`.
- It wants the rider, judged on **visible attributes only**:
  `riders.pricing.strength`, never `potential` or any other hidden trait —
  a human must never be able to infer a rider's future from where the AI
  bid. The rider is under `AI_AGEING_AGE` (the AI would list such a rider
  straight back out), the roster plus pending wins is under `AI_MAX_ROSTER`,
  and either the roster is **thin** (under `AI_MIN_ROSTER`) or the rider
  would rank among the `AI_NEED_RANK` strongest of that speciality.
- It can afford it. **Headroom** is half the balance
  (`AI_CUSHION_FRACTION`), less the sum of its **pending wins** — the live
  bids it is currently leading on open auctions — floored at zero. Nothing
  is escrowed at bid time, so without subtracting commitments one team
  could promise the same money to five auctions. A team with a zero or
  negative balance never bids.
- It is the best-placed team. When several want the same auction the bid
  goes to the lowest `buyer_rank`: thin rosters first, then the team with
  fewest riders of that speciality, then pk. Deterministic, and a tick
  re-run gives the same answer.

**Selling** (`list_ai_riders`) — on a tick that crosses a week, an unmanaged
team lists at most one rider, and only on the weeks
`(week.number + team.pk) % AI_LISTING_EVERY_WEEKS == 0` picks for it, so
roughly a quarter of them list each week. It never has an open listing of
its own, and never shrinks below `AI_MIN_ROSTER` — a team must stay a racing
team. From the riders that have no open auction, no `UNSOLD` one within
`AI_RELIST_COOLDOWN` (4 weeks, so the same unsold veteran does not reappear
every month) and a reserve above zero, it lists:

- its **weakest** candidate, if the roster is above `ROSTER_SIZE` (surplus);
- otherwise its **oldest ageing** candidate that is **not** among the
  `AI_NEED_RANK` strongest of their speciality — the veterans worth keeping
  are exactly the ones not for sale;
- otherwise nothing.

| Constant | Value | Why |
|---|---|---|
| `AI_MIN_ROSTER` | 10 | Two and a half 4-rider squads: freshness rotation at one race a week, with slack. |
| `AI_MAX_ROSTER` | 15 | Stops an AI team buying up to `ROSTER_CAP` (30). |
| `AI_NEED_RANK` | 2 | "Among its stronger riders" means the top two of a speciality. |
| `AI_AGEING_AGE` | 33 | About 20% of generated riders; value's career horizon has already fallen well below 1.0. |
| `AI_CUSHION_FRACTION` | 0.5 | An AI team spends at most half its balance. |
| `AI_LISTING_EVERY_WEEKS` | 4 | A trickle of AI sellers, not a flood. |
| `AI_RELIST_COOLDOWN` | 4 weeks | Stops the same unsold rider reappearing monthly. |

**Claiming a team stops the bidding.** `api/`'s claim endpoint withdraws
every live bid the claimed team held and cancels every open auction it was
selling, in the same transaction as the claim (`transfers/README.md`,
*Withdrawal and cancellation on claim*), so a new manager inherits neither an
in-progress purchase nor a sale the previous manager started.

**A failing AI market is recorded, never fatal.** Three levels, all landing
on `TickRun.error`: a bid that raises for one auction is skipped and the pass
continues; a listing that raises for one team is skipped and the other teams
still list; and a failure *building* the buyer table — which reads every
unmanaged team's ledger, before any per-auction guard exists — is caught
around the whole AI step, so the tick still settles its week, charges wages
and writes its `TickRun`. Losing a tick to the garnish would be a bad trade.

**Balances, measured.** Since #125 the average team, unmanaged teams
included, ends a settled season slightly ahead (about +$11,000 in season 2 of
a seeded run) instead of about $68,000 behind. Unmanaged teams always sign the
steady sponsor, so they sit at or a little below the average, and AI buying
power no longer drains over the long run. The bottom quarter still loses
money slowly. The targets, the before/after table and the
`scripts/measure_economy.py` command that reproduces them are in
`economy/README.md`, *Balance targets*. The #45 shortfall recorded there (the
cheapest trainer *left* averages about $2,500–3,100 a week, not $1,500) still
holds. It is now counted in the break-even rather than fighting it.

## The AI management (#45)

`world/ai_management.py` is the rest of an unmanaged team's week: the
trainer it hires, the focus it trains on and the sponsor it signs. Same shape
as the AI market — pure helpers (`dominant_attribute`, `focus_for_week`,
`cheapest_trainer`, `can_afford_trainer`) and three orchestrators — and it
lives here for the same reason: hiring needs a balance, and `world/` is the
only place `staff/` and `economy/` can meet. It goes through the same
`hire_trainer`, `set_focus` and `sign_offer` a human's API calls use. The
fourth decision, the squad, is `racing/`'s `course_pick_squad`, because
squads are picked inside `simulate_race` (`racing/README.md`, *Squads*).

| Orchestrator | When the tick runs it | What it does |
|---|---|---|
| `sign_ai_sponsors(season, at)` | Right after the season-open offer round; again after the week loop, for the current season | Signs the **steady** offer (`AI_SPONSOR_PROFILE`) for every unmanaged team with no contract. Calls `ensure_offer_round` first, which gives a round back to a team a claim had cleared. |
| `set_ai_focuses(week)` | Each crossed week, **before** `_apply_training_week` | For each staffed unmanaged team: one entry per rider, the dominant attribute of their speciality profile, in pk order; the week's focus is `entries[(week.number + team.pk) % len]`. Writes only on change. |
| `hire_ai_trainers(at)` | After the week loop, on a tick that crossed a week | Each unstaffed unmanaged team, in pk order, takes the **cheapest** remaining pool trainer (hire fee, then pk), never the best. |

**Affordability.** A team hires only if, after the fee, its balance still
covers `AI_STAFF_RESERVE_WEEKS` (12, a season) of wages plus the trainer's
salary. A runway check, deliberately separate from the market's
`AI_CUSHION_FRACTION`, which is a spending fraction. A team that cannot
afford one, or finds the pool empty, tries again at the next boundary. The
fee is booked inside `hire_trainer`'s `charge` callback, so a failed hire
rolls the ledger row back with it.

**Why the hire is after the week loop.** `tick()` builds the
trainer-salary map once, before the loop, on the promise that nobody hires
mid-tick. Hiring after it keeps that true; the new trainer's first salary is
charged at the next boundary.

**Deterministic and blind.** No randomness, so a re-run tick makes the same
choices, and every step is idempotent: a team with a trainer does not hire,
a team with a contract does not sign, an unchanged focus is not written. Only
visible things are read — a rider's speciality, a trainer's price.

**Claim and release.** A claim keeps the AI-hired trainer and voids the
sponsor (`teams/README.md`). A release keeps trainer, focus and sponsor, and
the AI sets the focus by its own rule from the next boundary.

**A failing AI management is recorded, never fatal.** Per-team failures are
caught inside each orchestrator; each call site in `tick()` is also guarded.
Everything lands on `TickRun.error`, and the tick still settles its week.

## Running the tick

Production runs this hourly, from cron:

```bash
manage.py tick
```

A developer moves the mock clock by hand instead, then ticks to process
whatever that made due:

```bash
manage.py mock_clock set 2027-03-01T09:00   # jump to an exact moment
manage.py mock_clock advance --to-next      # jump to the next scheduled race
manage.py mock_clock advance --by 1d        # move forward by a duration
manage.py mock_clock advance --by 1d6h      # durations compose: 1 day 6 hours
manage.py tick                              # then process what's now due
```

Every `mock_clock` subcommand refuses to run unless `GAME_CLOCK_CLASS` is
`MockClock` or `AcceleratedClock`. Staging has three more:

```bash
manage.py mock_clock status    # game time, speed, frozen or not (any mock clock)
manage.py mock_clock freeze    # accelerated clock only: stop game time
manage.py mock_clock resume    # accelerated clock only: carry on from the frozen moment
```

Staging's cron runs only `manage.py tick`, every 5 minutes
(`TICK_SCHEDULE="*/5 * * * *"` in the image, #128). **`TICK_ADVANCE_BY` stays
unset there**: the accelerated clock moves by itself, so advancing it as well
would skip game time.

## The accelerated clock (#129)

`world.clocks.AcceleratedClock` is the staging world's clock: the real game,
with time flowing at `settings.GAME_CLOCK_SPEED` (24 on staging) times real
time. One game day passes per real hour, a twelve-week season in about 84
real hours, and a race roughly every seven. The spec is
`specs/archive/staging-clock.md`.

- **It is a `MockClock` subclass**, so `mock_clock`, `seed_world --set-clock`
  and every `isinstance(clock, MockClock)` guard work on staging unchanged.
  `set` and `advance` still work, and time then flows on from the new value.
- **The row is an anchor.** `GameClock.current` is the game time at the real
  moment `GameClock.anchored_at`, and `now()` is
  `current + (real now − anchored_at) × speed`. Every write first works out
  the *effective* time under a row lock, then re-anchors. **Never
  `current += delta` on this clock**, because that drops the time that has
  flowed since the last write. `MockClock` stamps the anchor too and ignores
  it, so a world switched between the two clocks flows on from its last
  write.
- **Time moves between any two reads**, as on production. Nothing can depend
  on it standing still, and a tick still reads `now()` once and works with
  that.
- **Freeze** (`GameClock.frozen`) stops game time at the moment of freezing:
  no new races, wages, auction deadlines or inactivity come due. **Resume**
  carries on from the frozen moment, so no game time is skipped. Both are
  idempotent. `set` while frozen moves the frozen moment, and the clock stays
  frozen. **The flag survives `seed_world --reset`**, since the clock row is
  kept, so a world rebuilt while frozen stays frozen until `mock_clock
  resume`. The flag is on the row because gunicorn workers and the cron tick
  are separate processes.
- **Downtime is caught up, not skipped.** If the machine stops without a
  freeze, game time keeps running, and at 24× one real day is about 3.5 game
  weeks. The next ticks then charge every missed week and run the missed
  races in order, with *The catch-up cap* spreading a long backlog across
  ticks, exactly as production does after an outage. **Freeze before any
  planned downtime longer than about three real days.** That is the
  ten-game-week inactivity release (`INACTIVITY_WEEKS`), and an outage that
  long would release every manager's team.
- **What stays on real time:** the report-a-problem cap (20 per 24 real
  hours, `feedback/`), the API token throttle (60 a real minute, `api/`),
  login session expiry, and the timestamps that record when the server did
  something (`TickRun.started_at` / `finished_at`, a report's `created_at`, a
  lost-team message's `acknowledged_at`). This is expected and none of it
  decides what is due.
- **A staging world cannot be promoted to production as it stands.** After two
  real weeks at 24×, game time is about a year ahead of real time.
  Production (#133) starts from `seed_world --reset` on the real clock.

What the beta managers are told about all this is in
[`STAGING_BRIEFING.md`](STAGING_BRIEFING.md), written to go into the LLM
harness's prompt as it is (#132).

## Automatic seasons

With `settings.AUTO_DECLARE_SEASONS` on (`prod.py`, and so staging), each tick
begins by declaring the world calendar (`world_setup.WORLD_CALENDAR`) as the
next season whenever **at most one declared season has not yet ended**, using
`add_season()`. It declares at most one per tick, so a running world always
has the season being played plus the next one. A season added this way is
the same as one added by hand. The count lands on `TickRun.seasons_declared`,
and a failure (a broken calendar file, say) lands on `TickRun.error` without
stopping the tick.

- **It runs before `process_transitions`**, so after an outage past the last
  season's end, the next season exists by the time the close is recorded, and
  it opens in the same tick.
- **It is off in `base.py`, and so in development and the test suite.** Their
  small example calendars and season-crossing tests would otherwise grow
  seasons nobody declared.
- **A world with no season at all is left alone.** That is a fresh database,
  not a running world.

## Building a world (#139)

A beta or launch world is built by **one command**, not the five-step dev
recipe in `AGENTS.md`:

```bash
manage.py seed_world --starts-at 2027-03-01            # production: real clock, opens on that Monday
manage.py seed_world --set-clock                       # staging: MockClock, season 1 opens now
manage.py seed_world --set-clock --reset               # staging: wipe and rebuild between beta runs
manage.py add_season                                   # append the next season to a running world
```

`seed_world` (`world/world_setup.py`, `build_world`) creates **16 unmanaged
teams, all claimable**, a **trainer pool of 24**, and **four back-to-back
seasons** of the world calendar, `seasons/world.json`. Those numbers are
settled in `specs/archive/beta-world.md`. The pool is twice
`staff.generation.INITIAL_POOL_SIZE` because sixteen unmanaged teams each
hire the cheapest trainer they can afford (*The AI management*), and a pool
of twelve runs dry before a human arrives. (With `--set-clock` the pool
then reads 32, because opening season 1 adds the usual season-boundary
top-up, `staff.services.top_up_pool`.) Every number has a flag
(`--teams`, `--trainers`, `--seasons`), and `--calendar` points at a
different season file.

- **It composes the domains' own seeds**, `seed_teams`, `seed_trainers` and
  `load_season`, through `call_command`, so a change to how a team is seeded
  reaches a built world with no change here.
- **The order is teams, trainers, then seasons.** That is the ordering trap
  in `AGENTS.md`: no team gets a sponsor offer round when it is created, so
  the round comes from the tick that opens season 1, the same way it does
  for every later season.
- **`--starts-at`** is season 1's opening Monday (00:00 UTC). It defaults to
  the next Monday after the current game time. Each later season starts at
  the previous one's `ends_at`, using `load_season`'s `--number` and
  `--starts-at` overrides (`schedule/README.md`, *Declaring a season*). One
  file serves every season of every world.
- **`--set-clock` is for the accelerated staging world only** and refuses on
  `RealClock`. It moves the mock clock to the start *before* anything is
  seeded, so the opening ledger entries are stamped in game time. It then
  ticks once, so season 1 is open and every team has its sponsor offers
  before the first manager logs in. A production world built without it
  simply opens on its start date. During the lead time its teams are
  claimable, and sponsor offers appear when the season opens.
- **It never creates a user.** The demo account (`seed_user`) is for
  development only and must not exist in production.
- **It refuses to build over an existing world** (any team, trainer or
  season) unless `--reset` is passed. All the seeding runs in one
  transaction, so a broken calendar file leaves nothing half-built.
- **`add_season`** declares the calendar as the next season number, starting
  where the last declared season ends. In production and staging the tick
  calls it by itself before the world runs out (*Automatic seasons*), so
  the command is only needed by hand.

### The wipe

`seed_world --reset` calls `wipe_world()` first. It removes **the whole game
world and keeps every account**: teams, riders, trainers, seasons, races,
results and race logs, the ledger and fanbase, the market and youth squads.
A manager whose team disappears is left without a team, like a newly
registered player, and claims a new one.

- **It is gated on `settings.ALLOW_WORLD_RESET`.** That is off in `base.py`
  and therefore in `prod.py`, and on in `dev.py`. **The staging settings
  (#129) must turn it on explicitly.** It is deliberately not inferred from
  `DEBUG` or the settings module's name, because staging inherits prod.
- **It is one `TRUNCATE … RESTART IDENTITY CASCADE`** over every model of the
  apps in `WORLD_APPS`, preceded by `SET CONSTRAINTS ALL IMMEDIATE`. Postgres
  refuses to truncate a table with deferred foreign-key checks still
  pending, and Django's FKs are deferred. An ORM delete would have to
  unpick the PROTECT foreign keys (race → week, stage → tour) in the right
  order, and that order would go stale with every new model.
- **`WORLD_APPS` is an explicit list.** `accounts` and Django's own apps are
  not in it, and `world.GameClock` is kept. **A new app is not wiped until
  it is added to the list.** That is the safe default for something an
  operator might want to keep (problem reports, say, #131). **That only
  holds for an app with no database foreign-key constraint into a wiped
  table**: `TRUNCATE … CASCADE` empties every table that has one, whatever
  its app and whether or not any row uses it. `feedback.Report.team` is
  declared `db_constraint=False` for exactly this reason, and `wipe_world`
  clears that column before the truncate, so a kept report never points at
  the new team that reuses its old team's id. `world/tests/test_world_setup.py`
  checks a report survives a reset. A future kept app that points into the
  world needs the same treatment.
- Race log files are deleted from storage before the truncate, so a reset
  does not leave them orphaned on disk.

### The world calendar

`seasons/world.json` is the one calendar every season repeats, the same way
the real classics come back every year. It has 11 one-day races, the
three-day *Vuelta a Castilla y León* (week 4, Wednesday to Friday) and the
seven-day *Vuelta a Cataluña* (week 7, Monday to Sunday), for **21
race days**. That is the density the example seasons had, and the economy
was measured against it. The two `.example` files stay as they are, for
development.

**The names are Spanish**, modelled on real Spanish races (decided on
review of #139, since the beta's human testers play in Spanish, #137). Every race,
stage and marker uses Spanish place names: *Meta volante de …* for an
intermediate sprint, *Alto de …* or *Puerto de …* for a climb, and *Meta en …*
for the line. They are proper nouns and are not translated. Each course
still fits its place roughly, for example a flat coastal sprint at Almería,
a summit finish at Urkiola and the Lagos de Covadonga at the Picos de Europa.

Each race is built from one of a few terrain shapes, each aimed at one
winning speciality. **Sprinters** get flat bunch finishes. **Puncheurs** get 3 km at 4%
topping out 500 m from the line, which drops the sprinters but is too short
for a climber to get clear. **Rouleurs** get a 6 km rise at 2.5% topping out
1 km from the line, or a 20 km false-flat drag. A short 5% ramp right at the
line was tried for puncheurs, and so were strong wind and long 1% drags for
rouleurs. Each one went to climbers or sprinters too often. **Climbers** get summit finishes, two-climb
mountain days and steep hilly classics. The climb shapes are the engine's
audited `summit_finish`, `mountain_stage` and `lombardia` profiles
(`race_engine/README.md`, *Bundled configs*), so no course goes beyond
what the engine was tuned for. Every course carries markers: weighted
sprints, categorised climbs, and a finish-line marker that is a climb on a
puncheur or climber day.

**Balance check.** `check_calendar` (`racing/README.md`, *The calendar
check*) simulates every race day against freshly generated fields:

```bash
manage.py check_calendar seasons/world.json --seeds 1,2,3 --jobs 4
```

The rule (`specs/archive/beta-world.md`, In scope 3) is that climbers,
sprinters and puncheurs each win at least two race days a season, rouleurs
at least one (below), and no speciality wins more than 40%. The last run
passes (`balanced`):

```
seed 1-5, 21 race days a season           winner's speciality
  Clásica de Almería                      sprinter 4, puncheur 1
  Gran Premio de Llodio                   puncheur 4, rouleur 1
  Vuelta a La Rioja                       sprinter 3, puncheur 1, rouleur 1
  Castilla y León 1: Tierra de Campos     sprinter 4, puncheur 1
  Castilla y León 2: Murallas de Ávila    puncheur 3, sprinter 1, rouleur 1
  Castilla y León 3: Laguna Negra         climber 5
  Clásica de las Marismas                 sprinter 4, rouleur 1
  Clásica de Jaén                         climber 4, puncheur 1
  Clásica de Ordizia                      rouleur 2, puncheur 2, climber 1
  Cataluña 1: Costa Brava                 sprinter 5
  Cataluña 2: Llanos de Urgell            sprinter 3, rouleur 1, puncheur 1
  Cataluña 3: Muro de Manresa             puncheur 3, climber 1, rouleur 1
  Cataluña 4: Puertos del Pirineo         climber 3, domestique 2
  Cataluña 5: Delta del Ebro              sprinter 5
  Cataluña 6: La Molina                   climber 5
  Cataluña 7: Montjuïc                    puncheur 2, sprinter 2, climber 1
  Trofeo de las Hoces de Cuenca           sprinter 2, puncheur 2, climber 1
  Subida a Urkiola                        climber 5
  GP de los Picos de Europa               climber 3, domestique 2
  Clásica del Montseny                    puncheur 3, sprinter 2
  GP de la Ribera del Ebro                sprinter 5
  GC, both tours                          climber 9, domestique 1

  sprinter   8.0 a season  38%
  climber    5.8 a season  28%
  puncheur   4.8 a season  23%
  rouleur    1.6 a season   8%
  domestique 0.8 a season   4%
```

**Rouleurs are the weak spot, and that is the engine, not the calendar.** A
rouleur's edge is flat power, and today's engine has no time trial, no
echelons and no breakaways, which are the three places that edge decides a
race. Everywhere else the bunch holds and a sprinter wins the final. So the
rouleur minimum is **one win a season** (`MIN_WINS_BY_SPECIALITY`) until
time trials (#89, #90) give them their own day. Decided on #139.

Sprinters sit close to the 40% ceiling. Puncheur days are the noisiest,
because on a 4% ramp a puncheur and a climber are close and the field
decides it. The check uses unmanaged-team squads (`course_pick_order`). A
human who brings climbers to a puncheur day can sometimes steal it, which
is a choice worth having.

## What is deliberately not built

- **No player control over the clock at all.** No pausing, no skipping, no
  per-player time — the clock is shared world state, moved only by
  `mock_clock` in development or by cron in production. Staging's freeze is
  an operator's command, not a player's.
- **No in-game admin screen for the mock clock.** A command line tool is
  enough for now, staging's freeze, resume and status included.
- **No in-game sign that a world is accelerated.** Only LLM managers play on
  staging, and their briefing tells them.
- **No parallel race processing.** A tick works through claimed races one at
  a time. Fine while a game day holds at most a handful of races; the
  frugal next step, once that stops being true, is a queue held in the
  database the game already has, with workers claiming races — no broker
  service needed.

## Deployment requirement

Production must be an **always-on host with a reliable hourly scheduled
task** running `manage.py tick`. A platform that sleeps idle applications
cannot check for due work while asleep, and races start late by however long
the sleep lasted — such platforms are ruled out by this feature. The task
also needs to run long enough to work out a day's races, currently around
eight seconds each.

## What `world/` may import

Everything. `world/` and `api/` are the two apps allowed to know about every
other domain (`AGENTS.md`), because the tick is where all scheduled work
across the game gets triggered from. `world/clocks.py`'s `MockClock` imports
`racing.models.Race` locally (inside `advance_to_next_due`) to find the next
scheduled race — allowed by the dependency direction, done locally purely to
keep the file's top-level imports scoped to `world/`'s own models.

## What may import `world/`

Nothing. In particular `racing/` must not import `world/` — see
`racing/README.md`'s *Simulating a race* section for how `finished_at` is
passed in rather than read from the clock directly.
