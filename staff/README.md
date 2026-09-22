# Staff

## What this app owns

`Trainer` — the shared hiring pool and the one trainer slot a team may fill
from it. Hiring and firing (`services.hire_trainer`, `services.fire_trainer`),
generation (`generation.py`), and the season-boundary top-up
(`services.top_up_pool`). Plus the trainer's day job once hired: the team's
weekly training focus and its rollover record — `TrainingFocus` and
`TrainingWeekReport`, the heart of
[#36](https://github.com/mario595/cycling-manager/issues/36); see *Weekly
training*, below. What a trainer *costs* — the hire fee and the weekly
salary — is derived from their speciality in `pricing.py`, never stored; see
*What a trainer costs*, below. Not the physio or scout roles the original
brief also names — both wait on their own dependencies
([#41](https://github.com/mario595/cycling-manager/issues/41) for physio,
transfers/youth intake for scout).

## The one-slot rule

`Trainer.team` is a nullable `OneToOneField` to `teams.Team`, not a
`ForeignKey` on `Team` pointing at a trainer. `team = None` means the
trainer is unemployed, in the shared pool; a non-null `team` means they
fill that team's single slot.

This is what makes "a team cannot have two trainers" a database constraint
rather than an application-level rule someone has to remember to check: a
second `Trainer` row with the same `team` raises `IntegrityError` on save,
enforced the same way a `OneToOneField` enforces any other one-to-one
relationship.

The alternative — a `trainer` FK on `Team` — was rejected: it would invert
the dependency graph (`staff -> teams`, not `teams -> staff`), and it would
need a migration on `teams/` for a field only `staff/` cares about.

## Stored 1-100, displayed 0-10

A trainer's five skills (`climb`, `sprint`, `flat`, `resistance`,
`positioning` — deliberately the same names as `riders.models.
ENGINE_ATTRIBUTES`, since a training focus (#36) maps onto one of them) are
stored 1-100 and shown to the player on the 0-10 scale, through
`riders.display.to_display_scale` — the same mapping, the same function,
riders already use. See `riders/README.md`, *Display scale*.

Storing 1-10 directly (matching the product spec's player-facing wording
literally) was considered and rejected: ten buckets collapse the difference
between "clear speciality" and "close second", and #36 needs to scale a
training effect off the trainer's exact score in the focused skill, not off
a number already rounded away.

## What a trainer costs

A trainer costs a one-off **hire fee** and a **weekly salary**, both derived
from their speciality score by `pricing.py` and **never stored** (Design
decision 1). There is no `fee` or `salary` column on `Trainer` and no
migration to backfill: a trainer's skills are fixed for life, so a stored
price could only ever drift from the skills it is supposed to reflect.

- `weekly_salary(trainer)` interpolates linearly from
  `SALARY_AT_MIN_SPECIALITY` (1,500) at the bottom of the speciality band (70)
  to `SALARY_AT_MAX_SPECIALITY` (4,500) at the top (95), rounded to the
  nearest 50 so prices read as prices rather than hash output. The score is
  read through the derived `speciality` property
  (`getattr(trainer, trainer.speciality)`), so a sprinter prices off sprint,
  not off whichever attribute happens to be first.
- `hire_fee(trainer)` is `FEE_WEEKS_OF_SALARY` (12) × the weekly salary.

**The fee is the cooldown firing deliberately does not have** (Design
decision 7). `fire_trainer` is free, instant and has no penalty, so without a
fee a manager could fire before a lean week and rehire after it at no cost.
Twelve weeks is a full season, so dodging a few weeks never pays; and because
a trainer's skills never change, a rehire can never be cheaper than the first
hire. Overrule the constant if the balance feels wrong — it is one line.

**Hiring takes an injected `charge` callback, not an `economy/` import**
(Design decisions 2 and 3):

```python
hire_trainer(team, trainer_id, *, charge=None)
```

`charge` runs inside `hire_trainer`'s transaction, after the post-lock
availability re-check and before the hire is written, so a raise (the API's
`InsufficientFunds`, or anything else) rolls the whole thing back and leaves
the trainer in the pool. `staff/` may not import `economy/` (`AGENTS.md`), so
the caller passes the debit — `api/StaffView` books the fee; the seed path
passes no callback at all.

## The pool is shared, and hiring is contended

Every unemployed trainer (`team__isnull=True`) is visible to every team —
`services.available_trainers()`. Because two managers can try to hire the
same trainer at the same moment, `services.hire_trainer` locks the
requested row with `select_for_update()` and **no** `skip_locked`, then
re-checks `trainer.team_id is None` **after** the lock is held:

```python
trainer = Trainer.objects.select_for_update().get(pk=trainer_id)
if trainer.team_id is not None:
    raise TrainerNotAvailable(...)
```

This is the one genuinely concurrent operation in the app, and the
re-check after the lock is the line the whole feature depends on: without
it, the loser of a simultaneous hire silently overwrites the winner's claim
instead of being told the trainer is gone.

**Do not copy `teams.services.claim_team`'s `skip_locked=True` here.**
`claim_team` wants *any* unmanaged team and is happy to skip a contended
row and try the next one. Hiring is the opposite: the manager asked for
*that* trainer, specifically — `skip_locked` would make a contended row
silently vanish from the query, and the caller would see "not available"
indistinguishable from a genuine mistake, rather than "someone just took
this one".

The hire fee is debited through the same transaction as the hire (the
injected `charge` callback, below in *What a trainer costs*), so a trainer
and their fee can never end up out of step: either both land or neither
does.

## Generation guarantees the speciality

`generation.py` draws one skill (the speciality) from a high band (70-95)
and the other four from a lower, **non-overlapping** band (25-64). Because
the bands do not overlap, "exactly one skill is the clear highest" is true
by construction — there is no tie to break and no rejection loop. The
6-point gap between the bands' edges is chosen to survive the display
scale too: `floor(70/10)=7` against `floor(64/10)=6`, so the speciality
still reads as visibly taller on the bars a manager actually sees, not just
in the stored numbers.

The lower band's floor (25) exists for weekly training's benefit, not this
app's: #36 requires off-speciality training to always be worth something,
never zero, so no trainer skill is ever generated near the bottom of the
1-100 range.

## Weekly training

Once hired, a trainer earns their keep ([#36](https://github.com/mario595/cycling-manager/issues/36)):
the tick applies the team's training focus every time a `WeekTransition`
crosses, and writes what visibly changed to a `TrainingWeekReport` (one per
team per week). The physics live in `riders/` — `riders.services.training_deltas`,
and the `growth_debt` ledger it shares with the age curve — see
`riders/README.md`, *Weekly training*. This app owns the two models around
it:

- **`TrainingFocus`** — one row per team (`OneToOneField` to team), holding
  which of the five attributes the team is working on. **The focus is a
  property of the team's training programme, not of the person hired** (the
  plan's Design decision 5): firing a trainer and hiring another must not
  silently reset what the team was working on, and `Trainer` rows return to
  the shared pool where a stale focus would be meaningless. `DEFAULT_FOCUS`
  (`climb`) covers the no-row case; the row is created on demand by
  `focus_for` / `set_focus`. A team with no trainer has no focus at all.
- **`TrainingWeekReport`** — the stored "what changed" list for one team's
  week: the focus applied (blank when the team had no trainer) and the
  display-scale movements as JSON (`{"rider_id", "rider_name", "attribute",
  "from", "to"}`, an empty list normal). Written at rollover so the Training
  screen reports what last week did without diffing attributes after the
  fact (Design decision 7). `(team, week)` is unique — a second line of
  defence behind `WeekTransition`'s exactly-once guarantee.

Both are keyed to the **team**, not to `Trainer` — for exactly the reason
`Trainer.team` is a `OneToOneField` rather than an FK on `Team`: this app
owns the concept, and putting it on `teams.Team` would invert the
dependency graph (`teams` must not know about `staff`).

**A late tick applies the latest focus to every missed week, and that is
accepted** (Design decision 3). The focus is a single mutable field; a tick
that catches up three weeks late has no record of what was intended in each
— nobody asked for a per-week history of intent, and a late tick is a
server-health problem, not a game mechanic. What the tick *does* iterate is
the weeks themselves (`world.services._apply_training_week`), because each
week's races differ — see `world/README.md`, *How a tick works*.

## What `staff/` may import

`core`, `teams`, `riders` — matching `AGENTS.md`'s dependency graph, plus a
**string-only** reference to `schedule.Week`: `TrainingWeekReport.week` is a
`ForeignKey("schedule.Week", ...)` declared as a string, the same
import-free pattern `racing/models.py`'s `Race.week` uses, so
`staff/models.py` imports nothing from `schedule/`. The dependency is real
and `AGENTS.md`'s graph says so; only the module stays import-free. Never
`world/`, `api/`, or `racing/`. The season-boundary top-up is wired the
other way: `world.services.tick()` imports `staff.services.
top_up_pool` and calls it once per crossed `SeasonTransition`, using that
row's exactly-once guarantee for idempotency rather than anything tracked
in this app. See `world/README.md`, *How a tick works*.

## `seed_trainers` — the initial pool

```bash
python manage.py seed_trainers [--count=12] [--rng-seed=N]
```

Adds `--count` freshly generated trainers to the shared pool.
**Non-destructive** — unlike `riders/reset_riders`, it only adds and never
deletes, so it needs no `--yes`: there is no existing game content for it
to threaten. `--rng-seed` seeds the generator for a reproducible pool,
mainly useful for demos and manual testing.

## Future work / possible improvements

- **Physio slot** — once [#41](https://github.com/mario595/cycling-manager/issues/41)
  (injuries) gives it something to affect.
- **Scout slot** — once transfers/youth intake give it something to narrow.
- **AI/unmanaged teams hiring a trainer** — belongs to
  [#45](https://github.com/mario595/cycling-manager/issues/45); unmanaged
  teams stay unstaffed for now.
- **Poaching, contract renewal, a trainer quality curve over time** — no
  current plan; a trainer's five scores are fixed for life, and the only
  way to change teams is to be fired back into the pool first.
