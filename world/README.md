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
`MockClock`), `GameClock`, `TickRun`, and the `tick` and `mock_clock`
management commands. No calendar. It also owns **the AI market**
(`world/ai_market.py`): what an unmanaged team bids on and what it lists
when nobody is managing it — see *The AI market (#30)* below.

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
| `config/settings/prod.py` | *(inherits `RealClock` from `base.py`)* | **Deliberately not read from the environment**, unlike `dev.py`. Every other production setting in `prod.py` is env-driven, but the clock is the one exception: a non-real clock must never be a live-game possibility — not disabled, not gated behind a permission, simply not a code path production runs. An environment variable is a code path in `dev.py`, by design; it is not one in `prod.py`, also by design. |

`manage.py mock_clock` refuses to run — raising `CommandError` — unless the
active clock is `MockClock`. This is the runtime enforcement that a mistaken
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
   trainer pool.
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
   is applied **one week at a time**:
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
   loop: `if is_intake_week(week.number): youth_intake_riders +=
   run_intake(at=week.starts_at)` (#33) — every open squad's next youth
   batch, managed or not, dated to `week.starts_at` rather than `now()` so a
   late tick's batch is still found by `run_intake`'s own idempotency check
   and still reads as arriving in the week it belongs to. The count lands on
   `TickRun.youth_intake_riders`. See `riders/README.md`, *Youth intake*, for
   what a batch looks like and why intake runs here rather than earlier in
   the loop (after growth, training and charges, so a rider's baseline
   snapshot and first week of growth never land at the same instant).
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
   stamped at login by `api.services.touch_last_seen` — deliberately not
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
every live bid the claimed team held, in the same transaction as the claim
(`transfers/README.md`, *Withdrawal on claim*), so a new manager never
inherits an in-progress purchase.

**A failing AI market is recorded, never fatal.** Three levels, all landing
on `TickRun.error`: a bid that raises for one auction is skipped and the pass
continues; a listing that raises for one team is skipped and the other teams
still list; and a failure *building* the buyer table — which reads every
unmanaged team's ledger, before any per-auction guard exists — is caught
around the whole AI step, so the tick still settles its week, charges wages
and writes its `TickRun`. Losing a tick to the garnish would be a bad trade.

**Balances, measured.** Unmanaged teams earn no wages, prize money or
sponsorship; they only spend. A seeded season 1 left the average unmanaged
team with about **$330,000**, and at roughly `12 × $1,200` a week of wages
each team owes the market rather than the other way round, that is about
**three seasons** before AI buying dries up. The fix when it bites is
[#45](https://github.com/mario595/cycling-manager/issues/45)'s sponsorship,
not a fatter cushion here: a cushion large enough to matter would also let
AI teams bid away the human market.

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
`MockClock`.

## What is deliberately not built

- **No player control over the clock at all.** No pausing, no skipping, no
  per-player time — the clock is shared world state, moved only by
  `mock_clock` in development or by cron in production.
- **No in-game admin screen for the mock clock.** A command line tool is
  enough for now.
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
